# @AI_GENERATED
"""
data_pivot operator backend — 数据透视表（长表 → 宽表）。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "data_pivot"


def execute(params: dict, inputs: dict) -> dict:
    """
    数据透视：类似 Excel 透视表。

    params:
        - index (str | list[str]): 行索引列
        - columns (str | list[str]): 列索引列
        - values (str | list[str]): 汇总值列
        - aggfunc (str): 聚合函数（sum/mean/max/min/count），默认 mean
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    index = params.get("index")
    columns = params.get("columns")
    values = params.get("values")
    aggfunc = str(params.get("aggfunc") or "mean").strip().lower()

    if not index:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'index' is required")
    if not values:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'values' is required")

    # 校验列存在
    needed = []
    for x in [index, columns, values]:
        if x is None:
            continue
        if isinstance(x, str):
            needed.append(x)
        elif isinstance(x, list):
            needed.extend(x)
    for col in needed:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    try:
        result = pd.pivot_table(data, index=index, columns=columns, values=values, aggfunc=aggfunc)
        # 展平多层列
        if isinstance(result.columns, pd.MultiIndex):
            result.columns = ['_'.join(str(v) for v in col if v).strip('_') for col in result.columns]
        result = result.reset_index()
    except Exception as e:
        raise OperatorExecutionError(OPERATOR_ID, "PivotError", f"Pivot failed: {e}")

    logger.info(f"[{OPERATOR_ID}] shape={result.shape}, aggfunc={aggfunc}")
    return {"data": result}
# @AI_GENERATED: end
