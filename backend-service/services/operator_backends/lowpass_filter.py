# @AI_GENERATED
"""
lowpass_filter operator backend — Butterworth 低通滤波（去高频噪声）。
"""
from scipy.signal import butter, filtfilt
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "lowpass_filter"


def execute(params: dict, inputs: dict) -> dict:
    """
    Butterworth 低通滤波。

    params:
        - columns (list[str] | None): 目标列
        - cutoff (float): 截止频率 (Hz)
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
        cutoff = float(params.get("cutoff") or 0.4)
        sampling_rate = float(params.get("sampling_rate") or 1.0)
        order = int(params.get("order") or 4)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid numeric params: {e}")

    nyquist = sampling_rate / 2.0
    if not (0 < cutoff < nyquist):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"cutoff ({cutoff}) must be in (0, Nyquist ({nyquist}))"
        )

    b, a = butter(order, cutoff / nyquist, btype="low")

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)
    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    result = data.copy()
    min_len = max(3 * order, 27)
    for col in columns:
        series = result[col].astype(float).values
        if len(series) < min_len:
            logger.warning(f"[{OPERATOR_ID}] column '{col}' length ({len(series)}) too short, skipped")
            continue
        result[col] = filtfilt(b, a, series)

    logger.info(f"[{OPERATOR_ID}] cutoff={cutoff}Hz, fs={sampling_rate}Hz, order={order}")
    return {"data": result}
# @AI_GENERATED: end
