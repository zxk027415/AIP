# -*- coding: utf-8 -*-
import os
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


def load_wide_or_long_load_series(
    file_path: str,
    time_col: str = "record_time",
    load_col: str = "load",
    parent_id: Optional[str] = None,
    child_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    与 run_weihai_backtest.load_weihai_data 对齐的宽表/长表兼容加载。
    输出: record_time, load 的 15min 序列（已排序、去重、重采样、插值）。
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    if "feature_name" in df.columns and "value" in df.columns:
        m = (df["feature_name"] == load_col) | (df["feature_name"] == "load")
        t = df.loc[m].copy()
        if parent_id is not None and "parent_id" in t.columns:
            t = t[t["parent_id"] == parent_id]
        if child_id is not None and "child_id" in t.columns:
            t = t[t["child_id"] == child_id]
        load_df = t[[time_col, "value"]].copy()
        load_df.rename(columns={"value": load_col}, inplace=True)
    else:
        if time_col not in df.columns and "time" in df.columns:
            time_col = "time"
        if load_col not in df.columns:
            for alt in ("value", "load_value", "y"):
                if alt in df.columns:
                    load_col = alt
                    break
        load_df = df[[c for c in (time_col, load_col) if c in df.columns]].copy()
        if time_col not in load_df.columns or load_col not in load_df.columns:
            raise ValueError("CSV 需含 record_time+load/value 或长表 feature_name+value 列")

    load_df[time_col] = pd.to_datetime(load_df[time_col])
    load_df = load_df.sort_values(time_col).reset_index(drop=True)
    load_df = load_df.drop_duplicates(subset=time_col, keep="first")
    load_df = load_df.set_index(time_col)
    load_df = load_df.resample("15min").mean()
    load_df = load_df.interpolate(method="time")
    load_df = load_df.bfill().ffill()
    load_df = load_df.reset_index()
    logger.info(
        f"参考回测: 数据加载 {load_df[time_col].min()} ~ {load_df[time_col].max()}, n={len(load_df)}"
    )
    return load_df


def resolve_dataset_path(rel_or_abs: str, backend_dir: str) -> str:
    if not rel_or_abs:
        return rel_or_abs
    if os.path.isabs(rel_or_abs) and os.path.exists(rel_or_abs):
        return rel_or_abs
    candidates = [
        os.path.join(backend_dir, rel_or_abs),
        os.path.join(backend_dir, "datasets", os.path.basename(rel_or_abs)),
        os.path.join(backend_dir, "data", "workflows_enhanced", rel_or_abs),
        os.path.join(os.path.dirname(backend_dir), rel_or_abs),
        os.path.join(os.path.dirname(os.path.dirname(backend_dir)), rel_or_abs),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return os.path.join(backend_dir, rel_or_abs)
