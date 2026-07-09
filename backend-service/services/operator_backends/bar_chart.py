# @AI_GENERATED
"""
bar_chart operator backend — 柱状图 ECharts option 生成器。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "bar_chart"


def execute(params: dict, inputs: dict) -> dict:
    """
    生成 ECharts 柱状图 option。

    params:
        - x_column (str): X 轴分类列
        - y_column (str | list[str]): Y 轴数值列（支持多系列）
        - title (str, optional)
        - stack (bool): 是否堆叠，默认 False
    inputs:
        - data (pd.DataFrame)
    returns:
        {"chart_option": dict, "chart_type": "bar"}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    x_column = params.get("x_column")
    if not x_column:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'x_column' is required")

    y_column = params.get("y_column")
    if not y_column:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'y_column' is required")

    title = params.get("title", "")
    stack = str(params.get("stack", "false")).lower() in ("true", "1", "yes")
    y_columns = y_column if isinstance(y_column, list) else [y_column]

    if x_column not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"x_column '{x_column}' not found")
    for yc in y_columns:
        if yc not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"y_column '{yc}' not found")

    x_values = [str(v) for v in data[x_column].tolist()]
    series = []
    for yc in y_columns:
        s = {
            "name": yc,
            "type": "bar",
            "data": [float(v) if pd.notna(v) else None for v in data[yc]],
        }
        if stack:
            s["stack"] = "total"
        series.append(s)

    chart_option = {
        "title": {"text": title} if title else {},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": y_columns},
        "xAxis": {"type": "category", "data": x_values},
        "yAxis": {"type": "value"},
        "series": series,
    }
    logger.info(f"[{OPERATOR_ID}] {len(x_values)} bars, {len(y_columns)} series, stack={stack}")
    return {"chart_option": chart_option, "chart_type": "bar"}
# @AI_GENERATED: end
