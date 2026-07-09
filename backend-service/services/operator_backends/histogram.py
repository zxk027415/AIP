# @AI_GENERATED
"""
histogram operator backend — 直方图 ECharts option 生成器。

使用 numpy 计算分箱，生成 ECharts bar chart option。
"""
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "histogram"


def execute(params: dict, inputs: dict) -> dict:
    """生成 ECharts 直方图 option。"""
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    target_column = params.get("target_column")
    if not target_column:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "Parameter 'target_column' is required"
        )

    if target_column not in data.columns:
        raise OperatorExecutionError(
            OPERATOR_ID, "ColumnNotFoundError",
            f"target_column '{target_column}' not found. Available: {list(data.columns)}"
        )

    try:
        bins = int(params.get("bins") or 20)
    except (TypeError, ValueError):
        bins = 20

    title = params.get("title", "")

    series_data = data[target_column].dropna().astype(float)
    # 过滤 inf 值，避免 numpy histogram 内部 overflow
    series_data = series_data[np.isfinite(series_data)]
    if len(series_data) == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"Column '{target_column}' has no valid finite numeric values"
        )

    # 手动构造 bin edges，绕开 numpy.histogram 在极端 float 范围下的内部 overflow
    val_min = float(np.min(series_data))
    val_max = float(np.max(series_data))
    if val_min == val_max:
        # 所有值相同：造一个宽度 1.0 的桶，全部落在中间
        bin_edges = np.linspace(val_min - 0.5, val_max + 0.5, bins + 1)
    else:
        bin_edges = np.linspace(val_min, val_max, bins + 1)

    counts, _ = np.histogram(series_data, bins=bin_edges)

    x_labels = [
        f"{round(float(bin_edges[i]), 2)}-{round(float(bin_edges[i + 1]), 2)}"
        for i in range(len(counts))
    ]

    chart_option = {
        "title": {"text": title} if title else {},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": x_labels},
        "yAxis": {"type": "value"},
        "series": [
            {
                "name": target_column,
                "type": "bar",
                "data": [int(c) for c in counts],
            }
        ],
    }

    logger.info(f"[{OPERATOR_ID}] Generated histogram: {len(series_data)} values, {bins} bins")
    return {"chart_option": chart_option, "chart_type": "histogram"}
# @AI_GENERATED: end
