# @AI_GENERATED
"""
lasso_regression operator backend — Lasso 回归（训练 + 预测）。

使用 sklearn.linear_model.Lasso 实现 train/predict 双模式。

模式：
  train   — fit Lasso（可配置 alpha），80/20 holdout 评估，保存全量模型到磁盘，
             返回 model + model_id + feature_list + coefficients + intercept
  predict — 从 model_id 加载模型或接受内存 model 对象执行推理
"""
import logging
import os
import pickle
import time
import uuid

import numpy as np
import pandas as pd
from sklearn.linear_model import Lasso

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "lasso_regression"

logger = logging.getLogger(__name__)

# 模型保存目录（相对于 backend-service/）
_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "models")


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def _save_model(model, feature_list: list) -> str:
    """序列化模型到磁盘，返回 model_id（文件名不含扩展名）。"""
    _ensure_models_dir()
    model_id = f"lasso_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    path = os.path.join(_MODELS_DIR, f"{model_id}.pkl")
    payload = {"model": model, "feature_list": feature_list}
    with open(path, "wb") as f:
        pickle.dump(payload, f)
    logger.info(f"[{OPERATOR_ID}] Model saved: {path}")
    return model_id


def _load_model(model_id: str, model_path: str = ""):
    """从磁盘加载模型，返回 (model, feature_list)。

    优先级：
      1. model_path 非空 → 直接加载该路径的 pkl 文件
      2. model_id == "latest" → 自动加载 data/models/ 下前缀匹配的最新模型
      3. model_id 为具体 ID → 加载 data/models/{model_id}.pkl
    """
    if model_path and model_path.strip():
        path = model_path.strip()
        if not os.path.exists(path):
            raise OperatorExecutionError(
                OPERATOR_ID, "FileNotFoundError",
                f"指定的模型路径不存在: {path}"
            )
        with open(path, "rb") as f:
            payload = pickle.load(f)
        logger.info(f"[{OPERATOR_ID}] Model loaded from explicit path: {path}")
        return payload["model"], payload.get("feature_list", [])

    _ensure_models_dir()
    if model_id.strip().lower() == "latest":
        pkls = sorted(
            [f for f in os.listdir(_MODELS_DIR) if f.startswith("lasso_") and f.endswith(".pkl")],
            reverse=True,
        )
        if not pkls:
            raise OperatorExecutionError(
                OPERATOR_ID, "FileNotFoundError",
                f"No saved lasso_regression models found in {_MODELS_DIR}. Run training first."
            )
        model_id = pkls[0][:-4]
        logger.info(f"[{OPERATOR_ID}] 'latest' resolved to: {model_id}")

    path = os.path.join(_MODELS_DIR, f"{model_id}.pkl")
    if not os.path.exists(path):
        raise OperatorExecutionError(
            OPERATOR_ID, "FileNotFoundError",
            f"Model file not found: {path}. "
            f"Available models: {[f[:-4] for f in os.listdir(_MODELS_DIR) if f.endswith('.pkl')]}"
        )
    with open(path, "rb") as f:
        payload = pickle.load(f)
    return payload["model"], payload.get("feature_list", [])


