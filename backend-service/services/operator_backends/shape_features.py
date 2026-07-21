# @AI_GENERATED
"""
shape_features — 一维波形形态特征（时序语义，非计算机视觉）。

用于负荷曲线 / 光伏电流电压窗口：峰峰值、偏度、峰度、过零率、RMS 等。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "shape_features"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - column (str): 目标列，默认第一个数值列
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}  # 一行形态特征
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

    x = pd.to_numeric(data[column], errors="coerce").dropna().astype(float).values
    if len(x) < 3:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", f"Need >=3 points, got {len(x)}")

    dx = np.diff(x)
    zero_crossings = int(np.sum((x[:-1] * x[1:]) < 0))
    skew = float(stats.skew(x, bias=False))
    kurt = float(stats.kurtosis(x, bias=False))
    if not np.isfinite(skew):
        skew = 0.0
    if not np.isfinite(kurt):
        kurt = 0.0
    out = pd.DataFrame([{
        "shape_mean": float(np.mean(x)),
        "shape_std": float(np.std(x)),
        "shape_min": float(np.min(x)),
        "shape_max": float(np.max(x)),
        "shape_peak_to_peak": float(np.ptp(x)),
        "shape_rms": float(np.sqrt(np.mean(x ** 2))),
        "shape_skew": skew,
        "shape_kurtosis": kurt,
        "shape_zero_crossing_rate": float(zero_crossings / max(len(x) - 1, 1)),
        "shape_slope_mean": float(np.mean(dx)),
        "shape_abs_energy": float(np.sum(x ** 2)),
    }])
    logger.info(f"[{OPERATOR_ID}] column={column}, ptp={out.iloc[0]['shape_peak_to_peak']:.4f}")
    return {"data": out}
# @AI_GENERATED: end
