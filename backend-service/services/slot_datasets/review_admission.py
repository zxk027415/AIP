"""Admit path-A / daily-review labeled files into the slot cumulative ledger."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.slot_datasets.canvas_datasets import register_trainable_dataset
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.labeled_versions import publish_labeled_version
from services.slot_datasets.snapshots import (
    SOURCE_DAILY_REVIEW,
    SOURCE_PATH_A,
    include_labeled_version_in_cumulative,
)

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
# @AI_GENERATED: unified curated-ledger admission includes the TSC product path.
_PV_SLOTS = frozenset({"pv_day", "pv_point", "pv_tsc"})
# @AI_GENERATED: end


def _is_pv_slot(slot: str) -> bool:
    return str(slot or "").strip() in _PV_SLOTS


def _resolve_existing_file(file_path: str) -> Path:
    raw = str(file_path or "").strip().replace("\\", "/")
    if not raw:
        raise SlotDatasetError("missing_file_path", "file_path is required")
    candidates = [Path(raw), _BACKEND_DIR / raw, _BACKEND_DIR.parent / raw]
    for cand in candidates:
        if cand.is_file():
            return cand
    raise SlotDatasetError("file_not_found", f"source file not found: {raw}")


def _relative_backend_path(abs_path: Path) -> str:
    rel = os.path.relpath(str(abs_path.resolve()), start=str(_BACKEND_DIR))
    if rel.startswith(".."):
        raise SlotDatasetError("path_outside_backend", "file_path must resolve inside backend-service")
    return rel.replace("\\", "/")


def include_path_a_labeled_version(
    *,
    slot: str,
    dataset_version_id: str,
    reviewed_at: str | None = None,
    reviewer: str | None = None,
) -> dict[str, Any]:
    """Path A (clustering / proposal confirm) enters the slot cumulative ledger without freezing."""
    return include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=dataset_version_id,
        source=SOURCE_PATH_A,
        reviewed_at=reviewed_at,
        reviewer=reviewer,
        freeze=False,
    )


def admit_labeled_file_to_cumulative(
    *,
    slot: str,
    file_path: str,
    source: str,
    reviewed_at: str | None = None,
    reviewer: str | None = None,
    name: str | None = None,
    freeze: bool = False,
) -> dict[str, Any]:
    """Publish a labeled file as a confirm-box row, then include it in the cumulative ledger."""
    key = str(slot or "").strip()
    if not _is_pv_slot(key):
        raise SlotDatasetError(
            "invalid_slot", f"slot must be one of {sorted(_PV_SLOTS)!r}, got {key!r}"
        )
    abs_path = _resolve_existing_file(file_path)
    rel_path = _relative_backend_path(abs_path)
    version = publish_labeled_version(slot=key, file_path=rel_path, status="curated")
    canvas_row = register_trainable_dataset(
        dataset_id=version["dataset_version_id"],
        kind="labeled_version",
        slot=key,
        ref_id=version["dataset_version_id"],
        file_path=rel_path,
        name=name or f"{source} · {version['dataset_version_id']}",
    )
    included = include_labeled_version_in_cumulative(
        slot=key,
        dataset_version_id=version["dataset_version_id"],
        source=source,
        reviewed_at=reviewed_at,
        reviewer=reviewer,
        freeze=freeze,
    )
    return {
        "labeled_version": version,
        "canvas_row": canvas_row,
        **included,
    }


def _normalize_date_token(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.isna(parsed):
        return raw
    return parsed.strftime("%Y-%m-%d")


def _filter_unit_rows(frame: pd.DataFrame, unit_key: str) -> pd.DataFrame:
    key = str(unit_key or "").strip()
    if not key:
        return frame.iloc[0:0].copy()
    work = frame.copy()
    for col in ("entity_key", "member_key", "unit_key"):
        if col in work.columns:
            hit = work[work[col].astype(str) == key]
            if not hit.empty:
                return hit.copy()

    parts = [part for part in key.split("|") if part != ""]
    if not parts:
        return frame.iloc[0:0].copy()
    if "date" not in work.columns and "time" in work.columns:
        work["date"] = pd.to_datetime(work["time"], errors="coerce").dt.strftime("%Y-%m-%d")
    elif "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    keys = [col for col in ("site_id", "device_id", "branch_id", "date") if col in work.columns]
    if not keys:
        return frame.iloc[0:0].copy()
    n = min(len(keys), len(parts))
    mask = pd.Series(True, index=work.index)
    for col, value in zip(keys[:n], parts[:n]):
        token = _normalize_date_token(value) if col == "date" else str(value)
        series = work[col].astype(str)
        if col == "date":
            mask &= series.str.slice(0, 10) == token[:10]
        else:
            mask &= series == token
    hit = work.loc[mask].copy()
    if not hit.empty:
        return hit
    return frame.iloc[0:0].copy()


def admit_daily_review_unit(
    *,
    slot: str,
    review_id: str,
    unit_key: str,
    verdict_label: Any,
    source_csv_path: str,
    reviewed_at: str | None = None,
    reviewer: str | None = None,
) -> Optional[dict[str, Any]]:
    """Materialize one daily-review unit as a labeled CSV and include it in the slot ledger."""
    if not _is_pv_slot(slot):
        return None
    try:
        abs_path = _resolve_existing_file(source_csv_path)
    except SlotDatasetError:
        logger.warning("daily review skip: source file missing review=%s path=%s", review_id, source_csv_path)
        return None
    if abs_path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(abs_path)
    else:
        frame = pd.read_csv(abs_path)
    labeled = _filter_unit_rows(frame, unit_key)
    if labeled.empty:
        logger.warning("daily review skip: no rows for unit=%s review=%s", unit_key, review_id)
        return None
    labeled["label"] = int(verdict_label)
    safe_unit = "".join(ch if ch.isalnum() or ch in "-_|" else "_" for ch in str(unit_key))[:80]
    out_rel = f"data/slot_datasets/{slot}/review_slices/{review_id}/{safe_unit}.csv"
    out_abs = _BACKEND_DIR / out_rel
    out_abs.parent.mkdir(parents=True, exist_ok=True)
    labeled.to_csv(out_abs, index=False, encoding="utf-8")
    return admit_labeled_file_to_cumulative(
        slot=slot,
        file_path=out_rel,
        source=SOURCE_DAILY_REVIEW,
        reviewed_at=reviewed_at,
        reviewer=reviewer,
        name=f"按日回流 · {unit_key}",
        freeze=False,
    )
