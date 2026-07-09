# @AI_GENERATED
"""
correlation_analysis operator backend — 相关性分析。

计算 DataFrame 数值列间的 Pearson / Spearman / Kendall 相关系数矩阵。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "correlation_analysis"


def execute(params: dict, inputs: dict) -> dict:
    """
    相关性分析。

    params:
        - method (str): pearson / spearman / kendall，默认 pearson
        - columns (list[str] | None): 指定列，None 则全部数值列
    inputs:
        - data (pd.DataFrame)
    returns:
        {"correlation_matrix": pd.DataFrame, "method": str}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    method = str(params.get("method") or "pearson").strip().lower()
    if method not in ("pearson", "spearman", "kendall"):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"method must be pearson/spearman/kendall, got '{method}'")

    columns = params.get("columns")
    if columns:
        for col in columns:
            if col not in data.columns:
                raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")
        numeric_df = data[columns].select_dtypes(include="number")
    else:
        numeric_df = data.select_dtypes(include="number")

    if numeric_df.shape[1] < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Need at least 2 numeric columns for correlation")

    corr_matrix = numeric_df.corr(method=method)

    logger.info(f"[{OPERATOR_ID}] method={method}, shape={corr_matrix.shape}")
    return {"correlation_matrix": corr_matrix, "method": method}
# @AI_GENERATED: end
