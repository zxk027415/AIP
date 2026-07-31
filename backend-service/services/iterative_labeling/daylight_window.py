# -*- coding: utf-8 -*-
"""
services/iterative_labeling/daylight_window.py — 日照时钟窗解析器

**职责**：
- 按 `(site_id, 季节桶=月份1~12)` 判定白天/夜间的时钟窗 `[daylight_start, daylight_end)`
- `empirical`（默认）：用跨设备-天聚合的中位功率曲线推导，只用最近
  `lookback_months` 个月的数据，避免单个故障设备/坏天气日污染窗口，也避免
  早期衰减/遮挡变化的数据主导当前判定
- `fixed`（兜底）：数据不足或推导结果不合理时回退固定时钟 06:00–18:00

**关键设计决定**（K5/S1，详见 design.md 组件 3）：
- 白天/夜间**完全不看当日测量值**——现状 `solar_window._day_night_masks()` 用
  「当日 max(value) × irr_threshold」判定，会被故障本身的低出力污染（正午都能
  判成夜间）。本解析器只用时钟窗口，判定依据与当日数据无关。
- 推导用**跨天聚合的中位曲线**，不是单日曲线：单个故障设备或坏天气日在跨天
  聚合中只是一个极端值，被中位数挡掉，撼动不了窗口。
- 推导只用**最近 lookback_months 个月**数据（S1）：光伏板会衰减、遮挡会变化，
  早期形态未必代表现状。

**已实跑标定结果**（真实数据 `pv_cumulative_labeled_merged.parquet`，14 个
`(site_id, 月份)` 组，2026-07-30）：
- `peak_ratio=0.05` 为默认值，窗口时长 min/median/max = 2.67h/10.33h/23.92h
- 4h/20h 回退边界验证合理：真实触发 3 组回退（1 短窗、2 长窗），均为数据量
  偏小/异常的组，未误伤正常组
- `lookback_months=24` 在本数据集（总跨度 22 个月）上暂无裁剪效果，保留为
  默认初值，真实收益需在更长跨度的生产数据上验证

对应设计文档 `.kiro/specs/pv-fault-label-segment-redesign/design.md` 组件 3。
需求：7.16, 7.16a, 7.16b, 7.16c
"""

# @AI_GENERATED
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time as dt_time
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# 默认参数（已实跑标定，见模块 docstring）
DEFAULT_PEAK_RATIO = 0.05
DEFAULT_FIXED_START = dt_time(6, 0)
DEFAULT_FIXED_END = dt_time(18, 0)
DEFAULT_LOOKBACK_MONTHS = 24
MIN_WINDOW_HOURS = 4.0
MAX_WINDOW_HOURS = 20.0


@dataclass(frozen=True)
class DaylightWindow:
    """一个 (site_id, 季节桶) 的日照时钟窗解析结果。"""

    daylight_start: dt_time
    daylight_end: dt_time
    source: str  # "empirical" | "fixed"

    def contains(self, t: dt_time) -> bool:
        """判定给定时刻是否落在 [daylight_start, daylight_end) 内（白天）。"""
        return self.daylight_start <= t < self.daylight_end


