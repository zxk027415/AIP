# @AI_GENERATED
"""
spectral_features — 一维频谱特征（质心/带宽/滚降/主频等）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "spectral_features"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - column (str): 目标列，默认第一个数值列
        - sampling_rate (float): 采样率 Hz，默认 1.0
        - roll_off (float): 滚降能量比例，默认 0.85
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}  # 一行频谱特征
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
        fs = float(params.get("sampling_rate") or 1.0)
        roll_off = float(params.get("roll_off") or 0.85)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid numeric params: {e}")

    x = pd.to_numeric(data[column], errors="coerce").dropna().astype(float).values
    if len(x) < 4:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", f"Need >=4 points, got {len(x)}")

    x = x - np.mean(x)
    spec = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), d=1.0 / fs)
    power = spec ** 2
    total = float(np.sum(power)) + 1e-12

    centroid = float(np.sum(freqs * power) / total)
    bandwidth = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * power) / total))
    cum = np.cumsum(power) / total
    roll_idx = int(np.searchsorted(cum, min(max(roll_off, 0.0), 1.0)))
    roll_idx = min(roll_idx, len(freqs) - 1)
    rolloff = float(freqs[roll_idx])
    peak_idx = int(np.argmax(power))
    peak_freq = float(freqs[peak_idx])
    peak_power = float(power[peak_idx])

    out = pd.DataFrame([{
        "spectral_centroid": centroid,
        "spectral_bandwidth": bandwidth,
        "spectral_rolloff": rolloff,
        "spectral_peak_freq": peak_freq,
        "spectral_peak_power": peak_power,
        "spectral_energy": float(total),
    }])
    logger.info(f"[{OPERATOR_ID}] column={column}, centroid={centroid:.4f}")
    return {"data": out}
# @AI_GENERATED: end
