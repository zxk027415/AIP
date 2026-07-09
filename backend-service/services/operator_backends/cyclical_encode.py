# @AI_GENERATED
"""
cyclical_encode operator backend — 周期性 sin/cos 编码。

将周期性数值列（如小时 0-23、月份 1-12、星期 0-6）转为 sin/cos 对。
"""
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "cyclical_encode"


def execute(params: dict, inputs: dict) -> dict:
    """
    周期性 sin/cos 编码。

    params:
        - column (str): 要编码的列名
        - period (float): 周期长度（如 hour → 24, month → 12, weekday → 7）
        - drop_original (bool): 是否删除原始列，默认 False
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}  # 新增 {column}_sin, {column}_cos 列
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    column = params.get("column")
    if not column:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'column' is required")
    if column not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{column}' not found")

    try:
        period = float(params.get("period") or 24)
    except (TypeError, ValueError):
        period = 24.0

    drop_original = str(params.get("drop_original", "false")).lower() in ("true", "1", "yes")

    result = data.copy()
    values = result[column].astype(float)
    result[f"{column}_sin"] = np.sin(2 * np.pi * values / period)
    result[f"{column}_cos"] = np.cos(2 * np.pi * values / period)

    if drop_original:
        result = result.drop(columns=[column])

    logger.info(f"[{OPERATOR_ID}] column={column}, period={period}")
    return {"data": result}
# @AI_GENERATED: end
