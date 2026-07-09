# @AI_GENERATED
"""
one_hot_encode operator backend — 独热编码。

将分类列转为 0/1 虚拟变量列，支持指定列或自动检测 object/category 列。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "one_hot_encode"


def execute(params: dict, inputs: dict) -> dict:
    """
    独热编码。

    params:
        - columns (list[str] | None): 要编码的列，None 则自动选 object/category 列
        - drop_first (bool): 是否删除第一个类别（避免多重共线），默认 False
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame, "new_columns": list[str]}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    if data.empty:
        return {"data": data, "new_columns": []}

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include=["object", "category"]).columns)

    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    if not columns:
        return {"data": data.copy(), "new_columns": []}

    drop_first = str(params.get("drop_first", "false")).lower() in ("true", "1", "yes")

    original_cols = set(data.columns)
    result = pd.get_dummies(data, columns=columns, drop_first=drop_first)
    new_columns = [c for c in result.columns if c not in original_cols]

    logger.info(f"[{OPERATOR_ID}] Encoded {len(columns)} columns → {len(new_columns)} new columns")
    return {"data": result, "new_columns": new_columns}
# @AI_GENERATED: end
