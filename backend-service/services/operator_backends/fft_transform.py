# @AI_GENERATED
"""
fft_transform operator backend — 快速傅里叶变换（时域 → 频域）。

对指定信号列做 FFT，返回频率、幅值、相位。适用于振动/电流/声学分析。
"""
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "fft_transform"


def execute(params: dict, inputs: dict) -> dict:
    """
    FFT 变换。

    params:
        - column (str): 信号列名（时域数据）
        - sampling_rate (float): 采样率（Hz），默认 1.0
        - top_k (int): 只返回幅值最大的前 K 个频率分量（0 = 返回全部），默认 0
    inputs:
        - data (pd.DataFrame)
    returns:
        {
            "data": pd.DataFrame with columns [frequency, amplitude, phase],
            "dominant_frequency": float,  # 幅值最大的频率
        }
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    column = params.get("column")
    if not column:
        # 自动选第一个数值列
        numeric_cols = data.select_dtypes(include="number").columns
        if len(numeric_cols) == 0:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")
        column = numeric_cols[0]

    if column not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{column}' not found")

    try:
        sampling_rate = float(params.get("sampling_rate") or 1.0)
    except (TypeError, ValueError):
        sampling_rate = 1.0
    try:
        top_k = int(params.get("top_k") or 0)
    except (TypeError, ValueError):
        top_k = 0

    signal = data[column].dropna().astype(float).values
    if len(signal) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", f"Signal length ({len(signal)}) < 2")

    n = len(signal)
    fft_vals = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate)
    amplitude = np.abs(fft_vals) * 2.0 / n
    phase = np.angle(fft_vals)

    result_df = pd.DataFrame({
        "frequency": freqs,
        "amplitude": amplitude,
        "phase": phase,
    })

    # 跳过 DC（0 频率）找主频
    non_dc = result_df.iloc[1:] if len(result_df) > 1 else result_df
    dominant_freq = float(non_dc.loc[non_dc["amplitude"].idxmax(), "frequency"]) if len(non_dc) > 0 else 0.0

    if top_k > 0 and top_k < len(result_df):
        result_df = result_df.nlargest(top_k, "amplitude").reset_index(drop=True)

    logger.info(f"[{OPERATOR_ID}] n={n}, fs={sampling_rate}Hz, dominant_freq={dominant_freq:.4f}Hz")
    return {"data": result_df, "dominant_frequency": dominant_freq}
# @AI_GENERATED: end
