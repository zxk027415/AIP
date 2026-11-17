# -*- coding: utf-8 -*-
"""日照 / 夜间诊断窗口切分（fault-diag 侧实现，与平台 time_window_split 语义对齐）。"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import pandas as pd

SUPPORTED_SOLAR_MODES = (
    "daylight",
    "solar_period",
    "multiscale",
    "night",
    "day_and_night",
)


def _resolve_power_col(df, power_col, value_cols):
    if power_col and power_col in df.columns:
        return power_col
    for candidate in ("power", "value", "i_cal", "P", "pac"):
        if candidate in df.columns:
            return candidate
    if value_cols:
        for col in value_cols:
            if col in df.columns:
                return str(col)
    raise ValueError("无法解析功率/电流列；请显式传入 power_col 或 value_cols")


def _validate_params(solar_mode, irr_threshold, peak_ratio):
    if solar_mode not in SUPPORTED_SOLAR_MODES:
        raise ValueError(f"不支持的 solar_mode={solar_mode!r}")
    if not (0.0 < float(irr_threshold) < 1.0):
        raise ValueError("irr_threshold 须在 (0, 1) 内")
    if float(peak_ratio) <= float(irr_threshold):
        raise ValueError("peak_ratio 必须大于 irr_threshold")


def segment_solar_window(
    data: pd.DataFrame,
    id_cols: List[str],
    time_col: str,
    value_cols: Optional[List[str]] = None,
    solar_mode: str = "daylight",
    irr_threshold: float = 0.05,
    peak_ratio: float = 0.30,
    sub_window: str = "4h",
    power_col: Optional[str] = None,
) -> Tuple[pd.DataFrame, List[str]]:
    _validate_params(solar_mode, irr_threshold, peak_ratio)
    if data is None or data.empty:
        empty = data.copy() if data is not None else pd.DataFrame()
        if not empty.empty:
            empty = empty.copy()
            empty["time_window"] = pd.NaT
            empty["period_role"] = None
        return empty, []

    df = data.drop(columns=["time_window", "period_role"], errors="ignore").copy()
    actual_id_cols = [c for c in (id_cols or []) if c in df.columns]
    power = _resolve_power_col(df, power_col, value_cols)
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])
    df["_date"] = pd.to_datetime(df[time_col]).dt.normalize()

    warnings: List[str] = []
    pieces: List[pd.DataFrame] = []
    group_keys = actual_id_cols + ["_date"] if actual_id_cols else ["_date"]

    for key, group in df.groupby(group_keys, sort=False):
        power_s = pd.to_numeric(group[power], errors="coerce").fillna(0.0)
        max_power = float(power_s.max()) if len(power_s) else 0.0
        if max_power <= 0:
            daylight_mask = pd.Series(False, index=group.index)
            night_mask = pd.Series(True, index=group.index)
            warnings.append(f"{key}: max_power==0")
        else:
            threshold = max_power * float(irr_threshold)
            daylight_mask = power_s >= threshold
            night_mask = ~daylight_mask

        date_str = pd.Timestamp(group["_date"].iloc[0]).date().isoformat()

        if solar_mode in ("daylight", "day_and_night", "solar_period", "multiscale"):
            day_rows = group.loc[daylight_mask].copy()
            if not day_rows.empty:
                if solar_mode == "solar_period":
                    ps = pd.to_numeric(day_rows[power], errors="coerce").fillna(0.0)
                    peak_cut = max_power * float(peak_ratio)
                    peak_mask = ps > peak_cut
                    if peak_mask.any():
                        peak_df = day_rows.loc[peak_mask].copy()
                        peak_df["time_window"] = f"{date_str}#peak"
                        peak_df["period_role"] = "peak"
                        pieces.append(peak_df)
                    if (~peak_mask).any():
                        trans_df = day_rows.loc[~peak_mask].copy()
                        trans_df["time_window"] = f"{date_str}#trans"
                        trans_df["period_role"] = "trans"
                        pieces.append(trans_df)
                elif solar_mode == "multiscale":
                    whole = day_rows.copy()
                    whole["time_window"] = date_str
                    whole["period_role"] = "daylight"
                    pieces.append(whole)
                    sub = day_rows.copy()
                    floored = pd.to_datetime(sub[time_col]).dt.floor(sub_window)
                    sub["time_window"] = floored.map(
                        lambda ts: f"{pd.Timestamp(ts).isoformat(sep='T', timespec='seconds')}#sub"
                    )
                    sub["period_role"] = "daylight_sub"
                    pieces.append(sub)
                else:
                    day_rows["time_window"] = date_str
                    day_rows["period_role"] = "daylight"
                    pieces.append(day_rows)

        if solar_mode in ("night", "day_and_night"):
            night_rows = group.loc[night_mask].copy()
            if not night_rows.empty:
                night_rows["time_window"] = f"{date_str}#night"
                night_rows["period_role"] = "night"
                pieces.append(night_rows)

    if not pieces:
        empty = df.drop(columns=["_date"], errors="ignore").iloc[0:0].copy()
        empty["time_window"] = pd.Series(dtype=object)
        empty["period_role"] = pd.Series(dtype=object)
        return empty, warnings or ["solar_window 未产出任何样本"]

    out = pd.concat(pieces, ignore_index=True).drop(columns=["_date"], errors="ignore")
    return out, warnings
