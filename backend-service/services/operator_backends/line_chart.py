# @AI_GENERATED
"""
line_chart operator backend — 折线图 ECharts option 生成器。

根据输入 DataFrame 和 x_column / y_column 参数，生成符合 ECharts 5 规范的
line chart option JSON（纯 Python dict）。前端可直接用 echarts.setOption(chart_option) 渲染。

参数 (params)
-------------
- x_column  (str):           X 轴列名
- y_column  (str | list):    Y 轴列名，单列字符串或多列列表（多系列）
- title     (str, optional): 图表标题

输入 (inputs)
-------------
- data (pd.DataFrame): 含 x/y 列的数据

返回 (dict)
-----------
- chart_option (dict): ECharts option 对象
- chart_type   (str):  "line"
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "line_chart"


def execute(params: dict, inputs: dict) -> dict:
    """生成 ECharts 折线图 option。"""
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

    # 统一为列表
    y_columns = y_column if isinstance(y_column, list) else [y_column]

    # 校验列是否存在
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

    x_values = [str(v) for v in data[x_column].tolist()]

    series = []
    for yc in y_columns:
        values = data[yc].tolist()
        series.append({
            "name": yc,
            "type": "line",
            "data": [float(v) if pd.notna(v) else None for v in values],
        })

    chart_option = {
        "title": {"text": title} if title else {},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": y_columns},
        "xAxis": {"type": "category", "data": x_values},
        "yAxis": {"type": "value"},
        "series": series,
    }

    logger.info(f"[{OPERATOR_ID}] Generated line chart: {len(x_values)} points, {len(y_columns)} series")
    return {"chart_option": chart_option, "chart_type": "line"}
# @AI_GENERATED: end
