# @AI_GENERATED
"""
savgol_filter operator backend — Savitzky-Golay 滤波（多项式平滑）。

对数值列应用 Savitzky-Golay 滤波器，比移动平均能更好地保留峰谷特征。
"""
from scipy.signal import savgol_filter as _sg
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "savgol_filter"


def execute(params: dict, inputs: dict) -> dict:
    """
    Savitzky-Golay 滤波。

    params:
        - columns (list[str] | None): 目标列，None 则全部数值列
        - window_length (int): 窗口长度（必须为奇数），默认 5
        - polyorder (int): 多项式阶数（< window_length），默认 2
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
        window_length = int(params.get("window_length") or 5)
    except (TypeError, ValueError):
        window_length = 5
    if window_length % 2 == 0:
        window_length += 1  # 强制奇数

    try:
        polyorder = int(params.get("polyorder") or 2)
    except (TypeError, ValueError):
        polyorder = 2

    if polyorder >= window_length:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"polyorder ({polyorder}) must be < window_length ({window_length})"
        )

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)
    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    result = data.copy()
    for col in columns:
        series = result[col].astype(float)
        # 数据长度必须 >= window_length
        if len(series) < window_length:
            logger.warning(f"[{OPERATOR_ID}] column '{col}' length ({len(series)}) < window_length ({window_length}), skipped")
            continue
        result[col] = _sg(series.values, window_length=window_length, polyorder=polyorder)

    logger.info(f"[{OPERATOR_ID}] window_length={window_length}, polyorder={polyorder}, columns={columns}")
    return {"data": result}
# @AI_GENERATED: end
