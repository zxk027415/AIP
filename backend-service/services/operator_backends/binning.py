# @AI_GENERATED
"""
binning operator backend — 数值列分箱。

支持等宽（equal_width）、等频（equal_freq/quantile）、自定义边界（custom）。
"""
import pandas as pd
import numpy as np
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "binning"


def execute(params: dict, inputs: dict) -> dict:
    """
    数值列分箱。

    params:
        - column (str): 待分箱的列
        - method (str): "equal_width" | "equal_freq" | "custom"，默认 equal_width
        - bins (int): 桶数（method != custom 时），默认 5
        - edges (list[float]): 自定义边界（method=custom 时必填）
        - labels (list[str] | None): 桶标签，长度 = bins；不传则生成 "bin_0..bin_n"
        - output_column (str): 输出列名，默认 f"{column}_bin"
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    column = params.get("column")
    if not column:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "Parameter 'column' is required")
    if column not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{column}' not found")

    method = str(params.get("method") or "equal_width").strip().lower()
    try:
        bins = int(params.get("bins") or 5)
    except (TypeError, ValueError):
        bins = 5
    edges = params.get("edges")
    labels = params.get("labels")
    output_column = params.get("output_column") or f"{column}_bin"

    series = data[column].astype(float)
    result = data.copy()

    try:
        if method == "custom":
            if not edges or not isinstance(edges, list) or len(edges) < 2:
                raise OperatorExecutionError(
                    OPERATOR_ID, "ParameterError",
                    "method='custom' requires 'edges' list of >= 2 values"
                )
            bin_labels = labels if labels and len(labels) == len(edges) - 1 else False
            binned = pd.cut(series, bins=edges, labels=bin_labels, include_lowest=True)
        elif method in ("equal_freq", "quantile"):
            bin_labels = labels if labels and len(labels) == bins else False
            binned = pd.qcut(series, q=bins, labels=bin_labels, duplicates="drop")
        else:  # equal_width
            bin_labels = labels if labels and len(labels) == bins else False
            binned = pd.cut(series, bins=bins, labels=bin_labels, include_lowest=True)
    except ValueError as e:
        raise OperatorExecutionError(OPERATOR_ID, "BinningError", f"Binning failed: {e}")

    result[output_column] = binned.astype(str)  # 转字符串便于下游 one_hot 等
    logger.info(f"[{OPERATOR_ID}] column={column} method={method} bins={bins} → {output_column}")
    return {"data": result}
# @AI_GENERATED: end
