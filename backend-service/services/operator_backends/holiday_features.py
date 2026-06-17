# @AI_GENERATED
"""
holiday_features operator backend — Marks Chinese holidays in time series data.

Uses chinese_calendar library to identify Chinese statutory holidays.
Generates is_holiday (int) and holiday_name (str) columns.
Advanced param: remove_spring_festival (bool) to filter out Spring Festival data.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "holiday_features"


def _get_holiday_detail_safe(date):
    """
    Get holiday detail using chinese_calendar.
    Returns (is_holiday: bool, holiday_name: str or None).
    Falls back to weekend-based detection if library unavailable.
    """
    try:
        from chinese_calendar import get_holiday_detail
        on_holiday, holiday_name = get_holiday_detail(date)
        if on_holiday:
            return True, (holiday_name.value if hasattr(holiday_name, 'value') else str(holiday_name)) if holiday_name else "未知节假日"
        return False, ""
    except ImportError:
        # Fallback: weekend = holiday
        is_weekend = date.weekday() >= 5
        return is_weekend, ("周末" if is_weekend else "")
    except Exception:
        # For dates outside chinese_calendar's supported range
        is_weekend = date.weekday() >= 5
        return is_weekend, ("周末" if is_weekend else "")


def execute(params: dict, inputs: dict) -> dict:
    """
    Mark Chinese holidays in time series data.

    Args:
        params: Operator parameters including:
            - time_field (str, optional): Timestamp column name. Default "record_time".
            - remove_spring_festival (bool, optional): Whether to remove Spring Festival
              data rows. Default False.
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with is_holiday (int) and holiday_name (str) columns added.
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
    remove_spring = params.get("remove_spring_festival") or options.get("remove_spring_festival")
    if isinstance(remove_spring, str):
        remove_spring = remove_spring.lower() in ("true", "1", "yes")
    remove_spring = bool(remove_spring) if remove_spring is not None else False

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

    # Extract holiday info for each unique date to avoid redundant calls
    dates = df[time_field].dt.date
    unique_dates = dates.unique()

    holiday_map = {}
    for d in unique_dates:
        if pd.isna(d):
            holiday_map[d] = (0, "")
            continue
        is_hol, hol_name = _get_holiday_detail_safe(d)
        holiday_map[d] = (int(is_hol), hol_name)

    df["is_holiday"] = dates.map(lambda d: holiday_map.get(d, (0, ""))[0])
    df["holiday_name"] = dates.map(lambda d: holiday_map.get(d, (0, ""))[1])

    n_holidays = int(df["is_holiday"].sum())

    # Remove Spring Festival data if requested
    rows_before = len(df)
    if remove_spring:
        spring_keywords = ["春节", "Spring Festival", "除夕"]
        mask = df["holiday_name"].apply(
            lambda x: any(kw in str(x) for kw in spring_keywords)
        )
        df = df[~mask].reset_index(drop=True)
        removed = rows_before - len(df)
        if removed > 0:
            logger.info(
                f"[{OPERATOR_ID}] Removed {removed} Spring Festival rows"
            )

    logger.info(
        f"[{OPERATOR_ID}] Marked {n_holidays} holiday data points "
        f"(remove_spring_festival={remove_spring})"
    )

    return {"data": df}
# @AI_GENERATED: end
