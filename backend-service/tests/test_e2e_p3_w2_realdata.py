# @AI_GENERATED
"""P3 W2 真实数据 e2e — 时序预测 4 + 分类 4。"""
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
PV_POWER = os.path.join(_BACKEND_DIR, "data", "demo", "pv_power_data.csv")
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
def weihai_df():
    if not os.path.exists(WEIHAI_CSV):
        pytest.skip("weihai missing")
    df = pd.read_csv(WEIHAI_CSV)
    sub = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
    return sub.sort_values("record_time").head(600).reset_index(drop=True)


@pytest.fixture(scope="module")
def pv_power_df():
    if not os.path.exists(PV_POWER):
        pytest.skip("pv_power missing")
    return pd.read_csv(PV_POWER).head(500)


@pytest.fixture(scope="module")
def pv_cls():
    if not (os.path.exists(FAULT_TRAIN) and os.path.exists(FAULT_LABEL)):
        pytest.skip("pv fault data missing")
    train = pd.read_parquet(FAULT_TRAIN).head(2000)
    label = pd.read_parquet(FAULT_LABEL)
    # 常见列：device_id + 数值特征；标签列尽量兼容
    feat_cols = [c for c in ["value", "i_cal"] if c in train.columns]
    if len(feat_cols) < 2:
        feat_cols = list(train.select_dtypes(include="number").columns[:4])
    X = train[feat_cols].fillna(0.0)
    # 伪二分类：按 value 中位数（无可靠标签列时）
    if "label" in label.columns:
        y = label["label"].iloc[: len(X)].values
    elif "fault_type" in label.columns:
        y = (label["fault_type"].iloc[: len(X)] != 0).astype(int).values
    else:
        y = (X.iloc[:, 0] > X.iloc[:, 0].median()).astype(int).values
    # 保证至少两类
    if len(np.unique(y)) < 2:
        y = (X.iloc[:, 0] > X.iloc[:, 0].median()).astype(int).values
    return X, y


@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai missing")
class TestP3W2ForecastLoad:
    def test_rf_knn_exp_smoothing_on_weihai(self, router, weihai_df):
        df = weihai_df.rename(columns={"record_time": "timestamp"})[["timestamp", "value"]]
        for op_id, params in [
            ("random_forest_forecast", {"n_estimators": 30, "n_lags": 12, "forecast_horizon": 8}),
            ("knn_forecast", {"n_neighbors": 5, "n_lags": 12, "forecast_horizon": 8}),
            ("exponential_smoothing", {"forecast_horizon": 8, "trend": "add"}),
        ]:
            r = router.execute(
                op_id,
                {"timestamp_column": "timestamp", "value_column": "value", **params},
                {"data": df},
            )
            assert len(r["forecast"]) == 8, op_id
            assert np.all(np.isfinite(r["forecast"])), op_id
            print(f"\n  [{op_id}] mean_forecast={np.mean(r['forecast']):.3f} ✓")


@pytest.mark.skipif(not os.path.exists(PV_POWER), reason="pv_power missing")
class TestP3W2ForecastPvPower:
    def test_quantile_regression_on_pv_power(self, router, pv_power_df):
        cols = list(pv_power_df.columns)
        ts_col = "timestamp" if "timestamp" in cols else ("record_time" if "record_time" in cols else cols[0])
        for cand in ("power_actual", "power", "value"):
            if cand in cols:
                val_col = cand
                break
        else:
            val_col = cols[-1]
        df = pv_power_df[[ts_col, val_col]].copy()
        df = df.rename(columns={ts_col: "timestamp", val_col: "value"})
        r = router.execute(
            "quantile_regression_forecast",
            {
                "timestamp_column": "timestamp",
                "value_column": "value",
                "forecast_horizon": 6,
                "n_lags": 8,
                "quantile": 0.5,
            },
            {"data": df},
        )
        assert len(r["forecast"]) == 6
        assert np.all(np.isfinite(r["forecast"]))
        print(f"\n  [quantile_regression_forecast] forecast={r['forecast'][:3]}... ✓")


@pytest.mark.skipif(
    not (os.path.exists(FAULT_TRAIN) and os.path.exists(FAULT_LABEL)),
    reason="pv fault missing",
)
class TestP3W2ClassifyPv:
    def test_four_classifiers_on_pv_windows(self, router, pv_cls):
        X, y = pv_cls
        for op_id, params in [
            ("extra_trees_classifier", {"n_estimators": 40, "max_depth": 6}),
            ("adaboost_classifier", {"n_estimators": 40, "learning_rate": 0.5}),
            ("calibrated_classifier", {"cv": 2, "method": "sigmoid"}),
            ("lightgbm_classifier", {"n_estimators": 40, "max_depth": 4, "learning_rate": 0.1}),
        ]:
            r = router.execute(
                op_id,
                {"mode": "train", "save_model": "false", **params},
                {"features": X, "target": y},
            )
            assert len(r["predictions"]) == len(r["y_true"]), op_id
            assert len(r["predictions"]) > 0, op_id
            print(f"\n  [{op_id}] holdout_n={len(r['predictions'])} ✓")
# @AI_GENERATED: end
