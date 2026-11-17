# -*- coding: utf-8 -*-
"""日照 / 夜间诊断窗口切分（供 time_window_split 与 fault-diag set_time_window 共用）。"""

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


def _resolve_power_col(
    df: pd.DataFrame,
    power_col: Optional[str],
    value_cols: Optional[Sequence[str]],
) -> str:
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


def _date_key(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.normalize()


def _validate_params(solar_mode: str, irr_threshold: float, peak_ratio: float) -> None:
    if solar_mode not in SUPPORTED_SOLAR_MODES:
        raise ValueError(
            f"不支持的 solar_mode={solar_mode!r}；可选: {SUPPORTED_SOLAR_MODES}"
        )
    if not (0.0 < float(irr_threshold) < 1.0):
        raise ValueError("irr_threshold 须在 (0, 1) 内")
    if float(peak_ratio) <= float(irr_threshold):
        raise ValueError("peak_ratio 必须大于 irr_threshold")


def _day_night_masks(
    group: pd.DataFrame,
    power_col: str,
    irr_threshold: float,
) -> Tuple[pd.Series, pd.Series, float, Optional[str]]:
    power = pd.to_numeric(group[power_col], errors="coerce").fillna(0.0)
    max_power = float(power.max()) if len(power) else 0.0
    if max_power <= 0:
        return (
            pd.Series(False, index=group.index),
            pd.Series(True, index=group.index),
            max_power,
            "max_power==0，整组视为夜间/无效日照",
        )
    threshold = max_power * float(irr_threshold)
    daylight = power >= threshold
    night = ~daylight
    return daylight, night, max_power, None


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
    """按 solar_mode 产出带 ``time_window`` / ``period_role`` 的行级数据。"""
    _validate_params(solar_mode, irr_threshold, peak_ratio)
    if data is None or data.empty:
        empty = data.copy() if data is not None else pd.DataFrame()
        if not empty.empty:
            empty = empty.copy()
            empty["time_window"] = pd.NaT
            empty["period_role"] = None
        return empty, []

    df = data.drop(columns=["time_window", "period_role"], errors="ignore").copy()
    if time_col not in df.columns:
        raise ValueError(f"缺少时间列: {time_col}")

    actual_id_cols = [c for c in (id_cols or []) if c in df.columns]
    power = _resolve_power_col(df, power_col, value_cols)
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])
    df["_date"] = _date_key(df[time_col])

    warnings: List[str] = []
    pieces: List[pd.DataFrame] = []

    group_keys = actual_id_cols + ["_date"] if actual_id_cols else ["_date"]
    for key, group in df.groupby(group_keys, sort=False):
        daylight_mask, night_mask, max_power, warn = _day_night_masks(
            group, power, irr_threshold
        )
        if warn:
            warnings.append(f"{key}: {warn}")

        date_val = group["_date"].iloc[0]
        date_str = pd.Timestamp(date_val).date().isoformat()

        if solar_mode in ("daylight", "day_and_night", "solar_period", "multiscale"):
            day_rows = group.loc[daylight_mask].copy()
            if not day_rows.empty:
                if solar_mode == "solar_period":
                    power_s = pd.to_numeric(day_rows[power], errors="coerce").fillna(0.0)
                    peak_cut = max_power * float(peak_ratio)
                    peak_mask = power_s > peak_cut
                    trans_mask = ~peak_mask
                    if peak_mask.any():
                        peak_df = day_rows.loc[peak_mask].copy()
                        peak_df["time_window"] = f"{date_str}#peak"
                        peak_df["period_role"] = "peak"
                        pieces.append(peak_df)
                    else:
                        warnings.append(f"{key}: peak 段为空")
                    if trans_mask.any():
                        trans_df = day_rows.loc[trans_mask].copy()
                        trans_df["time_window"] = f"{date_str}#trans"
                        trans_df["period_role"] = "trans"
                        pieces.append(trans_df)
                    else:
                        warnings.append(f"{key}: trans 段为空")
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

    out = pd.concat(pieces, ignore_index=True)
    out = out.drop(columns=["_date"], errors="ignore")
    return out, warnings


def attach_night_anomaly_features(
    df: pd.DataFrame,
    *,
    current_col: str = "value",
    power_col: Optional[str] = None,
    night_zero_epsilon: float = 0.01,
    night_anomaly_current_threshold: Optional[float] = None,
) -> pd.DataFrame:
    """对 period_role=night 的窗口广播 night_* 特征列。"""
    from services.operator_backends.night_anomaly import compute_night_anomaly_features

    if df is None or df.empty or "period_role" not in df.columns:
        return df

    out = df.copy()
    night = out["period_role"].astype(str) == "night"
    if not night.any():
        return out

    feature_cols = [
        "night_nonzero_current_ratio",
        "night_current_mean",
        "night_current_max",
        "night_over_threshold_duration",
        "night_power_residual_mean",
    ]
    for col in feature_cols:
        if col not in out.columns:
            out[col] = pd.NA

    group_cols = [c for c in ("site_id", "device_id", "branch_id", "time_window") if c in out.columns]
    if "time_window" not in group_cols:
        return out

    for _, grp in out.loc[night].groupby(group_cols, sort=False):
        feats = compute_night_anomaly_features(
            grp,
            current_col=current_col if current_col in grp.columns else (
                power_col or "value"
            ),
            power_col=power_col if power_col in grp.columns else None,
            night_zero_epsilon=night_zero_epsilon,
            night_anomaly_current_threshold=night_anomaly_current_threshold,
        )
        idx = grp.index
        for key, value in feats.items():
            out.loc[idx, key] = value
    return out
