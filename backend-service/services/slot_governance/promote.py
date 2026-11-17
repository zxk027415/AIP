"""Promote model candidate into slot registry (G4 skeleton)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.slot_governance.model_candidates import find_model_candidate
from services.slot_governance.provenance import ProvenanceError, assert_product_slot
from services.slot_governance.registry import get_registry_store
from services.slot_governance.verification import VerificationError, get_verification

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_governance"


class PromoteError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _promotions_log_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "promotions_log.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_promotions_log(slot: str) -> list[dict[str, Any]]:
    path = _promotions_log_path(slot)
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        items = payload.get("events")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_promotions_log(slot: str, items: list[dict[str, Any]]) -> None:
    path = _promotions_log_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"slot": slot, "events": items}, handle, ensure_ascii=False, indent=2)


def find_promotion_by_idempotency(slot: str, idempotency_key: str) -> Optional[dict[str, Any]]:
    for event in _load_promotions_log(slot):
        if event.get("idempotency_key") == idempotency_key:
            return event
    return None


def list_promotions_log(slot: str) -> list[dict[str, Any]]:
    assert_product_slot(slot)
    return _load_promotions_log(slot)


def promote_model_candidate(
    model_candidate_id: str,
    *,
    verification_id: str,
    operator: str,
    reason: str,
    expected_registry_version: int,
    idempotency_key: str,
    production_slot: Optional[str] = None,
    set_as_production: bool = False,
) -> dict[str, Any]:
    if production_slot:
        assert_product_slot(production_slot)

    cand_slot, candidate = find_model_candidate(model_candidate_id)
    if candidate is None or cand_slot is None:
        raise PromoteError("candidate_not_found", f"model_candidate_id={model_candidate_id!r} not found")

    slot = production_slot or cand_slot
    assert_product_slot(slot)
    if slot != cand_slot:
        raise PromoteError(
            "slot_mismatch",
            f"production_slot={slot!r} != candidate.slot={cand_slot!r}",
        )

    if not idempotency_key.strip():
        raise PromoteError("missing_idempotency_key", "idempotency_key is required")
    if not operator.strip():
        raise PromoteError("missing_operator", "operator is required")
    if not reason.strip():
        raise PromoteError("missing_reason", "reason is required")

    existing = find_promotion_by_idempotency(slot, idempotency_key)
    if existing is not None:
        store = get_registry_store()
        return {
            "promotion": existing,
            "registry": store.get(slot),
            "idempotent_replay": True,
        }

    verification = get_verification(slot, verification_id)
    if verification is None:
        raise PromoteError("verification_not_found", f"verification_id={verification_id!r} not found")
    if verification.get("model_candidate_id") != model_candidate_id:
        raise PromoteError(
            "verification_candidate_mismatch",
            "verification.model_candidate_id does not match promote target",
        )
    if verification.get("passed") is not True:
        raise PromoteError("verification_not_passed", "verification.passed must be true")

    store = get_registry_store()
    registry = store.get(slot)
    current_version = int(registry.get("registry_version") or 0)
    if current_version != int(expected_registry_version):
        raise PromoteError(
            "registry_version_conflict",
            f"expected_registry_version={expected_registry_version} but current={current_version}",
        )

    champion = registry.get("champion") or {}
    previous_champion_ref = champion.get("champion_model_ref")
    adopted_ref = candidate.get("model_ref") or model_candidate_id

    challenger_group = {
        "challenger_model_ref": adopted_ref,
        "challenger_model_candidate_id": model_candidate_id,
        "challenger_source_workflow_id": candidate.get("source_workflow_id"),
        "challenger_source_workflow_version": candidate.get("source_workflow_version"),
        "challenger_source_execution_id": candidate.get("source_execution_id"),
        "challenger_model_artifact_ref": candidate.get("model_artifact_ref"),
        "challenger_verification_id": verification_id,
    }

    next_version = current_version + 1
    if set_as_production:
        new_champion = {
            "champion_model_ref": adopted_ref,
            "source_model_candidate_id": model_candidate_id,
            "source_workflow_id": candidate.get("source_workflow_id"),
            "source_workflow_version": candidate.get("source_workflow_version"),
            "source_execution_id": candidate.get("source_execution_id"),
            "model_artifact_ref": candidate.get("model_artifact_ref"),
            "verification_id": verification_id,
        }
        updated_registry = {
            "registry_version": next_version,
            "champion": new_champion,
            "challenger": None,
            "note": reason,
        }
        champion_changed = True
        new_champion_ref = adopted_ref
        resulting_champion_ref = adopted_ref
    else:
        updated_registry = {
            "registry_version": next_version,
            "champion": champion if champion else None,
            "challenger": challenger_group,
            "note": reason,
        }
        champion_changed = False
        new_champion_ref = None
        resulting_champion_ref = previous_champion_ref

    saved_registry = store.save(slot, updated_registry)

    promotion_event = {
        "promotion_id": f"prom-{uuid.uuid4().hex[:12]}",
        "model_candidate_id": model_candidate_id,
        "verification_id": verification_id,
        "production_slot": slot,
        "set_as_production": bool(set_as_production),
        "operator": operator,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "adopted_challenger_model_ref": adopted_ref,
        "previous_champion_model_ref": previous_champion_ref,
        "new_champion_model_ref": new_champion_ref,
        "resulting_champion_model_ref": resulting_champion_ref,
        "champion_changed": champion_changed,
        "registry_version_before": current_version,
        "registry_version_after": next_version,
        "promoted_at": _now_iso(),
    }

    log_items = _load_promotions_log(slot)
    log_items.append(promotion_event)
    _save_promotions_log(slot, log_items)

    return {
        "promotion": promotion_event,
        "registry": saved_registry,
        "idempotent_replay": False,
    }
