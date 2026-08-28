"""Admit completed review sessions into slot cumulative ledger (one session -> one ledger event, no freeze)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from services.iterative_labeling.review_session import ReviewSessionService
from services.iterative_labeling.storage.interfaces import ReviewResultRepository
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.review_admission import admit_labeled_file_to_cumulative
from services.slot_datasets.snapshots import SOURCE_DAILY_REVIEW
from services.slot_governance.provenance import assert_product_slot

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PV_PRODUCT_SLOTS = frozenset({"pv_day", "pv_point"})
_HOLDOUT_ROLES = frozenset({"holdout", "locked_holdout"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iterative_labeling_root() -> Path:
    root_str = os.environ.get("ITERATIVE_LABELING_DATA_ROOT", "data/iterative_labeling")
    root = Path(root_str)
    if not root.is_absolute():
        root = (_BACKEND_DIR / root).resolve()
    return root.resolve()


def _resolve_slice_path(rel_path: str) -> Path:
    raw = str(rel_path or "").replace("\\", "/").strip()
    if not raw:
        raise SlotDatasetError("missing_slice_path", "freeform label missing dataset_path")
    il_root = _iterative_labeling_root()
    stripped = raw
    for prefix in (
        "backend-service/data/iterative_labeling/",
        "data/iterative_labeling/",
    ):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :]
            break
    candidates = [
        _BACKEND_DIR / raw,
        _BACKEND_DIR.parent / raw,
        il_root / stripped,
        il_root / raw,
        Path(raw),
    ]
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand.resolve()
    raise SlotDatasetError("slice_not_found", f"slice file not found: {raw}")


def _relative_backend_path(abs_path: Path) -> str:
    rel = os.path.relpath(str(abs_path.resolve()), start=str(_BACKEND_DIR))
    if rel.startswith(".."):
        raise SlotDatasetError("path_outside_backend", "merged review file must stay under backend-service")
    return rel.replace("\\", "/")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _is_holdout_role(role: Any) -> bool:
    return str(role or "").strip().lower() in _HOLDOUT_ROLES


def _candidate_units_of(session: dict[str, Any]) -> list[dict[str, Any]]:
    ctx = session.get("prediction_context") or {}
    raw = ctx.get("candidate_units") or []
    return [item for item in raw if isinstance(item, dict)]


def _unit_role(unit: dict[str, Any], candidate_units: list[dict[str, Any]]) -> str:
    unit_key = _norm(unit.get("unit_key"))
    for cand in candidate_units:
        if _norm(cand.get("unit_key")) == unit_key and unit_key:
            role = str(cand.get("annotation_role_recommended") or "learning").strip().lower()
            return role or "learning"
    role = str(unit.get("annotation_role_recommended") or "").strip().lower()
    return role or "learning"


def _calendar_day(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = pd.to_datetime(raw, utc=True, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")
    return raw[:10]


def _label_covers_unit(label: dict[str, Any], unit: dict[str, Any]) -> bool:
    unit_key = _norm(unit.get("unit_key"))
    if unit_key and _norm(label.get("source_unit_key")) == unit_key:
        return True
    if unit_key and _norm(label.get("unit_key")) == unit_key:
        return True
    if (
        _norm(label.get("site_id")) == _norm(unit.get("site_id"))
        and _norm(label.get("device_id")) == _norm(unit.get("device_id"))
        and _norm(label.get("branch_id")) == _norm(unit.get("branch_id"))
    ):
        unit_day = _calendar_day(unit.get("time_window"))
        label_day = _calendar_day(label.get("t_start") or label.get("time_window"))
        if unit_day and label_day and unit_day == label_day:
            return True
    return False


def _unboxed_unit_keys(units: list[dict[str, Any]], labels: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for unit in units:
        if not any(_label_covers_unit(label, unit) for label in labels):
            missing.append(_norm(unit.get("unit_key")) or "?")
    return missing


def _label_is_holdout(
    label: dict[str, Any],
    units: list[dict[str, Any]],
    candidate_units: list[dict[str, Any]],
) -> bool:
    covered = [unit for unit in units if _label_covers_unit(label, unit)]
    if not covered:
        return False
    return all(_is_holdout_role(_unit_role(unit, candidate_units)) for unit in covered)


def _merge_freeform_slices(review_id: str, labels: list[dict[str, Any]]) -> tuple[Path, int]:
    frames: list[pd.DataFrame] = []
    seen: set[str] = set()
    for item in labels:
        rel = str(item.get("dataset_path") or "").strip()
        if not rel:
            continue
        path = _resolve_slice_path(rel)
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            frames.append(pd.read_parquet(path))
        else:
            frames.append(pd.read_csv(path, encoding="utf-8"))
    if not frames:
        raise SlotDatasetError("empty_freeform_labels", "no slice files to merge for cumulative admission")
    merged = pd.concat(frames, ignore_index=True)
    if "time" in merged.columns:
        merged["time"] = pd.to_datetime(merged["time"], errors="coerce", utc=True)
        merged = merged.sort_values("time")
    out_dir = _BACKEND_DIR / "data" / "slot_datasets" / "confirmed_reviews"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"review-{review_id}-{uuid.uuid4().hex[:8]}.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8")
    return out_path, int(len(merged))


def _mark_candidates_completed(slot: str, session: dict[str, Any], *, review_id: str) -> None:
    ctx = session.get("prediction_context") or {}
    candidate_ids = [
        str(value)
        for value in (ctx.get("annotation_candidate_ids") or [])
        if str(value).strip()
    ]
    single = str(ctx.get("annotation_candidate_id") or "").strip()
    if single:
        candidate_ids.append(single)
    if not candidate_ids:
        return
    from services.slot_datasets.annotation_candidates import _load_items, _save_items

    units = [item for item in (session.get("units") or []) if isinstance(item, dict)]
    candidate_units = _candidate_units_of(session)
    status_by_cid: dict[str, str] = {}
    for cand in candidate_units:
        cid = _norm(cand.get("annotation_candidate_id"))
        if not cid:
            continue
        status_by_cid[cid] = "holdout" if _is_holdout_role(_unit_role(cand, candidate_units)) else "approved"
        if units:
            matched = next((item for item in units if _norm(item.get("unit_key")) == _norm(cand.get("unit_key"))), None)
            if matched is not None:
                status_by_cid[cid] = "holdout" if _is_holdout_role(_unit_role(matched, candidate_units)) else "approved"

    wanted = set(candidate_ids)
    items = _load_items(slot)
    touched = False
    for item in items:
        cid = str(item.get("annotation_candidate_id") or "")
        if cid not in wanted:
            continue
        item["review_status"] = status_by_cid.get(cid, "approved")
        item["review_session_id"] = review_id
        item["review_completed_at"] = _now_iso()
        touched = True
    if touched:
        _save_items(slot, items)


def complete_review_session_and_admit(
    *,
    slot: str,
    review_id: str,
    review_repo: ReviewResultRepository,
    reviewer: str = "ui-operator",
) -> dict[str, Any]:
    """Merge boxed learning slices into daily_review ledger. Does not freeze. All units must be boxed."""
    key = str(slot or "").strip()
    if key not in _PV_PRODUCT_SLOTS:
        raise SlotDatasetError("invalid_slot", f"complete-and-admit only supports pv_day/pv_point, got {key!r}")
    assert_product_slot(key)

    service = ReviewSessionService(slot=key, review_repo=review_repo)
    session = service.get_session(review_id)
    if not session:
        raise SlotDatasetError("review_not_found", f"review session {review_id!r} not found")

    existing = session.get("cumulative_admission") or {}
    if isinstance(existing, dict) and (existing.get("completed") or existing.get("dataset_version_id")):
        return {
            "review_id": review_id,
            "slot": key,
            "idempotent_replay": True,
            **existing,
        }

    labels = [item for item in (session.get("freeform_labels") or []) if isinstance(item, dict)]
    units = [item for item in (session.get("units") or []) if isinstance(item, dict)]
    candidate_units = _candidate_units_of(session)

    if units:
        missing = _unboxed_unit_keys(units, labels)
        if missing:
            preview = ", ".join(missing[:8])
            extra = f" 等 {len(missing)} 条" if len(missing) > 8 else ""
            raise SlotDatasetError(
                "incomplete_review",
                f"尚有未框选的检测单元，无法完成纳入：{preview}{extra}",
            )
    elif not labels:
        raise SlotDatasetError("no_freeform_labels", "会话尚无框选标注，无法纳入累计训练集")

    learning_labels = [
        item for item in labels if not _label_is_holdout(item, units, candidate_units)
    ]
    holdout_labels = [item for item in labels if item not in learning_labels]

    completed_at = _now_iso()
    admission: dict[str, Any] = {
        "completed": True,
        "reviewed_at": completed_at,
        "source": SOURCE_DAILY_REVIEW,
        "freeform_label_count": len(labels),
        "learning_label_count": len(learning_labels),
        "holdout_label_count": len(holdout_labels),
        "dataset_version_id": None,
        "file_path": None,
        "row_count": 0,
        "freeze": None,
    }

    if learning_labels:
        merged_abs, merged_rows = _merge_freeform_slices(review_id, learning_labels)
        merged_rel = _relative_backend_path(merged_abs)
        ledger = admit_labeled_file_to_cumulative(
            slot=key,
            file_path=merged_rel,
            source=SOURCE_DAILY_REVIEW,
            reviewed_at=completed_at,
            reviewer=reviewer,
            name=f"审核完成 · {review_id}",
            freeze=False,
        )
        admission.update(
            {
                "dataset_version_id": ledger.get("dataset_version_id"),
                "file_path": merged_rel,
                "row_count": merged_rows,
                "freeze": ledger.get("freeze"),
            }
        )
    else:
        admission["skipped"] = True
        admission["reason"] = "holdout_only"

    session["cumulative_admission"] = admission
    session["status"] = "reviewed"
    session["review_completed_at"] = completed_at
    review_repo.save_verdict(key, review_id, session)
    _mark_candidates_completed(key, session, review_id=review_id)

    return {
        "review_id": review_id,
        "slot": key,
        "idempotent_replay": False,
        **admission,
    }
