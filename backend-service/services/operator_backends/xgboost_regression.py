# @AI_GENERATED
"""
xgboost_regression operator backend — XGBoost 回归（train/predict）。
"""
import logging
import os
import pickle
import time
import uuid

import numpy as np
import pandas as pd

try:
    from xgboost import XGBRegressor
except ImportError:
    XGBRegressor = None  # type: ignore[assignment]

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "xgboost_regression"
logger = logging.getLogger(__name__)
_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "models")


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def execute(params: dict, inputs: dict) -> dict:
    if XGBRegressor is None:
        raise OperatorExecutionError(OPERATOR_ID, "DependencyError", "xgboost package not installed")

    mode = str(params.get("mode") or "train").strip().lower()
    if mode not in ("train", "predict"):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid mode '{mode}'")

    try:
        n_estimators = int(params.get("n_estimators") or 100)
        max_depth = int(params.get("max_depth") or 6)
        learning_rate = float(params.get("learning_rate") or 0.1)
    except (TypeError, ValueError):
        n_estimators, max_depth, learning_rate = 100, 6, 0.1

    if mode == "train":
        features = inputs.get("features")
        target = inputs.get("target")
        if features is None or not isinstance(features, pd.DataFrame):
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "train requires 'features' as DataFrame")
        if target is None:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "train requires 'target'")

        try:
            y = np.asarray(target, dtype=float)
        except (ValueError, TypeError) as e:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", f"target non-numeric: {e}")

        n_total = len(features)
        idx = np.random.RandomState(42).permutation(n_total)
        n_train = int(n_total * 0.8)

        eval_model = XGBRegressor(
            n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate, random_state=42,
        )
        eval_model.fit(features.iloc[idx[:n_train]], y[idx[:n_train]])
        preds = eval_model.predict(features.iloc[idx[n_train:]])

        final_model = XGBRegressor(
            n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate, random_state=42,
        )
        final_model.fit(features, y)

        _ensure_models_dir()
        model_id = f"xgbr_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        with open(os.path.join(_MODELS_DIR, f"{model_id}.pkl"), "wb") as f:
            pickle.dump({"model": final_model, "feature_list": list(features.columns)}, f)

        logger.info(f"[{OPERATOR_ID}] train: n_estimators={n_estimators}, n={n_total}, model_id={model_id}")
        return {
            "model": final_model, "model_id": model_id, "feature_list": list(features.columns),
            "predictions": preds, "y_true": y[idx[n_train:]],
            "feature_importances": final_model.feature_importances_,
        }

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

        return {"predictions": model.predict(predict_features), "model_id": model_id_param}
# @AI_GENERATED: end
