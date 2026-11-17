# @AI_GENERATED
"""
P3 W1 真实数据 e2e — 特征工程 5 + 异常检测 5
============================================

负荷：load_forecast_refactored/datasets/load_true_weihai_260415.csv
光伏：fault-diag-algo-release-3.1/.../train_small.parquet
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
def weihai_df():
    if not os.path.exists(WEIHAI_CSV):
        pytest.skip("weihai csv missing")
    df = pd.read_csv(WEIHAI_CSV)
    sub = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
    sub = sub.sort_values("record_time").head(1200).reset_index(drop=True)
    return sub


@pytest.fixture(scope="module")
def pv_df():
    if not os.path.exists(FAULT_TRAIN):
        pytest.skip("train_small missing")
    df = pd.read_parquet(FAULT_TRAIN)
    return df.head(3000).copy()


@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai missing")
class TestP3W1FeaturesLoad:
    def test_autocorrelation_vs_statsmodels(self, router, weihai_df):
        from statsmodels.tsa.stattools import acf, pacf

        df = weihai_df[["value"]].copy()
        nlags = 12
        r = router.execute(
            "autocorrelation_features",
            {"column": "value", "nlags": nlags, "include_pacf": True},
            {"data": df},
        )
        series = df["value"].astype(float).values
        acf_ref = acf(series, nlags=nlags, fft=True)
        pacf_ref = pacf(series, nlags=nlags, method="ywm")
        for i in range(1, nlags + 1):
            assert abs(r["data"].iloc[0][f"acf_{i}"] - acf_ref[i]) < 1e-8
            assert abs(r["data"].iloc[0][f"pacf_{i}"] - pacf_ref[i]) < 1e-6
        print("\n  [autocorrelation_features] matches statsmodels ✓")

    def test_spectral_vs_numpy(self, router, weihai_df):
        df = weihai_df[["value"]].copy()
        r = router.execute(
            "spectral_features",
            {"column": "value", "sampling_rate": 1.0, "roll_off": 0.85},
            {"data": df},
        )
        x = df["value"].astype(float).values
        x = x - np.mean(x)
        power = np.abs(np.fft.rfft(x)) ** 2
        freqs = np.fft.rfftfreq(len(x), d=1.0)
        total = float(np.sum(power)) + 1e-12
        centroid = float(np.sum(freqs * power) / total)
        assert abs(r["data"].iloc[0]["spectral_centroid"] - centroid) < 1e-8
        print("\n  [spectral_features] centroid matches numpy ✓")

    def test_quantile_transform_vs_sklearn(self, router, weihai_df):
        from sklearn.preprocessing import QuantileTransformer

        df = weihai_df[["value"]].head(800).copy()
        r = router.execute(
            "quantile_transform",
            {"columns": ["value"], "output_distribution": "uniform", "n_quantiles": 100, "random_state": 42},
            {"data": df},
        )
        qt = QuantileTransformer(n_quantiles=100, output_distribution="uniform", random_state=42)
        expected = qt.fit_transform(df[["value"]].astype(float))
        np.testing.assert_allclose(r["data"]["value"].values, expected.ravel(), rtol=0, atol=1e-9)
        print("\n  [quantile_transform] matches sklearn ✓")

    @pytest.mark.parametrize("op_id,params", [
        ("zscore_anomaly", {"column": "value", "threshold": 3.0}),
        ("iqr_anomaly", {"column": "value", "factor": 1.5}),
        ("mad_anomaly", {"column": "value", "threshold": 3.5}),
        ("ewma_anomaly", {"column": "value", "span": 24, "threshold": 3.0}),
    ])
    def test_rule_anomaly_contract(self, router, weihai_df, op_id, params):
        df = weihai_df[["value"]].copy()
        r = router.execute(op_id, params, {"data": df})
        assert len(r["labels"]) == len(df)
        assert set(np.unique(r["labels"])).issubset({-1, 1})
        assert np.all(np.isfinite(r["scores"]))
        print(f"\n  [{op_id}] anomalies={int(np.sum(r['labels'] == -1))} ✓")


@pytest.mark.skipif(not os.path.exists(FAULT_TRAIN), reason="pv train missing")
class TestP3W1FeaturesPv:
    def test_shape_features_vs_scipy(self, router, pv_df):
        from scipy import stats

        df = pv_df[["value"]].head(2000).copy()
        r = router.execute("shape_features", {"column": "value"}, {"data": df})
        x = df["value"].astype(float).values
        assert abs(r["data"].iloc[0]["shape_skew"] - float(stats.skew(x, bias=False))) < 1e-8
        assert abs(r["data"].iloc[0]["shape_peak_to_peak"] - float(np.ptp(x))) < 1e-9
        print("\n  [shape_features] matches scipy ✓")

    def test_chi2_select_vs_sklearn(self, router, pv_df):
        from sklearn.feature_selection import SelectKBest, chi2

        # 构造简单非负特征 + 伪标签（用 value 分位）
        g = pv_df.head(1500).copy()
        feats = pd.DataFrame({
            "v": g["value"].astype(float).clip(lower=0),
            "i": g["i_cal"].astype(float).clip(lower=0),
            "v2": (g["value"].astype(float) ** 2).clip(lower=0),
            "abs_i": g["i_cal"].astype(float).abs(),
        })
        y = (feats["v"] > feats["v"].median()).astype(int).values
        r = router.execute("chi2_select", {"k": 2}, {"features": feats, "target": y})
        sel = SelectKBest(chi2, k=2).fit(feats, y)
        expected = [c for c, m in zip(feats.columns, sel.get_support()) if m]
        assert r["selected_columns"] == expected
        print(f"\n  [chi2_select] selected={r['selected_columns']} ✓")

    def test_knn_anomaly_contract(self, router, pv_df):
        df = pv_df[["value", "i_cal"]].head(800).copy()
        r = router.execute(
            "knn_anomaly",
            {"n_neighbors": 10, "contamination": 0.05},
            {"data": df},
        )
        assert len(r["labels"]) == len(df)
        n_anom = int(np.sum(r["labels"] == -1))
        assert 1 <= n_anom <= int(0.2 * len(df))
        print(f"\n  [knn_anomaly] anomalies={n_anom} ✓")
# @AI_GENERATED: end
