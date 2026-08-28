"""Annotation candidate store — separate from G4 model candidates."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.slot_governance.provenance import ProvenanceError, assert_product_slot, validate_execution_source
from services.slot_datasets.errors import SlotDatasetError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_datasets"


def _candidates_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "annotation_candidates.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_items(slot: str) -> list[dict[str, Any]]:
    path = _candidates_path(slot)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("candidates")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_items(slot: str, items: list[dict[str, Any]]) -> None:
    path = _candidates_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"slot": slot, "candidates": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _fingerprint(
    *,
    slot: str,
    entity_key: str,
    boundary_start: str,
    boundary_end: str,
    suggested_label: Any,
) -> str:
    payload = json.dumps(
        {
            "slot": slot,
            "entity_key": entity_key,
            "boundary_start": boundary_start,
            "boundary_end": boundary_end,
            "suggested_label": suggested_label,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def find_annotation_candidate(annotation_candidate_id: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    root = _DATA_DIR
    if not root.is_dir():
        return None, None
    target = str(annotation_candidate_id or "").strip()
    for slot_dir in root.iterdir():
        if not slot_dir.is_dir():
            continue
        for item in _load_items(slot_dir.name):
            if item.get("annotation_candidate_id") == target:
                return item.get("slot") or slot_dir.name, item
    return None, None


def list_annotation_candidates(slot: str, *, review_status: Optional[str] = None) -> list[dict[str, Any]]:
    assert_product_slot(slot)
    items = _load_items(slot)
    if review_status:
        return [item for item in items if item.get("review_status") == review_status]
    return items


def register_annotation_candidate(
    *,
    slot: str,
    source_workflow_id: str,
    source_execution_id: str,
    model_ref: Optional[str] = None,
    dataset_profile_ref: str,
    entity_key: str,
    boundary_start: str,
    boundary_end: str,
    suggested_label: Any,
    confidence: Optional[float] = None,
    policy_version: str = "v1",
    candidate_projection_enabled: bool = True,
    scenario_key: Optional[str] = None,
) -> dict[str, Any]:
    if scenario_key not in (None, ""):
        raise ProvenanceError(
            "scenario_key_not_allowed",
            "scenario_key is not allowed; send slot directly",
        )
    if not candidate_projection_enabled:
        raise SlotDatasetError(
            "candidate_projection_disabled",
            "candidate_projection_enabled must be true to register product annotation candidates",
        )

    provenance = validate_execution_source(
        slot=slot,
        source_workflow_id=source_workflow_id,
        source_execution_id=source_execution_id,
    )

    fp = _fingerprint(
        slot=slot,
        entity_key=entity_key,
        boundary_start=boundary_start,
        boundary_end=boundary_end,
        suggested_label=suggested_label,
    )
    for existing in _load_items(slot):
        if existing.get("fingerprint") == fp:
            return existing

    candidate_id = f"ac-{uuid.uuid4().hex[:12]}"
    record: dict[str, Any] = {
        "annotation_candidate_id": candidate_id,
        "slot": slot,
        "source_workflow_id": provenance["source_workflow_id"],
        "source_workflow_version": provenance.get("source_workflow_version"),
        "source_execution_id": provenance["source_execution_id"],
        "model_ref": model_ref,
        "dataset_profile_ref": dataset_profile_ref,
        "entity_key": entity_key,
        "boundary_start": boundary_start,
        "boundary_end": boundary_end,
        "suggested_label": suggested_label,
        "confidence": confidence,
        "policy_version": policy_version,
        "review_status": "pending",
        "fingerprint": fp,
        "registered_at": _now_iso(),
    }
    items = _load_items(slot)
    items.append(record)
    _save_items(slot, items)
    return record


def update_annotation_candidate_status(
    slot: str,
    annotation_candidate_id: str,
    *,
    review_status: str,
    reviewed_annotation_id: Optional[str] = None,
) -> dict[str, Any]:
    items = _load_items(slot)
    for item in items:
        if item.get("annotation_candidate_id") == annotation_candidate_id:
            item["review_status"] = review_status
            if reviewed_annotation_id:
                item["reviewed_annotation_id"] = reviewed_annotation_id
            item["review_updated_at"] = _now_iso()
            _save_items(slot, items)
            return item
    raise SlotDatasetError("candidate_not_found", f"annotation_candidate_id={annotation_candidate_id!r} not found")
