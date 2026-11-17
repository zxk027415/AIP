# @AI_GENERATED
"""剩余填批算子 L6 真实数据 e2e（不含 load_hdf5 / load_mongodb）。"""
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
def weihai_df():
    if not os.path.exists(WEIHAI_CSV):
        pytest.skip("weihai missing")
    df = pd.read_csv(WEIHAI_CSV)
    sub = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
    return sub.sort_values("record_time").head(800).reset_index(drop=True)


@pytest.fixture(scope="module")
def pv_df():
    if not os.path.exists(FAULT_TRAIN):
        pytest.skip("pv train missing")
    return pd.read_parquet(FAULT_TRAIN).head(2000)


@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai missing")
class TestRemainingRealdataLoad:
    def test_cyclical_encode_hour(self, router, weihai_df):
        df = weihai_df.copy()
        df["hour"] = pd.to_datetime(df["record_time"]).dt.hour
        r = router.execute(
            "cyclical_encode", {"column": "hour", "period": 24}, {"data": df[["hour", "value"]]},
        )
        assert "hour_sin" in r["data"].columns and "hour_cos" in r["data"].columns

    def test_data_type_convert_and_profile(self, router, weihai_df):
        df = weihai_df[["value"]].copy()
        df["value"] = df["value"].astype(str)
        r1 = router.execute(
            "data_type_convert",
            {"conversions": {"value": "float"}},
            {"data": df},
        )
        assert str(r1["data"]["value"].dtype).startswith("float")
        r2 = router.execute("data_profile", {}, {"data": r1["data"]})
        assert r2["n_rows"] == len(df)

    def test_data_merge_device_meta(self, router, weihai_df):
        left = weihai_df[["child_id", "value"]].head(50).copy()
        right = pd.DataFrame({"child_id": left["child_id"].unique(), "tag": ["load"] * left["child_id"].nunique()})
        r = router.execute("data_merge", {"join_key": "child_id", "how": "left"}, {"left": left, "right": right})
        assert "tag" in r["data"].columns

    def test_box_heatmap_charts(self, router, weihai_df):
        df = weihai_df[["value"]].head(200).copy()
        df["g"] = np.where(df["value"] > df["value"].median(), "hi", "lo")
        r_box = router.execute("box_chart", {"x_column": "g", "y_column": "value"}, {"data": df})
        assert r_box["chart_type"] == "box" or "chart_option" in r_box
        corr = router.execute("correlation_analysis", {}, {"data": weihai_df[["value"]].assign(v2=weihai_df["value"] * 0.9)})
        r_hm = router.execute("heatmap_chart", {}, {"correlation_matrix": corr["correlation_matrix"]})
        assert "chart_option" in r_hm

    def test_export_excel_relative(self, router, weihai_df):
        r = router.execute("export_excel", {}, {"data": weihai_df[["value"]].head(20)})
        assert not os.path.isabs(r["output_path"])
        assert r["rows_written"] == 20

    def test_roc_auc_on_threshold_labels(self, router, weihai_df):
        y = (weihai_df["value"] > weihai_df["value"].median()).astype(int).values
        score = (weihai_df["value"] - weihai_df["value"].mean()) / (weihai_df["value"].std() + 1e-9)
        # map to (0,1)
        prob = 1 / (1 + np.exp(-score))
        r = router.execute("roc_auc", {}, {"y_true": y.tolist(), "y_score": prob.tolist()})
        assert 0.0 <= r["score"] <= 1.0

    def test_prophet_on_weihai(self, router, weihai_df):
        try:
            import prophet  # noqa: F401
        except ImportError:
            pytest.skip("prophet not installed")
        df = weihai_df[["record_time", "value"]].tail(400).copy()
        r = router.execute(
            "prophet",
            {
                "timestamp_column": "record_time",
                "value_column": "value",
                "forecast_horizon": 8,
                "freq": "15min",
            },
            {"data": df},
        )
        assert len(r["forecast"]) == 8
        assert np.all(np.isfinite(r["forecast"]))


@pytest.mark.skipif(not os.path.exists(FAULT_TRAIN), reason="pv missing")
class TestRemainingRealdataPv:
    def test_anomaly_lof_elliptic_ocsvm(self, router, pv_df):
        X = pv_df[["value", "i_cal"]].head(500).copy()
        for op, params in [
            ("lof_detector", {"n_neighbors": 15, "contamination": 0.1}),
            ("elliptic_envelope", {"contamination": 0.1}),
            ("one_class_svm", {"mode": "fit_predict", "nu": 0.1, "save_model": "false"}),
        ]:
            r = router.execute(op, params, {"data": X})
            assert len(r["labels"]) == len(X)
            assert set(np.unique(r["labels"])).issubset({-1, 1})

    def test_agglomerative_and_silhouette(self, router, pv_df):
        X = pv_df[["value", "i_cal"]].head(300).copy()
        r = router.execute("agglomerative_clustering", {"n_clusters": 3}, {"data": X})
        assert len(r["labels"]) == len(X)
        r2 = router.execute("silhouette_score", {}, {"data": X, "labels": r["labels"]})
        assert -1.0 <= r2["score"] <= 1.0

    def test_data_pivot_value(self, router, pv_df):
        df = pv_df.head(200).copy()
        df["metric"] = "value"
        r = router.execute(
            "data_pivot",
            {"index": ["device_id"], "columns": "metric", "values": "value", "aggfunc": "mean"},
            {"data": df},
        )
        assert isinstance(r["data"], pd.DataFrame)
        assert len(r["data"]) > 0
# @AI_GENERATED: end
