# @AI_GENERATED
"""
rolling_statistics operator backend — Computes rolling statistical features.

Reuses logic from add_features.get_rolling_features.
Computes rolling mean/std/quantile over configurable window sizes.
Only uses historical data (no future leak) via shift(1) before rolling.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "rolling_statistics"

DEFAULT_WINDOW_SIZES = [24, 48, 96, 168]
DEFAULT_STATISTICS = ["mean", "std"]
SUPPORTED_STATISTICS = {"mean", "std", "max", "min", "quantile"}


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute rolling statistical features on target column.

    Args:
        params: Operator parameters including:
            - target_column (str, optional): Column to compute stats on. Default "load".
            - window_sizes (list, optional): Rolling window sizes. Default [24,48,96,168].
            - statistics (list, optional): Stats to compute. Default ["mean","std"].
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with new rolling statistic columns.
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

    window_sizes_raw = params.get("window_sizes") or options.get("window_sizes")
    if isinstance(window_sizes_raw, str):
        try:
            window_sizes_raw = json.loads(window_sizes_raw)
        except json.JSONDecodeError:
            window_sizes_raw = DEFAULT_WINDOW_SIZES
    window_sizes = (
        window_sizes_raw if isinstance(window_sizes_raw, list) else DEFAULT_WINDOW_SIZES
    )

    statistics_raw = params.get("statistics") or options.get("statistics")
    if isinstance(statistics_raw, str):
        try:
            statistics_raw = json.loads(statistics_raw)
        except json.JSONDecodeError:
            statistics_raw = DEFAULT_STATISTICS
    statistics = (
        statistics_raw if isinstance(statistics_raw, list) else DEFAULT_STATISTICS
    )
    base_shift = int(
        params.get("base_shift")
        or options.get("base_shift")
        or params.get("anchor_lag")
        or options.get("anchor_lag")
        or 1
    )
    min_periods = int(params.get("min_periods") or options.get("min_periods") or 1)

    # Validate statistics
    invalid = set(statistics) - SUPPORTED_STATISTICS
    if invalid:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Unsupported statistics: {sorted(invalid)}. "
            f"Supported: {sorted(SUPPORTED_STATISTICS)}",
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

    # Use shifted series to avoid future data leakage
    shifted = df[target_column].shift(base_shift)

    new_cols = 0
    for window in window_sizes:
        window = int(window)
        rolling = shifted.rolling(window=window, min_periods=min_periods)

        for stat in statistics:
            if stat == "mean":
                col_name = f"{target_column}_rolling_mean_{window}"
                df[col_name] = rolling.mean()
                new_cols += 1
            elif stat == "std":
                col_name = f"{target_column}_rolling_std_{window}"
                df[col_name] = rolling.std()
                new_cols += 1
            elif stat == "max":
                col_name = f"{target_column}_rolling_max_{window}"
                df[col_name] = rolling.max()
                new_cols += 1
            elif stat == "min":
                col_name = f"{target_column}_rolling_min_{window}"
                df[col_name] = rolling.min()
                new_cols += 1
            elif stat == "quantile":
                col_name = f"{target_column}_rolling_q50_{window}"
                df[col_name] = rolling.quantile(0.5)
                new_cols += 1

    logger.info(
        f"[{OPERATOR_ID}] Added {new_cols} rolling statistic columns "
        f"(windows={window_sizes}, stats={statistics}, target={target_column}, "
        f"base_shift={base_shift}, min_periods={min_periods})"
    )

    return {"data": df}
# @AI_GENERATED: end
