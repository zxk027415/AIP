# -*- coding: utf-8 -*-
# @AI_GENERATED: pv-fault-dual-path-serving 任务 2.5 —— 配置默认值与边界测试
"""双路径配置纯函数边界测试；不读取部署环境、不连接数据库。"""
from __future__ import annotations

import pytest

from services.scheduler.pv_dual_path.config import (
    DualPathConfig,
    _resolve_max_backfill_days,
    _resolve_max_device_days_per_cycle,
    _resolve_production_capacity_reserved_ratio,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 50),
        (-1, 50),
        (1, 1),
        (1000, 1000),
        (1001, 50),
    ],
)
def test_max_device_days_per_cycle_boundaries(raw, expected):
    """`max_device_days_per_cycle` — 单轮设备日上限：范围外回退 50，端点保留。"""
    assert _resolve_max_device_days_per_cycle(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1, 1),
        (3650, 3650),
        (3651, 14),
    ],
)
def test_max_backfill_days_boundaries(raw, expected):
    """`max_backfill_days` — 最大回看天数：合法范围 1–3650。"""
    assert _resolve_max_backfill_days(raw) == expected


@pytest.mark.parametrize("raw", [0, 0.8, 1])
def test_production_capacity_reserved_ratio_inclusive_boundaries(raw):
    """`production_capacity_reserved_ratio` — 生产容量预留比例：0 与 1 均合法。"""
    assert _resolve_production_capacity_reserved_ratio(raw) == pytest.approx(raw)


def test_all_design_defaults():
    """全部 14 个设计默认值保持为任务 2.3 的单一事实来源。"""
    config = DualPathConfig()
    assert config.completeness_ratio == pytest.approx(0.9)
    assert config.expected_point_count == 288
    assert config.max_device_days_per_cycle == 50
    assert config.max_backfill_days == 14
    assert config.recent_window_backfill_days == 7
    assert config.production_capacity_reserved_ratio == pytest.approx(0.8)
    assert config.shadow_report_valid_days == 14
    assert config.min_comparable_device_days == 200
    assert config.min_shadow_coverage_rate == pytest.approx(0.9)
    assert config.retrain_change_threshold == 200
    assert config.retrain_period_days == 7
    assert config.promotion_margin == pytest.approx(0.0)
    assert config.no_coverage_failure_cycles == 24
    assert config.path_failed_cycles == 3
# @AI_GENERATED: end
