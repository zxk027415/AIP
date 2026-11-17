# @AI_GENERATED
"""
data_merge operator backend — 数据合并算子。

对两个输入 DataFrame（left / right）按指定 join_key 进行合并，
等价于 SQL JOIN 语义，支持 inner / left / right / outer 四种连接方式。

校验：
  - inputs["left"] / inputs["right"] 不是 DataFrame 时，抛 InputError
  - join_key 在 left 或 right 中不存在时，抛 ColumnNotFoundError
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "data_merge"

_VALID_HOW = {"inner", "left", "right", "outer"}


def execute(params: dict, inputs: dict) -> dict:
    """
    按 join_key 合并 left 与 right 两个 DataFrame。

    Args:
        params:
            - join_key (str, required): 用于合并的列名（两侧必须都存在）。
            - how      (str, optional): 连接方式，inner/left/right/outer，默认 "inner"。
        inputs:
            - left  (pd.DataFrame): 左侧数据表。
            - right (pd.DataFrame): 右侧数据表。

    Returns:
        {"data": pd.DataFrame}  # 合并后的结果表

    Raises:
        OperatorExecutionError(InputError):       left 或 right 不是 DataFrame。
        OperatorExecutionError(ColumnNotFoundError): join_key 在 left 或 right 中不存在。
        OperatorExecutionError(ParameterError):   how 值不合法。
    """
    # ── 校验输入 DataFrames ───────────────────────────────────────────────────
    left = inputs.get("left")
    right = inputs.get("right")

    if left is None or not isinstance(left, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'left' must be a pandas DataFrame"
        )
    if right is None or not isinstance(right, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'right' must be a pandas DataFrame"
        )

    # ── 解析参数 ──────────────────────────────────────────────────────────────
    join_key = params.get("join_key")
    if not join_key or not isinstance(join_key, str):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            "Parameter 'join_key' is required and must be a non-empty string",
        )
    join_key = join_key.strip()

    how = str(params.get("how") or "inner").strip().lower()
    if how not in _VALID_HOW:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Invalid 'how' value '{how}'. Must be one of {sorted(_VALID_HOW)}",
        )

    # ── 校验 join_key 存在 ────────────────────────────────────────────────────
    if join_key not in left.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ColumnNotFoundError",
            f"join_key '{join_key}' not found in left DataFrame. "
            f"Available columns: {list(left.columns)}",
        )
    if join_key not in right.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ColumnNotFoundError",
            f"join_key '{join_key}' not found in right DataFrame. "
            f"Available columns: {list(right.columns)}",
        )

    # ── 执行合并 ──────────────────────────────────────────────────────────────
    result = pd.merge(left, right, on=join_key, how=how)
    logger.info(
        f"[{OPERATOR_ID}] Merged left({left.shape}) + right({right.shape}) "
        f"on='{join_key}', how='{how}' -> result{result.shape}"
    )

    return {"data": result}
# @AI_GENERATED: end
