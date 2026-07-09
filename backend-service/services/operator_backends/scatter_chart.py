# @AI_GENERATED
"""
scatter_chart operator backend — 散点图 ECharts option 生成器。

与 line_chart 接口一致，但 series type 为 "scatter"，
xAxis 使用 value 类型（而非 category），data 格式为 [[x, y], ...]。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "scatter_chart"


def execute(params: dict, inputs: dict) -> dict:
    """生成 ECharts 散点图 option。"""
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    x_column = params.get("x_column")
    if not x_column:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "Parameter 'x_column' is required"
        )

    y_column = params.get("y_column")
    if not y_column:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "Parameter 'y_column' is required"
        )

    title = params.get("title", "")
    y_columns = y_column if isinstance(y_column, list) else [y_column]

    if x_column not in data.columns:
        raise OperatorExecutionError(
            OPERATOR_ID, "ColumnNotFoundError",
            f"x_column '{x_column}' not found. Available: {list(data.columns)}"
        )
    for yc in y_columns:
        if yc not in data.columns:
            raise OperatorExecutionError(
                OPERATOR_ID, "ColumnNotFoundError",
                f"y_column '{yc}' not found. Available: {list(data.columns)}"
            )

    series = []
    for yc in y_columns:
        points = []
        for _, row in data.iterrows():
            xv = row[x_column]
            yv = row[yc]
            if pd.notna(xv) and pd.notna(yv):
                points.append([float(xv), float(yv)])
        series.append({
            "name": yc,
            "type": "scatter",
            "data": points,
        })

    chart_option = {
        "title": {"text": title} if title else {},
        "tooltip": {"trigger": "item"},
        "legend": {"data": y_columns},
        "xAxis": {"type": "value"},
        "yAxis": {"type": "value"},
        "series": series,
    }

    logger.info(f"[{OPERATOR_ID}] Generated scatter chart: {len(data)} rows, {len(y_columns)} series")
    return {"chart_option": chart_option, "chart_type": "scatter"}
# @AI_GENERATED: end
