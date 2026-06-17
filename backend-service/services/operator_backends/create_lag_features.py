# @AI_GENERATED
"""
create_lag_features operator backend — Generates lag features by shifting target column.

Shifts the target column by specified lag periods.
NaN values from shifting are preserved (not filled).
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "create_lag_features"

DEFAULT_LAGS = [1, 24, 168]


def execute(params: dict, inputs: dict) -> dict:
    """
    Generate lag features for the target column.

    Args:
        params: Operator parameters including:
            - lags (list, optional): Lag periods. Default [1, 24, 168].
            - target_column (str, optional): Column to lag. Default "load".
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with new lag columns (NaN preserved).
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

    target_column = (
        params.get("target_column")
        or options.get("target_column")
        or "load"
    )

    lags_raw = params.get("lags") if params.get("lags") is not None else (options.get("lags") or options.get("lag_periods"))
    if isinstance(lags_raw, str):
        try:
            lags_raw = json.loads(lags_raw)
        except json.JSONDecodeError:
            lags_raw = DEFAULT_LAGS
    lags = lags_raw if isinstance(lags_raw, list) else DEFAULT_LAGS
    lag_days_raw = params.get("lag_days") or options.get("lag_days") or []
    if isinstance(lag_days_raw, str):
        try:
            lag_days_raw = json.loads(lag_days_raw)
        except json.JSONDecodeError:
            lag_days_raw = []
    lag_days = lag_days_raw if isinstance(lag_days_raw, list) else []
    horizon_per_day = int(
        params.get("horizon_per_day") or options.get("horizon_per_day") or 96
    )
    add_same_time_ensemble = bool(
        params.get("add_same_time_ensemble")
        if params.get("add_same_time_ensemble") is not None
        else options.get("add_same_time_ensemble", False)
    )

    df = data.copy()

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning as-is")
        return {"data": df}

    if target_column not in df.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"Target column '{target_column}' not found. "
            f"Available columns: {list(df.columns)}",
        )

    all_lags = []
    for lag in lags:
        all_lags.append(int(lag))
    if horizon_per_day > 0:
        for day_lag in lag_days:
            all_lags.append(int(day_lag) * horizon_per_day)
    all_lags = sorted({x for x in all_lags if x > 0})

    new_cols = 0
    for lag in all_lags:
        col_name = f"{target_column}_lag_{lag}"
        df[col_name] = df[target_column].shift(lag)
        new_cols += 1

    if add_same_time_ensemble and horizon_per_day > 0:
        lag_7 = f"{target_column}_lag_{7 * horizon_per_day}"
        lag_14 = f"{target_column}_lag_{14 * horizon_per_day}"
        lag_21 = f"{target_column}_lag_{21 * horizon_per_day}"
        if lag_7 in df.columns and lag_14 in df.columns:
            df["same_time_2w"] = (df[lag_7] + df[lag_14]) / 2.0
            new_cols += 1
        if lag_7 in df.columns and lag_14 in df.columns and lag_21 in df.columns:
            df["same_time_3w"] = (df[lag_7] + df[lag_14] + df[lag_21]) / 3.0
            new_cols += 1

    logger.info(
        f"[{OPERATOR_ID}] Added {new_cols} lag columns "
        f"(lags={all_lags}, target={target_column}, horizon_per_day={horizon_per_day}, "
        f"add_same_time_ensemble={add_same_time_ensemble})"
    )

    return {"data": df}
# @AI_GENERATED: end
