# @AI_GENERATED
"""P3 W3 真实数据 e2e — 聚类 / 采样 / 评估。"""
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
        pytest.skip("pv missing")
    return pd.read_parquet(FAULT_TRAIN).head(1500)


@pytest.mark.skipif(not os.path.exists(FAULT_TRAIN), reason="pv missing")
class TestP3W3ClusterPv:
    def test_three_clusterers(self, router, pv_df):
        X = pv_df[["value", "i_cal"]].fillna(0.0).head(600)
        for op_id, params in [
            ("hdbscan_cluster", {"min_cluster_size": 15}),
            ("gmm_cluster", {"n_components": 3, "random_state": 0}),
            ("optics_cluster", {"min_samples": 10}),
        ]:
            r = router.execute(op_id, params, {"data": X})
            assert len(r["labels"]) == len(X), op_id
            print(f"\n  [{op_id}] n_clusters={r['n_clusters_found']} ✓")


@pytest.mark.skipif(not os.path.exists(FAULT_TRAIN), reason="pv missing")
class TestP3W3SampleEvalPv:
    def test_imbalance_adasyn_stratified_balanced_acc(self, router, pv_df):
        X = pv_df[["value", "i_cal"]].fillna(0.0).head(800)
        # 人为制造不平衡伪标签
        y = (X["value"] > X["value"].quantile(0.85)).astype(int).values
        imb = router.execute("class_imbalance_check", {"imbalance_threshold": 2.0}, {"target": y})
        assert imb["n_classes"] == 2
        assert imb["is_imbalanced"] is True

        ada = router.execute(
            "adasyn_oversample", {"n_neighbors": 5, "random_state": 0},
            {"features": X, "target": y},
        )
        assert ada["n_synthetic"] > 0
        assert len(ada["features"]) > len(X)

        samp = router.execute(
            "stratified_sample", {"sample_ratio": 0.5, "random_state": 0},
            {"features": ada["features"], "target": ada["target"]},
        )
        assert samp["n_rows"] == len(samp["features"])

        # holdout 伪评估：多数类预测
        y_true = samp["target"]
        y_pred = np.zeros_like(y_true)
        ba = router.execute("balanced_accuracy", {}, {"y_true": y_true, "y_pred": y_pred})
        assert 0.0 <= ba["score"] <= 1.0
        print(f"\n  [sample/eval] syn={ada['n_synthetic']} ba={ba['score']:.3f} ✓")


@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai missing")
class TestP3W3PinballLoad:
    def test_pinball_on_weihai_quantile_proxy(self, router, weihai_df):
        y = weihai_df["value"].astype(float).values[-200:]
        # 用滚动中位数作分位代理预测
        pred = pd.Series(y).rolling(12, min_periods=1).median().values
        r = router.execute("pinball_loss", {"quantile": 0.5}, {"y_true": y, "y_pred": pred})
        assert np.isfinite(r["score"])
        print(f"\n  [pinball_loss] score={r['score']:.4f} ✓")
# @AI_GENERATED: end
