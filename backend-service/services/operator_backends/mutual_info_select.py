# @AI_GENERATED
"""
mutual_info_select operator backend — 互信息特征选择。

按互信息评分排序，选出前 k 个与目标最相关的特征。
"""
import pandas as pd
import numpy as np
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "mutual_info_select"


def execute(params: dict, inputs: dict) -> dict:
    """
    互信息特征选择。

    params:
        - task (str): "classification" | "regression"，默认自动判断
        - top_k (int): 保留前 k 个特征，默认 10
    inputs:
        - features (pd.DataFrame)
        - target (array-like)
    returns:
        {
            "data": pd.DataFrame,       # 只含 top_k 特征列
            "selected_columns": list[str],
            "scores": dict,             # {列名: 互信息得分}
        }
    """
    features = inputs.get("features")
    target = inputs.get("target")
    if features is None or not isinstance(features, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'features' must be a pandas DataFrame")
    if target is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'target' is required")

    try:
        top_k = int(params.get("top_k") or 10)
    except (TypeError, ValueError):
        top_k = 10

    task = str(params.get("task") or "").strip().lower()
    y = np.asarray(target)
    if not task:
        # 自动判断：整数或类别数少 → 分类，浮点 → 回归
        if y.dtype.kind in ("i", "u", "b", "O") and len(np.unique(y)) <= min(20, len(y) // 4):
            task = "classification"
        else:
            task = "regression"

    numeric_features = features.select_dtypes(include="number")
    if numeric_features.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric features found")

    try:
        if task == "classification":
            scores = mutual_info_classif(numeric_features, y, random_state=42)
        else:
            scores = mutual_info_regression(numeric_features, y, random_state=42)
    except Exception as e:
        raise OperatorExecutionError(OPERATOR_ID, "SelectionError", f"Mutual info failed: {e}")

    score_map = dict(zip(numeric_features.columns, scores.tolist()))
    # 按分数降序选 top_k
    sorted_cols = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
    top_k_actual = min(top_k, len(sorted_cols))
    selected = [c for c, _ in sorted_cols[:top_k_actual]]

    result = features[selected].copy()
    logger.info(f"[{OPERATOR_ID}] task={task}, top_k={top_k_actual}, selected={selected}")
    return {
        "data": result,
        "selected_columns": selected,
        "scores": {c: round(float(s), 6) for c, s in score_map.items()},
    }
# @AI_GENERATED: end
