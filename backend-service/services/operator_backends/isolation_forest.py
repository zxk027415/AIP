# @AI_GENERATED
"""
isolation_forest operator backend — 孤立森林异常检测。

基于 sklearn.ensemble.IsolationForest 实现，自动选取输入 DataFrame 的数值列。
支持 fit_predict / predict 双模式：
  fit_predict — 用输入数据训练并预测，可选保存模型到磁盘
  predict     — 从磁盘加载已有模型（通过 model_id）进行预测

参数 (params)
-------------
- mode          (str):   "fit_predict" | "predict"，默认 "fit_predict"
- contamination (float): 异常点比例先验，默认 0.1
- n_estimators  (int):   树数量，默认 100
- random_state  (int):   随机种子，默认 42
- model_id      (str):   predict 模式时指定已保存模型的 ID（必填）

输入 (inputs)
-------------
- data (pd.DataFrame): 待检测数据（含数值列）

返回 (dict)
-----------
- labels (np.ndarray): 预测标签（-1 = 异常，1 = 正常）
- scores (np.ndarray): 异常分数（decision_function 的原始输出；
                        IsolationForest 中越低越异常）
- model_id (str):      fit_predict 模式且保存后，返回模型 ID；否则为空字符串

错误
----
- InputError: 若 data 为空或不是 DataFrame
- InputError: 若 predict 模式下 model_id 未指定
- FileNotFoundError: 若 predict 模式下模型文件不存在
"""
import logging
import os
import pickle
import time
import uuid

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "isolation_forest"

logger = logging.getLogger(__name__)

# 模型保存目录（相对于 backend-service/）
_MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "models",
)
_MODEL_PREFIX = "iforest_"


def _ensure_models_dir() -> None:
    os.makedirs(_MODELS_DIR, exist_ok=True)


def _save_model(model, feature_cols: list) -> str:
    """保存模型到磁盘，返回 model_id。"""
    _ensure_models_dir()
    model_id = f"{_MODEL_PREFIX}{int(time.time())}_{uuid.uuid4().hex[:6]}"
    path = os.path.join(_MODELS_DIR, f"{model_id}.pkl")
    with open(path, "wb") as f:
        pickle.dump({"model": model, "feature_cols": feature_cols}, f)
    logger.info(f"[{OPERATOR_ID}] Model saved: {path}")
    return model_id


def _load_model(model_id: str):
    """从磁盘加载模型，返回 (model, feature_cols)。"""
    _ensure_models_dir()
    path = os.path.join(_MODELS_DIR, f"{model_id}.pkl")
    if not os.path.exists(path):
        available = [
            f[:-4] for f in os.listdir(_MODELS_DIR)
            if f.endswith(".pkl") and f.startswith(_MODEL_PREFIX)
        ]
        raise OperatorExecutionError(
            OPERATOR_ID, "FileNotFoundError",
            f"Model file not found: {path}. Available iforest models: {available}"
        )
    with open(path, "rb") as f:
        payload = pickle.load(f)
    logger.info(f"[{OPERATOR_ID}] Model loaded: {path}")
    return payload["model"], payload.get("feature_cols", [])


def execute(params: dict, inputs: dict) -> dict:
    """
    孤立森林异常检测。

    Args:
        params:
            - mode          (str):   "fit_predict" | "predict"，默认 "fit_predict"
            - contamination (float): 异常比例，默认 0.1
            - n_estimators  (int):   树数，默认 100
            - random_state  (int):   随机种子，默认 42
            - model_id      (str):   predict 模式时必填
            - save_model    (bool):  fit_predict 时是否保存模型，默认 true
        inputs:
            - data (pd.DataFrame): 待检测数据

    Returns:
        {
            "labels":   np.ndarray,  # -1=异常, 1=正常
            "scores":   np.ndarray,  # decision_function 输出，越低越异常
            "model_id": str,         # fit_predict+save 时返回模型 ID，否则 ""
        }
    """
    # ── 解析输入 ──────────────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'data' must be a pandas DataFrame"
        )
    if data.empty:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'data' is empty"
        )

    # ── 解析参数 ──────────────────────────────────────────────────────────────
    mode = str(params.get("mode") or "fit_predict").strip().lower()
    if mode not in ("fit_predict", "predict"):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"Invalid mode '{mode}'. Must be 'fit_predict' or 'predict'"
        )

    try:
        contamination = float(params.get("contamination") or 0.1)
    except (TypeError, ValueError):
        contamination = 0.1

    try:
        n_estimators = int(params.get("n_estimators") or 100)
    except (TypeError, ValueError):
        n_estimators = 100

    try:
        random_state = int(params.get("random_state") or 42)
    except (TypeError, ValueError):
        random_state = 42

    model_id_param = str(params.get("model_id") or "").strip()
    save_model_flag = str(params.get("save_model", "true")).lower() not in ("false", "0", "no")

    # ── 自动选取数值列 ────────────────────────────────────────────────────────
    numeric_df = data.select_dtypes(include=[np.number])
    if numeric_df.empty:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "No numeric columns found in input DataFrame"
        )
    feature_cols = list(numeric_df.columns)
    X = numeric_df.fillna(numeric_df.mean()).values

    # ── fit_predict 模式 ──────────────────────────────────────────────────────
    if mode == "fit_predict":
        clf = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
        )
        clf.fit(X)
        labels: np.ndarray = clf.predict(X).astype(int)   # -1 or 1
        scores: np.ndarray = clf.decision_function(X).astype(float)

        saved_model_id = ""
        if save_model_flag:
            saved_model_id = _save_model(clf, feature_cols)

        n_anomaly = int(np.sum(labels == -1))
        logger.info(
            f"[{OPERATOR_ID}] fit_predict: n_samples={len(X)}, "
            f"contamination={contamination}, anomalies={n_anomaly}, "
            f"model_id={saved_model_id or '(not saved)'}"
        )
        return {"labels": labels, "scores": scores, "model_id": saved_model_id}

    # ── predict 模式 ──────────────────────────────────────────────────────────
    else:
        if not model_id_param:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "predict mode requires params['model_id'] to be set"
            )
        clf, saved_feature_cols = _load_model(model_id_param)

        # 按保存的特征列对齐（若存在）
        if saved_feature_cols:
            present = [c for c in saved_feature_cols if c in numeric_df.columns]
            if present:
                X = numeric_df[present].fillna(numeric_df[present].mean()).values

        labels = clf.predict(X).astype(int)
        scores = clf.decision_function(X).astype(float)

        n_anomaly = int(np.sum(labels == -1))
        logger.info(
            f"[{OPERATOR_ID}] predict: n_samples={len(X)}, "
            f"model_id={model_id_param}, anomalies={n_anomaly}"
        )
        return {"labels": labels, "scores": scores, "model_id": model_id_param}
# @AI_GENERATED: end
