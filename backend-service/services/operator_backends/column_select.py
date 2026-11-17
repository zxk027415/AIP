# @AI_GENERATED
"""
column_select operator backend — 列选择算子。

从输入 DataFrame 中保留指定的列子集，其余列丢弃。
常用于工作流中对宽表进行裁剪，减少下游算子的无关列干扰。

校验：
  - columns 中存在数据中没有的列名时，抛 ColumnNotFoundError
  - inputs["data"] 不是 DataFrame 时，抛 InputError
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "column_select"


def execute(params: dict, inputs: dict) -> dict:
    """
    选取指定列，返回只含目标列的 DataFrame。

    Args:
        params:
            - columns (list[str], required): 要保留的列名列表。
        inputs:
            - data (pd.DataFrame): 输入数据。

    Returns:
        {"data": pd.DataFrame}  # 仅包含 columns 中指定的列

    Raises:
        OperatorExecutionError(InputError):       data 不是 DataFrame。
        OperatorExecutionError(ColumnNotFoundError): columns 中有列在数据中不存在。
    """
    # ── 校验输入 DataFrame ────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # ── 解析 columns 参数 ─────────────────────────────────────────────────────
    columns = params.get("columns")
    if not columns or not isinstance(columns, list):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            "Parameter 'columns' is required and must be a non-empty list of column names",
        )

    # ── 检查缺失列 ────────────────────────────────────────────────────────────
    missing = [c for c in columns if c not in data.columns]
    if missing:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ColumnNotFoundError",
            f"Columns not found in data: {missing}. "
            f"Available columns: {list(data.columns)}",
        )

    # ── 选取列 ────────────────────────────────────────────────────────────────
    result = data[columns].copy()
    logger.info(
        f"[{OPERATOR_ID}] Selected {len(columns)} column(s) from "
        f"{len(data.columns)}-column DataFrame; "
        f"output shape={result.shape}"
    )

    return {"data": result}
# @AI_GENERATED: end
