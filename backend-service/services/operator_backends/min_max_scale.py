# @AI_GENERATED
"""
min_max_scale operator backend — Min-Max 归一化。

对 DataFrame 中指定列（或全部数值列）逐列应用 sklearn MinMaxScaler，
将数值缩放到 [0, 1] 区间。非目标列保持不变。

接口约定：
  params:
    - columns (list[str] | None): 要缩放的列名列表；None 则自动选全部数值列
  inputs:
    - data (pd.DataFrame): 输入数据

返回：
  {"data": pd.DataFrame}  # 目标列已归一化，其余列保持不变
"""
import logging

import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "min_max_scale"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    Min-Max 归一化。

    Args:
        params:
            - columns (list[str] | None): 要缩放的列名列表。
              若为 None 或不传，则自动选取 DataFrame 中全部数值列。
        inputs:
            - data (pd.DataFrame): 含待缩放列的输入数据

    Returns:
        {"data": pd.DataFrame}  # 目标列缩放至 [0, 1]，其余列不变

    Raises:
        OperatorExecutionError(OPERATOR_ID, "InputError", ...):
            inputs 中缺少 "data" 键，或值不是 DataFrame。
        OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", ...):
            params["columns"] 中指定的某列不存在于 DataFrame。
    """
    # ── 解析输入 ──────────────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'data' must be a pandas DataFrame"
        )

    # ── 空 DataFrame 直接返回，不报错 ─────────────────────────────────────────
    if data.empty:
        logger.info(f"[{OPERATOR_ID}] 输入 DataFrame 为空，直接返回")
        return {"data": data}

    # ── 解析目标列 ────────────────────────────────────────────────────────────
    columns = params.get("columns")
    if columns is None:
        # 自动选取全部数值列
        columns = list(data.select_dtypes(include="number").columns)
        logger.info(f"[{OPERATOR_ID}] columns 未指定，自动选取数值列: {columns}")
    else:
        # 校验指定列是否存在
        for col in columns:
            if col not in data.columns:
                raise OperatorExecutionError(
                    OPERATOR_ID, "ColumnNotFoundError",
                    f"Column '{col}' not found in data. "
                    f"Available columns: {list(data.columns)}"
                )

    if not columns:
        logger.info(f"[{OPERATOR_ID}] 无可缩放的列，返回原始数据")
        return {"data": data.copy()}

    # ── 逐列应用 MinMaxScaler ─────────────────────────────────────────────────
    result = data.copy()
    for col in columns:
        scaler = MinMaxScaler()
        result[col] = scaler.fit_transform(result[[col]]).ravel()

    logger.info(f"[{OPERATOR_ID}] Min-Max 缩放完成，处理列: {columns}")
    return {"data": result}
# @AI_GENERATED: end
