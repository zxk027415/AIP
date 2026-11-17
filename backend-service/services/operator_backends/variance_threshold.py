# @AI_GENERATED
"""
variance_threshold operator backend — 方差阈值特征选择。

删除方差小于阈值的低方差特征（近似常数列）。
"""
import pandas as pd
from sklearn.feature_selection import VarianceThreshold
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "variance_threshold"


def execute(params: dict, inputs: dict) -> dict:
    """
    方差阈值选择。

    params:
        - threshold (float): 方差阈值，默认 0.0（只删完全常数列）
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame, "removed_columns": list[str]}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    if data.empty:
        return {"data": data, "removed_columns": []}

    try:
        threshold = float(params.get("threshold") if params.get("threshold") is not None else 0.0)
    except (TypeError, ValueError):
        threshold = 0.0

    numeric_df = data.select_dtypes(include="number")
    if numeric_df.empty:
        return {"data": data.copy(), "removed_columns": []}

    selector = VarianceThreshold(threshold=threshold)
    try:
        selector.fit(numeric_df)
    except ValueError as e:
        raise OperatorExecutionError(OPERATOR_ID, "SelectionError", f"VarianceThreshold fit failed: {e}")

    mask = selector.get_support()
    kept_numeric = [c for c, k in zip(numeric_df.columns, mask) if k]
    removed = [c for c, k in zip(numeric_df.columns, mask) if not k]

    # 保留非数值列 + 保留下来的数值列
    non_numeric = [c for c in data.columns if c not in numeric_df.columns]
    result = data[non_numeric + kept_numeric].copy()

    logger.info(f"[{OPERATOR_ID}] threshold={threshold}, removed={removed}")
    return {"data": result, "removed_columns": removed}
# @AI_GENERATED: end
