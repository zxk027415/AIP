# @AI_GENERATED
"""
workday_features operator backend — Marks workday/non-workday in time series data.

Reuses common.holidays.if_workday logic.
Generates is_workday (int) column.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "workday_features"


def execute(params: dict, inputs: dict) -> dict:
    """
    Mark workday/non-workday for each timestamp.

    Args:
        params: Operator parameters including:
            - time_field (str, optional): Timestamp column name. Default "record_time".
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with is_workday (int) column added.
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # Parse options
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    time_field = params.get("time_field") or options.get("time_field") or "record_time"

    df = data.copy()

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning as-is")
        return {"data": df}

    if time_field not in df.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"Timestamp column '{time_field}' not found in input DataFrame. "
            f"Available columns: {list(df.columns)}",
        )

    # Ensure timestamp is datetime
    df[time_field] = pd.to_datetime(df[time_field], errors="coerce")

    # @AI_GENERATED
    # 使用 chinese_calendar 库判断工作日，完全不依赖本地代码
    try:
        from chinese_calendar import is_workday as cc_is_workday
        df["is_workday"] = df[time_field].apply(
            lambda x: 1 if cc_is_workday(x.date() if hasattr(x, 'date') else x) else 0
        )
    except ImportError:
        # Fallback: 周一到周五=工作日
        df["is_workday"] = (df[time_field].dt.dayofweek < 5).astype(int)
    # @AI_GENERATED: end

    n_workdays = int(df["is_workday"].sum())
    n_total = len(df)
    logger.info(
        f"[{OPERATOR_ID}] Marked {n_workdays}/{n_total} data points as workday"
    )

    return {"data": df}
# @AI_GENERATED: end
