# @AI_GENERATED
"""
xgboost_classifier operator backend — XGBoost 分类器（train/predict）。
"""
import logging
import os
import pickle
import time
import uuid

import numpy as np
import pandas as pd

try:
    from xgboost import XGBClassifier
except ImportError:
    XGBClassifier = None  # type: ignore[assignment]

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "xgboost_classifier"
logger = logging.getLogger(__name__)
_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "models")


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def execute(params: dict, inputs: dict) -> dict:
    if XGBClassifier is None:
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

        y = np.asarray(target)
        classes = np.unique(y)
        if len(classes) < 2:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "target must have >= 2 classes")

        # XGBoost 需要类别标签从 0 开始的连续整数
        label_map = {c: i for i, c in enumerate(classes)}
        y_encoded = np.array([label_map[v] for v in y])

        n_total = len(features)
        idx = np.random.RandomState(42).permutation(n_total)
        n_train = int(n_total * 0.8)

        clf_eval = XGBClassifier(
            n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate,
            random_state=42, use_label_encoder=False, eval_metric="logloss",
        )
        clf_eval.fit(features.iloc[idx[:n_train]], y_encoded[idx[:n_train]])
        preds_encoded = clf_eval.predict(features.iloc[idx[n_train:]])

        inv_map = {i: c for c, i in label_map.items()}
        preds = np.array([inv_map[p] for p in preds_encoded])

        clf_full = XGBClassifier(
            n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate,
            random_state=42, use_label_encoder=False, eval_metric="logloss",
        )
        clf_full.fit(features, y_encoded)

        _ensure_models_dir()
        model_id = f"xgbc_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        with open(os.path.join(_MODELS_DIR, f"{model_id}.pkl"), "wb") as f:
            pickle.dump({"model": clf_full, "feature_list": list(features.columns), "label_map": label_map}, f)

        logger.info(f"[{OPERATOR_ID}] train: n_estimators={n_estimators}, n={n_total}, model_id={model_id}")
        return {
            "model": clf_full, "model_id": model_id, "feature_list": list(features.columns),
            "predictions": preds, "y_true": y[idx[n_train:]],
            "feature_importances": clf_full.feature_importances_,
        }

    else:
        model = inputs.get("model")
        model_id_param = params.get("model_id") or ""
        label_map = None
        if model is None and model_id_param:
            _ensure_models_dir()
            path = os.path.join(_MODELS_DIR, f"{model_id_param}.pkl")
            if not os.path.exists(path):
                raise OperatorExecutionError(OPERATOR_ID, "FileNotFoundError", f"Model not found: {path}")
            with open(path, "rb") as f:
                payload = pickle.load(f)
            model = payload["model"]
            label_map = payload.get("label_map")
        if model is None:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "predict requires model or model_id")

        predict_features = inputs.get("predict_features")
        if predict_features is None:
            predict_features = inputs.get("data")
        if predict_features is None or not isinstance(predict_features, pd.DataFrame):
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "predict requires 'predict_features' as DataFrame")

        preds_encoded = model.predict(predict_features)
        if label_map:
            inv_map = {i: c for c, i in label_map.items()}
            preds = np.array([inv_map.get(int(p), p) for p in preds_encoded])
        else:
            preds = preds_encoded
        return {"predictions": preds, "model_id": model_id_param}
# @AI_GENERATED: end
