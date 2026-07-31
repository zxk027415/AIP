# -*- coding: utf-8 -*-
"""
tests/test_daylight_window.py — DaylightWindowResolver 单元测试

对应 `.kiro/specs/pv-fault-label-segment-redesign/tasks.md` 任务 6。
"""
from __future__ import annotations

from datetime import time as dt_time

import numpy as np
import pandas as pd
import pytest

from services.iterative_labeling.daylight_window import (
    DaylightWindow,
    DaylightWindowResolver,
)


def _make_synthetic_day(date: str, site_id: str, peak_value: float = 50.0, noise=None) -> pd.DataFrame:
    """构造单日 288 点的合成光照曲线：06:00~18:00 为钟形曲线，其余为 0。"""
    times = pd.date_range(f"{date} 00:00", periods=288, freq="5min")
    hours = times.hour + times.minute / 60.0
    values = np.where(
        (hours >= 6) & (hours < 18),
        peak_value * np.sin((hours - 6) / 12 * np.pi),
        0.0,
    )
    if noise is not None:
        values = values + noise(len(values))
    return pd.DataFrame({"site_id": site_id, "time": times, "value": values})


def test_contains_uses_half_open_interval():
    w = DaylightWindow(dt_time(6, 0), dt_time(18, 0), source="fixed")
    assert w.contains(dt_time(6, 0)) is True
    assert w.contains(dt_time(17, 59)) is True
    assert w.contains(dt_time(18, 0)) is False
    assert w.contains(dt_time(5, 59)) is False


def test_build_table_derives_window_close_to_synthetic_daylight():
    # 10 天合成数据，窗口应能推出接近 06:00-18:00
    frames = [_make_synthetic_day(f"2020-05-{d:02d}", "S1") for d in range(1, 11)]
    df = pd.concat(frames, ignore_index=True)

    resolver = DaylightWindowResolver(peak_ratio=0.05)
    table = resolver.build_table(df)

    assert (("S1", 5) in table)
    window = table[("S1", 5)]
    assert window.source == "empirical"
    # 中位曲线在阈值处推导，起止应接近 06:00/18:00（±1小时内）
    assert abs(window.daylight_start.hour - 6) <= 1
    assert abs(window.daylight_end.hour - 18) <= 1


def test_single_faulty_day_does_not_move_the_window():
    """核心不变量：单个故障设备/坏天气日不能撼动跨天中位数窗口（避免循环论证）。"""
    normal_days = [_make_synthetic_day(f"2020-05-{d:02d}", "S1") for d in range(1, 10)]
    # 第 10 天整天故障、功率恒为 0（模拟坏天气/停机）
    faulty_day = pd.DataFrame({
        "site_id": "S1",
        "time": pd.date_range("2020-05-10 00:00", periods=288, freq="5min"),
        "value": 0.0,
    })

    without_fault = pd.concat(normal_days, ignore_index=True)
    with_fault = pd.concat(normal_days + [faulty_day], ignore_index=True)

    resolver = DaylightWindowResolver(peak_ratio=0.05)
    table_a = resolver.build_table(without_fault)
    table_b = resolver.build_table(with_fault)

    window_a = table_a[("S1", 5)]
    window_b = table_b[("S1", 5)]
    # 加入一天全零的"故障日"后，窗口起止不应发生变化（中位数不受单日极端值影响）
    assert window_a.daylight_start == window_b.daylight_start
    assert window_a.daylight_end == window_b.daylight_end


def test_seasonal_bucket_groups_by_month_across_years():
    """季节桶按月份分组，跨年份的同一月份应共用一个桶。"""
    d1 = _make_synthetic_day("2020-05-08", "S1")
    d2 = _make_synthetic_day("2021-05-08", "S1")  # 同月份不同年
    df = pd.concat([d1, d2], ignore_index=True)

    resolver = DaylightWindowResolver(peak_ratio=0.05)
    table = resolver.build_table(df)

    # 应只产生一个 (S1, 5) 键，而不是按 "2020-05"/"2021-05" 分成两个
    keys_for_may = [k for k in table if k[0] == "S1" and k[1] == 5]
    assert len(keys_for_may) == 1


def test_insufficient_data_falls_back_to_fixed():
    """数据量为空/不足时回退 fixed 窗口。"""
    df = pd.DataFrame({"site_id": ["S1"], "time": [pd.Timestamp("2020-05-08 12:00")], "value": [0.0]})
    resolver = DaylightWindowResolver(peak_ratio=0.05)
    table = resolver.build_table(df)

    window = table.get(("S1", 5))
    assert window is not None
    assert window.source == "fixed"


def test_unreasonable_duration_falls_back_to_fixed():
    """全天恒定非零功率会推出接近 24h 的窗口，应触发 >20h 回退。"""
    times = pd.date_range("2020-10-01 00:00", periods=288, freq="5min")
    df = pd.DataFrame({"site_id": "S1", "time": times, "value": 10.0})  # 全天恒定，无日夜差异
    resolver = DaylightWindowResolver(peak_ratio=0.05)
    table = resolver.build_table(df)

    window = table[("S1", 10)]
    assert window.source == "fixed"  # 时长会 >20h，触发回退


def test_resolve_missing_combination_returns_fixed_without_recompute():
    """resolve() 对表中不存在的组合直接返回 fixed，不现场推导（需求 12.16b 对应机制）。"""
    resolver = DaylightWindowResolver()
    empty_table: dict = {}
    window = resolver.resolve(empty_table, site_id="unknown-site", month_of_year=7)
    assert window.source == "fixed"
    assert window is resolver.fixed_window


def test_invalid_peak_ratio_raises():
    with pytest.raises(ValueError):
        DaylightWindowResolver(peak_ratio=1.5)
    with pytest.raises(ValueError):
        DaylightWindowResolver(peak_ratio=0.0)


def test_real_data_calibration_matches_documented_results():
    """用真实数据复现 design.md 记录的标定结果：peak_ratio=0.05 下窗口时长范围、
    以及真实存在的短窗/长窗回退案例。"""
    import os

    path = os.path.join(
        os.path.dirname(__file__), "..", "datasets", "pv_cumulative_labeled_merged.parquet"
    )
    if not os.path.exists(path):
        pytest.skip("真实数据文件不存在，跳过（该测试仅在有数据的环境中运行）")

    df = pd.read_parquet(path)
    resolver = DaylightWindowResolver(peak_ratio=0.05)
    table = resolver.build_table(df)

    assert len(table) == 14  # 与 design.md 记录一致：14 个 (site_id, 月份) 组
    fixed_count = sum(1 for w in table.values() if w.source == "fixed")
    assert fixed_count == 3  # design.md 记录：1 短窗 + 2 长窗回退
