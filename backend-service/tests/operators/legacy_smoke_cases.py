# @AI_GENERATED
"""
P4 Legacy Wave L1 — 烟测用例表（数据源 + 预处理 + 核心特征）。

供 test_legacy_operators_smoke.py / test_legacy_batch_coverage.py 复用。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEGACY_WAVE_L1 = frozenset({
    "load_csv", "handle_missing", "detect_outliers", "row_filter",
    "label_encode", "merge_label", "time_window_split",
    "create_lag_features", "extract_time_features", "rolling_statistics", "diff_features",
})

P4_NEW_OPERATORS = frozenset({"ks_test"})


def _ts_df(n: int = 48) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=n, freq="h")
    vals = np.sin(np.arange(n) / 6.0) * 5 + 10
    vals[5] = np.nan
    return pd.DataFrame({"record_time": ts, "value": vals, "device_id": ["d1"] * n})


def _make_tmp_csv(tmp_path) -> str:
    p = tmp_path / "legacy_smoke.csv"
    _ts_df(30).to_csv(p, index=False)
    return str(p)


def _pv_merge_source_label():
    ts = pd.date_range("2024-01-01", periods=20, freq="h")
    src = pd.DataFrame({
        "device_id": ["d1"] * 20,
        "time": ts,
        "value": np.linspace(1, 2, 20),
    })
    lbl = pd.DataFrame({
        "device_id": ["d1"] * 2,
        "time": [ts[0], ts[10]],
        "custom_label_id": [0, 1],
    })
    return src, lbl


# (op_id, params_builder, inputs_builder, expected_keys, extra_asserts)
# extra_asserts 在 smoke 文件里绑定 _output_is_dataframe 等

def legacy_wave_l1_smoke_specs():
    """返回 L1 波 smoke 规格（不含 extra_asserts 函数引用）。"""
    return [
        (
            "load_csv",
            lambda tp: {"file_path": _make_tmp_csv(tp), "timestamp_column": "record_time"},
            lambda _tp: {},
            ["data"],
            "dataframe",
        ),
        (
            "handle_missing",
            lambda _tp: {"time_field": "record_time", "target_column": "value", "method": "linear"},
            lambda _tp: {"data": _ts_df(40)},
            ["data"],
            "dataframe",
        ),
        (
            "detect_outliers",
            lambda _tp: {"target_column": "value", "method": "zscore", "window": 12, "threshold": 3.0},
            lambda _tp: {"data": _ts_df(40).ffill()},
            ["data", "outlier_indices"],
            "dataframe",
        ),
        (
            "row_filter",
            lambda _tp: {"column_filters": {"device_id": "d1"}},
            lambda _tp: {"data": _ts_df(20)},
            ["data"],
            "dataframe",
        ),
        (
            "label_encode",
            lambda _tp: {"mode": "encode", "label_col": "label", "label_map": '{"a": 0, "b": 1}'},
            lambda _tp: {"data": pd.DataFrame({"label": ["a", "b", "a", "c"]})},
            ["data"],
            "dataframe",
        ),
        (
            "merge_label",
            lambda _tp: {"id_fields": ["device_id"], "time_field": "time", "label_col": "custom_label_id"},
            lambda _tp: dict(zip(["source_data", "label_data"], _pv_merge_source_label())),
            ["data"],
            "dataframe",
        ),
        (
            "time_window_split",
            lambda _tp: {"window": "1d", "time_field": "time", "id_fields": ["device_id"]},
            lambda _tp: {
                "data": pd.DataFrame({
                    "device_id": ["d1"] * 48,
                    "time": pd.date_range("2024-01-01", periods=48, freq="h"),
                    "value": np.arange(48, dtype=float),
                }),
            },
            ["data"],
            "dataframe",
        ),
        (
            "create_lag_features",
            lambda _tp: {"target_column": "value", "lags": [1, 2]},
            lambda _tp: {"data": _ts_df(30).bfill()},
            ["data"],
            "dataframe",
        ),
        (
            "extract_time_features",
            lambda _tp: {"timestamp_column": "record_time", "features": ["hour", "dayofweek"]},
            lambda _tp: {"data": _ts_df(24)},
            ["data"],
            "dataframe",
        ),
        (
            "rolling_statistics",
            lambda _tp: {"target_column": "value", "window_sizes": [3, 6], "statistics": ["mean"]},
            lambda _tp: {"data": _ts_df(30).bfill()},
            ["data"],
            "dataframe",
        ),
        (
            "diff_features",
            lambda _tp: {"target_column": "value", "diff_periods": [1]},
            lambda _tp: {"data": _ts_df(30).bfill()},
            ["data"],
            "dataframe",
        ),
        (
            "ks_test",
            lambda _tp: {"alpha": 0.05},
            lambda _tp: {
                "sample_a": list(np.random.RandomState(0).randn(50)),
                "sample_b": list(np.random.RandomState(1).randn(50) + 0.5),
            },
            ["statistic", "pvalue", "drift_detected"],
            "ks_test",
        ),
    ]
# @AI_GENERATED: end
