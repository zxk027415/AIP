# @AI_GENERATED
"""
median_filter operator backend — 中值滤波（去脉冲噪声）。
"""
from scipy.ndimage import median_filter as _median
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "median_filter"


def execute(params: dict, inputs: dict) -> dict:
    """
    中值滤波。

    params:
        - columns (list[str] | None): 目标列
        - size (int): 窗口大小，默认 3
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
        size = int(params.get("size") or 3)
    except (TypeError, ValueError):
        size = 3
    if size < 1:
        size = 3

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)
    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    result = data.copy()
    for col in columns:
        result[col] = _median(result[col].astype(float).values, size=size)

    logger.info(f"[{OPERATOR_ID}] size={size}, columns={columns}")
    return {"data": result}
# @AI_GENERATED: end
