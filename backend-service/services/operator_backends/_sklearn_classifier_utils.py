# @AI_GENERATED
"""sklearn 风格 train/predict 分类器共享工具（_ 开头，不注册）。"""
from __future__ import annotations

import os
import pickle
import time
import uuid
from typing import Callable, Optional

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError

_MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "models",
)


def ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def _to_bool(v, default: bool = True) -> bool:
    if v is None:
        return default
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "on")
    return bool(v)


def run_sklearn_classifier(
    operator_id: str,
    params: dict,
    inputs: dict,
    model_factory: Callable[[], object],
    *,
    model_prefix: str,
    importance_attr: Optional[str] = "feature_importances_",
) -> dict:
    """统一 train/predict：holdout 评估 + 全量重训 + 可选落盘。"""
    mode = str(params.get("mode") or "train").strip().lower()
    if mode not in ("train", "predict"):
        raise OperatorExecutionError(operator_id, "ParameterError", f"Invalid mode '{mode}'")

    if mode == "train":
        features = inputs.get("features")
        target = inputs.get("target")
        if features is None or not isinstance(features, pd.DataFrame):
            raise OperatorExecutionError(operator_id, "InputError", "train requires 'features' as DataFrame")
        if target is None:
            raise OperatorExecutionError(operator_id, "InputError", "train requires 'target'")

        y = np.asarray(target)
        if len(np.unique(y)) < 2:
            raise OperatorExecutionError(operator_id, "InputError", "target must have >= 2 classes")

        n_total = len(features)
        idx = np.random.RandomState(42).permutation(n_total)
        n_train = max(int(n_total * 0.8), 1)

        clf_eval = model_factory()
        clf_eval.fit(features.iloc[idx[:n_train]], y[idx[:n_train]])
        preds = clf_eval.predict(features.iloc[idx[n_train:]])

        clf_full = model_factory()
        clf_full.fit(features, y)

        save_model = _to_bool(params.get("save_model"), default=True)
        model_id = f"{model_prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        if save_model:
            ensure_models_dir()
            with open(os.path.join(_MODELS_DIR, f"{model_id}.pkl"), "wb") as f:
                pickle.dump({"model": clf_full, "feature_list": list(features.columns)}, f)

        if importance_attr and hasattr(clf_full, importance_attr):
            importances = np.asarray(getattr(clf_full, importance_attr), dtype=float)
        else:
            importances = np.zeros(features.shape[1], dtype=float)

        return {
            "model": clf_full,
            "model_id": model_id,
            "feature_list": list(features.columns),
            "predictions": preds,
            "y_true": y[idx[n_train:]],
            "feature_importances": importances,
        }

    model = inputs.get("model")
    model_id_param = params.get("model_id") or ""
    if model is None and model_id_param:
        ensure_models_dir()
        path = os.path.join(_MODELS_DIR, f"{model_id_param}.pkl")
        if not os.path.exists(path):
            raise OperatorExecutionError(operator_id, "FileNotFoundError", f"Model not found: {path}")
        with open(path, "rb") as f:
            payload = pickle.load(f)
        model = payload["model"]
    if model is None:
        raise OperatorExecutionError(operator_id, "InputError", "predict requires model or model_id")

    predict_features = inputs.get("predict_features")
    if predict_features is None:
        predict_features = inputs.get("data")
    if predict_features is None or not isinstance(predict_features, pd.DataFrame):
        raise OperatorExecutionError(
            operator_id, "InputError", "predict requires 'predict_features' as DataFrame",
        )
    return {"predictions": model.predict(predict_features), "model_id": model_id_param}
# @AI_GENERATED: end
