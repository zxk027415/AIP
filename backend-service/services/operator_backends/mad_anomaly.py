# @AI_GENERATED
"""
mad_anomaly — 中位数绝对偏差（MAD）异常检测。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "mad_anomaly"

# 正态分布一致性常数：MAD ≈ 0.6745 * sigma
_MAD_C = 0.6745


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - column (str | None)
        - threshold (float): 修正 z 阈值，默认 3.0
    inputs:
        - data (pd.DataFrame)
    returns:
        {"labels": ndarray, "scores": ndarray}  # score = |x-median| / (MAD/0.6745)
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")
    if data.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' is empty")

    try:
        threshold = float(params.get("threshold") if params.get("threshold") is not None else 3.0)
    except (TypeError, ValueError):
        threshold = 3.0

    column = params.get("column")
    if column:
        if column not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{column}' not found")
        x = pd.to_numeric(data[column], errors="coerce").astype(float).values
        med = np.nanmedian(x)
        mad = np.nanmedian(np.abs(x - med))
        scale = (mad / _MAD_C) if mad > 1e-12 else 1.0
        scores = np.abs(x - med) / scale
    else:
        numeric = data.select_dtypes(include="number")
        if numeric.empty:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")
        X = numeric.astype(float).values
        med = np.nanmedian(X, axis=0)
        mad = np.nanmedian(np.abs(X - med), axis=0)
        scale = np.where(mad > 1e-12, mad / _MAD_C, 1.0)
        scores = np.nanmax(np.abs(X - med) / scale, axis=1)

    scores = np.nan_to_num(scores, nan=0.0)
    labels = np.where(scores >= threshold, -1, 1).astype(int)
    logger.info(f"[{OPERATOR_ID}] threshold={threshold}, anomalies={int(np.sum(labels == -1))}")
    return {"labels": labels, "scores": scores}
# @AI_GENERATED: end
