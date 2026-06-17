# @AI_GENERATED
"""
peak_valley_features operator backend — Marks peak/valley/flat periods.

Classifies each timestamp into peak, valley, or flat period based on hour of day.
Default peak/valley/flat definitions follow typical Chinese electricity pricing periods.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "peak_valley_features"

# Default Chinese electricity peak/valley/flat hour definitions
# Peak: 8-11, 18-21; Valley: 0-7, 23; Flat: 12-17, 22
DEFAULT_PEAK_HOURS = [8, 9, 10, 11, 18, 19, 20, 21]
DEFAULT_VALLEY_HOURS = [0, 1, 2, 3, 4, 5, 6, 7, 23]


def execute(params: dict, inputs: dict) -> dict:
    """
    Mark peak/valley/flat periods based on hour of day.

    Args:
        params: Operator parameters including:
            - time_field (str, optional): Timestamp column name. Default "record_time".
            - peak_hours (list, optional): Hours classified as peak.
            - valley_hours (list, optional): Hours classified as valley.
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with peak_valley_flag column (1=peak, -1=valley, 0=flat).
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

    peak_hours_raw = params.get("peak_hours") or options.get("peak_hours")
    if isinstance(peak_hours_raw, str):
        try:
            peak_hours_raw = json.loads(peak_hours_raw)
        except json.JSONDecodeError:
            peak_hours_raw = DEFAULT_PEAK_HOURS
    peak_hours = set(
        peak_hours_raw if isinstance(peak_hours_raw, list) else DEFAULT_PEAK_HOURS
    )

    valley_hours_raw = params.get("valley_hours") or options.get("valley_hours")
    if isinstance(valley_hours_raw, str):
        try:
            valley_hours_raw = json.loads(valley_hours_raw)
        except json.JSONDecodeError:
            valley_hours_raw = DEFAULT_VALLEY_HOURS
    valley_hours = set(
        valley_hours_raw if isinstance(valley_hours_raw, list) else DEFAULT_VALLEY_HOURS
    )

    df = data.copy()

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning as-is")
        return {"data": df}

    # Determine hour source: use existing 'hour' column or extract from time_field
    if "hour" in df.columns:
        hours = df["hour"]
    elif time_field in df.columns:
        df[time_field] = pd.to_datetime(df[time_field], errors="coerce")
        hours = df[time_field].dt.hour
    else:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"Neither 'hour' column nor timestamp column '{time_field}' found. "
            f"Available columns: {list(df.columns)}",
        )

    def classify_hour(h):
        if h in peak_hours:
            return 1
        elif h in valley_hours:
            return -1
        return 0

    df["peak_valley_flag"] = hours.apply(classify_hour)

    n_peak = int((df["peak_valley_flag"] == 1).sum())
    n_valley = int((df["peak_valley_flag"] == -1).sum())
    n_flat = int((df["peak_valley_flag"] == 0).sum())
    logger.info(
        f"[{OPERATOR_ID}] Marked peak={n_peak}, valley={n_valley}, flat={n_flat} periods"
    )

    return {"data": df}
# @AI_GENERATED: end
