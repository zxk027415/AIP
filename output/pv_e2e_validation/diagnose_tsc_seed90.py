# @AI_GENERATED
"""Re-run strict split seed 90 and persist prediction-level diagnostics.

The production evaluator stores aggregate split metrics but not predictions.
This read-only validation reconstructs the same real freeze/grid/split and fits
one MultiRocket model to explain the low strict score without touching any
registry, candidate, cumulative state, or execution history.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

from services.iterative_labeling.tsc.model_registry import get_model
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
REPORT_PATH = Path("../output/pv_e2e_validation/tsc_seed90_diagnostics.json")
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


def _counts(values: np.ndarray) -> dict[str, int]:
    return {str(key): int(value) for key, value in sorted(Counter(values.tolist()).items())}


def main() -> None:
    started = time.time()
    loaded = load_data({"file_path": FREEZE_PATH.as_posix(), "time_field": "time"}, {})["data"]
    samples = make_grid(GRID_PARAMS, {"data": loaded})["samples"]
    X = np.asarray(samples["X"], dtype=np.float32)
    y = np.asarray(samples["y"]).reshape(-1)
    meta = samples["meta"]

    config = StrictEvalConfig(
        split_mode="strict",
        n_repeats=10,
        held_device_ratio=0.6,
        n_test_days=5,
        base_seed=90,
        min_test_samples=30,
        require_isolation=True,
    )
    dates = _window_start_dates(meta)
    split = _make_split(y, meta, dates, config, 90)
    assert split is not None
    train_idx, test_idx = split
    labels_full = sorted(int(value) for value in np.unique(y))
    labels_test = sorted(int(value) for value in np.unique(y[test_idx]))

    model = get_model("multirocket")
    model.fit(X[train_idx], y[train_idx])
    predictions = np.asarray(model.predict(X[test_idx])).reshape(-1)

    fixed_macro_f1 = float(
        f1_score(y[test_idx], predictions, average="macro", labels=labels_full, zero_division=0)
    )
    present_macro_f1 = float(
        f1_score(y[test_idx], predictions, average="macro", labels=labels_test, zero_division=0)
    )
    balanced_accuracy = float(balanced_accuracy_score(y[test_idx], predictions))
    labels_confusion = sorted(
        set(int(value) for value in y[test_idx])
        | set(int(value) for value in predictions)
    )
    report = {
        "_comment": "@AI_GENERATED",
        "status": "passed",
        "scope": "real_freeze_strict_seed90_prediction_diagnostics",
        "freeze_path": FREEZE_PATH.as_posix(),
        "config": {
            "split_mode": "strict",
            "seed": 90,
            "held_device_ratio": 0.6,
            "n_test_days": 5,
            "min_test_samples": 30,
        },
        "dataset": {
            "n_samples": int(len(y)),
            "labels_full": labels_full,
            "class_distribution": _counts(y),
        },
        "split": {
            "n_train": int(len(train_idx)),
            "n_test": int(len(test_idx)),
            "train_date_min": str(min(dates[train_idx])),
            "train_date_max": str(max(dates[train_idx])),
            "test_date_min": str(min(dates[test_idx])),
            "test_date_max": str(max(dates[test_idx])),
            "train_label_distribution": _counts(y[train_idx]),
            "test_label_distribution": _counts(y[test_idx]),
            "prediction_distribution": _counts(predictions),
            "labels_test_present": labels_test,
            "n_labels_test_present": len(labels_test),
            "macro_f1_ceiling_from_absent_classes": round(len(labels_test) / len(labels_full), 6),
        },
        "metrics": {
            "macro_f1_fixed_13_labels": round(fixed_macro_f1, 6),
            "macro_f1_present_test_labels_only": round(present_macro_f1, 6),
            "balanced_accuracy": round(balanced_accuracy, 6),
            "accuracy": round(float(accuracy_score(y[test_idx], predictions)), 6),
            "balanced_accuracy_chance_level": round(1.0 / len(labels_test), 6),
        },
        "confusion": {
            "labels": labels_confusion,
            "matrix": confusion_matrix(
                y[test_idx], predictions, labels=labels_confusion
            ).tolist(),
        },
        "classification_report_present_and_predicted_labels": classification_report(
            y[test_idx],
            predictions,
            labels=labels_confusion,
            output_dict=True,
            zero_division=0,
        ),
        "elapsed_sec": round(time.time() - started, 3),
        "governance_side_effects": False,
        "_comment_end": "@AI_GENERATED: end",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "n_train": len(train_idx),
                "n_test": len(test_idx),
                "test_distribution": report["split"]["test_label_distribution"],
                "prediction_distribution": report["split"]["prediction_distribution"],
                "macro_f1_fixed_13": report["metrics"]["macro_f1_fixed_13_labels"],
                "macro_f1_present_only": report["metrics"]["macro_f1_present_test_labels_only"],
                "balanced_accuracy": report["metrics"]["balanced_accuracy"],
                "report": REPORT_PATH.as_posix(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
