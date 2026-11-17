# @AI_GENERATED
"""
P4-β 评估/采样波 — 烟测用例表。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

P4_BETA_EVAL = frozenset({
    "confusion_matrix",
    "mse_rmse_mae",
    "smape_score",
    "precision_recall_f1",
    "stratified_cv_eval",
    "random_forest_classifier",
    "smote_oversample",
    "tsfresh_extract",
})


def _y_cls():
    y_true = np.array([0, 1, 0, 1, 2, 0, 1, 2, 0, 1])
    y_pred = np.array([0, 1, 0, 0, 2, 0, 1, 1, 0, 2])
    return y_true, y_pred


def _y_reg():
    y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y_pred = np.array([1.1, 2.0, 2.8, 4.2, 4.9])
    return y_true, y_pred


def _classification_features_target():
    from sklearn.datasets import make_classification

    x, y = make_classification(
        n_samples=60, n_features=6, n_informative=4, n_redundant=0,
        n_classes=2, random_state=42,
    )
    return pd.DataFrame(x, columns=[f"f{i}" for i in range(6)]), y


def _smote_balanced_features_target():
    """两类样本数相等且均已 >= limit，SMOTE 不合成新样本（确定性 no-op）。"""
    rng = np.random.RandomState(42)
    x = pd.DataFrame(rng.randn(40, 4), columns=[f"f{i}" for i in range(4)])
    y = np.array([0] * 20 + [1] * 20)
    return x, y


def _stratified_cv_frame():
    rng = np.random.RandomState(7)
    n = 48
    return pd.DataFrame({
        "site_id": ["s1"] * n,
        "device_id": ["d1"] * n,
        "branch_id": ["b1"] * n,
        "time_window": pd.date_range("2024-01-01", periods=n, freq="D"),
        "f1": rng.randn(n),
        "f2": rng.randn(n),
        "f3": rng.randn(n),
        "label": np.array([0] * 24 + [1] * 24),
    })


def _tsfresh_input_df():
    rng = np.random.RandomState(3)
    n = 40
    ts = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({
        "device_id": ["d1"] * n,
        "time_window": ts,
        "value": np.sin(np.arange(n) / 4.0) + rng.randn(n) * 0.05,
        "i_cal": np.cos(np.arange(n) / 4.0) + rng.randn(n) * 0.05,
    })


def eval_beta_smoke_specs():
    y_true, y_pred = _y_cls()
    yt, yp = _y_reg()
    return [
        (
            "confusion_matrix",
            lambda _tp: {},
            lambda _tp: {"y_true": y_true, "y_pred": y_pred},
            ["matrix", "report"],
            "confusion_matrix",
        ),
        (
            "mse_rmse_mae",
            lambda _tp: {},
            lambda _tp: {"y_true": yt, "y_pred": yp},
            ["mse", "rmse", "mae"],
            "regression_metrics",
        ),
        (
            "smape_score",
            lambda _tp: {},
            lambda _tp: {"y_true": yt, "y_pred": yp},
            ["score"],
            "score",
        ),
        (
            "precision_recall_f1",
            lambda _tp: {"average": "macro"},
            lambda _tp: {"y_true": y_true, "y_pred": y_pred},
            ["accuracy", "precision", "recall", "f1"],
            "classification_metrics",
        ),
        (
            "stratified_cv_eval",
            lambda _tp: {
                "n_repeats": 2,
                "test_ratio": 0.25,
                "k": 3,
                "n_estimators": 20,
                "random_state": 42,
                "smote_limit": 40,
                "save_final_model": "false",
                "id_fields": ["site_id", "device_id", "branch_id", "time_window"],
                "target_col": "label",
            },
            lambda _tp: {"stat_features": _stratified_cv_frame()},
            ["accuracy_mean", "macro_f1_mean", "confusion_matrix"],
            "stratified_cv",
        ),
        (
            "random_forest_classifier",
            lambda _tp: {"mode": "train", "n_estimators": 20, "save_model": "false"},
            lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
            ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
            "classifier_train",
        ),
        (
            "smote_oversample",
            lambda _tp: {"limit": 15},
            lambda _tp: dict(zip(["features", "target"], _smote_balanced_features_target())),
            ["features", "target"],
            "smote",
        ),
        (
            "tsfresh_extract",
            lambda _tp: {
                "id_fields": ["device_id", "time_window"],
                "value_fields": ["value", "i_cal"],
            },
            lambda _tp: {"data": _tsfresh_input_df()},
            ["data"],
            "dataframe",
        ),
    ]
# @AI_GENERATED: end
