# @AI_GENERATED
"""
svm_classifier operator backend — 支持向量机分类器（训练 + 预测）。

遵循 random_forest_classifier.py 的 train/predict 模式。
使用 SVC(probability=True) 以支持 predict_proba / 置信度输出。

模式：
  train   — fit SVC，80/20 holdout 评估，全量数据重训后保存模型，
             返回 model + model_id + feature_list + holdout predictions/y_true
  predict — 从 model_id 加载模型或接受内存 model 对象执行推理，返回 predictions + confidences

校验：
  - train 模式：target 唯一类别数 < 2 时抛 InputError
  - train 模式：features 不是 pd.DataFrame 时抛 InputError
"""
import json
import logging
import os
import pickle
import time
import uuid

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix as sk_confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.svm import SVC

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "svm_classifier"

logger = logging.getLogger(__name__)

# 模型保存目录（相对于 backend-service/）
_MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "models",
)


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)


def _save_model(clf, feature_list: list, metrics: dict = None) -> str:
    """序列化模型到磁盘，返回 model_id（文件名不含扩展名）。"""
    _ensure_models_dir()
    model_id = f"svm_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    path = os.path.join(_MODELS_DIR, f"{model_id}.pkl")
    payload = {"model": clf, "feature_list": feature_list}
    with open(path, "wb") as f:
        pickle.dump(payload, f)
    logger.info(f"[{OPERATOR_ID}] Model saved: {path}")
    if metrics:
        metrics_path = os.path.join(_MODELS_DIR, f"{model_id}_metrics.json")
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        logger.info(f"[{OPERATOR_ID}] Metrics saved: {metrics_path}")
    return model_id


