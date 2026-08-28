"""Model candidate registration with workflow provenance gate."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.slot_governance.provenance import ProvenanceError, assert_product_slot, validate_execution_provenance

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_governance"


def _candidates_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "model_candidates.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_candidates(slot: str) -> list[dict[str, Any]]:
    path = _candidates_path(slot)
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items = payload.get("candidates")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_candidates(slot: str, items: list[dict[str, Any]]) -> None:
    path = _candidates_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"slot": slot, "candidates": items}, handle, ensure_ascii=False, indent=2)


def list_model_candidates(slot: str) -> list[dict[str, Any]]:
    assert_product_slot(slot)
    return _load_candidates(slot)


def find_model_candidate(model_candidate_id: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Search all slot partitions for a candidate id."""
    root = _DATA_DIR
    if not root.is_dir():
        return None, None
    target = str(model_candidate_id or "").strip()
    if not target:
        return None, None
    for slot_dir in root.iterdir():
        if not slot_dir.is_dir():
            continue
        for item in _load_candidates(slot_dir.name):
            if item.get("model_candidate_id") == target:
                return item.get("slot") or slot_dir.name, item
    return None, None


def register_model_candidate(
    *,
    slot: str,
    source_workflow_id: str,
    source_execution_id: str,
    model_artifact_ref: str,
    source_workflow_version: Optional[str] = None,
    model_ref: Optional[str] = None,
    scenario_key: Optional[str] = None,
) -> dict[str, Any]:
    if scenario_key not in (None, ""):
        raise ProvenanceError(
            "scenario_key_not_allowed",
            "scenario_key is not allowed; send slot directly",
        )

    provenance = validate_execution_provenance(
        slot=slot,
        source_workflow_id=source_workflow_id,
        source_execution_id=source_execution_id,
        model_artifact_ref=model_artifact_ref,
    )

    if source_workflow_version not in (None, ""):
        provenance["source_workflow_version"] = source_workflow_version

    candidate_id = f"mc-{uuid.uuid4().hex[:12]}"
    record: dict[str, Any] = {
        "model_candidate_id": candidate_id,
        "slot": slot,
        "source_workflow_id": provenance["source_workflow_id"],
        "source_workflow_version": provenance.get("source_workflow_version"),
        "source_execution_id": provenance["source_execution_id"],
        "model_artifact_ref": provenance["model_artifact_ref"],
        "model_ref": model_ref or candidate_id,
        "registered_at": _now_iso(),
        "status": "registered",
        "execution_status": provenance.get("execution_status"),
    }

    items = _load_candidates(slot)
    items.append(record)
    _save_candidates(slot, items)
    return record
