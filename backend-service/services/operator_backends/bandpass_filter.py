# @AI_GENERATED
"""
bandpass_filter operator backend — Butterworth 带通滤波。

保留 [low_cutoff, high_cutoff] 频段内的信号，滤除其他频率。
"""
from scipy.signal import butter, filtfilt
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "bandpass_filter"


def execute(params: dict, inputs: dict) -> dict:
    """
    Butterworth 带通滤波。

    params:
        - columns (list[str] | None): 目标列
        - low_cutoff (float): 低截止频率 (Hz)
        - high_cutoff (float): 高截止频率 (Hz)
        - sampling_rate (float): 采样率 (Hz)，默认 1.0
        - order (int): 滤波器阶数，默认 4
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    if data.empty:
        return {"data": data}

    try:
        low_cutoff = float(params.get("low_cutoff") or 0.1)
        high_cutoff = float(params.get("high_cutoff") or 0.4)
        sampling_rate = float(params.get("sampling_rate") or 1.0)
        order = int(params.get("order") or 4)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid numeric params: {e}")

    nyquist = sampling_rate / 2.0
    if not (0 < low_cutoff < high_cutoff < nyquist):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"Require 0 < low_cutoff ({low_cutoff}) < high_cutoff ({high_cutoff}) < Nyquist ({nyquist})"
        )

    low_norm = low_cutoff / nyquist
    high_norm = high_cutoff / nyquist
    b, a = butter(order, [low_norm, high_norm], btype="band")

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)
    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    result = data.copy()
    # filtfilt 需要 padlen 长度信号，取 3*order 作最小要求
    min_len = max(3 * order, 27)
    for col in columns:
        series = result[col].astype(float).values
        if len(series) < min_len:
            logger.warning(f"[{OPERATOR_ID}] column '{col}' length ({len(series)}) too short for filter order {order}, skipped")
            continue
        result[col] = filtfilt(b, a, series)

    logger.info(f"[{OPERATOR_ID}] low={low_cutoff}Hz, high={high_cutoff}Hz, fs={sampling_rate}Hz, order={order}")
    return {"data": result}
# @AI_GENERATED: end
