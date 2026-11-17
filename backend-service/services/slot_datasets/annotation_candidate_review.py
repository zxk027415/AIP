"""Convert G5 annotation candidates into curve-review sessions (rev-*).

Product rule:
- One complete rolling detection (same source_execution_id) -> one rev-* session.
- Fallback group key: slot + detection calendar day (registered_at).
- Session contains multiple units (device-day / detection intervals), not one session per candidate.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.iterative_labeling.label_registry import LabelRegistryService
from services.iterative_labeling.review_session import ReviewSessionService
from services.iterative_labeling.storage.interfaces import ReviewResultRepository
from services.slot_datasets.annotation_candidates import find_annotation_candidate
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.snapshots import get_cumulative_ledger
from services.slot_governance.provenance import assert_product_slot

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PREDICTION_BATCH_DIR = _BACKEND_DIR / "data" / "iterative_labeling" / "prediction_batches"

_SLOT_DEFAULT_SOURCE: dict[str, str] = {
    "pv_day": "data/slot_datasets/pv_day/snapshots/snap-pv_day-v2.parquet",
    "pv_point": "data/slot_datasets/pv_point/snapshots/snap-pv_point-v5.parquet",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _norm_id(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_entity_key(entity_key: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in str(entity_key or "").split("|")]
    while len(parts) < 3:
        parts.append("")
    return parts[0], parts[1], parts[2]


def _resolve_backend_file(rel_path: str) -> Path:
    raw = str(rel_path or "").replace("\\", "/").strip()
    if not raw:
        raise SlotDatasetError("missing_file_path", "source path is required")
    candidates = [
        _BACKEND_DIR / raw,
        _BACKEND_DIR.parent / raw,
        Path(raw),
    ]
    for cand in candidates:
        if cand.is_file():
            return cand.resolve()
    raise SlotDatasetError("file_not_found", f"source file not found: {raw}")


def _relative_project_path(abs_path: Path) -> str:
    for base in (_BACKEND_DIR.parent, _BACKEND_DIR):
        try:
            rel = abs_path.resolve().relative_to(base.resolve())
            return rel.as_posix()
        except ValueError:
            continue
    raise SlotDatasetError("path_outside_project", "source path must resolve inside project root")


def _latest_freeze_artifact(slot: str) -> Optional[str]:
    try:
        ledger = get_cumulative_ledger(slot)
    except Exception:
        return None
    latest = ledger.get("latest_freeze") or {}
    for version in ledger.get("freeze_versions") or []:
        if int(version.get("snapshot_version") or 0) == int(latest.get("snapshot_version") or 0):
            artifact = str(version.get("artifact_ref") or "").strip()
            if artifact:
                return artifact.replace("\\", "/")
    return None


def _prediction_batch_source(slot: str, execution_id: str) -> Optional[str]:
    batch_dir = _PREDICTION_BATCH_DIR / slot.replace("/", "_")
    if not batch_dir.is_dir():
        return None
    target = str(execution_id or "").strip()
    for path in sorted(batch_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(payload.get("source_execution_id") or "") != target:
            continue
        batch_path = str(payload.get("source_csv_path") or payload.get("dataset_version") or "").strip()
        if batch_path:
            return batch_path.replace("\\", "/")
    return None


def resolve_candidate_source_csv_path(*, slot: str, candidate: dict[str, Any]) -> str:
    """Resolve a project-relative source CSV/parquet for curve review."""
    for key in ("source_csv_path", "source_day_snapshot_path"):
        raw = str(candidate.get(key) or "").strip()
        if raw:
            _resolve_backend_file(raw)
            return raw.replace("\\", "/")

    execution_id = str(candidate.get("source_execution_id") or "").strip()
    if execution_id:
        batch_source = _prediction_batch_source(slot, execution_id)
        if batch_source:
            _resolve_backend_file(batch_source)
            return batch_source.replace("\\", "/")

    latest = _latest_freeze_artifact(slot)
    if latest:
        _resolve_backend_file(latest)
        return latest.replace("\\", "/")

    fallback = _SLOT_DEFAULT_SOURCE.get(slot)
    if fallback:
        _resolve_backend_file(fallback)
        return fallback

    raise SlotDatasetError(
        "missing_source_csv_path",
        f"cannot resolve review source for slot={slot!r} candidate={candidate.get('annotation_candidate_id')!r}",
    )


def _time_window_from_candidate(candidate: dict[str, Any]) -> str:
    if candidate.get("date"):
        return str(pd.Timestamp(candidate["date"]).strftime("%Y-%m-%d"))
    for key in ("boundary_start", "boundary_end"):
        raw = str(candidate.get(key) or "").strip()
        if not raw:
            continue
        parsed = pd.to_datetime(raw, utc=True, errors="coerce")
        if pd.notna(parsed):
            return parsed.strftime("%Y-%m-%d")
    raise SlotDatasetError("missing_time_window", "candidate has no date/boundary for time_window")


def _detection_day_from_candidate(candidate: dict[str, Any]) -> str:
    """Use the device-day being reviewed, not the queue registered_at."""
    if candidate.get("date"):
        parsed = pd.to_datetime(candidate["date"], utc=True, errors="coerce")
        if pd.notna(parsed):
            return parsed.strftime("%Y-%m-%d")
    for key in ("boundary_start", "boundary_end"):
        raw = str(candidate.get(key) or "").strip()
        if not raw:
            continue
        parsed = pd.to_datetime(raw, utc=True, errors="coerce")
        if pd.notna(parsed):
            return parsed.strftime("%Y-%m-%d")
    registered = str(candidate.get("registered_at") or "").strip()
    if registered:
        parsed = pd.to_datetime(registered, utc=True, errors="coerce")
        if pd.notna(parsed):
            return parsed.strftime("%Y-%m-%d")
    return _time_window_from_candidate(candidate)


def detection_group_id(*, slot: str, candidate: dict[str, Any]) -> str:
    """Stable id for one complete detection batch (prefer source_execution_id)."""
    execution_id = str(candidate.get("source_execution_id") or "").strip()
    if execution_id:
        return f"det-{slot}-{execution_id}"
    day = _detection_day_from_candidate(candidate)
    return f"det-{slot}-{day}"


# @AI_GENERATED: explicit product mapping prevents unknown slots from silently becoming day models.
def _modeling_profile(slot: str) -> tuple[str, str]:
    profiles = {
        "pv_day": ("legacy_day", "day"),
        "pv_point": ("seq_annotation", "point"),
        "pv_tsc": ("tsc", "day"),
    }
    profile = profiles.get(str(slot or "").strip())
    if profile is None:
        raise SlotDatasetError("invalid_slot", f"unsupported annotation review slot: {slot!r}")
    return profile
# @AI_GENERATED: end


def list_pending_annotation_candidates_for_review(slot: str) -> list[dict[str, Any]]:
    """Pending candidates that do not yet have a linked rev-* session."""
    from services.slot_datasets.annotation_candidates import list_annotation_candidates

    key = str(slot or "").strip()
    assert_product_slot(key)
    pending: list[dict[str, Any]] = []
    for item in list_annotation_candidates(key):
        status = str(item.get("review_status") or "pending")
        if status == "rejected":
            continue
        if str(item.get("review_session_id") or "").strip():
            continue
        if status in {"pending", "in_review"}:
            pending.append(dict(item))
    return pending


def list_pending_detection_groups(slot: str) -> list[dict[str, Any]]:
    """Group pending candidates by one complete detection (execution id or detection day)."""
    key = str(slot or "").strip()
    assert_product_slot(key)
    pending = list_pending_annotation_candidates_for_review(key)
    grouped: dict[str, dict[str, Any]] = {}
    for item in pending:
        gid = detection_group_id(slot=key, candidate=item)
        bucket = grouped.get(gid)
        if bucket is None:
            bucket = {
                "detection_group_id": gid,
                "slot": key,
                "source_execution_id": item.get("source_execution_id"),
                "detection_date": _detection_day_from_candidate(item),
                "source_workflow_id": item.get("source_workflow_id"),
                "candidate_count": 0,
                "annotation_candidate_ids": [],
                "detection_dates": [],
                "review_session_id": None,
            }
            grouped[gid] = bucket
        bucket["candidate_count"] = int(bucket["candidate_count"]) + 1
        bucket["annotation_candidate_ids"].append(item.get("annotation_candidate_id"))
        day = _detection_day_from_candidate(item)
        dates = bucket.setdefault("detection_dates", [])
        if day and day not in dates:
            dates.append(day)
    groups = list(grouped.values())
    for bucket in groups:
        dates = sorted(str(item) for item in (bucket.pop("detection_dates", None) or []) if item)
        if not dates:
            bucket["detection_date"] = ""
        elif len(dates) == 1:
            bucket["detection_date"] = dates[0]
        else:
            bucket["detection_date"] = f"{dates[0]}~{dates[-1]}"
    groups.sort(key=lambda row: (str(row.get("detection_date") or ""), str(row.get("detection_group_id") or "")), reverse=True)
    return groups


# @AI_GENERATED: 保留机器候选的 TSC 日级结论、逐窗证据和模型角色供审核页消费。
def _candidate_to_unit(candidate: dict[str, Any]) -> dict[str, Any]:
    site_id, device_id, branch_id = _parse_entity_key(str(candidate.get("entity_key") or ""))
    if not device_id:
        raise SlotDatasetError("invalid_entity_key", f"entity_key missing device_id: {candidate.get('entity_key')!r}")
    time_window = _time_window_from_candidate(candidate)
    suggested = candidate.get("suggested_label")
    try:
        predicted_label = int(suggested) if suggested is not None and str(suggested) != "" else None
    except (TypeError, ValueError):
        predicted_label = None
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
    per_window_details = (
        candidate.get("per_window_details")
        or candidate.get("windows")
        or evidence.get("per_window_details")
        or evidence.get("windows")
        or []
    )
    model_window_config = (
        candidate.get("model_window_config")
        or candidate.get("window_config")
        or evidence.get("model_window_config")
        or evidence.get("window_config")
        or {}
    )
    unit_key = f"{_norm_id(site_id)}|{_norm_id(device_id)}|{_norm_id(branch_id)}|{time_window}"
    return {
        "unit_key": unit_key,
        "site_id": site_id or None,
        "device_id": device_id,
        "branch_id": branch_id or None,
        "time_window": time_window,
        "target_day": candidate.get("target_day") or evidence.get("target_day") or time_window,
        "predicted_label": predicted_label,
        "confidence": float(candidate.get("confidence") or evidence.get("day_confidence") or 0.0),
        "n_windows": int(candidate.get("n_windows") or evidence.get("n_windows") or len(per_window_details)),
        "per_window_predictions": candidate.get("per_window_predictions") or evidence.get("per_window_predictions") or [],
        "per_window_details": per_window_details,
        "aggregation": candidate.get("aggregation") or evidence.get("aggregation"),
        "model_name": candidate.get("model_name") or evidence.get("model_name"),
        "model_window_config": model_window_config,
        "model_ref": candidate.get("model_ref") or evidence.get("model_ref"),
        "model_source": candidate.get("model_source") or evidence.get("model_source"),
        "model_role": candidate.get("model_role") or candidate.get("model_source") or evidence.get("model_role"),
        "model_candidate_id": candidate.get("model_candidate_id") or evidence.get("model_candidate_id"),
        "annotation_candidate_id": candidate.get("annotation_candidate_id"),
        "annotation_role_recommended": candidate.get("annotation_role_recommended") or "learning",
        "candidate_boundary_start": candidate.get("boundary_start"),
        "candidate_boundary_end": candidate.get("boundary_end"),
    }
# @AI_GENERATED: end


def _link_candidates_to_session(slot: str, candidate_ids: list[str], review_id: str) -> None:
    from services.slot_datasets.annotation_candidates import _load_items, _save_items

    wanted = {str(cid) for cid in candidate_ids if cid}
    items = _load_items(slot)
    touched = False
    for item in items:
        if str(item.get("annotation_candidate_id") or "") not in wanted:
            continue
        item["review_session_id"] = review_id
        item["review_status"] = "in_review"
        item["review_started_at"] = _now_iso()
        touched = True
    if touched:
        _save_items(slot, items)


def _candidates_in_detection_group(slot: str, group_key: str) -> list[dict[str, Any]]:
    from services.slot_datasets.annotation_candidates import list_annotation_candidates

    return [
        dict(item)
        for item in list_annotation_candidates(slot)
        if detection_group_id(slot=slot, candidate=item) == group_key
        and str(item.get("review_status") or "") != "rejected"
    ]


def _existing_group_session(
    *,
    slot: str,
    group_key: str,
    review_repo: ReviewResultRepository,
    registry_service: LabelRegistryService,
) -> Optional[dict[str, Any]]:
    group_candidates = _candidates_in_detection_group(slot, group_key)
    review_ids = {
        str(item.get("review_session_id") or "").strip()
        for item in group_candidates
        if str(item.get("review_session_id") or "").strip()
    }
    if not review_ids:
        return None
    if len(review_ids) > 1:
        raise SlotDatasetError(
            "detection_group_split",
            f"detection group has multiple review_session_id values: {sorted(review_ids)!r}",
        )
    review_id = next(iter(review_ids))
    service = ReviewSessionService(slot=slot, review_repo=review_repo, registry_service=registry_service)
    session = service.get_session(review_id)
    if not session:
        return None
    return {
        "review_id": review_id,
        "total_count": session.get("total_count", len(group_candidates)),
        "detection_group_id": group_key,
        "candidate_count": len(group_candidates),
        "idempotent_replay": True,
    }


def create_review_session_from_detection_group(
    *,
    slot: str,
    detection_group_id_value: str,
    review_repo: ReviewResultRepository,
    registry_service: LabelRegistryService,
    reviewer: str = "ui-operator",
    source_csv_path: Optional[str] = None,
) -> dict[str, Any]:
    """Materialize one rev-* session for all pending candidates in a detection group."""
    key = str(slot or "").strip()
    assert_product_slot(key)
    group_key = str(detection_group_id_value or "").strip()
    if not group_key:
        raise SlotDatasetError("missing_detection_group_id", "detection_group_id is required")

    existing = _existing_group_session(
        slot=key,
        group_key=group_key,
        review_repo=review_repo,
        registry_service=registry_service,
    )
    if existing is not None:
        return existing

    pending = list_pending_annotation_candidates_for_review(key)
    group_candidates = [
        item for item in pending if detection_group_id(slot=key, candidate=item) == group_key
    ]
    if not group_candidates:
        raise SlotDatasetError("detection_group_empty", f"no pending candidates for group {group_key!r}")

    modeling_path, prediction_granularity = _modeling_profile(key)
    resolved_source = str(
        source_csv_path or resolve_candidate_source_csv_path(slot=key, candidate=group_candidates[0])
    ).strip()
    source_rel = _relative_project_path(_resolve_backend_file(resolved_source))

    units_by_key: dict[str, dict[str, Any]] = {}
    for candidate in group_candidates:
        unit = _candidate_to_unit(candidate)
        units_by_key[str(unit["unit_key"])] = unit
    prediction_units = [
        {k: v for k, v in unit.items() if not str(k).startswith("annotation_") and not str(k).startswith("candidate_")}
        for unit in units_by_key.values()
    ]

    first = group_candidates[0]
    execution_id = str(first.get("source_execution_id") or group_key)
    days = sorted({_detection_day_from_candidate(item) for item in group_candidates})
    detection_date = days[0] if len(days) <= 1 else f"{days[0]}~{days[-1]}"
    review_service = ReviewSessionService(slot=key, review_repo=review_repo, registry_service=registry_service)
    session = review_service.create_session(
        loop_id=f"detection-{detection_date}",
        prediction_batch_id=f"det-{execution_id}",
        prediction_units=prediction_units,
        llm_suggestions={},
        prediction_context={
            "source_csv_path": source_rel,
            "load_config": {},
            "window_config": {"time_field": "time", "window": "1D", "id_fields": ["site_id", "device_id", "branch_id"]},
            "modeling_path": modeling_path,
            "prediction_granularity": prediction_granularity,
            "manual_labeling": True,
            "review_kind": str(first.get("review_kind") or "annotation_candidate_review"),
            "detection_group_id": group_key,
            "detection_date": detection_date,
            "source_execution_id": execution_id,
            "annotation_candidate_ids": [item.get("annotation_candidate_id") for item in group_candidates],
            "candidate_units": list(units_by_key.values()),
            "review_instructions": first.get("review_instructions"),
            "reviewer": reviewer,
            "one_detection_one_session": True,
        },
    )

    review_id = str(session["review_id"])
    candidate_ids = [str(item.get("annotation_candidate_id") or "") for item in group_candidates]
    _link_candidates_to_session(key, candidate_ids, review_id)

    return {
        "review_id": review_id,
        "total_count": session.get("total_count", len(prediction_units)),
        "detection_group_id": group_key,
        "detection_date": detection_date,
        "candidate_count": len(group_candidates),
        "slot": key,
        "prediction_granularity": prediction_granularity,
        "source_csv_path": source_rel,
        "idempotent_replay": False,
    }


def create_review_session_from_annotation_candidate(
    *,
    slot: str,
    annotation_candidate_id: str,
    review_repo: ReviewResultRepository,
    registry_service: LabelRegistryService,
    reviewer: str = "ui-operator",
    source_csv_path: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve candidate's detection group and create the full daily detection session."""
    key = str(slot or "").strip()
    assert_product_slot(key)
    cand_slot, candidate = find_annotation_candidate(annotation_candidate_id)
    if candidate is None:
        raise SlotDatasetError("candidate_not_found", f"annotation_candidate_id={annotation_candidate_id!r} not found")
    if cand_slot != key:
        raise SlotDatasetError("slot_mismatch", f"candidate slot={cand_slot!r} != requested slot={key!r}")
    group_key = detection_group_id(slot=key, candidate=candidate)
    result = create_review_session_from_detection_group(
        slot=key,
        detection_group_id_value=group_key,
        review_repo=review_repo,
        registry_service=registry_service,
        reviewer=reviewer,
        source_csv_path=source_csv_path,
    )
    result["annotation_candidate_id"] = annotation_candidate_id
    return result
