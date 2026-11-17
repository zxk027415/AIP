# @AI_GENERATED
"""
pct_change_features operator backend — Computes percentage change features.

Calculates percentage change on the target column over configurable periods.
Reuses logic from add_features.get_pct_rate_feature.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "pct_change_features"

DEFAULT_PERIODS = [1]


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute percentage change features on target column.

    Args:
        params: Operator parameters including:
            - target_column (str, optional): Column to compute pct change. Default "load".
            - periods (list, optional): Periods for pct_change. Default [1].
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with new pct_change columns.
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

    periods_raw = params.get("periods") or options.get("periods")
    if isinstance(periods_raw, str):
        try:
            periods_raw = json.loads(periods_raw)
        except json.JSONDecodeError:
            periods_raw = DEFAULT_PERIODS
    periods = periods_raw if isinstance(periods_raw, list) else DEFAULT_PERIODS

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
    for period in periods:
        period = int(period)
        col_name = f"{target_column}_pct_change_{period}"
        df[col_name] = df[target_column].pct_change(periods=period)
        new_cols += 1

    logger.info(
        f"[{OPERATOR_ID}] Added {new_cols} pct_change columns "
        f"(periods={periods}, target={target_column})"
    )

    return {"data": df}
# @AI_GENERATED: end
