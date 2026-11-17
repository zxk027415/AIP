# @AI_GENERATED
"""Preflight the real pv_tsc freeze for ten strict splits without fitting models.

Run from backend-service with PYTHONPATH=. so every project path remains relative.
The report is written under ../output/pv_e2e_validation/. The template defaults
are checked first; if sparse coverage makes them infeasible, this script searches
only strict alternatives while retaining ten repeats and min_test_samples=30.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from services.iterative_labeling.tsc.tsc_strict_eval import (
    StrictEvalConfig,
    _isolation_report,
    _make_split,
    _window_start_dates,
)
from services.operator_backends.load_csv import execute as load_data
from services.operator_backends.tsc_sliding_window import execute as make_grid

FREEZE_PATH = Path(
    "data/slot_datasets/pv_tsc/snapshots/"
    "snap-pv_tsc-20260904-100046-981f.parquet"
)
REPORT_PATH = Path("../output/pv_e2e_validation/tsc_strict10_preflight.json")
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
DEFAULT_HELD_DEVICE_RATIO = 0.3
DEFAULT_N_TEST_DAYS = 3
HELD_DEVICE_RATIO_CANDIDATES = (0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7)
N_TEST_DAYS_CANDIDATES = (3, 4, 5, 7)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _config(held_device_ratio: float, n_test_days: int) -> StrictEvalConfig:
    return StrictEvalConfig(
        split_mode="strict",
        n_repeats=10,
        held_device_ratio=held_device_ratio,
        n_test_days=n_test_days,
        base_seed=90,
        min_test_samples=30,
        require_isolation=True,
    )


def _inspect_splits(
    X: np.ndarray,
    y: np.ndarray,
    meta: Any,
    dates: np.ndarray,
    config: StrictEvalConfig,
    *,
    check_isolation: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in range(config.base_seed, config.base_seed + config.n_repeats):
        split = _make_split(y, meta, dates, config, seed)
        if split is None:
            rows.append({"seed": seed, "ready": False, "reason": "insufficient_dates"})
            continue
        train_idx, test_idx = split
        train_classes = sorted(int(value) for value in np.unique(y[train_idx]))
        test_classes = sorted(int(value) for value in np.unique(y[test_idx]))
        isolation = (
            _isolation_report(
                X,
                meta,
                train_idx,
                test_idx,
                dates,
                config.split_mode,
            )
            if check_isolation
            else None
        )
        ready = bool(
            len(test_idx) >= config.min_test_samples
            and len(train_classes) >= 2
            and len(test_classes) >= 2
            and (not check_isolation or bool((isolation or {}).get("clean")))
        )
        reasons: list[str] = []
        if len(test_idx) < config.min_test_samples:
            reasons.append("test_samples_below_30")
        if len(train_classes) < 2:
            reasons.append("train_has_fewer_than_2_classes")
        if len(test_classes) < 2:
            reasons.append("test_has_fewer_than_2_classes")
        if check_isolation and not bool((isolation or {}).get("clean")):
            reasons.append("isolation_not_clean")
        rows.append(
            {
                "seed": seed,
                "ready": ready,
                "reasons": reasons,
                "n_train": int(len(train_idx)),
                "n_test": int(len(test_idx)),
                "train_classes": train_classes,
                "test_classes": test_classes,
                "isolation": isolation,
            }
        )
    return rows


def _all_ready(rows: list[dict[str, Any]]) -> bool:
    return len(rows) == 10 and all(row.get("ready") is True for row in rows)


def _config_payload(config: StrictEvalConfig) -> dict[str, Any]:
    return {
        "split_mode": config.split_mode,
        "n_repeats": config.n_repeats,
        "held_device_ratio": config.held_device_ratio,
        "n_test_days": config.n_test_days,
        "base_seed": config.base_seed,
        "min_test_samples": config.min_test_samples,
        "require_isolation": config.require_isolation,
    }


def main() -> None:
    started = time.time()
    if not FREEZE_PATH.is_file():
        raise FileNotFoundError(f"real freeze not found: {FREEZE_PATH.as_posix()}")

    loaded = load_data(
        {"file_path": FREEZE_PATH.as_posix(), "time_field": "time"},
        {},
    )["data"]
    raw_rows = int(len(loaded))
    raw_columns = [str(column) for column in loaded.columns]

    samples = make_grid(GRID_PARAMS, {"data": loaded})["samples"]
    X = np.asarray(samples["X"], dtype=np.float32)
    y = np.asarray(samples["y"]).reshape(-1)
    meta = samples["meta"]
    load_stats = dict(samples.get("load_stats") or {})

    assert X.ndim == 3 and tuple(X.shape[1:]) == (288, 3), X.shape
    assert list(samples.get("channels") or []) == ["value", "i_cal", "is_measured"]
    assert set(np.unique(X[:, :, 2]).tolist()).issubset({0.0, 1.0})
    assert len(X) == len(y) == len(meta)

    dates = _window_start_dates(meta)
    default_config = _config(DEFAULT_HELD_DEVICE_RATIO, DEFAULT_N_TEST_DAYS)
    default_rows = _inspect_splits(
        X,
        y,
        meta,
        dates,
        default_config,
        check_isolation=True,
    )

    feasibility: list[dict[str, Any]] = []
    for n_test_days in N_TEST_DAYS_CANDIDATES:
        for held_device_ratio in HELD_DEVICE_RATIO_CANDIDATES:
            candidate = _config(held_device_ratio, n_test_days)
            rows = _inspect_splits(
                X,
                y,
                meta,
                dates,
                candidate,
                check_isolation=False,
            )
            feasibility.append(
                {
                    "config": _config_payload(candidate),
                    "n_ready": sum(row.get("ready") is True for row in rows),
                    "min_n_test": min(
                        (int(row.get("n_test") or 0) for row in rows),
                        default=0,
                    ),
                    "all_ready_before_isolation_check": _all_ready(rows),
                }
            )

    feasible = [
        row for row in feasibility if row["all_ready_before_isolation_check"] is True
    ]
    feasible.sort(
        key=lambda row: (
            abs(float(row["config"]["held_device_ratio"]) - DEFAULT_HELD_DEVICE_RATIO)
            + 0.05 * abs(int(row["config"]["n_test_days"]) - DEFAULT_N_TEST_DAYS),
            int(row["config"]["n_test_days"]),
            float(row["config"]["held_device_ratio"]),
        )
    )

    selected_config = default_config
    selected_rows = default_rows
    selection_reason = "template_defaults_ready"
    if not _all_ready(default_rows) and feasible:
        selected = feasible[0]["config"]
        selected_config = _config(
            float(selected["held_device_ratio"]),
            int(selected["n_test_days"]),
        )
        selected_rows = _inspect_splits(
            X,
            y,
            meta,
            dates,
            selected_config,
            check_isolation=True,
        )
        selection_reason = "minimal_strict_alternative_for_sparse_real_freeze"

    selected_ready = _all_ready(selected_rows)
    status = (
        "passed_default"
        if _all_ready(default_rows)
        else "passed_strict_alternative"
        if selected_ready
        else "failed_no_strict10_configuration"
    )
    report = {
        "status": status,
        "scope": "real_pv_tsc_freeze_strict10_split_preflight_without_model_fit",
        "freeze_path": FREEZE_PATH.as_posix(),
        "freeze_sha256": _sha256(FREEZE_PATH),
        "raw_rows": raw_rows,
        "raw_columns": raw_columns,
        "sample_shape": [int(value) for value in X.shape],
        "sample_count": int(len(y)),
        "class_distribution": {
            str(label): int(count)
            for label, count in zip(*np.unique(y, return_counts=True))
        },
        "grid_stats": load_stats,
        "template_default": {
            "config": _config_payload(default_config),
            "n_ready": sum(row.get("ready") is True for row in default_rows),
            "all_ready": _all_ready(default_rows),
            "splits": default_rows,
        },
        "feasibility_search": feasibility,
        "selected": {
            "selection_reason": selection_reason,
            "config": _config_payload(selected_config),
            "n_ready": sum(row.get("ready") is True for row in selected_rows),
            "all_ready": selected_ready,
            "splits": selected_rows,
        },
        "elapsed_sec": round(time.time() - started, 3),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_jsonable),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": status,
                "template_default_ready": report["template_default"]["n_ready"],
                "selected_config": report["selected"]["config"],
                "selected_ready": report["selected"]["n_ready"],
                "report": REPORT_PATH.as_posix(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if not selected_ready:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
