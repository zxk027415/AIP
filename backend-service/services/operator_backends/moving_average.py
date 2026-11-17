# @AI_GENERATED
"""
moving_average operator backend — 移动平均平滑。

支持简单移动平均 (SMA)、加权移动平均 (WMA)、指数移动平均 (EMA)。
"""
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "moving_average"


def execute(params: dict, inputs: dict) -> dict:
    """
    移动平均平滑。

    params:
        - columns (list[str] | None): 要平滑的列，None 则全部数值列
        - window (int): 窗口大小，默认 5
        - method (str): sma / ema / wma，默认 sma
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}  # 平滑后的 DataFrame（NaN 行保留）
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    if data.empty:
        return {"data": data}

    try:
        window = int(params.get("window") or 5)
    except (TypeError, ValueError):
        window = 5

    method = str(params.get("method") or "sma").strip().lower()
    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)

    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    result = data.copy()
    for col in columns:
        if method == "ema":
            result[col] = result[col].ewm(span=window, adjust=False).mean()
        elif method == "wma":
            weights = list(range(1, window + 1))
            result[col] = result[col].rolling(window=window).apply(
                lambda x: sum(w * v for w, v in zip(weights, x)) / sum(weights), raw=True
            )
        else:  # sma
            result[col] = result[col].rolling(window=window).mean()

    logger.info(f"[{OPERATOR_ID}] method={method}, window={window}, columns={columns}")
    return {"data": result}
# @AI_GENERATED: end
