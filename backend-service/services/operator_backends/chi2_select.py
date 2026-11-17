# @AI_GENERATED
"""
chi2_select — 卡方检验特征选择（分类任务）。

要求特征非负；若存在负值则平移到最小值为 0。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.feature_selection import SelectKBest, chi2

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "chi2_select"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - k (int): 保留特征数，默认 10
    inputs:
        - features (pd.DataFrame)
        - target (array-like)
    returns:
        {"data": pd.DataFrame, "selected_columns": list[str], "scores": dict}
    """
    features = inputs.get("features")
    target = inputs.get("target")
    if features is None or not isinstance(features, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'features' must be a pandas DataFrame")
    if target is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'target' is required")
    if features.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "features is empty")

    try:
        k = int(params.get("k") or 10)
    except (TypeError, ValueError):
        k = 10

    numeric = features.select_dtypes(include="number").copy()
    if numeric.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric features found")

    # chi2 要求非负
    min_vals = numeric.min()
    shift = min_vals.clip(upper=0)
    numeric = numeric - shift

    y = np.asarray(target)
    if len(y) != len(numeric):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"features rows ({len(numeric)}) != target length ({len(y)})",
        )

    k_eff = min(k, numeric.shape[1])
    selector = SelectKBest(score_func=chi2, k=k_eff)
    try:
        selector.fit(numeric.fillna(0), y)
    except Exception as e:
        raise OperatorExecutionError(OPERATOR_ID, "SelectionError", f"chi2 selection failed: {e}")

    mask = selector.get_support()
    selected = [c for c, m in zip(numeric.columns, mask) if m]
    scores = {
        c: float(s) if np.isfinite(s) else 0.0
        for c, s in zip(numeric.columns, selector.scores_)
    }
    result = features[selected].copy()
    logger.info(f"[{OPERATOR_ID}] k={k_eff}, selected={selected}")
    return {"data": result, "selected_columns": selected, "scores": scores}
# @AI_GENERATED: end
