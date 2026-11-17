# @AI_GENERATED
"""
box_chart operator backend — 箱线图 ECharts option 生成器。

对指定列生成箱线图（最小值、Q1、中位数、Q3、最大值）。
"""
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "box_chart"


def execute(params: dict, inputs: dict) -> dict:
    """
    生成 ECharts 箱线图 option。

    params:
        - columns (list[str] | None): 目标列，None 则全部数值列
        - title (str, optional)
    inputs:
        - data (pd.DataFrame)
    returns:
        {"chart_option": dict, "chart_type": "boxplot"}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    title = params.get("title", "")
    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)

    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    if not columns:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns to plot")

    # 构造 boxplot 数据：每列一组 [min, Q1, median, Q3, max]
    box_data = []
    for col in columns:
        series = data[col].dropna().astype(float)
        if len(series) == 0:
            box_data.append([0, 0, 0, 0, 0])
        else:
            q1 = float(np.percentile(series, 25))
            q3 = float(np.percentile(series, 75))
            box_data.append([
                float(series.min()),
                q1,
                float(np.median(series)),
                q3,
                float(series.max()),
            ])

    chart_option = {
        "title": {"text": title} if title else {},
        "tooltip": {"trigger": "item"},
        "xAxis": {"type": "category", "data": columns},
        "yAxis": {"type": "value"},
        "series": [{
            "name": "boxplot",
            "type": "boxplot",
            "data": box_data,
        }],
    }

    logger.info(f"[{OPERATOR_ID}] Generated boxplot for {len(columns)} columns")
    return {"chart_option": chart_option, "chart_type": "boxplot"}
# @AI_GENERATED: end
