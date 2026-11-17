# @AI_GENERATED
"""
P4-γ 剩余算子 — 烟测用例表（预测栈 + 模型 IO + 数据源 + 调参）。
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

P4_GAMMA = frozenset({
    "train_test_split_ts",
    "resample_timeseries",
    "multi_step_forecast",
    "ridge_forecast",
    "xgboost_forecast",
    "lightgbm_forecast",
    "catboost_forecast",
    "ensemble_forecast",
    "save_model_artifact",
    "load_model_artifact",
    "batch_predict_classifier",
    "load_database",
    "load_api",
    "auto_tune_xgboost",
    "auto_tune_lightgbm",
    "auto_tune_catboost",
})

_REGISTRY_REF = "p4-gamma-smoke-model-ref"


def _ts_df(n: int = 60) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=n, freq="h")
    vals = np.sin(np.arange(n) / 5.0) * 8 + np.arange(n) * 0.2
    return pd.DataFrame({"record_time": ts, "value": vals})


def _forecast_matrix_inputs():
    from sklearn.datasets import make_regression

    x, y = make_regression(n_samples=80, n_features=4, noise=0.05, random_state=42)
    feat = pd.DataFrame(x, columns=list("abcd"))
    split = 60
    test_n = 20
    return {
        "train_features": feat.iloc[:split].copy(),
        "train_target": y[:split],
        "test_features": feat.iloc[split:].copy().assign(
            record_time=pd.date_range("2024-06-01", periods=test_n, freq="h"),
        ),
        "test_target": y[split:],
    }


def _split_bundle():
    ts = _ts_df(50)
    n_train = 40
    return {
        "train_features": ts.iloc[:n_train].copy(),
        "train_target": ts.iloc[:n_train]["value"].to_numpy(),
        "test_features": ts.iloc[n_train:].copy(),
        "test_target": ts.iloc[n_train:]["value"].to_numpy(),
    }


def _ensure_registry_model():
    from sklearn.linear_model import Ridge

    from services.operator_execution import model_registry

    m = Ridge(alpha=1.0).fit([[1.0], [2.0], [3.0]], [1.0, 2.0, 3.0])
    model_registry.register_model(_REGISTRY_REF, m, ["value"], {"operator": "smoke"})
    return {}


def _make_sqlite(tmp_path) -> str:
    db = tmp_path / "gamma_smoke.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE readings (record_time TEXT, value REAL)")
    conn.executemany(
        "INSERT INTO readings VALUES (?, ?)",
        [("2024-01-01 00:00:00", 1.0), ("2024-01-01 01:00:00", 2.0), ("2024-01-01 02:00:00", 3.0)],
    )
    conn.commit()
    conn.close()
    return str(db)


def _batch_predict_inputs():
    from sklearn.ensemble import RandomForestClassifier

    rng = np.random.RandomState(0)
    x = pd.DataFrame(rng.randn(24, 3), columns=list("abc"))
    y = np.array([0] * 12 + [1] * 12)
    model = RandomForestClassifier(n_estimators=10, random_state=0).fit(x, y)
    feat = x.copy()
    feat["site_id"] = ["s1"] * len(x)
    feat["device_id"] = [f"d{i}" for i in range(len(x))]
    feat["time_window"] = pd.date_range("2024-01-01", periods=len(x), freq="h")
    feat = feat.set_index(["site_id", "device_id", "time_window"])
    return {"model": model, "predict_features": feat}


def gamma_smoke_specs():
    fmx = _forecast_matrix_inputs()
    split = _split_bundle()
    return [
        (
            "train_test_split_ts",
            lambda _tp: {"train_ratio": 0.8, "time_field": "record_time", "target_column": "value"},
            lambda _tp: {"data": _ts_df(50)},
            ["train_features", "train_target", "test_features", "test_target"],
            "split_ts",
        ),
        (
            "resample_timeseries",
            lambda _tp: {"frequency": "2h", "method": "mean", "time_field": "record_time"},
            lambda _tp: {"data": _ts_df(48)},
            ["data"],
            "dataframe",
        ),
        (
            "multi_step_forecast",
            lambda _tp: {"forecast_steps": 4, "strategy": "recursive"},
            lambda _tp: dict(split),
            ["forecast_config", "train_features", "train_target", "test_features", "test_target"],
            "multi_step",
        ),
        (
            "ridge_forecast",
            lambda _tp: {"mode": "train", "alpha": 1.0},
            lambda _tp: dict(fmx),
            ["predictions", "model", "model_id", "model_ref", "y_pred", "oof_rmse", "forecast_values"],
            "forecast_train",
        ),
        (
            "xgboost_forecast",
            lambda _tp: {"mode": "train", "n_estimators": 20, "allow_missing_dependency": True},
            lambda _tp: dict(fmx),
            ["predictions", "model_id", "forecast_values"],
            "forecast_train",
        ),
        (
            "lightgbm_forecast",
            lambda _tp: {"mode": "train", "allow_missing_dependency": True},
            lambda _tp: dict(fmx),
            ["predictions", "model_id", "forecast_values"],
            "forecast_train",
        ),
        (
            "catboost_forecast",
            lambda _tp: {"mode": "train", "allow_missing_dependency": True},
            lambda _tp: dict(fmx),
            ["predictions", "model_id", "forecast_values"],
            "forecast_train",
        ),
        (
            "ensemble_forecast",
            lambda _tp: {"weight_mode": "equal", "prediction_keys": "y_pred_a,y_pred_b"},
            lambda _tp: {
                "y_pred_a": np.array([1.0, 2.0, 3.0, 4.0]),
                "y_pred_b": np.array([1.2, 1.8, 3.1, 3.9]),
            },
            ["y_pred", "predictions", "forecast_values", "model_weights", "weight_mode_used"],
            "ensemble",
        ),
        (
            "save_model_artifact",
            lambda _tp: {"model_ref": _REGISTRY_REF},
            lambda _tp: {
                "model": __import__("sklearn.linear_model", fromlist=["Ridge"]).Ridge().fit([[1], [2]], [1, 2]),
                "feature_list": ["value"],
            },
            ["model_ref", "model_id", "feature_list", "saved"],
            "artifact",
        ),
        (
            "load_model_artifact",
            lambda _tp: {"model_ref": _REGISTRY_REF},
            lambda _tp: (_ensure_registry_model() or {}),
            ["model_ref", "model_id", "model", "feature_list", "metadata"],
            "artifact",
        ),
        (
            "batch_predict_classifier",
            lambda _tp: {"batch_size": 8},
            lambda _tp: _batch_predict_inputs(),
            ["predictions", "failure_count"],
            "batch_predict",
        ),
        (
            "load_database",
            lambda tp: {
                "db_type": "sqlite",
                "connection_string": _make_sqlite(tp),
                "query": "SELECT record_time, value FROM readings ORDER BY record_time",
            },
            lambda _tp: {},
            ["data"],
            "dataframe",
        ),
        (
            "load_api",
            lambda _tp: {"url": "http://smoke.local/data", "method": "GET"},
            lambda _tp: {},
            ["data"],
            "load_api_mock",
        ),
        (
            "auto_tune_xgboost",
            lambda _tp: {"n_trials": 2, "cv_folds": 2},
            lambda _tp: {
                "train_features": fmx["train_features"],
                "train_target": fmx["train_target"],
            },
            ["best_params", "model"],
            "auto_tune",
        ),
        (
            "auto_tune_lightgbm",
            lambda _tp: {"n_trials": 2, "cv_folds": 2},
            lambda _tp: {
                "train_features": fmx["train_features"],
                "train_target": fmx["train_target"],
            },
            ["best_params", "model"],
            "auto_tune",
        ),
        (
            "auto_tune_catboost",
            lambda _tp: {"n_trials": 2, "cv_folds": 2},
            lambda _tp: {
                "train_features": fmx["train_features"],
                "train_target": fmx["train_target"],
            },
            ["best_params", "model"],
            "auto_tune",
        ),
    ]
# @AI_GENERATED: end
