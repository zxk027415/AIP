# @AI_GENERATED
"""
pie_chart operator backend — 饼图 ECharts option 生成器。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "pie_chart"


def execute(params: dict, inputs: dict) -> dict:
    """
    生成 ECharts 饼图 option。

    params:
        - name_column (str): 分类名列
        - value_column (str): 数值列
        - title (str, optional)
        - top_k (int, default 0): 只显示 top_k 大的类别，0=全部
    inputs:
        - data (pd.DataFrame)
    returns:
        {"chart_option": dict, "chart_type": "pie"}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    name_column = params.get("name_column")
    value_column = params.get("value_column")
    if not name_column:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'name_column' is required")
    if not value_column:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'value_column' is required")
    if name_column not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"name_column '{name_column}' not found")
    if value_column not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"value_column '{value_column}' not found")

    title = params.get("title", "")
    try:
        top_k = int(params.get("top_k") or 0)
    except (TypeError, ValueError):
        top_k = 0

    # 按 name 聚合 value，取和
    agg = data.groupby(name_column)[value_column].sum().sort_values(ascending=False)
    if top_k > 0:
        agg = agg.head(top_k)

    pie_data = [{"name": str(k), "value": float(v)} for k, v in agg.items() if pd.notna(v)]

    chart_option = {
        "title": {"text": title} if title else {},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"orient": "vertical", "left": "left"},
        "series": [{
            "name": value_column,
            "type": "pie",
            "radius": "60%",
            "data": pie_data,
            "emphasis": {
                "itemStyle": {
                    "shadowBlur": 10,
                    "shadowOffsetX": 0,
                    "shadowColor": "rgba(0, 0, 0, 0.5)",
                }
            },
        }],
    }

    logger.info(f"[{OPERATOR_ID}] {len(pie_data)} slices")
    return {"chart_option": chart_option, "chart_type": "pie"}
# @AI_GENERATED: end
