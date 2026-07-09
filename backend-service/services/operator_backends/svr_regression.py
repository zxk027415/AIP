# @AI_GENERATED
"""
svr_regression operator backend — 支持向量回归 (SVR)。

train/predict 双模式。
"""
import logging
import os
import pickle
import time
import uuid

import numpy as np
import pandas as pd
from sklearn.svm import SVR

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "svr_regression"
logger = logging.getLogger(__name__)
_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "models")


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def execute(params: dict, inputs: dict) -> dict:
    mode = str(params.get("mode") or "train").strip().lower()
    if mode not in ("train", "predict"):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid mode '{mode}'")

    kernel = str(params.get("kernel") or "rbf").strip().lower()
    try:
        C = float(params.get("C") or 1.0)
    except (TypeError, ValueError):
        C = 1.0
    try:
        epsilon = float(params.get("epsilon") or 0.1)
    except (TypeError, ValueError):
        epsilon = 0.1

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

        eval_model = SVR(kernel=kernel, C=C, epsilon=epsilon)
        eval_model.fit(features.iloc[idx[:n_train]], y[idx[:n_train]])
        preds = eval_model.predict(features.iloc[idx[n_train:]])

        final_model = SVR(kernel=kernel, C=C, epsilon=epsilon)
        final_model.fit(features, y)

        _ensure_models_dir()
        model_id = f"svr_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        with open(os.path.join(_MODELS_DIR, f"{model_id}.pkl"), "wb") as f:
            pickle.dump({"model": final_model, "feature_list": list(features.columns)}, f)

        logger.info(f"[{OPERATOR_ID}] train: kernel={kernel}, C={C}, model_id={model_id}")
        return {"model": final_model, "model_id": model_id, "feature_list": list(features.columns),
                "predictions": preds, "y_true": y[idx[n_train:]]}

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
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "predict requires DataFrame")
        return {"predictions": model.predict(predict_features), "model_id": model_id_param}
# @AI_GENERATED: end
