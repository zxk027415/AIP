# @AI_GENERATED
"""
data_profile operator backend — 数据概况分析。

生成 DataFrame 的统计摘要：行列数、缺失率、数据类型分布、数值列统计量等。
"""
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "data_profile"


def execute(params: dict, inputs: dict) -> dict:
    """
    数据概况分析。

    params: (无必填参数)
    inputs:
        - data (pd.DataFrame)
    returns:
        {
            "n_rows": int,
            "n_columns": int,
            "dtypes": dict,
            "missing_summary": dict,
            "numeric_summary": dict,
            "memory_usage_mb": float,
        }
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    n_rows, n_columns = data.shape
    dtypes = {col: str(dtype) for col, dtype in data.dtypes.items()}

    # 缺失率
    missing_counts = data.isnull().sum()
    missing_summary = {
        col: {"missing_count": int(missing_counts[col]), "missing_rate": round(float(missing_counts[col] / n_rows), 4) if n_rows > 0 else 0}
        for col in data.columns
    }

    # 数值列统计
    numeric_df = data.select_dtypes(include="number")
    numeric_summary = {}
    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        numeric_summary[col] = {
            "mean": round(float(series.mean()), 4) if len(series) > 0 else None,
            "std": round(float(series.std()), 4) if len(series) > 1 else None,
            "min": float(series.min()) if len(series) > 0 else None,
            "max": float(series.max()) if len(series) > 0 else None,
            "median": float(series.median()) if len(series) > 0 else None,
            "q25": float(series.quantile(0.25)) if len(series) > 0 else None,
            "q75": float(series.quantile(0.75)) if len(series) > 0 else None,
        }

    memory_mb = round(float(data.memory_usage(deep=True).sum()) / 1024 / 1024, 3)

    logger.info(f"[{OPERATOR_ID}] {n_rows} rows × {n_columns} cols, memory={memory_mb} MB")
    return {
        "n_rows": n_rows,
        "n_columns": n_columns,
        "dtypes": dtypes,
        "missing_summary": missing_summary,
        "numeric_summary": numeric_summary,
        "memory_usage_mb": memory_mb,
    }
# @AI_GENERATED: end
