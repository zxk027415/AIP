# @AI_GENERATED
"""
gaussian_filter operator backend — 高斯滤波（平滑）。
"""
from scipy.ndimage import gaussian_filter1d
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "gaussian_filter"


def execute(params: dict, inputs: dict) -> dict:
    """
    一维高斯滤波。

    params:
        - columns (list[str] | None): 目标列
        - sigma (float): 高斯核标准差，默认 1.0
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
        sigma = float(params.get("sigma") or 1.0)
    except (TypeError, ValueError):
        sigma = 1.0

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)
    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    result = data.copy()
    for col in columns:
        result[col] = gaussian_filter1d(result[col].astype(float).values, sigma=sigma)

    logger.info(f"[{OPERATOR_ID}] sigma={sigma}, columns={columns}")
    return {"data": result}
# @AI_GENERATED: end
