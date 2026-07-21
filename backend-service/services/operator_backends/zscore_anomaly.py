# @AI_GENERATED
"""
zscore_anomaly — Z-Score 规则异常检测。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "zscore_anomaly"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - column (str | None): 单列；为空则对全部数值列按行取最大 |z|
        - threshold (float): |z| 阈值，默认 3.0
    inputs:
        - data (pd.DataFrame)
    returns:
        {"labels": ndarray (-1 异常 / 1 正常), "scores": ndarray (|z|)}
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
        mu, sigma = np.nanmean(x), np.nanstd(x)
        sigma = sigma if sigma > 1e-12 else 1.0
        scores = np.abs((x - mu) / sigma)
    else:
        numeric = data.select_dtypes(include="number")
        if numeric.empty:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")
        X = numeric.astype(float).values
        mu = np.nanmean(X, axis=0)
        sigma = np.nanstd(X, axis=0)
        sigma = np.where(sigma > 1e-12, sigma, 1.0)
        z = np.abs((X - mu) / sigma)
        scores = np.nanmax(z, axis=1)

    scores = np.nan_to_num(scores, nan=0.0)
    labels = np.where(scores >= threshold, -1, 1).astype(int)
    logger.info(f"[{OPERATOR_ID}] threshold={threshold}, anomalies={int(np.sum(labels == -1))}")
    return {"labels": labels, "scores": scores}
# @AI_GENERATED: end
