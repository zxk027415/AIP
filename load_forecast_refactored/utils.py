"""
Minimal utilities required to run the offline backtest.

This is a compatibility module for legacy imports used by ``run.py`` and
``features/engine.py``.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from loguru import logger


def smape(y_true, y_pred, eps: float = 1e-8) -> float:
    """
    Symmetric mean absolute percentage error in percent.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.maximum(eps, (np.abs(y_true) + np.abs(y_pred)) / 2.0)
    return float(np.mean(np.abs(y_pred - y_true) / denom) * 100.0)


def shift_len_mapping(shift_str: str, daily_horizon: int) -> int:
    """
    Map human shift strings like '3H'/'2D' to row shift length.
    For day-based shifts: D * daily_horizon.
    For hour-based shifts: approximate using daily_horizon / 24.
    """
    if not shift_str:
        return 0
    s = str(shift_str).strip().upper()
    try:
        if s.endswith("D"):
            return int(float(s[:-1]) * daily_horizon)
        if s.endswith("H"):
            per_hour = max(1, int(round(daily_horizon / 24)))
            return int(float(s[:-1]) * per_hour)
        if s.endswith("MIN"):
            # rare; treat as 1 step
            return 1
    except Exception:
        return 0
    return 0


def capture_df_delay_info(df: pd.DataFrame,
                          is_training: str,
                          trigger_time: str,
                          time_field: str = "record_time") -> Dict[str, Any]:
    """
    In the original system this recorded late-arriving data info.
    For offline backtests we return a lightweight dict payload.
    """
    return {
        "trigger_time": trigger_time,
        "is_training": is_training,
        "raw_data_delay_info": json.dumps({"note": "offline_backtest_stub"}),
    }


def get_delay_info_from_offline_db(task_id: str, parent_id: str, child_id: str, operate_status: str):
    """
    Stub for DI scenario shift/delay lookup.
    Returns an empty DataFrame in offline mode.
    """
    return pd.DataFrame()


def df_recovery_by_self_defined(load_df: pd.DataFrame,
                               that_time_latest: Dict[str, str],
                               time_granularity: str,
                               time_field: str = "record_time",
                               load_field: str = "load"):
    """
    Stub for late data recovery. In offline backtests we assume the loaded CSV
    is already consistent; return inputs unchanged.
    """
    his_min_max = pd.DataFrame({"min": [pd.to_numeric(load_df[load_field], errors="coerce").min()],
                                "max": [pd.to_numeric(load_df[load_field], errors="coerce").max()]}) if (
        load_df is not None and not load_df.empty and load_field in load_df.columns
    ) else pd.DataFrame()
    return load_df, his_min_max


def predict_format_transform(pred_re: List[float],
                             forecast_timestamps: List[str],
                             his_min_max: pd.DataFrame,
                             time_field: str = "record_time",
                             load_field: str = "load") -> List[Dict[str, Any]]:
    """
    Transform prediction vector into the legacy JSON list format expected by
    ``run.py``.

    Each item:
      - 'time': unix timestamp (seconds)
      - load_field: clipped prediction value
    """
    preds = np.asarray(pred_re, dtype=float).flatten()
    if his_min_max is not None and not his_min_max.empty and {"min", "max"} <= set(his_min_max.columns):
        vmin = float(his_min_max["min"].iloc[0])
        vmax = float(his_min_max["max"].iloc[0])
        if np.isfinite(vmin) and np.isfinite(vmax) and vmin < vmax:
            preds = np.clip(preds, vmin, vmax)

    out = []
    for ts_str, v in zip(forecast_timestamps, preds.tolist()):
        dt = pd.to_datetime(ts_str)
        out.append({"time": int(dt.timestamp()), load_field: float(v)})
    return out


# ---- legacy no-op / optional functions ----
def predict_format_transform_v2(*args, **kwargs):
    return predict_format_transform(*args, **kwargs)


def delay_info_insert_offline_db(*args, **kwargs):
    logger.info("delay_info_insert_offline_db: stub (no-op)")


def insert_beta(*args, **kwargs):
    logger.info("insert_beta: stub (no-op)")


def get_delay_info_from_offline_db_v2(*args, **kwargs):
    return pd.DataFrame()


def df_recovery_from_db(*args, **kwargs):
    logger.info("df_recovery_from_db: stub (no-op)")
    return pd.DataFrame(), pd.DataFrame()

