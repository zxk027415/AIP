"""Export gold labeled tables into backend-service so they can enter the cumulative ledger.

Day gold is the full all_labeled_combined parquet (not an 800-row sample).
Point gold is the realtime-point POC snapshot with cluster / human_range / point_rest_normal
(K4 companion) labels joined onto measurements. Day labels are not broadcast.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from services.slot_datasets.labeled_versions import list_labeled_versions
from services.slot_datasets.review_admission import admit_labeled_file_to_cumulative
from services.slot_datasets.snapshots import (
    SOURCE_PATH_A,
    get_cumulative_ledger,
    include_labeled_version_in_cumulative,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_DIR = _BACKEND_DIR.parent

DAY_GOLD_REL = "data/slot_datasets/pv_day/gold/all_labeled_combined.parquet"
POINT_GOLD_REL = "data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet"
POINT_POC_REL = "data/realtime_point_poc/snapshots/point-poc-20260821044728-684bf7f6"
_JOIN_KEYS = ["site_id", "device_id", "branch_id", "time"]

_DAY_SRC_CANDIDATES = [
    _PROJECT_DIR / "fault-diag-algo-release-3.1" / "relate_data" / "all_labeled_combined.parquet",
    _PROJECT_DIR / "fault-diag-algo-release-3.1" / "相关数据" / "all_labeled_combined.parquet",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_time(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    except (TypeError, ValueError):
        return pd.to_datetime(series, errors="coerce", utc=True)


def export_day_gold(*, overwrite: bool = True) -> dict[str, Any]:
    src = next((path for path in _DAY_SRC_CANDIDATES if path.is_file()), None)
    if src is None:
        raise FileNotFoundError("all_labeled_combined.parquet not found under fault-diag-algo-release-3.1")
    dest = _BACKEND_DIR / DAY_GOLD_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    if overwrite or not dest.is_file():
        shutil.copy2(src, dest)
    rows = int(pd.read_parquet(dest, columns=["label"]).shape[0])
    return {
        "slot": "pv_day",
        "file_path": DAY_GOLD_REL,
        "source_name": src.name,
        "rows": rows,
    }


def export_point_gold(*, overwrite: bool = True) -> dict[str, Any]:
    snap = _BACKEND_DIR / POINT_POC_REL
    meas_path = snap / "measurements.parquet"
    labels_path = snap / "point_labels.parquet"
    if not meas_path.is_file() or not labels_path.is_file():
        raise FileNotFoundError(f"point POC snapshot missing under {POINT_POC_REL}")
    dest = _BACKEND_DIR / POINT_GOLD_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and not overwrite:
        labeled = pd.read_parquet(dest, columns=["label"])
        return {
            "slot": "pv_point",
            "file_path": POINT_GOLD_REL,
            "rows": int(len(labeled)),
            "labeled_rows": int(labeled["label"].notna().sum()),
            "skipped": True,
        }

    meas = pd.read_parquet(meas_path)
    labels = pd.read_parquet(labels_path)
    meas["time"] = _normalize_time(meas["time"])
    labels["time"] = _normalize_time(labels["time"])
    keep = [col for col in (*_JOIN_KEYS, "label_id", "source") if col in labels.columns]
    lab = labels[keep].rename(columns={"label_id": "label"})
    lab = lab.drop_duplicates(subset=_JOIN_KEYS, keep="last")
    out = meas.merge(lab, on=_JOIN_KEYS, how="left")
    out["label"] = pd.to_numeric(out["label"], errors="coerce")
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(dest, index=False)
    return {
        "slot": "pv_point",
        "file_path": POINT_GOLD_REL,
        "rows": int(len(out)),
        "labeled_rows": int(out["label"].notna().sum()),
        "sources": (
            out["source"].fillna("unlabeled").value_counts().to_dict()
            if "source" in out.columns
            else {}
        ),
    }


def _find_version_by_path(slot: str, file_path: str) -> dict[str, Any] | None:
    wanted = str(file_path or "").replace("\\", "/").strip()
    for row in list_labeled_versions(slot):
        if str(row.get("file_path") or "").replace("\\", "/").strip() == wanted:
            return dict(row)
    return None


def _admit_or_reuse(*, slot: str, file_path: str, name: str, freeze: bool) -> dict[str, Any]:
    existing = _find_version_by_path(slot, file_path)
    if existing:
        included = include_labeled_version_in_cumulative(
            slot=slot,
            dataset_version_id=str(existing["dataset_version_id"]),
            source=SOURCE_PATH_A,
            reviewed_at=_utc_now() if freeze else None,
            reviewer="gold_bootstrap",
            freeze=freeze,
        )
        return {"labeled_version": existing, "reused": True, **included}
    return admit_labeled_file_to_cumulative(
        slot=slot,
        file_path=file_path,
        source=SOURCE_PATH_A,
        reviewed_at=_utc_now(),
        reviewer="gold_bootstrap",
        name=name,
        freeze=freeze,
    )


def admit_gold_bases(*, slots: list[str] | None = None, freeze: bool = True) -> dict[str, Any]:
    wanted = [str(item).strip() for item in (slots or ["pv_day", "pv_point"])]
    exported: dict[str, Any] = {}
    admitted: dict[str, Any] = {}
    if "pv_day" in wanted:
        exported["pv_day"] = export_day_gold()
        admitted["pv_day"] = _admit_or_reuse(
            slot="pv_day",
            file_path=DAY_GOLD_REL,
            name="金标准 · 天路径全量 all_labeled_combined",
            freeze=freeze,
        )
    if "pv_point" in wanted:
        exported["pv_point"] = export_point_gold()
        admitted["pv_point"] = _admit_or_reuse(
            slot="pv_point",
            file_path=POINT_GOLD_REL,
            name="金标准 · 点路径 K4 伴生 POC 684bf7f6",
            freeze=freeze,
        )
    ledgers = {slot: get_cumulative_ledger(slot) for slot in wanted if slot in {"pv_day", "pv_point"}}
    return {"exported": exported, "admitted": admitted, "ledgers": ledgers}
