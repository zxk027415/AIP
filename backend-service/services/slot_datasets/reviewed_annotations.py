"""Reviewed annotation store (G5)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.slot_governance.provenance import assert_product_slot
from services.slot_datasets.annotation_candidates import (
    find_annotation_candidate,
    update_annotation_candidate_status,
)
from services.slot_datasets.errors import SlotDatasetError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_datasets"


def _annotations_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "reviewed_annotations.json"


def _reviews_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "review_transactions.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_annotations(slot: str) -> list[dict[str, Any]]:
    path = _annotations_path(slot)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("annotations")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_annotations(slot: str, items: list[dict[str, Any]]) -> None:
    path = _annotations_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"slot": slot, "annotations": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_review_tx(slot: str) -> list[dict[str, Any]]:
    path = _reviews_path(slot)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("transactions")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_review_tx(slot: str, items: list[dict[str, Any]]) -> None:
    path = _reviews_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"slot": slot, "transactions": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_review_by_idempotency(slot: str, idempotency_key: str) -> Optional[dict[str, Any]]:
    for tx in _load_review_tx(slot):
        if tx.get("idempotency_key") == idempotency_key:
            return tx
    return None


def list_reviewed_annotations(slot: str) -> list[dict[str, Any]]:
    assert_product_slot(slot)
    return _load_annotations(slot)


def approve_annotation_candidate(
    *,
    slot: str,
    annotation_candidate_id: str,
    reviewer: str,
    idempotency_key: str,
    final_label: Optional[Any] = None,
    label_space_version: str = "v1",
    annotation_role: str = "learning",
) -> dict[str, Any]:
    assert_product_slot(slot)
    if not idempotency_key.strip():
        raise SlotDatasetError("missing_idempotency_key", "idempotency_key is required")
    if not reviewer.strip():
        raise SlotDatasetError("missing_reviewer", "reviewer is required")

    existing_tx = find_review_by_idempotency(slot, idempotency_key)
    if existing_tx is not None:
        if existing_tx.get("annotation_candidate_id") != annotation_candidate_id:
            raise SlotDatasetError(
                "idempotency_conflict",
                "idempotency_key reused with different annotation_candidate_id",
            )
        ann_id = existing_tx.get("reviewed_annotation_id")
        for ann in _load_annotations(slot):
            if ann.get("reviewed_annotation_id") == ann_id:
                return {"reviewed_annotation": ann, "transaction": existing_tx, "idempotent_replay": True}
        raise SlotDatasetError("review_state_corrupt", "idempotent transaction missing reviewed annotation")

    cand_slot, candidate = find_annotation_candidate(annotation_candidate_id)
    if candidate is None:
        raise SlotDatasetError("candidate_not_found", f"annotation_candidate_id={annotation_candidate_id!r} not found")
    if cand_slot != slot:
        raise SlotDatasetError("slot_mismatch", f"candidate slot={cand_slot!r} != requested slot={slot!r}")
    if candidate.get("review_status") == "approved":
        for ann in _load_annotations(slot):
            if ann.get("source_annotation_candidate_id") == annotation_candidate_id:
                return {"reviewed_annotation": ann, "transaction": None, "idempotent_replay": True}

    label = final_label if final_label is not None else candidate.get("suggested_label")
    reviewed_id = f"ra-{uuid.uuid4().hex[:12]}"
    reviewed: dict[str, Any] = {
        "reviewed_annotation_id": reviewed_id,
        "slot": slot,
        "source_annotation_candidate_id": annotation_candidate_id,
        "reviewer": reviewer,
        "reviewed_at": _now_iso(),
        "entity_key": candidate.get("entity_key"),
        "boundary_start": candidate.get("boundary_start"),
        "boundary_end": candidate.get("boundary_end"),
        "original_label": candidate.get("suggested_label"),
        "final_label": label,
        "label_space_version": label_space_version,
        "annotation_role": annotation_role,
        "model_ref": candidate.get("model_ref"),
        "dataset_profile_ref": candidate.get("dataset_profile_ref"),
    }

    tx = {
        "transaction_id": f"rtx-{uuid.uuid4().hex[:12]}",
        "slot": slot,
        "annotation_candidate_id": annotation_candidate_id,
        "reviewed_annotation_id": reviewed_id,
        "action": "approve",
        "reviewer": reviewer,
        "idempotency_key": idempotency_key,
        "created_at": _now_iso(),
    }

    annotations = _load_annotations(slot)
    annotations.append(reviewed)
    _save_annotations(slot, annotations)

    txs = _load_review_tx(slot)
    txs.append(tx)
    _save_review_tx(slot, txs)

    update_annotation_candidate_status(
        slot,
        annotation_candidate_id,
        review_status="approved",
        reviewed_annotation_id=reviewed_id,
    )

    return {"reviewed_annotation": reviewed, "transaction": tx, "idempotent_replay": False}


def reject_annotation_candidate(
    *,
    slot: str,
    annotation_candidate_id: str,
    reviewer: str,
    idempotency_key: str,
    reason: str,
) -> dict[str, Any]:
    assert_product_slot(slot)
    existing_tx = find_review_by_idempotency(slot, idempotency_key)
    if existing_tx is not None:
        return {"transaction": existing_tx, "idempotent_replay": True}

    cand_slot, candidate = find_annotation_candidate(annotation_candidate_id)
    if candidate is None:
        raise SlotDatasetError("candidate_not_found", f"annotation_candidate_id={annotation_candidate_id!r} not found")
    if cand_slot != slot:
        raise SlotDatasetError("slot_mismatch", f"candidate slot={cand_slot!r} != requested slot={slot!r}")

    tx = {
        "transaction_id": f"rtx-{uuid.uuid4().hex[:12]}",
        "slot": slot,
        "annotation_candidate_id": annotation_candidate_id,
        "action": "reject",
        "reviewer": reviewer,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "created_at": _now_iso(),
    }
    txs = _load_review_tx(slot)
    txs.append(tx)
    _save_review_tx(slot, txs)

    update_annotation_candidate_status(slot, annotation_candidate_id, review_status="rejected")
    return {"transaction": tx, "idempotent_replay": False}