class DaylightWindowResolver:
    """日照时钟窗解析器。

    用法：
        resolver = DaylightWindowResolver()
        table = resolver.build_table(measurements_df)
        window = resolver.resolve(table, site_id="S1", month_of_year=5)
        is_daylight = window.contains(some_timestamp.time())
    """

    def __init__(
        self,
        peak_ratio: float = DEFAULT_PEAK_RATIO,
        lookback_months: int = DEFAULT_LOOKBACK_MONTHS,
        fixed_start: dt_time = DEFAULT_FIXED_START,
        fixed_end: dt_time = DEFAULT_FIXED_END,
        min_window_hours: float = MIN_WINDOW_HOURS,
        max_window_hours: float = MAX_WINDOW_HOURS,
    ) -> None:
        if not (0.0 < peak_ratio < 1.0):
            raise ValueError(f"peak_ratio 须在 (0, 1) 内，当前值：{peak_ratio}")
        self.peak_ratio = peak_ratio
        self.lookback_months = lookback_months
        self.fixed_window = DaylightWindow(fixed_start, fixed_end, source="fixed")
        self.min_window_hours = min_window_hours
        self.max_window_hours = max_window_hours

    def build_table(
        self,
        measurements: pd.DataFrame,
        *,
        site_col: str = "site_id",
        time_col: str = "time",
        value_col: str = "value",
        reference_time: Optional[pd.Timestamp] = None,
    ) -> Dict[Tuple[str, int], DaylightWindow]:
        """按 `(site_id, 月份1~12)` 批量推导日照窗，产出全表，供随模型持久化。

        Args:
            measurements: 含 site_col/time_col/value_col 的测量数据。
            reference_time: 回溯窗锚点，默认取 measurements 中最新时间戳。

        Returns:
            {(site_id, month_of_year): DaylightWindow}；数据不足或推导不合理的
            组落到 fixed 窗口（仍会出现在返回表中，source="fixed"）。
        """
        if measurements is None or measurements.empty:
            return {}

        df = measurements[[site_col, time_col, value_col]].copy()
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.dropna(subset=[time_col])
        if df.empty:
            return {}

        ref = reference_time or df[time_col].max()
        ref = pd.Timestamp(ref)

        table: Dict[Tuple[str, int], DaylightWindow] = {}
        fallback_log = []

        for site_id, site_df in df.groupby(site_col):
            for month in range(1, 13):
                bucket = site_df[site_df[time_col].dt.month == month]
                if bucket.empty:
                    continue

                # 只用最近 lookback_months 个月的数据；不足则放宽到全历史该桶
                cutoff = ref - pd.DateOffset(months=self.lookback_months)
                recent = bucket[bucket[time_col] >= cutoff]
                candidate = recent if not recent.empty else bucket

                window = self._derive_from_bucket(candidate, time_col, value_col)
                if window is None:
                    fallback_log.append((site_id, month, "insufficient_data"))
                    table[(site_id, month)] = self.fixed_window
                    continue

                dur_hours = self._duration_hours(window)
                if dur_hours < self.min_window_hours or dur_hours > self.max_window_hours:
                    fallback_log.append((site_id, month, f"unreasonable_duration={dur_hours:.2f}h"))
                    table[(site_id, month)] = self.fixed_window
                    continue

                table[(site_id, month)] = window

        if fallback_log:
            logger.warning(
                "DaylightWindowResolver: %d 个 (site_id, 月份) 回退到 fixed 窗口: %s",
                len(fallback_log), fallback_log,
            )
        return table

    def resolve(
        self,
        table: Dict[Tuple[str, int], DaylightWindow],
        site_id: str,
        month_of_year: int,
    ) -> DaylightWindow:
        """从已构建的表中取窗口；表中缺该组合时返回 fixed 兜底，不现场推导。"""
        return table.get((site_id, month_of_year), self.fixed_window)

    # ------------------------------------------------------------------
    # 内部：中位曲线推导
    # ------------------------------------------------------------------

    def _derive_from_bucket(
        self, bucket: pd.DataFrame, time_col: str, value_col: str
    ) -> Optional[DaylightWindow]:
        """对给定桶按 time-of-day 求跨设备-天中位曲线，推导 [start, end)。"""
        tod_min = bucket[time_col].dt.hour * 60 + bucket[time_col].dt.minute
        median_curve = bucket.groupby(tod_min)[value_col].median()
        if median_curve.empty or median_curve.max() <= 0:
            return None

        threshold = median_curve.max() * self.peak_ratio
        above = median_curve[median_curve >= threshold]
        if above.empty:
            return None

        start_min, end_min = int(above.index.min()), int(above.index.max())
        start_t = dt_time(start_min // 60, start_min % 60)
        # end 取右开区间：下一采样点起为夜间，用 +1 分钟近似对齐半开语义
        end_total = min(end_min + 1, 24 * 60 - 1)
        end_t = dt_time(end_total // 60, end_total % 60)
        return DaylightWindow(start_t, end_t, source="empirical")

    @staticmethod
    def _duration_hours(window: DaylightWindow) -> float:
        start_min = window.daylight_start.hour * 60 + window.daylight_start.minute
        end_min = window.daylight_end.hour * 60 + window.daylight_end.minute
        return (end_min - start_min) / 60.0

# @AI_GENERATED: end
