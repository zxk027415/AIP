"""Per-slot model registry store (JSON, relative paths only)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_governance"


def _registry_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "registry.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty_registry_view(slot: str, *, diagnostic: str | None = None) -> dict[str, Any]:
    return {
        "slot": slot,
        "registry_version": 0,
        "updated_at": None,
        "champion": None,
        "challenger": None,
        "note": None,
        "empty": True,
        "diagnostic": diagnostic or "registry not initialized for this slot",
    }


class SlotModelRegistryStore:
    def get(self, slot: str) -> dict[str, Any]:
        path = _registry_path(slot)
        if not path.is_file():
            return empty_registry_view(slot)
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return empty_registry_view(slot, diagnostic="registry file corrupted")
        payload.setdefault("slot", slot)
        payload["empty"] = payload.get("registry_version", 0) == 0
        return payload

    def save(self, slot: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = _registry_path(slot)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(payload)
        payload["slot"] = slot
        payload["updated_at"] = _now_iso()
        payload["empty"] = False
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return payload

    def next_version(self, slot: str) -> int:
        current = self.get(slot)
        return int(current.get("registry_version") or 0) + 1


def set_rolling_detect_model(
    slot: str,
    *,
    model_candidate_id: str | None = None,
    model_artifact_ref: str | None = None,
    operator: str = "ui",
    reason: str | None = None,
) -> dict[str, Any]:
    """Select which registered (or explicit) artifact the next daily detect uses. Not a Champion promote."""
    from services.slot_governance.model_candidates import find_model_candidate

    key = str(slot or "").strip()
    cid, artifact = _resolve_candidate_artifact(model_candidate_id, model_artifact_ref)
    store = get_registry_store()
    current = dict(store.get(key))
    current["rolling_detect_model"] = {
        "model_candidate_id": cid,
        "model_artifact_ref": artifact,
        "set_at": _now_iso(),
        "operator": operator,
        "reason": reason,
    }
    if current.get("registry_version") in (None, 0):
        current["registry_version"] = 1
    return store.save(key, current)


def _resolve_candidate_artifact(
    model_candidate_id: str | None,
    model_artifact_ref: str | None,
) -> tuple[str | None, str | None]:
    from services.slot_governance.model_candidates import find_model_candidate

    cid = str(model_candidate_id or "").strip() or None
    artifact = str(model_artifact_ref or "").replace("\\", "/").strip() or None
    if not cid and not artifact:
        raise ValueError("model_candidate_id or model_artifact_ref is required")
    if cid:
        _, found = find_model_candidate(cid)
        if found is None:
            raise ValueError(f"candidate_not_found: {cid}")
        artifact = str(found.get("model_artifact_ref") or artifact or "").replace("\\", "/")
        cid = str(found.get("model_candidate_id") or cid)
    return cid, artifact


def set_production_model(
    slot: str,
    *,
    model_candidate_id: str | None = None,
    model_artifact_ref: str | None = None,
    operator: str = "ui",
    reason: str | None = None,
) -> dict[str, Any]:
    """Mark a model as production (champion) and dual-write rolling_detect_model."""
    cid, artifact = _resolve_candidate_artifact(model_candidate_id, model_artifact_ref)
    store = get_registry_store()
    current = dict(store.get(slot))
    current["champion"] = {
        "champion_model_ref": cid,
        "champion_model_artifact_ref": artifact,
        "set_at": _now_iso(),
        "operator": operator,
        "reason": reason,
    }
    current["rolling_detect_model"] = {
        "model_candidate_id": cid,
        "model_artifact_ref": artifact,
        "set_at": _now_iso(),
        "operator": operator,
        "reason": reason or "set_production_model",
    }
    if current.get("registry_version") in (None, 0):
        current["registry_version"] = 1
    else:
        current["registry_version"] = int(current.get("registry_version") or 0) + 1
    return store.save(slot, current)


def set_candidate_model(
    slot: str,
    *,
    model_candidate_id: str | None = None,
    model_artifact_ref: str | None = None,
    operator: str = "ui",
    reason: str | None = None,
) -> dict[str, Any]:
    """Mark a model as candidate (challenger). Does not change daily detect."""
    cid, artifact = _resolve_candidate_artifact(model_candidate_id, model_artifact_ref)
    store = get_registry_store()
    current = dict(store.get(slot))
    current["challenger"] = {
        "challenger_model_candidate_id": cid,
        "challenger_model_ref": cid,
        "challenger_model_artifact_ref": artifact,
        "set_at": _now_iso(),
        "operator": operator,
        "reason": reason,
    }
    if current.get("registry_version") in (None, 0):
        current["registry_version"] = 1
    return store.save(slot, current)


_registry_store = SlotModelRegistryStore()


def get_registry_store() -> SlotModelRegistryStore:
    return _registry_store
