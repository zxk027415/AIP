# @AI_GENERATED
"""
stationarity_test operator backend — 平稳性检验。

对时序数据执行 ADF (Augmented Dickey-Fuller) 检验，判断序列是否平稳。
"""
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "stationarity_test"


def execute(params: dict, inputs: dict) -> dict:
    """
    平稳性检验 (ADF)。

    params:
        - column (str): 待检验列名
        - significance (float): 显著性水平，默认 0.05
    inputs:
        - data (pd.DataFrame)
    returns:
        {
            "is_stationary": bool,
            "adf_statistic": float,
            "p_value": float,
            "critical_values": dict,
            "conclusion": str
        }
    """
    from statsmodels.tsa.stattools import adfuller

    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    column = params.get("column")
    if not column:
        # 自动选取第一个数值列
        numeric_cols = data.select_dtypes(include="number").columns
        if len(numeric_cols) == 0:
            raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")
        column = numeric_cols[0]

    if column not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{column}' not found")

    try:
        significance = float(params.get("significance") or 0.05)
    except (TypeError, ValueError):
        significance = 0.05

    series = data[column].dropna().astype(float)
    if len(series) < 10:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", f"Need at least 10 data points, got {len(series)}")

    result = adfuller(series, autolag="AIC")
    adf_stat = float(result[0])
    p_value = float(result[1])
    critical_values = {k: float(v) for k, v in result[4].items()}
    is_stationary = p_value < significance

    conclusion = (
        f"序列 '{column}' {'是平稳的' if is_stationary else '不是平稳的'} "
        f"(p={p_value:.4f}, 显著性水平={significance})"
    )

    logger.info(f"[{OPERATOR_ID}] {conclusion}")
    return {
        "is_stationary": is_stationary,
        "adf_statistic": adf_stat,
        "p_value": p_value,
        "critical_values": critical_values,
        "conclusion": conclusion,
    }
# @AI_GENERATED: end
