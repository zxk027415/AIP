# @AI_GENERATED
"""
naive_bayes_classifier operator backend — 朴素贝叶斯分类器（train/predict）。

使用 sklearn.naive_bayes.GaussianNB，假设特征服从高斯分布。
"""
import logging
import os
import pickle
import time
import uuid

import numpy as np
import pandas as pd
from sklearn.naive_bayes import GaussianNB

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "naive_bayes_classifier"
logger = logging.getLogger(__name__)
_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "models")


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def execute(params: dict, inputs: dict) -> dict:
    mode = str(params.get("mode") or "train").strip().lower()
    if mode not in ("train", "predict"):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid mode '{mode}'")

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

        clf_eval = GaussianNB()
        clf_eval.fit(features.iloc[idx[:n_train]], y[idx[:n_train]])
        preds = clf_eval.predict(features.iloc[idx[n_train:]])

        clf_full = GaussianNB()
        clf_full.fit(features, y)

        _ensure_models_dir()
        model_id = f"nb_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        with open(os.path.join(_MODELS_DIR, f"{model_id}.pkl"), "wb") as f:
            pickle.dump({"model": clf_full, "feature_list": list(features.columns)}, f)

        logger.info(f"[{OPERATOR_ID}] train: n={n_total}, model_id={model_id}")
        return {
            "model": clf_full, "model_id": model_id, "feature_list": list(features.columns),
            "predictions": preds, "y_true": y[idx[n_train:]],
            # NB 无 feature_importances_，返回零向量占位
            "feature_importances": np.zeros(features.shape[1]),
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
