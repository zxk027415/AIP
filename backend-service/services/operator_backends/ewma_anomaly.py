# @AI_GENERATED
"""
ewma_anomaly — EWMA 控制图式异常检测（残差相对历史波动）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "ewma_anomaly"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - column (str): 目标列，默认第一个数值列
        - span (int): ewm span，默认 20
        - threshold (float): |残差|/滚动std 阈值，默认 3.0
    inputs:
        - data (pd.DataFrame)
    returns:
        {"labels": ndarray, "scores": ndarray}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")
    if data.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' is empty")

    column = params.get("column")
    if not column:
        num_cols = list(data.select_dtypes(include="number").columns)
        if not num_cols:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")
        column = num_cols[0]
    if column not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{column}' not found")

    try:
        span = int(params.get("span") or 20)
        threshold = float(params.get("threshold") if params.get("threshold") is not None else 3.0)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid numeric params: {e}")
    span = max(2, span)

    s = pd.to_numeric(data[column], errors="coerce").astype(float)
    ewma = s.ewm(span=span, adjust=False).mean()
    resid = s - ewma
    roll_std = resid.ewm(span=span, adjust=False).std(bias=False)
    scale = roll_std.replace(0, np.nan).fillna(resid.std() or 1.0)
    scores = (resid.abs() / scale).fillna(0.0).to_numpy(dtype=float)
    labels = np.where(scores >= threshold, -1, 1).astype(int)

    logger.info(f"[{OPERATOR_ID}] column={column}, span={span}, anomalies={int(np.sum(labels == -1))}")
    return {"labels": labels, "scores": scores}
# @AI_GENERATED: end
