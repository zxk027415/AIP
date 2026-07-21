# @AI_GENERATED
"""
autocorrelation_features — 序列 ACF/PACF 特征（负荷/光伏时序诊断）。

对指定数值列计算全局自相关与偏自相关，返回一行特征 DataFrame。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "autocorrelation_features"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - column (str): 目标列，默认取第一个数值列
        - nlags (int): 最大滞后，默认 24
        - include_pacf (bool): 是否计算 PACF，默认 True
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}  # 一行：acf_1..acf_k [, pacf_1..]
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
        nlags = int(params.get("nlags") or 24)
    except (TypeError, ValueError):
        nlags = 24
    nlags = max(1, nlags)
    include_pacf = str(params.get("include_pacf", "true")).lower() not in ("false", "0", "no")

    series = pd.to_numeric(data[column], errors="coerce").dropna().astype(float).values
    if len(series) < nlags + 2:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"Need at least nlags+2={nlags + 2} points, got {len(series)}",
        )

    try:
        from statsmodels.tsa.stattools import acf, pacf
    except ImportError as e:
        raise OperatorExecutionError(OPERATOR_ID, "DependencyError", f"statsmodels required: {e}")

    acf_vals = acf(series, nlags=nlags, fft=True)
    feat = {f"acf_{i}": float(np.nan_to_num(acf_vals[i], nan=0.0)) for i in range(1, nlags + 1)}
    if include_pacf:
        # pacf 在短序列/奇异矩阵上可能数值警告；method 选 ywm 更稳
        try:
            pacf_vals = pacf(series, nlags=nlags, method="ywm")
        except Exception:
            pacf_vals = np.zeros(nlags + 1)
        for i in range(1, nlags + 1):
            feat[f"pacf_{i}"] = float(np.nan_to_num(pacf_vals[i], nan=0.0))

    out = pd.DataFrame([feat])
    logger.info(f"[{OPERATOR_ID}] column={column}, nlags={nlags}, features={out.shape[1]}")
    return {"data": out}
# @AI_GENERATED: end
