# @AI_GENERATED
"""
gradient_boosting_classifier operator backend — 梯度提升分类器（训练 + 预测）。

使用 sklearn.ensemble.GradientBoostingClassifier。
"""
import logging
import os
import pickle
import time
import uuid

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "gradient_boosting_classifier"
logger = logging.getLogger(__name__)
_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "models")


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def execute(params: dict, inputs: dict) -> dict:
    mode = str(params.get("mode") or "train").strip().lower()
    if mode not in ("train", "predict"):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid mode '{mode}'")

    try:
        n_estimators = int(params.get("n_estimators") or 100)
    except (TypeError, ValueError):
        n_estimators = 100
    try:
        learning_rate = float(params.get("learning_rate") or 0.1)
    except (TypeError, ValueError):
        learning_rate = 0.1
    try:
        max_depth = int(params.get("max_depth") or 3)
    except (TypeError, ValueError):
        max_depth = 3

    if mode == "train":
        features = inputs.get("features")
        target = inputs.get("target")
        if features is None or not isinstance(features, pd.DataFrame):
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "train requires 'features' as DataFrame")
        if target is None:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "train requires 'target'")

        y = np.asarray(target)
        if len(np.unique(y)) < 2:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "target must have >= 2 classes")

        n_total = len(features)
        idx = np.random.RandomState(42).permutation(n_total)
        n_train = int(n_total * 0.8)
        X_train, X_test = features.iloc[idx[:n_train]], features.iloc[idx[n_train:]]
        y_train, y_test = y[idx[:n_train]], y[idx[n_train:]]

        clf = GradientBoostingClassifier(n_estimators=n_estimators, learning_rate=learning_rate, max_depth=max_depth, random_state=42)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)

        clf_full = GradientBoostingClassifier(n_estimators=n_estimators, learning_rate=learning_rate, max_depth=max_depth, random_state=42)
        clf_full.fit(features, y)

        _ensure_models_dir()
        model_id = f"gbc_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        with open(os.path.join(_MODELS_DIR, f"{model_id}.pkl"), "wb") as f:
            pickle.dump({"model": clf_full, "feature_list": list(features.columns)}, f)

        logger.info(f"[{OPERATOR_ID}] train: n_estimators={n_estimators}, lr={learning_rate}, model_id={model_id}")
        return {"model": clf_full, "model_id": model_id, "feature_list": list(features.columns),
                "predictions": preds, "y_true": y_test, "feature_importances": clf_full.feature_importances_}

    else:
        model = inputs.get("model")
        model_id_param = params.get("model_id") or ""
        if model is None and model_id_param:
            _ensure_models_dir()
            path = os.path.join(_MODELS_DIR, f"{model_id_param}.pkl")
            if not os.path.exists(path):
                raise OperatorExecutionError(OPERATOR_ID, "FileNotFoundError", f"Model not found: {path}")
            with open(path, "rb") as f:
                payload = pickle.load(f)
            model = payload["model"]

        if model is None:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "predict requires model or model_id")

        predict_features = inputs.get("predict_features")
        if predict_features is None:
            predict_features = inputs.get("data")
        if predict_features is None or not isinstance(predict_features, pd.DataFrame):
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "predict requires 'predict_features' as DataFrame")

        predictions = model.predict(predict_features)
        return {"predictions": predictions, "model_id": model_id_param}
# @AI_GENERATED: end
