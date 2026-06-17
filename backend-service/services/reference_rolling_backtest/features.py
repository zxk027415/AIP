# -*- coding: utf-8 -*-
"""无穿越特征工程：与 load_forecast_refactored/run_weihai_backtest.py 对齐。"""
import re
import numpy as np
import pandas as pd


def if_workday(date):
    try:
        from chinese_calendar import is_workday

        return is_workday(pd.to_datetime(date))
    except Exception:
        return pd.to_datetime(date).weekday() <= 4


def build_features(df: pd.DataFrame, time_field: str = "record_time", load_field: str = "load", daily_horizon: int = 96):
    feat = df.copy()
    feat[time_field] = pd.to_datetime(feat[time_field])
    dh = int(daily_horizon)

    feat["is_holiday"] = feat[time_field].apply(lambda x: 0 if if_workday(x) else 1)
    feat["day"] = feat[time_field].dt.day
    feat["yday"] = feat[time_field].dt.dayofyear
    feat["month"] = feat[time_field].dt.month
    feat["dayofweek"] = feat[time_field].dt.dayofweek
    feat["hour"] = feat[time_field].dt.hour
    feat["minute"] = feat[time_field].dt.minute
    feat["period"] = feat["hour"] * 4 + feat["minute"] // 15

    feat["hour_sin"] = np.sin(2 * np.pi * feat["hour"] / 24)
    feat["hour_cos"] = np.cos(2 * np.pi * feat["hour"] / 24)
    feat["wday_sin"] = np.sin(2 * np.pi * feat["dayofweek"] / 7)
    feat["wday_cos"] = np.cos(2 * np.pi * feat["dayofweek"] / 7)
    feat["yday_sin"] = np.sin(2 * np.pi * feat["yday"] / 365)
    feat["yday_cos"] = np.cos(2 * np.pi * feat["yday"] / 365)
    feat["month_sin"] = np.sin(2 * np.pi * feat["month"] / 12)
    feat["month_cos"] = np.cos(2 * np.pi * feat["month"] / 12)

    for lag in [1, 2, 3, 4, 5, 6, 7, 14, 21, 28]:
        feat[f"lag_{lag}d"] = feat[load_field].shift(lag * dh)

    feat["same_time_2w"] = (feat["lag_7d"] + feat["lag_14d"]) / 2
    feat["same_time_3w"] = (feat["lag_7d"] + feat["lag_14d"] + feat["lag_21d"]) / 3

    load_prev = feat[load_field].shift(1)
    feat["diff_1"] = load_prev - load_prev.shift(1)
    feat["diff_96"] = load_prev - load_prev.shift(dh)
    feat["diff_192"] = load_prev - load_prev.shift(2 * dh)
    feat["diff_96_of_96"] = load_prev.shift(dh - 1) - load_prev.shift(2 * dh - 1)

    load_yd = feat[load_field].shift(dh)
    for w in [4, 8, 12, 24, 48, 96]:
        feat[f"roll_{w}_mean"] = load_yd.rolling(w, center=False, min_periods=1).mean().values
        feat[f"roll_{w}_std"] = load_yd.rolling(w, center=False, min_periods=1).std().values
        feat[f"roll_{w}_max"] = load_yd.rolling(w, center=False, min_periods=1).max().values
        feat[f"roll_{w}_min"] = load_yd.rolling(w, center=False, min_periods=1).min().values

    feat["date"] = feat[time_field].dt.strftime("%Y-%m-%d")
    ds = feat.groupby("date")[load_field].agg(["mean", "max", "min", "std"]).reset_index()
    ds.columns = ["date", "day_mean", "day_max", "day_min", "day_std"]
    ds["day_pv"] = ds["day_max"] - ds["day_min"]
    ds["day_pv_rate"] = ds["day_pv"] / ds["day_max"].replace(0, np.nan)
    ds["day_rate"] = ds["day_mean"] / ds["day_max"].replace(0, np.nan)
    for c in ["day_mean", "day_max", "day_min", "day_std", "day_pv", "day_pv_rate", "day_rate"]:
        ds[c] = ds[c].shift(1)
    feat = feat.merge(ds, on="date", how="left")

    ds2 = feat.groupby("date")["lag_1d"].agg(["mean", "std"]).reset_index()
    ds2.columns = ["date", "lag1d_day_mean", "lag1d_day_std"]
    ds2["lag1d_day_mean"] = ds2["lag1d_day_mean"].shift(1)
    ds2["lag1d_day_std"] = ds2["lag1d_day_std"].shift(1)
    feat = feat.merge(ds2, on="date", how="left")

    return feat
