# @AI_GENERATED
"""
resample_timeseries operator backend — Resamples time series data to a target frequency.

Reuses logic from data_process.get_completed_timestamp:
generates a complete timestamp grid from min to max time, fills missing with NaN.
Supports mean/sum/max/min aggregation methods.
Advanced params: task_type, time_granularity, time_field, load_field.
"""
import json

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "resample_timeseries"


def _to_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return bool(v)


def _resample_frame_segment(
    df: pd.DataFrame,
    *,
    time_field: str,
    frequency: str,
    method: str,
) -> pd.DataFrame:
    """Resample one continuous time segment without creating rows outside it."""
    if df.empty:
        return df.copy()

    segment = df.copy()
    segment[time_field] = pd.to_datetime(segment[time_field], errors="coerce")
    segment = segment.sort_values(time_field).drop_duplicates(subset=[time_field], keep="first")

    start = segment[time_field].min()
    end = segment[time_field].max()
    if pd.isna(start) or pd.isna(end):
        return segment

    full_index = pd.date_range(start=start, end=end, freq=frequency)
    base = pd.DataFrame({time_field: full_index})

    numeric_cols = segment.select_dtypes(include=[np.number]).columns.tolist()
    if numeric_cols:
        df_indexed = segment.set_index(time_field)
        agg_func = getattr(df_indexed[numeric_cols].resample(frequency), method)
        resampled = agg_func().reset_index()
    else:
        resampled = segment[[time_field]].copy()

    return base.merge(resampled, how="left", on=time_field)


def execute(params: dict, inputs: dict) -> dict:
    """
    Resample time series data to a target frequency and generate a complete timestamp grid.

    Args:
        params: Operator parameters including:
            - frequency (str, optional): Target frequency, e.g. "15min", "1H". Default "15min".
            - method (str, optional): Aggregation method: mean/sum/max/min. Default "mean".
            - task_type (str, optional): Forecast task type (advanced).
            - time_granularity (str, optional): Time granularity (advanced).
            - time_field (str, optional): Timestamp column name. Default "record_time".
            - load_field (str, optional): Load/value column name. Default "load".
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with complete timestamp grid at target frequency.
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # Parse options if provided as JSON string
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    # Resolve parameters (params take priority, then options, then defaults)
    frequency = params.get("frequency") or options.get("time_granularity") or options.get("frequency") or "15min"
    method = params.get("method") or options.get("method") or "mean"
    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    load_field = params.get("load_field") or options.get("load_field") or "load"
    gcfg = params.get("_global_config") or {}
    strict_alignment_raw = params.get("strict_alignment_mode")
    if strict_alignment_raw is None:
        strict_alignment_raw = options.get("strict_alignment_mode")
    if strict_alignment_raw is None and isinstance(gcfg, dict):
        strict_alignment_raw = gcfg.get("strict_alignment_mode")
    strict_alignment_mode = _to_bool(strict_alignment_raw, False)
    skip_when_strict = _to_bool(
        params.get("skip_when_strict_alignment")
        if params.get("skip_when_strict_alignment") is not None
        else options.get("skip_when_strict_alignment"),
        False,
    )

    valid_methods = {"mean", "sum", "max", "min"}
    if method not in valid_methods:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Invalid method '{method}'. Must be one of {sorted(valid_methods)}",
        )

    df = data.copy()

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning as-is")
        return {"data": df}

    if time_field not in df.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ColumnError",
            f"Time field '{time_field}' not found in input columns: {list(df.columns)}",
        )

    # Ensure datetime type
    df[time_field] = pd.to_datetime(df[time_field], errors="coerce")

    if strict_alignment_mode and skip_when_strict:
        train_end_raw = gcfg.get("backtest_train_end") if isinstance(gcfg, dict) else None
        pred_start_raw = gcfg.get("backtest_pred_start") if isinstance(gcfg, dict) else None
        train_end = pd.to_datetime(train_end_raw, errors="coerce") if train_end_raw else pd.NaT
        pred_start = pd.to_datetime(pred_start_raw, errors="coerce") if pred_start_raw else pd.NaT

        if pd.notna(train_end) and pd.notna(pred_start):
            train_part = df[df[time_field] <= train_end]
            pred_part = df[df[time_field] >= pred_start]
            resampled_parts = [
                _resample_frame_segment(
                    part,
                    time_field=time_field,
                    frequency=frequency,
                    method=method,
                )
                for part in (train_part, pred_part)
                if not part.empty
            ]
            out = (
                pd.concat(resampled_parts, ignore_index=True)
                if resampled_parts
                else df.iloc[0:0].copy()
            )
            out = out.sort_values(time_field).reset_index(drop=True)
            logger.info(
                f"[{OPERATOR_ID}] strict_alignment_mode enabled, resampled separated "
                f"train/pred segments {len(df)} -> {len(out)} rows"
            )
            return {"data": out}

        logger.info(f"[{OPERATOR_ID}] strict_alignment_mode enabled, bypass resampling")
        return {"data": df.sort_values(time_field).reset_index(drop=True)}

    df = df.sort_values(time_field).drop_duplicates(subset=[time_field], keep="first")

    start = df[time_field].min()
    end = df[time_field].max()

    if pd.isna(start) or pd.isna(end):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "DataError",
            "Could not determine time range — timestamps may be invalid",
        )

    # Generate complete timestamp grid
    full_index = pd.date_range(start=start, end=end, freq=frequency)
    base = pd.DataFrame({time_field: full_index})

    # Identify numeric columns for aggregation
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # If there are duplicate timestamps at the target frequency, aggregate them
    df_indexed = df.set_index(time_field)
    numeric_df = df_indexed[numeric_cols] if numeric_cols else df_indexed

    if not numeric_df.empty and len(numeric_df) > 0:
        agg_func = getattr(numeric_df.resample(frequency), method)
        resampled = agg_func()
        resampled = resampled.reset_index()
    else:
        resampled = df

    # Merge with complete grid to fill gaps with NaN
    out = base.merge(resampled, how="left", on=time_field)

    rows_before = len(df)
    rows_after = len(out)
    logger.info(
        f"[{OPERATOR_ID}] Resampled {rows_before} -> {rows_after} rows "
        f"(freq={frequency}, method={method})"
    )

    return {"data": out}
# @AI_GENERATED: end
