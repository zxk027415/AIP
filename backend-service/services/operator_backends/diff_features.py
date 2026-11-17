# @AI_GENERATED
"""
diff_features operator backend — Computes difference features on target column.

Generates 1st order diff and seasonal diff features.
Reuses logic from add_features.get_diff_features.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "diff_features"

DEFAULT_DIFF_PERIODS = [1]
DEFAULT_SEASONAL_PERIOD = 24


def _to_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return bool(v)


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute difference features on target column.

    Args:
        params: Operator parameters including:
            - target_column (str, optional): Column to diff. Default "load".
            - diff_periods (list, optional): Diff orders/periods. Default [1].
            - seasonal_period (int, optional): Seasonal diff period. Default 24.
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with new diff columns.
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

    diff_periods_raw = params.get("diff_periods") or options.get("diff_periods")
    if isinstance(diff_periods_raw, str):
        try:
            diff_periods_raw = json.loads(diff_periods_raw)
        except json.JSONDecodeError:
            diff_periods_raw = DEFAULT_DIFF_PERIODS
    diff_periods = (
        diff_periods_raw if isinstance(diff_periods_raw, list) else DEFAULT_DIFF_PERIODS
    )

    seasonal_period = params.get("seasonal_period") or options.get("seasonal_period")
    if seasonal_period is not None:
        seasonal_period = int(seasonal_period)
    else:
        seasonal_period = DEFAULT_SEASONAL_PERIOD
    no_leak_mode = _to_bool(
        params.get("no_leak_mode")
        if params.get("no_leak_mode") is not None
        else options.get("no_leak_mode"),
        False,
    )
    horizon_per_day = int(
        params.get("horizon_per_day") or options.get("horizon_per_day") or 96
    )
    include_cross_day = _to_bool(
        params.get("include_cross_day_diff")
        if params.get("include_cross_day_diff") is not None
        else options.get("include_cross_day_diff"),
        True,
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

    new_cols = 0

    if no_leak_mode:
        base_col = f"{target_column}_prev"
        if base_col not in df.columns:
            df[base_col] = df[target_column].shift(1)
        for period in diff_periods:
            period = int(period)
            col_name = f"{target_column}_diff_{period}"
            df[col_name] = df[base_col] - df[base_col].shift(period)
            new_cols += 1

        for d in (horizon_per_day, 2 * horizon_per_day):
            col_name = f"{target_column}_diff_{d}"
            if col_name not in df.columns:
                df[col_name] = df[base_col] - df[base_col].shift(d)
                new_cols += 1

        if include_cross_day:
            col_name = f"{target_column}_diff_{horizon_per_day}_of_{horizon_per_day}"
            df[col_name] = (
                df[base_col].shift(horizon_per_day)
                - df[base_col].shift(2 * horizon_per_day)
            )
            new_cols += 1

        logger.info(
            f"[{OPERATOR_ID}] Added {new_cols} no-leak diff columns "
            f"(target={target_column}, horizon_per_day={horizon_per_day})"
        )
        return {"data": df}

    # 1st order diff (and any additional diff periods)
    for period in diff_periods:
        period = int(period)
        col_name = f"{target_column}_diff_{period}"
        df[col_name] = df[target_column].diff(periods=period)
        new_cols += 1

    # Seasonal diff
    col_name = f"{target_column}_seasonal_diff_{seasonal_period}"
    df[col_name] = df[target_column].diff(periods=seasonal_period)
    new_cols += 1

    logger.info(
        f"[{OPERATOR_ID}] Added {new_cols} diff columns "
        f"(diff_periods={diff_periods}, seasonal_period={seasonal_period}, "
        f"target={target_column})"
    )

    return {"data": df}
# @AI_GENERATED: end
