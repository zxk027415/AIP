# @AI_GENERATED
"""
heatmap_chart operator backend — 热力图 ECharts option 生成器。

适用于相关矩阵、混淆矩阵等二维数值展示。
"""
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "heatmap_chart"


def execute(params: dict, inputs: dict) -> dict:
    """
    生成 ECharts 热力图 option。

    params:
        - title (str, optional)
    inputs:
        - data (pd.DataFrame): 二维数值矩阵（行列名作为坐标轴）
        或
        - correlation_matrix (pd.DataFrame): 相关系数矩阵
    returns:
        {"chart_option": dict, "chart_type": "heatmap"}
    """
    data = inputs.get("data")
    if data is None:
        data = inputs.get("correlation_matrix")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' or 'correlation_matrix' must be a DataFrame")

    title = params.get("title", "")
    x_labels = [str(c) for c in data.columns]
    y_labels = [str(i) for i in data.index]

    # 构建 [[x_idx, y_idx, value], ...] 格式
    heat_data = []
    for yi, row_label in enumerate(data.index):
        for xi, col_label in enumerate(data.columns):
            val = data.iloc[yi, xi]
            heat_data.append([xi, yi, round(float(val), 4) if pd.notna(val) else None])

    # 计算值范围
    values = [v[2] for v in heat_data if v[2] is not None]
    v_min = min(values) if values else 0
    v_max = max(values) if values else 1

    chart_option = {
        "title": {"text": title} if title else {},
        "tooltip": {"position": "top"},
        "xAxis": {"type": "category", "data": x_labels, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": y_labels, "splitArea": {"show": True}},
        "visualMap": {"min": v_min, "max": v_max, "calculable": True, "orient": "horizontal", "left": "center", "bottom": "0%"},
        "series": [{
            "name": title or "heatmap",
            "type": "heatmap",
            "data": heat_data,
            "label": {"show": True},
        }],
    }

    logger.info(f"[{OPERATOR_ID}] Generated heatmap: {len(y_labels)}×{len(x_labels)}")
    return {"chart_option": chart_option, "chart_type": "heatmap"}
# @AI_GENERATED: end