def execute(params: dict, inputs: dict) -> dict:
    """
    Lasso 回归算子。

    Args:
        params:
            - mode       (str):   "train" | "predict"，默认 "train"
            - alpha      (float): L1 正则化强度，默认 1.0
            - model_id   (str):   predict 模式时指定已保存的模型 ID（或直接传 model 对象）
            - model_path (str):   predict 模式时指定模型文件完整路径（优先于 model_id）
        inputs (train mode):
            - features   (pd.DataFrame): 训练特征矩阵
            - target     (array-like):   训练标签（数值型）
        inputs (predict mode):
            - model              (Lasso, optional): 已训练模型对象
            - predict_features   (pd.DataFrame): 预测特征矩阵（或 'data'）

    Returns (train mode):
        {
            "model":        Lasso,
            "model_id":     str,
            "feature_list": list[str],
            "predictions":  np.ndarray,   # holdout 20% 预测值
            "y_true":       np.ndarray,   # holdout 20% 真实值
            "coefficients": np.ndarray,   # 来自 .coef_
            "intercept":    float,        # 来自 .intercept_
        }
    Returns (predict mode):
        {
            "predictions": np.ndarray,
            "model_id":    str,
        }
    """
    # ── 解析参数 ──────────────────────────────────────────────────────────────
    mode = str(params.get("mode") or "train").strip().lower()
    if mode not in ("train", "predict"):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"Invalid mode '{mode}'. Must be 'train' or 'predict'"
        )

    try:
        alpha = float(params.get("alpha") if params.get("alpha") is not None else 1.0)
    except (TypeError, ValueError):
        alpha = 1.0

    model_id_param = str(params.get("model_id") or "").strip()
    model_path_param = str(params.get("model_path") or "").strip()

    # ── 训练模式 ──────────────────────────────────────────────────────────────
    if mode == "train":
        features = inputs.get("features")
        target = inputs.get("target")

        if features is None or not isinstance(features, pd.DataFrame):
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "train mode requires input 'features' as pd.DataFrame"
            )
        if target is None:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "train mode requires input 'target'"
            )

        # 验证 target 为数值类型
        try:
            y = np.asarray(target, dtype=float)
        except (ValueError, TypeError) as exc:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                f"target contains non-numeric values: {exc}"
            )

        if len(features) != len(y):
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                f"features rows ({len(features)}) != target length ({len(y)})"
            )
        if len(features) == 0:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "features is empty"
            )

        # 80/20 shuffle split（RandomState(42) 固定种子）
        n_total = len(features)
        shuffle_idx = np.random.RandomState(42).permutation(n_total)
        features_shuffled = features.iloc[shuffle_idx].reset_index(drop=True)
        y_shuffled = y[shuffle_idx]

        n_train = int(n_total * 0.8)
        X_train = features_shuffled.iloc[:n_train]
        X_test = features_shuffled.iloc[n_train:]
        y_train = y_shuffled[:n_train]
        y_test = y_shuffled[n_train:]

        # 评估用模型（holdout）
        eval_model = Lasso(alpha=alpha)
        eval_model.fit(X_train, y_train)
        predictions_test = eval_model.predict(X_test)

        # 全量数据重训（部署/保存用）
        final_model = Lasso(alpha=alpha)
        final_model.fit(features, y)

        feature_list = list(features.columns)
        model_id = _save_model(final_model, feature_list)

        logger.info(
            f"[{OPERATOR_ID}] train: alpha={alpha}, n_samples={n_total} "
            f"(train={n_train}, test={n_total - n_train}), "
            f"n_features={features.shape[1]}, model_id={model_id}"
        )

        return {
            "model": final_model,
            "model_id": model_id,
            "feature_list": feature_list,
            "predictions": predictions_test,
            "y_true": y_test,
            "coefficients": final_model.coef_,
            "intercept": float(final_model.intercept_),
        }

    # ── 预测模式 ──────────────────────────────────────────────────────────────
    else:  # predict
        model = inputs.get("model")
        loaded_feature_list = []
        resolved_model_id = model_id_param

        if model is None and (model_id_param or model_path_param):
            model, loaded_feature_list = _load_model(
                model_id_param or "latest", model_path_param
            )
            if model_id_param.strip().lower() == "latest":
                _ensure_models_dir()
                pkls = sorted(
                    [f for f in os.listdir(_MODELS_DIR) if f.startswith("lasso_") and f.endswith(".pkl")],
                    reverse=True,
                )
                if pkls:
                    resolved_model_id = pkls[0][:-4]
            logger.info(f"[{OPERATOR_ID}] Loaded model from disk: {resolved_model_id}")

        if model is None:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "predict mode requires either inputs['model'] or params['model_id']"
            )

        predict_features = (
            inputs.get("predict_features")
            if inputs.get("predict_features") is not None
            else inputs.get("data")
        )

        if predict_features is None or not isinstance(predict_features, pd.DataFrame):
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "predict mode requires input 'predict_features' (or 'data') as pd.DataFrame"
            )
        if len(predict_features) == 0:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "predict_features is empty"
            )

        # 按训练时的 feature_list 对齐列
        if loaded_feature_list:
            present = [f for f in loaded_feature_list if f in predict_features.columns]
            if present:
                predict_features = predict_features[present]

        predictions = model.predict(predict_features)

        logger.info(
            f"[{OPERATOR_ID}] predict: n_samples={len(predict_features)}, "
            f"model_id={model_id_param or '(in-memory)'}"
        )

        return {
            "predictions": predictions,
            "model_id": resolved_model_id,
        }
# @AI_GENERATED: end
