# @AI_GENERATED
"""P4-γ 剩余算子 L6 真实数据 e2e（威海 + 光伏）。"""
from __future__ import annotations

import os
import sqlite3
import sys
import warnings
from unittest.mock import MagicMock, patch

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


def _weihai_feature_df(weihai_df: pd.DataFrame) -> pd.DataFrame:
    """威海子集 + 日历数值特征（切分后 train_features 仍有可用列）。"""
    df = weihai_df[["record_time", "value"]].copy()
    rt = pd.to_datetime(df["record_time"])
    df["hour"] = rt.dt.hour.astype(float)
    df["dow"] = rt.dt.dayofweek.astype(float)
    return df


def _numeric_feature_matrix(features: pd.DataFrame) -> pd.DataFrame:
    tr_x = features.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if tr_x.empty:
        raise ValueError("no numeric feature columns after split")
    return tr_x


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
    sub["record_time"] = pd.to_datetime(sub["record_time"])
    return sub.sort_values("record_time").head(400).reset_index(drop=True)


@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai missing")
class TestGammaLoadForecastRealdata:
    def test_train_test_split_and_resample(self, router, weihai_df):
        df = weihai_df[["record_time", "value"]].copy()
        split = router.execute(
            "train_test_split_ts",
            {"train_ratio": 0.8, "time_field": "record_time", "target_column": "value"},
            {"data": df},
        )
        assert len(split["train_features"]) > len(split["test_features"])
        rs = router.execute(
            "resample_timeseries",
            {"frequency": "1h", "method": "mean", "time_field": "record_time"},
            {"data": df},
        )
        assert len(rs["data"]) > 0

    def test_ridge_xgb_ensemble_pipeline(self, router, weihai_df):
        df = _weihai_feature_df(weihai_df)
        split = router.execute(
            "train_test_split_ts",
            {"train_ratio": 0.75, "time_field": "record_time", "target_column": "value"},
            {"data": df},
        )
        ms = router.execute("multi_step_forecast", {"forecast_steps": 3}, split)
        assert ms["forecast_config"]["forecast_steps"] == 3

        tr_x = _numeric_feature_matrix(split["train_features"])
        te_x = _numeric_feature_matrix(split["test_features"])
        te_x = te_x.assign(record_time=split["test_features"]["record_time"].values)

        ridge = router.execute(
            "ridge_forecast",
            {"mode": "train", "alpha": 1.0},
            {
                "train_features": tr_x,
                "train_target": split["train_target"],
                "test_features": te_x,
                "test_target": split["test_target"],
            },
        )
        xgb = router.execute(
            "xgboost_forecast",
            {"mode": "train", "n_estimators": 30, "allow_missing_dependency": True},
            {
                "train_features": tr_x,
                "train_target": split["train_target"],
                "test_features": te_x,
                "test_target": split["test_target"],
            },
        )
        ens = router.execute(
            "ensemble_forecast",
            {"weight_mode": "equal", "prediction_keys": "y_pred_ridge,y_pred_xgb"},
            {"y_pred_ridge": ridge["y_pred"], "y_pred_xgb": xgb["y_pred"]},
        )
        assert len(ens["forecast_values"]) > 0

        saved = router.execute(
            "save_model_artifact",
            {"model_ref": "gamma-weihai-ridge", "source_operator": "ridge_forecast"},
            {"model": ridge["model"], "feature_list": list(tr_x.columns), "model_id": ridge["model_id"]},
        )
        loaded = router.execute("load_model_artifact", {"model_ref": saved["model_ref"]}, {})
        assert loaded["model"] is not None

    def test_auto_tune_xgboost_weihai(self, router, weihai_df):
        df = _weihai_feature_df(weihai_df)
        split = router.execute(
            "train_test_split_ts",
            {"train_ratio": 0.8, "time_field": "record_time", "target_column": "value"},
            {"data": df},
        )
        tr_x = _numeric_feature_matrix(split["train_features"])
        r = router.execute(
            "auto_tune_xgboost",
            {"n_trials": 2, "cv_folds": 2},
            {"train_features": tr_x, "train_target": split["train_target"]},
        )
        assert "best_params" in r

    def test_load_database_weihai_sqlite(self, router, weihai_df, tmp_path):
        db = tmp_path / "weihai.db"
        weihai_df[["record_time", "value"]].to_sql("load", sqlite3.connect(str(db)), index=False)
        r = router.execute(
            "load_database",
            {
                "db_type": "sqlite",
                "connection_string": str(db),
                "query": "SELECT record_time, value FROM load ORDER BY record_time LIMIT 50",
            },
            {},
        )
        assert len(r["data"]) == 50

    def test_load_api_mock_weihai_shape(self, router, weihai_df):
        payload = weihai_df.head(5)[["record_time", "value"]].astype({"record_time": str}).to_dict("records")
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = payload
        with patch("services.operator_backends.load_api.requests.get", return_value=mock_resp):
            r = router.execute("load_api", {"url": "http://mock/load"}, {})
        assert len(r["data"]) == 5


@pytest.mark.skipif(not os.path.exists(FAULT_TRAIN), reason="pv missing")
class TestGammaPvFaultRealdata:
    def test_batch_predict_pv(self, router):
        train = pd.read_parquet(FAULT_TRAIN).head(300)
        label = pd.read_parquet(FAULT_LABEL) if os.path.exists(FAULT_LABEL) else None
        if label is not None:
            train["date"] = pd.to_datetime(train["time"]).dt.date
            label["date"] = pd.to_datetime(label["time"]).dt.date
            merged = train.merge(
                label[["site_id", "device_id", "branch_id", "date", "custom_label_id"]],
                on=["site_id", "device_id", "branch_id", "date"],
                how="inner",
            )
            y = merged["custom_label_id"].astype(int).values
            x = merged[["value", "i_cal"]].astype(float).fillna(0)
        else:
            x = train[["value", "i_cal"]].astype(float).fillna(0)
            y = (x["value"] > x["value"].median()).astype(int).values

        if len(np.unique(y)) < 2:
            pytest.skip("single class")
        rfc = router.execute(
            "random_forest_classifier",
            {"mode": "train", "n_estimators": 30, "save_model": "false"},
            {"features": x, "target": y},
        )
        feat = x.copy()
        feat["site_id"] = train.loc[feat.index, "site_id"].values if "site_id" in train.columns else "s1"
        feat["device_id"] = train.loc[feat.index, "device_id"].values if "device_id" in train.columns else "d1"
        feat["time_window"] = pd.date_range("2024-01-01", periods=len(feat), freq="h")
        feat = feat.set_index(["site_id", "device_id", "time_window"])
        batch = router.execute(
            "batch_predict_classifier",
            {"batch_size": 50},
            {"model": rfc["model"], "predict_features": feat},
        )
        assert len(batch["predictions"]) == len(feat)
# @AI_GENERATED: end
