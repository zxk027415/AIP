"""Verification records (immutable evidence, G4 skeleton)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.slot_governance.model_candidates import find_model_candidate
from services.slot_governance.provenance import ProvenanceError, assert_product_slot

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_governance"


class VerificationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _verifications_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "verifications.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_verifications(slot: str) -> list[dict[str, Any]]:
    path = _verifications_path(slot)
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        items = payload.get("verifications")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_verifications(slot: str, items: list[dict[str, Any]]) -> None:
    path = _verifications_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"slot": slot, "verifications": items}, handle, ensure_ascii=False, indent=2)


def list_verifications(slot: str) -> list[dict[str, Any]]:
    assert_product_slot(slot)
    return _load_verifications(slot)


def get_verification(slot: str, verification_id: str) -> Optional[dict[str, Any]]:
    for item in _load_verifications(slot):
        if item.get("verification_id") == verification_id:
            return item
    return None


def find_verification_by_idempotency(slot: str, idempotency_key: str) -> Optional[dict[str, Any]]:
    for item in _load_verifications(slot):
        if item.get("idempotency_key") == idempotency_key:
            return item
    return None


def register_verification(
    *,
    slot: str,
    model_candidate_id: str,
    evaluation_contract_ref: str,
    idempotency_key: str,
    passed: bool = True,
    registry_version_at_start: int = 0,
    baseline_model_ref: Optional[str] = None,
    verification_source_workflow_id: Optional[str] = None,
    verification_source_execution_id: Optional[str] = None,
    evaluation_artifact_ref: Optional[str] = None,
) -> dict[str, Any]:
    assert_product_slot(slot)
    if not idempotency_key.strip():
        raise VerificationError("missing_idempotency_key", "idempotency_key is required")

    existing = find_verification_by_idempotency(slot, idempotency_key)
    if existing is not None:
        return existing

    _slot, candidate = find_model_candidate(model_candidate_id)
    if candidate is None:
        raise VerificationError("candidate_not_found", f"model_candidate_id={model_candidate_id!r} not found")
    if _slot != slot:
        raise VerificationError("slot_mismatch", f"candidate slot={_slot!r} != requested slot={slot!r}")

    verification_id = f"ver-{uuid.uuid4().hex[:12]}"
    record: dict[str, Any] = {
        "verification_id": verification_id,
        "slot": slot,
        "model_candidate_id": model_candidate_id,
        "evaluation_contract_ref": evaluation_contract_ref,
        "passed": bool(passed),
        "eligible_for_pool": bool(passed),
        "registry_version_at_start": int(registry_version_at_start),
        "baseline_model_ref": baseline_model_ref,
        "candidate_source_workflow_id": candidate.get("source_workflow_id"),
        "candidate_source_workflow_version": candidate.get("source_workflow_version"),
        "candidate_source_execution_id": candidate.get("source_execution_id"),
        "model_artifact_ref": candidate.get("model_artifact_ref"),
        "verification_source_workflow_id": verification_source_workflow_id,
        "verification_source_execution_id": verification_source_execution_id,
        "evaluation_artifact_ref": evaluation_artifact_ref,
        "idempotency_key": idempotency_key,
        "created_at": _now_iso(),
        "status": "completed" if passed else "failed",
    }

    items = _load_verifications(slot)
    items.append(record)
    _save_verifications(slot, items)
    return record
