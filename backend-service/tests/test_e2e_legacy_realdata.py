# @AI_GENERATED
"""
P4 Legacy Wave L1 + ks_test — L6 真实数据 e2e。

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
FAULT_LABEL = os.path.join(
    _AIP_ROOT, "fault-diag-algo-release-3.1", "enos_fault_diag", "test", "label_small.parquet",
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
    if "parent_id" in df.columns:
        df = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
    df["record_time"] = pd.to_datetime(df["record_time"])
    return df.sort_values("record_time").head(800).reset_index(drop=True)


@pytest.fixture(scope="module")
def pv_df():
    if not os.path.exists(FAULT_TRAIN):
        pytest.skip("train_small missing")
    return pd.read_parquet(FAULT_TRAIN).head(2000).copy()


@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai missing")
class TestLegacyLoadForecastRealdata:
    def test_load_csv_weihai(self, router):
        r = router.execute("load_csv", {"file_path": WEIHAI_CSV, "delimiter": ","}, {})
        assert len(r["data"]) > 100
        print("\n  [load_csv] weihai rows:", len(r["data"]))

    def test_handle_missing_weihai(self, router, weihai_df):
        df = weihai_df.copy()
        df.loc[df.index[10:15], "value"] = np.nan
        r = router.execute(
            "handle_missing",
            {"time_field": "record_time", "target_column": "value", "method": "linear"},
            {"data": df},
        )
        assert r["data"]["value"].isna().sum() == 0
        print("\n  [handle_missing] filled NaN ✓")

    def test_detect_outliers_weihai(self, router, weihai_df):
        r = router.execute(
            "detect_outliers",
            {"target_column": "value", "method": "zscore", "window": 24, "threshold": 3.0},
            {"data": weihai_df[["record_time", "value"]].copy()},
        )
        assert "outlier_indices" in r
        print("\n  [detect_outliers] outliers:", len(r["outlier_indices"]))

    def test_row_filter_weihai(self, router, weihai_df):
        r = router.execute(
            "row_filter",
            {"column_filters": {"parent_id": "park_01"}},
            {"data": weihai_df},
        )
        assert len(r["data"]) == len(weihai_df)

    def test_create_lag_features_weihai(self, router, weihai_df):
        r = router.execute(
            "create_lag_features",
            {"target_column": "value", "lags": [1, 24]},
            {"data": weihai_df[["record_time", "value"]].copy()},
        )
        assert "value_lag_1" in r["data"].columns

    def test_extract_time_features_weihai(self, router, weihai_df):
        r = router.execute(
            "extract_time_features",
            {"timestamp_column": "record_time", "features": ["hour", "dayofweek"]},
            {"data": weihai_df.copy()},
        )
        assert "hour" in r["data"].columns

    def test_rolling_statistics_weihai(self, router, weihai_df):
        r = router.execute(
            "rolling_statistics",
            {"target_column": "value", "window_sizes": [6, 24], "statistics": ["mean"]},
            {"data": weihai_df[["record_time", "value"]].copy()},
        )
        assert any("mean" in c for c in r["data"].columns)

    def test_diff_features_weihai(self, router, weihai_df):
        r = router.execute(
            "diff_features",
            {"target_column": "value", "diff_periods": [1]},
            {"data": weihai_df[["record_time", "value"]].copy()},
        )
        assert any("diff" in c for c in r["data"].columns)

    def test_ks_test_weihai_segments(self, router, weihai_df):
        a = weihai_df["value"].iloc[:200].dropna().tolist()
        b = weihai_df["value"].iloc[200:400].dropna().tolist()
        r = router.execute("ks_test", {"alpha": 0.05}, {"sample_a": a, "sample_b": b})
        assert 0.0 <= r["pvalue"] <= 1.0
        print("\n  [ks_test] p=", r["pvalue"], "drift=", r["drift_detected"])


@pytest.mark.skipif(
    not os.path.exists(FAULT_TRAIN) or not os.path.exists(FAULT_LABEL),
    reason="pv data missing",
)
class TestLegacyPvFaultRealdata:
    def test_merge_label_pv(self, router):
        src = pd.read_parquet(FAULT_TRAIN).head(500)
        lbl = pd.read_parquet(FAULT_LABEL)
        r = router.execute(
            "merge_label",
            {"id_fields": ["device_id"], "time_field": "time", "label_col": "custom_label_id"},
            {"source_data": src, "label_data": lbl},
        )
        assert "custom_label_id" in r["data"].columns or len(r["data"]) > 0

    def test_time_window_split_pv(self, router):
        df = pd.read_parquet(FAULT_TRAIN).head(400)
        r = router.execute(
            "time_window_split",
            {"window": "1d", "time_field": "time", "id_fields": ["device_id"]},
            {"data": df},
        )
        assert len(r["data"]) > 0

    def test_label_encode_pv(self, router):
        df = pd.DataFrame({"label": ["normal", "fault", "normal"]})
        r = router.execute(
            "label_encode",
            {"mode": "encode", "label_col": "label", "label_map": '{"normal": 0, "fault": 1}'},
            {"data": df},
        )
        assert set(r["data"]["label"].unique()) <= {0, 1, -1}
# @AI_GENERATED: end
