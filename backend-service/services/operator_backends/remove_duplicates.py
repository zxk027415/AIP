# @AI_GENERATED
"""
remove_duplicates operator backend — 去重算子。

对输入 DataFrame 执行行去重，可指定只按部分列判断重复（subset）。
返回去重后的数据及删除的行数，方便下游感知数据量变化。

校验：
  - subset 中存在数据中没有的列名时，抛 ColumnNotFoundError
  - inputs["data"] 不是 DataFrame 时，抛 InputError
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "remove_duplicates"


def execute(params: dict, inputs: dict) -> dict:
    """
    删除重复行，返回去重结果及删除行数。

    Args:
        params:
            - subset (list[str] | None, optional):
                判断重复时考虑的列名列表；None 表示使用全部列。
        inputs:
            - data (pd.DataFrame): 输入数据。

    Returns:
        {
            "data": pd.DataFrame,  # 去重后的 DataFrame
            "rows_removed": int,   # 被删除的重复行数
        }

    Raises:
        OperatorExecutionError(InputError):       data 不是 DataFrame。
        OperatorExecutionError(ColumnNotFoundError): subset 中有列在数据中不存在。
    """
    # ── 校验输入 DataFrame ────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # ── 解析 subset 参数 ──────────────────────────────────────────────────────
    subset = params.get("subset")
    # 允许 None（全列去重）或 list[str]
    if subset is not None:
        if not isinstance(subset, list):
            raise OperatorExecutionError(
                OPERATOR_ID,
                "ParameterError",
                "Parameter 'subset' must be a list of column names or null/omitted",
            )
        # 检查 subset 中是否有不存在的列
        missing = [c for c in subset if c not in data.columns]
        if missing:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "ColumnNotFoundError",
                f"Subset columns not found in data: {missing}. "
                f"Available columns: {list(data.columns)}",
            )
        # 空列表等价于全列去重（pandas drop_duplicates 行为一致）
        effective_subset = subset if subset else None
    else:
        effective_subset = None

    # ── 执行去重 ──────────────────────────────────────────────────────────────
    rows_before = len(data)
    result = data.drop_duplicates(subset=effective_subset).copy()
    rows_removed = rows_before - len(result)

    logger.info(
        f"[{OPERATOR_ID}] Removed {rows_removed} duplicate row(s) "
        f"(before={rows_before}, after={len(result)}, "
        f"subset={effective_subset})"
    )

    return {"data": result, "rows_removed": rows_removed}
# @AI_GENERATED: end
