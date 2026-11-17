# @AI_GENERATED
"""
P4-β 特征工程 — L6 真实数据 e2e。

威海负荷 CSV + 光伏 train_small.parquet
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
_AIP_ROOT = os.path.dirname(_BACKEND_DIR)

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

WEIHAI_CSV = os.path.join(
    _AIP_ROOT, "load_forecast_refactored", "datasets", "load_true_weihai_260415.csv",
)
FAULT_TRAIN = os.path.join(
    _AIP_ROOT, "fault-diag-algo-release-3.1", "enos_fault_diag", "test", "train_small.parquet",
)

from services.operator_execution.router import OperatorRouter


@pytest.fixture(scope="session")
def router():
    r = OperatorRouter()
    r.auto_discover(os.path.join(_BACKEND_DIR, "services", "operator_backends"))
    return r


@pytest.fixture(scope="module")
def weihai_df(router):
    if not os.path.exists(WEIHAI_CSV):
        pytest.skip("weihai csv missing")
    r = router.execute("load_csv", {"file_path": WEIHAI_CSV, "delimiter": ","}, {})
    df = r["data"]
    sub = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
    sub["record_time"] = pd.to_datetime(sub["record_time"])
    return sub.sort_values("record_time").head(600).reset_index(drop=True)


@pytest.fixture(scope="module")
def pv_df():
    if not os.path.exists(FAULT_TRAIN):
        pytest.skip("train_small missing")
    return pd.read_parquet(FAULT_TRAIN).head(1500).copy()


@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai missing")
class TestFeatureLoadForecastRealdata:
    def test_shift_features_weihai(self, router, weihai_df):
        r = router.execute("shift_features", {"time_field": "record_time"}, {"data": weihai_df.copy()})
        assert "shift_label" in r["data"].columns

    def test_pct_change_weihai(self, router, weihai_df):
        df = weihai_df[["record_time", "value"]].copy()
        r = router.execute(
            "pct_change_features", {"target_column": "value", "periods": [1, 24]}, {"data": df},
        )
        assert "value_pct_change_1" in r["data"].columns

    def test_peak_valley_weihai(self, router, weihai_df):
        r = router.execute("peak_valley_features", {"time_field": "record_time"}, {"data": weihai_df.copy()})
        assert "peak_valley_flag" in r["data"].columns

    def test_workday_holiday_weihai(self, router, weihai_df):
        w = router.execute("workday_features", {"time_field": "record_time"}, {"data": weihai_df.copy()})
        h = router.execute("holiday_features", {"time_field": "record_time"}, {"data": weihai_df.copy()})
        assert "is_workday" in w["data"].columns
        assert "is_holiday" in h["data"].columns

    def test_sliding_window_weihai(self, router, weihai_df):
        df = weihai_df[["record_time", "value"]].copy()
        r = router.execute(
            "sliding_window", {"window_size": 24, "step": 6, "target_column": "value"}, {"data": df},
        )
        assert len(r["data"]) < len(df)

    def test_extract_statistical_weihai(self, router, weihai_df):
        df = weihai_df[["record_time", "value"]].copy()
        r = router.execute(
            "extract_statistical_features",
            {"target_column": "value", "mode": "expanding", "statistics": ["mean"]},
            {"data": df},
        )
        assert any("hist_mean" in c for c in r["data"].columns)


@pytest.mark.skipif(not os.path.exists(FAULT_TRAIN), reason="pv missing")
class TestFeaturePvFaultRealdata:
    def test_ts_comparison_pv(self, router, pv_df):
        df = pv_df.copy()
        df["value_b"] = df["value"] * 0.9 + df["i_cal"] * 0.1
        r = router.execute(
            "ts_comparison_features",
            {
                "id_fields": ["device_id"],
                "value_fields": ["value", "value_b"],
                "options": {"compute_distance": False},
            },
            {"data": df},
        )
        assert isinstance(r["data"], pd.DataFrame)

    def test_feature_select_pv(self, router, pv_df):
        df = pv_df[["value", "i_cal"]].copy()
        df["value_lag"] = df["value"].shift(1)
        df["i_ratio"] = df["i_cal"] / (df["value"].abs() + 1e-6)
        df = df.dropna().head(400)
        df["label"] = (df["value"] > df["value"].median()).astype(int)
        r = router.execute(
            "feature_select",
            {"method": "f_test", "k": 2, "target_col": "label"},
            {"data": df},
        )
        assert len(r["feature_list"]) == 2
# @AI_GENERATED: end
