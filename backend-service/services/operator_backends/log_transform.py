# @AI_GENERATED
"""
log_transform operator backend — 对数变换。

支持 ln / log2 / log10，可选 +1 偏移避免 log(0)。
"""
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "log_transform"


def execute(params: dict, inputs: dict) -> dict:
    """
    对数变换。

    params:
        - columns (list[str] | None): 目标列，None 全部数值列
        - base (str): "ln" / "log2" / "log10"，默认 "ln"
        - offset (float): 加到原值上再取 log，默认 1（避免 log(0)）
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    if data.empty:
        return {"data": data}

    base = str(params.get("base") or "ln").strip().lower()
    try:
        offset = float(params.get("offset") if params.get("offset") is not None else 1)
    except (TypeError, ValueError):
        offset = 1.0

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)

    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    log_fn = {"ln": np.log, "log2": np.log2, "log10": np.log10}.get(base, np.log)

    result = data.copy()
    for col in columns:
        result[col] = log_fn(result[col] + offset)

    logger.info(f"[{OPERATOR_ID}] base={base}, offset={offset}, columns={columns}")
    return {"data": result}
# @AI_GENERATED: end
