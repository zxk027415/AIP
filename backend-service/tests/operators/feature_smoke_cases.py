# @AI_GENERATED
"""
P4-β 特征工程波 — 烟测用例表。

供 test_feature_operators_smoke.py / test_feature_batch_coverage.py 复用。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

P4_BETA_FE = frozenset({
    "shift_features",
    "pct_change_features",
    "peak_valley_features",
    "workday_features",
    "holiday_features",
    "extract_statistical_features",
    "ts_comparison_features",
    "sliding_window",
    "feature_select",
})


def _ts_df(n: int = 48) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=n, freq="h")
    vals = np.sin(np.arange(n) / 6.0) * 5 + 10
    return pd.DataFrame({"record_time": ts, "value": vals, "device_id": ["d1"] * n})


def _comparison_df() -> pd.DataFrame:
    n = 32
    ts = pd.date_range("2024-01-01", periods=n, freq="h")
    t = np.arange(n, dtype=float)
    return pd.DataFrame({
        "device_id": ["d1"] * n,
        "record_time": ts,
        "value_a": np.sin(t / 4.0) + 1.0,
        "value_b": np.cos(t / 4.0) + 1.0,
    })


def _feature_select_df() -> pd.DataFrame:
    rng = np.random.RandomState(42)
    df = pd.DataFrame(rng.randn(80, 6), columns=[f"f{i}" for i in range(6)])
    df["label"] = (rng.rand(80) > 0.55).astype(int)
    return df


def feature_beta_smoke_specs():
    """返回 P4-β 特征工程 smoke 规格。"""
    return [
        (
            "shift_features",
            lambda _tp: {"time_field": "record_time"},
            lambda _tp: {"data": _ts_df(24)},
            ["data"],
            "dataframe",
        ),
        (
            "pct_change_features",
            lambda _tp: {"target_column": "value", "periods": [1]},
            lambda _tp: {"data": _ts_df(30)},
            ["data"],
            "dataframe",
        ),
        (
            "peak_valley_features",
            lambda _tp: {"time_field": "record_time"},
            lambda _tp: {"data": _ts_df(24)},
            ["data"],
            "dataframe",
        ),
        (
            "workday_features",
            lambda _tp: {"time_field": "record_time"},
            lambda _tp: {"data": _ts_df(48)},
            ["data"],
            "dataframe",
        ),
        (
            "holiday_features",
            lambda _tp: {"time_field": "record_time", "remove_spring_festival": False},
            lambda _tp: {"data": _ts_df(48)},
            ["data"],
            "dataframe",
        ),
        (
            "extract_statistical_features",
            lambda _tp: {
                "target_column": "value",
                "source_column": "value",
                "mode": "expanding",
                "statistics": ["mean", "std"],
                "period": 12,
            },
            lambda _tp: {"data": _ts_df(40)},
            ["data"],
            "dataframe",
        ),
        (
            "ts_comparison_features",
            lambda _tp: {
                "id_fields": ["device_id"],
                "value_fields": ["value_a", "value_b"],
                "options": {"compute_correlation": True, "compute_distance": False, "compute_regression": True},
            },
            lambda _tp: {"data": _comparison_df()},
            ["data"],
            "dataframe",
        ),
        (
            "sliding_window",
            lambda _tp: {"window_size": 12, "step": 2, "target_column": "value"},
            lambda _tp: {"data": _ts_df(36)},
            ["data"],
            "dataframe",
        ),
        (
            "feature_select",
            lambda _tp: {"method": "mutual_info", "k": 3, "target_col": "label"},
            lambda _tp: {"data": _feature_select_df()},
            ["selected_features", "feature_list", "target"],
            "feature_select",
        ),
    ]
# @AI_GENERATED: end
