# @AI_GENERATED
"""
extract_time_features operator backend — Extracts time-based features from timestamp column.

Reuses logic from features/engine.py time feature extraction.
Supports hour/dayofweek/month/day/quarter/is_holiday features.
time_zone from global config injection.
Merges extracted feature columns into input DataFrame.
"""
import json

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "extract_time_features"

# All supported time features
SUPPORTED_FEATURES = {
    "hour",
    "minute",
    "period",
    "dayofweek",
    "month",
    "day",
    "yday",
    "quarter",
    "is_holiday",
    "hour_sin",
    "hour_cos",
    "wday_sin",
    "wday_cos",
    "yday_sin",
    "yday_cos",
    "month_sin",
    "month_cos",
}


def execute(params: dict, inputs: dict) -> dict:
    """
    Extract time features from timestamp column.

    Args:
        params: Operator parameters including:
            - features (list, optional): List of feature names to extract.
              Default: all supported features.
            - time_field (str, optional): Timestamp column name. Default "record_time".
            - time_zone (str, optional): Timezone for conversion. Default "Asia/Shanghai".
              Typically injected from global config.
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with new time feature columns merged.
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

    features_raw = params.get("features") or options.get("features")
    if isinstance(features_raw, str):
        try:
            features_raw = json.loads(features_raw)
        except json.JSONDecodeError:
            features_raw = list(SUPPORTED_FEATURES)
    features = features_raw if isinstance(features_raw, list) else list(SUPPORTED_FEATURES)

    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    time_zone = params.get("time_zone") or options.get("time_zone") or "Asia/Shanghai"

    # Validate features
    invalid = set(features) - SUPPORTED_FEATURES
    if invalid:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Unsupported features: {sorted(invalid)}. "
            f"Supported: {sorted(SUPPORTED_FEATURES)}",
        )

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

    # Localize to timezone if needed
    ts = df[time_field]
    try:
        import pytz
        tz = pytz.timezone(time_zone)
        if ts.dt.tz is None:
            ts_localized = ts.dt.tz_localize(tz)
        else:
            ts_localized = ts.dt.tz_convert(tz)
    except Exception:
        ts_localized = ts

    # Extract features (reuses logic from features/engine.py)
    extracted_count = 0
    for feat in features:
        if feat == "hour":
            df["hour"] = ts_localized.dt.hour
            extracted_count += 1
        elif feat == "minute":
            df["minute"] = ts_localized.dt.minute
            extracted_count += 1
        elif feat == "period":
            hour = ts_localized.dt.hour
            minute = ts_localized.dt.minute
            df["period"] = hour * 4 + (minute // 15)
            extracted_count += 1
        elif feat == "dayofweek":
            df["dayofweek"] = ts_localized.dt.dayofweek
            extracted_count += 1
        elif feat == "month":
            df["month"] = ts_localized.dt.month
            extracted_count += 1
        elif feat == "day":
            df["day"] = ts_localized.dt.day
            extracted_count += 1
        elif feat == "yday":
            df["yday"] = ts_localized.dt.dayofyear
            extracted_count += 1
        elif feat == "quarter":
            df["quarter"] = ts_localized.dt.quarter
            extracted_count += 1
        elif feat == "is_holiday":
            # @AI_GENERATED
            # 使用 chinese_calendar 库判断节假日，完全不依赖本地代码
            try:
                from chinese_calendar import is_workday as cc_is_workday
                df["is_holiday"] = ts_localized.apply(
                    lambda x: 0 if cc_is_workday(x.date() if hasattr(x, 'date') else x) else 1
                )
            except ImportError:
                # Fallback: 周末=节假日
                df["is_holiday"] = (ts_localized.dt.dayofweek >= 5).astype(int)
            # @AI_GENERATED: end
            extracted_count += 1
        elif feat == "hour_sin":
            hour = ts_localized.dt.hour
            df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
            extracted_count += 1
        elif feat == "hour_cos":
            hour = ts_localized.dt.hour
            df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
            extracted_count += 1
        elif feat == "wday_sin":
            wday = ts_localized.dt.dayofweek
            df["wday_sin"] = np.sin(2 * np.pi * wday / 7)
            extracted_count += 1
        elif feat == "wday_cos":
            wday = ts_localized.dt.dayofweek
            df["wday_cos"] = np.cos(2 * np.pi * wday / 7)
            extracted_count += 1
        elif feat == "yday_sin":
            yday = ts_localized.dt.dayofyear
            df["yday_sin"] = np.sin(2 * np.pi * yday / 365)
            extracted_count += 1
        elif feat == "yday_cos":
            yday = ts_localized.dt.dayofyear
            df["yday_cos"] = np.cos(2 * np.pi * yday / 365)
            extracted_count += 1
        elif feat == "month_sin":
            month = ts_localized.dt.month
            df["month_sin"] = np.sin(2 * np.pi * month / 12)
            extracted_count += 1
        elif feat == "month_cos":
            month = ts_localized.dt.month
            df["month_cos"] = np.cos(2 * np.pi * month / 12)
            extracted_count += 1

    logger.info(
        f"[{OPERATOR_ID}] Extracted {extracted_count} time features: {features} "
        f"(time_zone={time_zone})"
    )

    return {"data": df}
# @AI_GENERATED: end
