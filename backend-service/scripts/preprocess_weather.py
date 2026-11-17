#!/usr/bin/env python3
"""
预处理脚本：合并威海天气数据和负荷数据为一张宽表。

输入：
  - datasets/ens_avg_weihai.csv       天气数据（小时级宽表）
  - datasets/load_true_weihai_260415.csv  负荷数据（15分钟级长表）

输出：
  - datasets/load_weather_weihai.csv   合并后的小时级宽表

用法：
  cd backend-service && python scripts/preprocess_weather.py
"""

import os
import sys

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEATHER_PATH = os.path.join(BASE_DIR, "datasets", "ens_avg_weihai.csv")
LOAD_PATH = os.path.join(BASE_DIR, "datasets", "load_true_weihai_260415.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "datasets", "load_weather_weihai.csv")


def load_weather(path: str) -> pd.DataFrame:
    """加载天气 CSV，解析时间戳，设为索引。"""
    df = pd.read_csv(path)
    # 处理 BOM
    df.columns = [c.lstrip("﻿") for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    # 只保留数值列
    cols = ["temperature", "wind_speed", "wind_direction", "pressure", "rainfall"]
    return df[[c for c in cols if c in df.columns]]


def load_and_pivot_load(path: str) -> pd.DataFrame:
    """加载负荷 CSV（长表），pivot 为宽表，重采样到小时级。"""
    df = pd.read_csv(path)
    df["record_time"] = pd.to_datetime(df["record_time"])

    # 只取 load 特征
    df_load = df[df["feature_name"] == "load"].copy()
    if df_load.empty:
        raise ValueError("负荷数据中未找到 feature_name='load' 的行")

    # Pivot：record_time 为索引，parent_id+child_id 组合为列名
    df_wide = df_load.pivot_table(
        index="record_time",
        columns=["parent_id", "child_id"],
        values="value",
        aggfunc="mean",
    )
    df_wide.columns = ["_".join(str(c) for c in col) for col in df_wide.columns]
    df_wide = df_wide.sort_index()

    # 重采样到小时级（取均值）
    df_hourly = df_wide.resample("1h").mean()

    # 如果只有一列，重命名为 load
    if len(df_hourly.columns) == 1:
        df_hourly.columns = ["load"]
    return df_hourly


def merge_and_clean(load: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """合并负荷和天气数据，处理缺失值。"""
    merged = load.join(weather, how="inner")

    # 前向填充天气缺失值（最多 3 小时）
    weather_cols = [c for c in weather.columns if c in merged.columns]
    merged[weather_cols] = merged[weather_cols].ffill(limit=3)

    # 删除仍有 NaN 的行
    before = len(merged)
    merged = merged.dropna()
    after = len(merged)
    if before > after:
        print(f"  删除含 NaN 的行: {before - after}")

    return merged


def main():
    print("=" * 50)
    print("  威海负荷+天气数据预处理")
    print("=" * 50)

    # 1. 加载天气
    print(f"\n[1/4] 加载天气: {WEATHER_PATH}")
    weather = load_weather(WEATHER_PATH)
    print(f"  {len(weather)} 行, 列: {list(weather.columns)}")
    print(f"  时间范围: {weather.index.min()} ~ {weather.index.max()}")

    # 2. 加载并 pivot 负荷
    print(f"\n[2/4] 加载负荷: {LOAD_PATH}")
    load = load_and_pivot_load(LOAD_PATH)
    print(f"  {len(load)} 行 (小时级), 列: {list(load.columns)}")
    print(f"  时间范围: {load.index.min()} ~ {load.index.max()}")

    # 3. 合并
    print("\n[3/4] 合并...")
    merged = merge_and_clean(load, weather)
    print(f"  {len(merged)} 行")
    print(f"  时间范围: {merged.index.min()} ~ {merged.index.max()}")
    print(f"  列: {list(merged.columns)}")

    # 统计天气覆盖
    weather_cols = [c for c in weather.columns if c in merged.columns]
    for col in weather_cols:
        nulls = merged[col].isna().sum()
        print(f"  {col}: {nulls} 缺失 / {len(merged)}")

    # 4. 输出
    print(f"\n[4/4] 输出: {OUTPUT_PATH}")
    merged = merged.reset_index()
    merged = merged.rename(columns={"index": "record_time"} if "index" in merged.columns else {"timestamp": "record_time"})
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"  已写入 {len(merged)} 行, {len(merged.columns)} 列")

    print("\n" + "=" * 50)
    print("  完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
