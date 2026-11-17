"""Build manual gold review queue for rare day labels missing from pv_point snapshots."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.iterative_labeling.label_registry import LabelRegistryService
from services.slot_datasets.errors import SlotDatasetError
from services.slot_governance.provenance import assert_product_slot

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_datasets"

DEFAULT_RARE_LABEL_IDS = (9, 10, 16)
DEFAULT_DAY_SNAPSHOT_REL = "data/slot_datasets/pv_day/snapshots/snap-pv_day-v2.parquet"
QUEUE_REL = "data/slot_datasets/pv_point/review_queues/rare_class_9_10_16.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_backend_path(rel_path: str) -> Path:
    raw = str(rel_path or "").replace("\\", "/").strip()
    if not raw:
        raise SlotDatasetError("missing_file_path", "file_path is required")
    path = Path(raw)
    if path.is_file():
        return path.resolve()
    candidate = _BACKEND_DIR / raw
    if candidate.is_file():
        return candidate.resolve()
    raise SlotDatasetError("file_not_found", f"file not found: {raw}")


def _entity_key(site_id: Any, device_id: Any, branch_id: Any) -> str:
    return "|".join(str(part) for part in (site_id, device_id, branch_id))


def _day_boundary_iso(date_value: Any) -> tuple[str, str]:
    day = pd.Timestamp(date_value).tz_localize("UTC") if pd.Timestamp(date_value).tzinfo is None else pd.Timestamp(date_value).tz_convert("UTC")
    start = day.normalize()
    end = start + pd.Timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _label_name_map(slot: str = "pv_fault") -> dict[int, str]:
    registry = LabelRegistryService(slot=slot).get_current()
    return {
        int(item["label_id"]): str(item["label_name"])
        for item in registry.get("labels", [])
    }


def build_rare_class_review_queue(
    *,
    slot: str = "pv_point",
    day_snapshot_path: str = DEFAULT_DAY_SNAPSHOT_REL,
    rare_label_ids: tuple[int, ...] = DEFAULT_RARE_LABEL_IDS,
    registry_slot: str = "pv_fault",
    holdout_one_per_label: bool = True,
) -> dict[str, Any]:
    """List device-days for rare labels that need manual point-level human_range gold."""
    assert_product_slot(slot)
    abs_path = _resolve_backend_path(day_snapshot_path)
    frame = pd.read_parquet(abs_path)
    if "label" not in frame.columns:
        raise SlotDatasetError("missing_label_column", f"{day_snapshot_path} has no label column")

    frame = frame.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame["date"] = frame["time"].dt.date
    keys = ["site_id", "device_id", "branch_id", "date"]
    entity_days = (
        frame.dropna(subset=["label", "time"])
        .groupby(keys, dropna=False)
        .agg(
            label=("label", lambda s: int(pd.Series(s).mode().iloc[0])),
            point_count=("time", "size"),
            t_min=("time", "min"),
            t_max=("time", "max"),
        )
        .reset_index()
    )
    rare_set = {int(value) for value in rare_label_ids}
    subset = entity_days[entity_days["label"].astype(int).isin(rare_set)].copy()
    subset = subset.sort_values(["label", "site_id", "device_id", "branch_id", "date"]).reset_index(drop=True)

    names = _label_name_map(registry_slot)
    holdout_labels_seen: set[int] = set()
    items: list[dict[str, Any]] = []
    for row in subset.itertuples(index=False):
        label_id = int(row.label)
        boundary_start, boundary_end = _day_boundary_iso(row.date)
        role = "learning"
        if holdout_one_per_label and label_id not in holdout_labels_seen:
            role = "locked_holdout"
            holdout_labels_seen.add(label_id)
        entity = _entity_key(row.site_id, row.device_id, row.branch_id)
        queue_item_id = f"rq-{hashlib.sha256(f'{entity}|{row.date}|{label_id}'.encode()).hexdigest()[:12]}"
        items.append(
            {
                "queue_item_id": queue_item_id,
                "label_id": label_id,
                "label_name": names.get(label_id, f"故障{label_id}"),
                "site_id": str(row.site_id),
                "device_id": str(row.device_id),
                "branch_id": str(row.branch_id),
                "entity_key": entity,
                "date": str(row.date),
                "point_count": int(row.point_count),
                "time_min": pd.Timestamp(row.t_min).isoformat(),
                "time_max": pd.Timestamp(row.t_max).isoformat(),
                "boundary_start": boundary_start,
                "boundary_end": boundary_end,
                "annotation_role_recommended": role,
                "review_status": "pending",
                "review_kind": "point_candidate_manual_gold",
                "review_instructions": (
                    "在天路径标签基础上人工框选真实故障区间（human_range）；"
                    "框外写 point_rest_normal=0；禁止整日广播故障标签。"
                ),
                "source_day_snapshot_path": day_snapshot_path.replace("\\", "/"),
            }
        )

    by_label = (
        subset.groupby("label")
        .agg(device_days=("label", "size"), entities=("device_id", "nunique"))
        .astype(int)
        .to_dict(orient="index")
    )
    return {
        "queue_id": "rq-pv_point-rare-9-10-16-v1",
        "slot": slot,
        "created_at": _now_iso(),
        "purpose": "manual_point_gold_for_rare_day_labels",
        "registry_slot": registry_slot,
        "source_day_snapshot_path": day_snapshot_path.replace("\\", "/"),
        "rare_label_ids": sorted(rare_set),
        "summary": {
            "total_items": len(items),
            "holdout_items": sum(1 for item in items if item["annotation_role_recommended"] == "locked_holdout"),
            "by_label": {str(k): v for k, v in by_label.items()},
        },
        "items": items,
    }


def save_rare_class_review_queue(payload: dict[str, Any], *, rel_path: str = QUEUE_REL) -> str:
    rel = str(rel_path or QUEUE_REL).replace("\\", "/")
    target = _BACKEND_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return rel


def load_rare_class_review_queue(*, rel_path: str = QUEUE_REL) -> dict[str, Any]:
    target = _BACKEND_DIR / str(rel_path or QUEUE_REL).replace("\\", "/")
    if not target.is_file():
        raise SlotDatasetError("review_queue_not_found", f"review queue not found: {rel_path}")
    return json.loads(target.read_text(encoding="utf-8"))


def sync_review_queue_to_annotation_candidates(payload: dict[str, Any]) -> dict[str, Any]:
    """Mirror queue items into annotation_candidates.json for slot API listing (no point labels written)."""
    slot = str(payload.get("slot") or "pv_point")
    assert_product_slot(slot)
    from services.slot_datasets.annotation_candidates import _load_items, _save_items

    existing = _load_items(slot)
    existing_fps = {str(item.get("fingerprint")) for item in existing if item.get("fingerprint")}
    queue_id = str(payload.get("queue_id") or "rq-unknown")
    added = 0
    for item in payload.get("items") or []:
        fp_payload = json.dumps(
            {
                "queue_id": queue_id,
                "queue_item_id": item.get("queue_item_id"),
                "entity_key": item.get("entity_key"),
                "date": item.get("date"),
                "label_id": item.get("label_id"),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(fp_payload.encode("utf-8")).hexdigest()[:16]
        if fingerprint in existing_fps:
            continue
        existing.append(
            {
                "annotation_candidate_id": f"ac-{uuid.uuid4().hex[:12]}",
                "slot": slot,
                "source_workflow_id": "path-a-manual-gold",
                "source_execution_id": queue_id,
                "dataset_profile_ref": "pv-day-gold@v2",
                "entity_key": item.get("entity_key"),
                "boundary_start": item.get("boundary_start"),
                "boundary_end": item.get("boundary_end"),
                "suggested_label": item.get("label_id"),
                "confidence": None,
                "policy_version": "rare_class_manual_v1",
                "review_status": "pending",
                "fingerprint": fingerprint,
                "registered_at": _now_iso(),
                "queue_origin": queue_id,
                "queue_item_id": item.get("queue_item_id"),
                "label_name": item.get("label_name"),
                "annotation_role_recommended": item.get("annotation_role_recommended"),
                "review_kind": item.get("review_kind"),
                "review_instructions": item.get("review_instructions"),
                "source_day_snapshot_path": item.get("source_day_snapshot_path"),
                "date": item.get("date"),
            }
        )
        existing_fps.add(fingerprint)
        added += 1
    _save_items(slot, existing)
    return {"slot": slot, "added": added, "total_candidates": len(existing)}
