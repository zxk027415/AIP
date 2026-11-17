# @AI_GENERATED
"""Profile the real pv_tsc cumulative freeze to explain its date coverage.

Run from backend-service with PYTHONPATH=. Read-only: it only reads the freeze
and writes a JSON report under ../output/pv_e2e_validation/.

Answers three questions with measurements instead of inherited comments:
  1. How many distinct days does the freeze actually contain, and what is the span?
  2. Why does the template split (n_test_days=3) yield too few test samples?
  3. What is the structural ceiling of macro_f1 given the label space used?
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.iterative_labeling.tsc.tsc_strict_eval import (
    StrictEvalConfig,
    _make_split,
    _window_start_dates,
)
from services.operator_backends.load_csv import execute as load_data
from services.operator_backends.tsc_sliding_window import execute as make_grid

FREEZE_PATH = Path(
    "data/slot_datasets/pv_tsc/snapshots/"
    "snap-pv_tsc-20260904-100046-981f.parquet"
)
REPORT_PATH = Path("../output/pv_e2e_validation/tsc_freeze_profile.json")
GRID_PARAMS: dict[str, Any] = {
    "representation": "clock_grid_288_mask",
    "window_length": 288,
    "channels": ["value", "i_cal", "is_measured"],
    "series_keys": ["site_id", "device_id", "branch_id"],
    "purity_threshold": 0.7,
    "min_occupied_slots": 173,
    "min_daytime_occupancy": 0.8,
    "max_daytime_gap_slots": 6,
    "require_all_hours_covered": True,
    "preprocess_method": "per_sample_zscore",
}
USED_CONFIG = {"held_device_ratio": 0.6, "n_test_days": 5}
TEMPLATE_CONFIG = {"held_device_ratio": 0.3, "n_test_days": 3}


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _profile_raw(df: pd.DataFrame) -> dict[str, Any]:
    frame = df.copy()
    frame["time"] = pd.to_datetime(frame["time"])
    frame["date"] = frame["time"].dt.date

    dates = sorted(frame["date"].unique())
    span_days = (dates[-1] - dates[0]).days + 1 if dates else 0
    rows_per_date = frame.groupby("date").size().sort_index()
    devices_per_date = frame.groupby("date")["device_id"].nunique().sort_index()

    series = frame[["site_id", "device_id", "branch_id"]].astype(str).agg("|".join, axis=1)
    frame["series_key"] = series
    raw_device_days = frame.groupby(["series_key", "date"]).size()
    dates_per_series = raw_device_days.reset_index().groupby("series_key")["date"].nunique()

    extra: dict[str, Any] = {}
    for column in ("tsc_target_day", "time_window", "_dataset_version_id"):
        if column in frame.columns:
            counts = frame[column].astype(str).value_counts()
            extra[column] = {
                "n_distinct": int(counts.size),
                "top": {str(k): int(v) for k, v in counts.head(12).items()},
            }
    if "tsc_target_day" in frame.columns:
        target_days = pd.to_datetime(frame["tsc_target_day"], errors="coerce").dt.date
        aligned = int((target_days == frame["date"]).sum())
        extra["tsc_target_day_equals_row_date_rows"] = aligned
        extra["tsc_target_day_distinct_days"] = int(target_days.dropna().nunique())

    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns if column not in {"date", "series_key"}],
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "n_distinct_dates": len(dates),
        "calendar_span_days": span_days,
        "date_coverage_ratio": round(len(dates) / span_days, 4) if span_days else None,
        "all_dates": dates,
        "n_sites": int(frame["site_id"].nunique()),
        "n_devices": int(frame["device_id"].nunique()),
        "n_series_keys": int(frame["series_key"].nunique()),
        "raw_device_days": int(len(raw_device_days)),
        "theoretical_device_days_if_dense": int(frame["series_key"].nunique() * len(dates)),
        "dates_per_series": {
            "mean": round(float(dates_per_series.mean()), 3),
            "median": float(dates_per_series.median()),
            "min": int(dates_per_series.min()),
            "max": int(dates_per_series.max()),
            "histogram": {
                str(k): int(v)
                for k, v in sorted(Counter(dates_per_series.tolist()).items())
            },
        },
        "rows_per_date": {str(k): int(v) for k, v in rows_per_date.items()},
        "devices_per_date": {str(k): int(v) for k, v in devices_per_date.items()},
        "label_distribution": {
            str(k): int(v) for k, v in frame["label"].value_counts(dropna=False).items()
        },
        "extra_columns": extra,
    }


def _profile_grid(y: np.ndarray, meta: pd.DataFrame) -> dict[str, Any]:
    dates = _window_start_dates(meta)
    frame = pd.DataFrame(
        {
            "date": dates,
            "device_id": meta["device_id"].astype(str).values,
            "label": y,
        }
    )
    per_date = frame.groupby("date").agg(
        samples=("label", "size"),
        devices=("device_id", "nunique"),
        classes=("label", "nunique"),
    )
    ordered = sorted(frame["date"].unique())
    return {
        "samples": int(len(y)),
        "n_distinct_dates": len(ordered),
        "date_min": ordered[0] if ordered else None,
        "date_max": ordered[-1] if ordered else None,
        "n_devices": int(frame["device_id"].nunique()),
        "n_classes": int(len(np.unique(y))),
        "samples_per_date": {str(k): int(v) for k, v in per_date["samples"].items()},
        "devices_per_date": {str(k): int(v) for k, v in per_date["devices"].items()},
        "classes_per_date": {str(k): int(v) for k, v in per_date["classes"].items()},
        "last_5_dates": [str(value) for value in ordered[-5:]],
        "samples_in_last_3_dates": int(frame["date"].isin(ordered[-3:]).sum()),
        "samples_in_last_5_dates": int(frame["date"].isin(ordered[-5:]).sum()),
        "class_distribution": {
            str(label): int(count)
            for label, count in zip(*np.unique(y, return_counts=True))
        },
    }


def _split_ceiling(
    X: np.ndarray,
    y: np.ndarray,
    meta: pd.DataFrame,
    held_device_ratio: float,
    n_test_days: int,
) -> dict[str, Any]:
    """Quantify how the fixed 13-label macro average caps achievable macro_f1."""
    n_labels_full = int(len(np.unique(y)))
    config = StrictEvalConfig(
        split_mode="strict",
        n_repeats=10,
        held_device_ratio=held_device_ratio,
        n_test_days=n_test_days,
        base_seed=90,
        min_test_samples=30,
        require_isolation=True,
    )
    dates = _window_start_dates(meta)
    rows: list[dict[str, Any]] = []
    for seed in range(90, 100):
        split = _make_split(y, meta, dates, config, seed)
        if split is None:
            rows.append({"seed": seed, "usable": False, "reason": "insufficient_dates"})
            continue
        train_idx, test_idx = split
        test_classes = sorted(int(value) for value in np.unique(y[test_idx]))
        n_test_classes = len(test_classes)
        rows.append(
            {
                "seed": seed,
                "usable": bool(len(test_idx) >= config.min_test_samples and n_test_classes >= 2),
                "n_train": int(len(train_idx)),
                "n_test": int(len(test_idx)),
                "n_test_classes": n_test_classes,
                "test_classes": test_classes,
                "macro_f1_ceiling_if_perfect": round(n_test_classes / n_labels_full, 4)
                if n_labels_full
                else None,
                "balanced_accuracy_chance_level": round(1.0 / n_test_classes, 4)
                if n_test_classes
                else None,
                "train_coverage_of_dataset": round(len(train_idx) / len(y), 4),
            }
        )
    usable = [row for row in rows if row.get("usable")]
    ceilings = [
        row["macro_f1_ceiling_if_perfect"]
        for row in usable
        if row.get("macro_f1_ceiling_if_perfect") is not None
    ]
    chances = [
        row["balanced_accuracy_chance_level"]
        for row in usable
        if row.get("balanced_accuracy_chance_level") is not None
    ]
    return {
        "config": {
            "held_device_ratio": held_device_ratio,
            "n_test_days": n_test_days,
            "min_test_samples": 30,
            "n_labels_in_macro_average": n_labels_full,
        },
        "n_usable_splits": len(usable),
        "mean_macro_f1_ceiling": round(float(np.mean(ceilings)), 4) if ceilings else None,
        "mean_balanced_accuracy_chance": round(float(np.mean(chances)), 4) if chances else None,
        "splits": rows,
    }


def main() -> None:
    assert FREEZE_PATH.is_file(), FREEZE_PATH.as_posix()
    loaded = load_data({"file_path": FREEZE_PATH.as_posix(), "time_field": "time"}, {})["data"]
    raw_profile = _profile_raw(loaded)

    samples = make_grid(GRID_PARAMS, {"data": loaded})["samples"]
    X = np.asarray(samples["X"], dtype=np.float32)
    y = np.asarray(samples["y"]).reshape(-1)
    meta = samples["meta"]
    grid_profile = _profile_grid(y, meta)
    grid_profile["grid_skip_reasons"] = dict(samples.get("load_stats") or {})

    report = {
        "freeze_path": FREEZE_PATH.as_posix(),
        "raw_freeze": raw_profile,
        "grid_dataset": grid_profile,
        "grid_retention_ratio": round(
            grid_profile["samples"] / raw_profile["raw_device_days"], 4
        )
        if raw_profile["raw_device_days"]
        else None,
        "template_split_analysis": _split_ceiling(
            X, y, meta, TEMPLATE_CONFIG["held_device_ratio"], TEMPLATE_CONFIG["n_test_days"]
        ),
        "used_split_analysis": _split_ceiling(
            X, y, meta, USED_CONFIG["held_device_ratio"], USED_CONFIG["n_test_days"]
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_jsonable),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "rows": raw_profile["rows"],
                "n_distinct_dates": raw_profile["n_distinct_dates"],
                "date_min": str(raw_profile["date_min"]),
                "date_max": str(raw_profile["date_max"]),
                "calendar_span_days": raw_profile["calendar_span_days"],
                "n_series_keys": raw_profile["n_series_keys"],
                "raw_device_days": raw_profile["raw_device_days"],
                "grid_samples": grid_profile["samples"],
                "grid_dates": grid_profile["n_distinct_dates"],
                "samples_in_last_3_dates": grid_profile["samples_in_last_3_dates"],
                "template_usable_splits": report["template_split_analysis"]["n_usable_splits"],
                "used_mean_macro_f1_ceiling": report["used_split_analysis"]["mean_macro_f1_ceiling"],
                "used_mean_balanced_acc_chance": report["used_split_analysis"][
                    "mean_balanced_accuracy_chance"
                ],
                "report": REPORT_PATH.as_posix(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
