# @AI_GENERATED
"""
iqr_anomaly — IQR 篱笆异常检测。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "iqr_anomaly"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - column (str | None): 单列；为空则对全部数值列按行聚合
        - factor (float): IQR 倍数，默认 1.5（catalog 的 threshold 也可传入作 factor）
    inputs:
        - data (pd.DataFrame)
    returns:
        {"labels": ndarray, "scores": ndarray}  # score = 越界距离 / IQR
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")
    if data.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' is empty")

    raw = params.get("factor", params.get("threshold", 1.5))
    try:
        factor = float(raw if raw is not None else 1.5)
    except (TypeError, ValueError):
        factor = 1.5

    column = params.get("column")
    if column:
        if column not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{column}' not found")
        x = pd.to_numeric(data[column], errors="coerce").astype(float).values
        q1, q3 = np.nanpercentile(x, [25, 75])
        iqr = max(float(q3 - q1), 1e-12)
        low, high = q1 - factor * iqr, q3 + factor * iqr
        scores = np.maximum(low - x, 0.0) / iqr + np.maximum(x - high, 0.0) / iqr
        labels = np.where((x < low) | (x > high), -1, 1).astype(int)
    else:
        numeric = data.select_dtypes(include="number")
        if numeric.empty:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")
        X = numeric.astype(float).values
        q1 = np.nanpercentile(X, 25, axis=0)
        q3 = np.nanpercentile(X, 75, axis=0)
        iqr = np.maximum(q3 - q1, 1e-12)
        low, high = q1 - factor * iqr, q3 + factor * iqr
        below = np.maximum(low - X, 0.0) / iqr
        above = np.maximum(X - high, 0.0) / iqr
        scores = np.nanmax(below + above, axis=1)
        labels = np.where(np.any((X < low) | (X > high), axis=1), -1, 1).astype(int)

    scores = np.nan_to_num(scores, nan=0.0)
    logger.info(f"[{OPERATOR_ID}] factor={factor}, anomalies={int(np.sum(labels == -1))}")
    return {"labels": labels, "scores": scores}
# @AI_GENERATED: end
