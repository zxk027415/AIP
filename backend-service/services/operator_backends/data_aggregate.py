# @AI_GENERATED
"""
data_aggregate operator backend — 数据聚合。

按指定列分组，对目标列执行聚合函数（sum/mean/max/min/count/std/median）。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "data_aggregate"

_VALID_AGGS = {"sum", "mean", "max", "min", "count", "std", "median", "first", "last"}


def execute(params: dict, inputs: dict) -> dict:
    """
    分组聚合。

    params:
        - group_by (list[str]): 分组列
        - agg_columns (list[str]): 需要聚合的目标列
        - agg_func (str): 聚合函数名，默认 "mean"
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    group_by = params.get("group_by")
    if not group_by or not isinstance(group_by, list):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'group_by' must be a non-empty list")

    agg_columns = params.get("agg_columns")
    if not agg_columns or not isinstance(agg_columns, list):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'agg_columns' must be a non-empty list")

    agg_func = str(params.get("agg_func") or "mean").strip().lower()
    if agg_func not in _VALID_AGGS:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"agg_func must be one of {sorted(_VALID_AGGS)}")

    for col in group_by + agg_columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    result = data.groupby(group_by, as_index=False)[agg_columns].agg(agg_func)

    logger.info(f"[{OPERATOR_ID}] group_by={group_by}, agg={agg_func}, result shape={result.shape}")
    return {"data": result}
# @AI_GENERATED: end
