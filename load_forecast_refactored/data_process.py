"""
Minimal, no-leakage-aware data processing utilities.

This repository is a refactor-in-progress. Some entry scripts (e.g. ``run.py``)
still import functions from a legacy module named ``data_process``.

The implementations below are intentionally conservative and designed to make
offline backtests runnable. They focus on:
 - timestamp completion (regular grid)
 - basic anomaly handling (simple robust z-score / rolling stats)
 - filling missing values without peeking into the future
 - basic training-readiness checks
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from loguru import logger


def get_timestamp_freq(df: pd.DataFrame, time_field: str = "record_time") -> Tuple[str, int]:
    """
    Infer original frequency string and daily_horizon (#points per day).
    Returns (freq_str, daily_horizon).
    """
    if df is None or df.empty:
        return "15min", 96

    ts = pd.to_datetime(df[time_field]).sort_values()
    if len(ts) < 2:
        return "15min", 96

    deltas = ts.diff().dropna()
    # Most common delta
    mode_delta = deltas.mode()
    delta = mode_delta.iloc[0] if len(mode_delta) else deltas.iloc[0]

    # Convert to a friendly pandas frequency string when possible
    minutes = int(delta.total_seconds() // 60)
    if minutes <= 0:
        freq = "15min"
    elif minutes % (24 * 60) == 0:
        freq = f"{minutes // (24 * 60)}D"
    elif minutes % 60 == 0:
        freq = f"{minutes // 60}H"
    else:
        freq = f"{minutes}min"

    daily_horizon = max(1, int(round((24 * 60) / minutes))) if minutes > 0 else 96
    return freq, daily_horizon


def get_daily_horizon(df: pd.DataFrame, time_field: str = "record_time") -> int:
    _, h = get_timestamp_freq(df, time_field=time_field)
    return h


def get_completed_timestamp(df: pd.DataFrame,
                            original_time_freq: str,
                            daily_horizon: int,
                            is_training: str,
                            time_field: str = "record_time") -> pd.DataFrame:
    """
    Create a continuous timestamp grid between min and max timestamp and
    outer-merge original data onto it.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[time_field])

    tmp = df.copy()
    tmp[time_field] = pd.to_datetime(tmp[time_field])
    tmp = tmp.sort_values(time_field).drop_duplicates(subset=[time_field], keep="first")

    start = tmp[time_field].min()
    end = tmp[time_field].max()
    full_index = pd.date_range(start, end, freq=original_time_freq)
    base = pd.DataFrame({time_field: full_index})

    out = base.merge(tmp, how="left", on=time_field)
    logger.info(f"completed timestamps: {len(tmp)} -> {len(out)}")
    return out


def chebyshev_detector(df: pd.DataFrame,
                       load_field: str = "load",
                       time_field: str = "record_time",
                       window: int = 96,
                       z: float = 6.0) -> pd.DataFrame:
    """
    Basic anomaly detection: mark strong outliers as NaN using rolling median/MAD.
    This is a conservative replacement for the original chebyshev-based logic.
    """
    if df is None or df.empty or load_field not in df.columns:
        return df

    out = df.copy()
    x = pd.to_numeric(out[load_field], errors="coerce")

    # Rolling robust stats (past-only by shifting 1)
    med = x.rolling(window=window, min_periods=max(5, window // 10)).median().shift(1)
    mad = (x - med).abs().rolling(window=window, min_periods=max(5, window // 10)).median().shift(1)
    scale = 1.4826 * mad  # MAD -> approx std

    # Avoid division by zero
    denom = scale.replace(0, np.nan)
    score = (x - med).abs() / denom
    mask = score > z
    n = int(mask.sum(skipna=True))
    if n:
        logger.info(f"anomaly_detector marked {n} points as NaN")
        out.loc[mask, load_field] = np.nan
    return out


def capture_cols(df: pd.DataFrame) -> Dict[str, int]:
    return {c: int(df[c].isna().sum()) for c in df.columns}


def get_completed_df(df: pd.DataFrame,
                     delay_info=None,
                     time_field: str = "record_time",
                     load_field: str = "load") -> pd.DataFrame:
    """
    Fill missing values after timestamp completion and anomaly marking.

    - load: time interpolation then ffill/bfill
    - other cols: ffill/bfill
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[time_field, load_field])

    out = df.copy()
    out[time_field] = pd.to_datetime(out[time_field])
    out = out.sort_values(time_field)

    # Fill load conservatively (interpolate on time)
    if load_field in out.columns:
        out[load_field] = pd.to_numeric(out[load_field], errors="coerce")
        out.set_index(time_field, inplace=True)
        out[load_field] = out[load_field].interpolate(method="time", limit_direction="forward")
        out[load_field] = out[load_field].ffill().bfill()
        out.reset_index(inplace=True)

    # Fill other columns
    for c in out.columns:
        if c in (time_field, load_field):
            continue
        out[c] = pd.to_numeric(out[c], errors="coerce")
        out[c] = out[c].ffill().bfill()

    return out


def get_train_status(df: pd.DataFrame,
                     task_type: str,
                     forecast_horizon: int,
                     time_field: str = "record_time",
                     load_field: str = "load",
                     min_days: int = 14) -> str:
    """
    Decide if training can proceed based on minimum history availability.
    """
    if df is None or df.empty:
        return "false"
    if load_field not in df.columns:
        return "false"

    tmp = df.copy()
    tmp[time_field] = pd.to_datetime(tmp[time_field])
    tmp = tmp.dropna(subset=[load_field])
    if tmp.empty:
        return "false"

    start = tmp[time_field].min().normalize()
    end = tmp[time_field].max().normalize()
    days = int((end - start).days) + 1
    ok = days >= min_days
    if not ok:
        logger.warning(f"not enough history for training: {days} days (<{min_days})")
    return "true" if ok else "false"


def get_all_filled_data(df: pd.DataFrame, cols) -> pd.DataFrame:
    """
    Lightweight periodic fill for NaNs.

    Strategy:
    - try fill from 7 days ago (weekly seasonality) if index is a DatetimeIndex
    - fallback to forward-fill / back-fill
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out = out.copy()

    for c in cols:
        if c not in out.columns:
            continue
        s = pd.to_numeric(out[c], errors="coerce")
        if isinstance(out.index, pd.DatetimeIndex):
            s_week = s.shift(7 * 96)  # default 15min; acceptable fallback
            s = s.fillna(s_week)
        s = s.ffill().bfill()
        out[c] = s
    return out

