# @AI_GENERATED
"""
P4-β 评估/采样 — L6 真实数据 e2e。

威海负荷（回归指标）+ 光伏 train_small（分类/SMOTE/tsfresh/RFC）
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


@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai missing")
class TestEvalLoadForecastRealdata:
    @pytest.fixture(scope="class")
    def weihai_series(self, router):
        r = router.execute("load_csv", {"file_path": WEIHAI_CSV, "delimiter": ","}, {})
        df = r["data"]
        sub = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
        sub = sub.sort_values("record_time").head(200).reset_index(drop=True)
        y_true = sub["value"].astype(float).values
        y_pred = y_true + np.random.RandomState(0).randn(len(y_true)) * 0.05
        return y_true, y_pred

    def test_mse_rmse_mae_weihai(self, router, weihai_series):
        y_true, y_pred = weihai_series
        r = router.execute("mse_rmse_mae", {}, {"y_true": y_true, "y_pred": y_pred})
        assert all(np.isfinite(r[k]) for k in ("mse", "rmse", "mae"))

    def test_smape_weihai(self, router, weihai_series):
        y_true, y_pred = weihai_series
        r = router.execute("smape_score", {}, {"y_true": y_true, "y_pred": y_pred})
        assert 0.0 <= r["score"] < 100.0


@pytest.mark.skipif(
    not os.path.exists(FAULT_TRAIN) or not os.path.exists(FAULT_LABEL),
    reason="pv data missing",
)
class TestEvalPvFaultRealdata:
    @pytest.fixture(scope="class")
    def pv_xy(self):
        train = pd.read_parquet(FAULT_TRAIN).head(800)
        label = pd.read_parquet(FAULT_LABEL)
        train["date"] = pd.to_datetime(train["time"]).dt.date
        label["date"] = pd.to_datetime(label["time"]).dt.date
        merged = train.merge(
            label[["site_id", "device_id", "branch_id", "date", "custom_label_id"]],
            on=["site_id", "device_id", "branch_id", "date"],
            how="inner",
        ).drop_duplicates()
        merged = merged.rename(columns={"custom_label_id": "label"})
        feat = merged[["value", "i_cal"]].astype(float).dropna()
        y = merged.loc[feat.index, "label"].astype(int).values
        return feat, y

    def test_smote_oversample_pv(self, router, pv_xy):
        x, y = pv_xy
        before = len(y)
        r = router.execute("smote_oversample", {"limit": 120}, {"features": x, "target": y})
        assert len(r["target"]) >= before

    def test_random_forest_classifier_pv(self, router, pv_xy):
        x, y = pv_xy
        if len(np.unique(y)) < 2:
            pytest.skip("single class")
        r = router.execute(
            "random_forest_classifier",
            {"mode": "train", "n_estimators": 40, "save_model": "false"},
            {"features": x, "target": y},
        )
        assert len(r["predictions"]) > 0

    def test_tsfresh_extract_pv(self, router):
        df = pd.read_parquet(FAULT_TRAIN).head(200).copy()
        df["time_window"] = pd.to_datetime(df["time"]).dt.floor("D")
        r = router.execute(
            "tsfresh_extract",
            {"id_fields": ["device_id", "time_window"], "value_fields": ["value", "i_cal"]},
            {"data": df},
        )
        assert isinstance(r["data"], pd.DataFrame)
        assert r["data"].shape[0] > 0

    def test_stratified_cv_eval_pv(self, router):
        train = pd.read_parquet(FAULT_TRAIN).head(600)
        label = pd.read_parquet(FAULT_LABEL)
        train["date"] = pd.to_datetime(train["time"]).dt.date
        label["date"] = pd.to_datetime(label["time"]).dt.date
        merged = train.merge(
            label[["site_id", "device_id", "branch_id", "date", "custom_label_id"]],
            on=["site_id", "device_id", "branch_id", "date"],
            how="inner",
        ).drop_duplicates()
        merged["time_window"] = pd.to_datetime(merged["date"])
        merged = merged.rename(columns={"custom_label_id": "label"})
        id_fields = ["site_id", "device_id", "branch_id", "time_window"]
        stat = router.execute(
            "extract_statistical_features",
            {
                "mode": "groupby_aggregate",
                "id_fields": id_fields,
                "value_fields": ["value", "i_cal"],
                "compute_diff": False,
                "quantiles": [],
            },
            {"data": merged},
        )["data"]
        label_win = merged.groupby(id_fields)["label"].max().reset_index()
        feat = stat.merge(label_win, on=id_fields, how="inner").dropna()
        if len(feat) < 12:
            pytest.skip("too few samples")
        r = router.execute(
            "stratified_cv_eval",
            {
                "n_repeats": 2,
                "test_ratio": 0.2,
                "k": 5,
                "n_estimators": 30,
                "random_state": 42,
                "smote_limit": 80,
                "save_final_model": "false",
                "id_fields": id_fields,
                "target_col": "label",
            },
            {"stat_features": feat},
        )
        assert "accuracy_mean" in r and "macro_f1_mean" in r

    def test_precision_and_confusion_pv(self, router, pv_xy):
        x, y = pv_xy
        rfc = router.execute(
            "random_forest_classifier",
            {"mode": "train", "n_estimators": 30, "save_model": "false"},
            {"features": x.head(200), "target": y[:200]},
        )
        pr = router.execute(
            "precision_recall_f1", {"average": "macro"},
            {"y_true": rfc["y_true"], "y_pred": rfc["predictions"]},
        )
        cm = router.execute(
            "confusion_matrix", {},
            {"y_true": rfc["y_true"], "y_pred": rfc["predictions"]},
        )
        assert "f1" in pr
        assert "matrix" in cm
# @AI_GENERATED: end