def _load_model(model_id: str, model_path: str = ""):
    """从磁盘加载模型，返回 (clf, feature_list)。

    优先级：
      1. model_path 非空 → 直接加载该路径的 pkl 文件
      2. model_id == "latest" → 自动加载 data/models/ 下最新的 svm_ 模型
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
            [f for f in os.listdir(_MODELS_DIR) if f.startswith("svm_") and f.endswith(".pkl")],
            reverse=True,
        )
        if not pkls:
            pkls = sorted(
                [f for f in os.listdir(_MODELS_DIR) if f.endswith(".pkl")],
                reverse=True,
            )
        if not pkls:
            raise OperatorExecutionError(
                OPERATOR_ID, "FileNotFoundError",
                f"No saved models found in {_MODELS_DIR}. Run the training pipeline first."
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


def _load_model_metrics(model_id: str) -> dict:
    """加载模型对应的评估指标 JSON（训练时保存）。找不到返回空 dict。"""
    _ensure_models_dir()
    if model_id.strip().lower() == "latest":
        pkls = sorted(
            [f for f in os.listdir(_MODELS_DIR) if f.startswith("svm_") and f.endswith(".pkl")],
            reverse=True,
        )
        if pkls:
            model_id = pkls[0][:-4]
    metrics_path = os.path.join(_MODELS_DIR, f"{model_id}_metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def execute(params: dict, inputs: dict) -> dict:
    """
    支持向量机分类器。

    Args:
        params:
            - mode       (str):   "train" | "predict"，默认 "train"
            - kernel     (str):   核函数 "linear" | "rbf" | "poly"，默认 "rbf"
            - C          (float): 正则化参数，默认 1.0
            - save_model (bool):  train 模式是否保存模型，默认 true
            - model_id   (str):   predict 模式指定已保存的模型 ID
            - model_path (str):   predict 模式直接指定模型文件路径
        inputs (train mode):
            - features (pd.DataFrame): 训练特征矩阵
            - target   (array-like):   训练标签
        inputs (predict mode):
            - model            (SVC, optional): 已训练模型对象
            - predict_features (pd.DataFrame): 预测特征矩阵（也接受 'data'）

    Returns (train mode):
        {
            "model":               SVC,
            "model_id":            str,
            "feature_list":        list[str],
            "predictions":         np.ndarray,   # holdout 20% 预测结果
            "y_true":              np.ndarray,
            "feature_importances": np.ndarray,   # linear kernel: |coef_| norm; others: zeros
        }
    Returns (predict mode):
        {
            "predictions":  np.ndarray,
            "confidences":  np.ndarray,  # 最大类概率（predict_proba）
            "model_id":     str,
        }
    """
    # ── 解析参数 ──────────────────────────────────────────────────────────────
    mode = str(params.get("mode") or "train").strip().lower()
    if mode not in ("train", "predict"):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"Invalid mode '{mode}'. Must be 'train' or 'predict'"
        )

    kernel = str(params.get("kernel") or "rbf").strip().lower()
    if kernel not in ("linear", "rbf", "poly", "sigmoid"):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"Invalid kernel '{kernel}'. Must be one of: linear, rbf, poly, sigmoid"
        )

    try:
        C = float(params.get("C") or 1.0)
    except (TypeError, ValueError):
        C = 1.0

    save_model_flag = str(params.get("save_model", "true")).lower() not in ("false", "0", "no")
    model_id_param = params.get("model_id") or ""
    model_path_param = params.get("model_path") or ""

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

        y = np.asarray(target)
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

        unique_classes = np.unique(y)
        if len(unique_classes) < 2:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                f"target must have at least 2 unique classes, got {len(unique_classes)}: {unique_classes.tolist()}"
            )

        # 80/20 shuffle split
        n_total = len(features)
        random_state = 42
        shuffle_idx = np.random.RandomState(random_state).permutation(n_total)
        features_shuffled = features.iloc[shuffle_idx].reset_index(drop=True)
        y_shuffled = y[shuffle_idx]

        n_train = int(n_total * 0.8)
        X_train = features_shuffled.iloc[:n_train]
        X_test = features_shuffled.iloc[n_train:]
        y_train = y_shuffled[:n_train]
        y_test = y_shuffled[n_train:]

        clf_eval = SVC(kernel=kernel, C=C, probability=True, random_state=random_state)
        clf_eval.fit(X_train, y_train)
        predictions_test = clf_eval.predict(X_test)

        # feature_importances: linear kernel 可用 coef_，其他核为零向量
        if kernel == "linear" and hasattr(clf_eval, "coef_"):
            coef = clf_eval.coef_
            feature_importances = np.linalg.norm(coef, axis=0)
        else:
            feature_importances = np.zeros(features.shape[1])

        # 全量重训最终模型（部署用）
        clf = SVC(kernel=kernel, C=C, probability=True, random_state=random_state)
        clf.fit(features, y)

        feature_list = inputs.get("feature_list") or list(features.columns)

        model_id = ""
        if save_model_flag:
            labels_sorted = sorted(set(y_test.tolist()) | set(predictions_test.tolist()))
            cm = sk_confusion_matrix(y_test, predictions_test, labels=labels_sorted)
            eval_metrics = {
                "accuracy": round(float(accuracy_score(y_test, predictions_test)), 4),
                "precision": round(float(precision_score(y_test, predictions_test, average="macro", zero_division=0)), 4),
                "recall": round(float(recall_score(y_test, predictions_test, average="macro", zero_division=0)), 4),
                "f1": round(float(f1_score(y_test, predictions_test, average="macro", zero_division=0)), 4),
                "confusion_matrix": {
                    "labels": [str(x) for x in labels_sorted],
                    "data": cm.tolist(),
                },
                "classification_report": classification_report(
                    y_test, predictions_test, labels=labels_sorted, zero_division=0
                ),
            }
            model_id = _save_model(clf, feature_list, metrics=eval_metrics)

        logger.info(
            f"[{OPERATOR_ID}] train: kernel={kernel}, C={C}, "
            f"n_samples={n_total} (train={n_train}, test={n_total - n_train}), "
            f"n_features={features.shape[1]}, model_id={model_id or '(not saved)'}"
        )

        return {
            "model": clf,
            "model_id": model_id,
            "feature_list": feature_list,
            "predictions": predictions_test,
            "y_true": y_test,
            "feature_importances": feature_importances,
        }

    # ── 预测模式 ──────────────────────────────────────────────────────────────
    else:  # predict
        model = inputs.get("model")
        loaded_feature_list = []

        resolved_model_id = model_id_param
        if model is None and (model_id_param or model_path_param):
            model, loaded_feature_list = _load_model(model_id_param or "latest", model_path_param)
            if model_id_param.strip().lower() == "latest":
                _ensure_models_dir()
                pkls = sorted(
                    [f for f in os.listdir(_MODELS_DIR) if f.startswith("svm_") and f.endswith(".pkl")],
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

        if loaded_feature_list:
            present = [f for f in loaded_feature_list if f in predict_features.columns]
            if present:
                predict_features = predict_features[present]

        predictions = model.predict(predict_features)

        confidences = None
        try:
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(predict_features)
                confidences = np.max(proba, axis=1).astype(float)
        except Exception as _e:
            logger.warning(f"[{OPERATOR_ID}] predict_proba 失败，置信度置空: {_e}")

        saved_metrics = {}
        if model_id_param:
            saved_metrics = _load_model_metrics(model_id_param)

        logger.info(
            f"[{OPERATOR_ID}] predict: n_samples={len(predict_features)}, "
            f"model_id={model_id_param or '(in-memory)'}"
        )

        result = {"predictions": predictions, "model_metrics": saved_metrics, "model_id": resolved_model_id}
        if confidences is not None:
            result["confidences"] = confidences
        return result
# @AI_GENERATED: end
