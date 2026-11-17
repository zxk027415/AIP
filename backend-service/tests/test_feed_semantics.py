# -*- coding: utf-8 -*-
"""三条路径喂数到达语义（feed_semantics）的单元测试。

覆盖两件事：

1. **语义正确** —— 点路径按点（无整日门槛）、日路径等 occupancy 到齐、TSC 额外要求
   窗口覆盖率；缺失处置三条各不相同。
2. **防漂移** —— 本模块声明的阈值必须与既有唯一来源一致（ledger 常量、SamplerConfig 默认值）。
   这三条与生产常量同源，任一处被改动后测试立刻变红，不允许静默漂移。
"""

from __future__ import annotations

import dataclasses

import pytest

from services.slot_datasets import feed_semantics as fs
from services.slot_datasets.observability_ledger import (
    EXPECTED_POINTS,
    HOLD_DAYS,
    OCCUPANCY_READY,
)


def test_granularity_matches_design():
    """点路径按点推进；日路径与 TSC 等整日。"""
    assert fs.granularity_for("pv_point") == fs.GRANULARITY_POINT
    assert fs.granularity_for("pv_day") == fs.GRANULARITY_DEVICE_DAY
    assert fs.granularity_for("pv_tsc") == fs.GRANULARITY_DEVICE_DAY


def test_day_thresholds_come_from_observability_ledger():
    """日级阈值必须来自 ledger 唯一来源，不在本模块复制。"""
    thresholds = fs._day_thresholds()
    assert thresholds["expected_points"] == EXPECTED_POINTS
    assert thresholds["occupancy_ready"] == OCCUPANCY_READY
    assert thresholds["hold_days"] == HOLD_DAYS


def test_tsc_min_coverage_matches_sampler_config_default():
    """防漂移：TSC 覆盖率阈值必须与 sliding_window_sampler 的 SamplerConfig 默认值一致。"""
    from services.iterative_labeling.tsc.sliding_window_sampler import SamplerConfig

    field = next(f for f in dataclasses.fields(SamplerConfig) if f.name == "min_coverage")
    assert field.default == fs.TSC_MIN_COVERAGE, (
        f"SamplerConfig.min_coverage 默认值 {field.default!r} 与 feed_semantics."
        f"TSC_MIN_COVERAGE {fs.TSC_MIN_COVERAGE!r} 不一致——两处必须同源"
    )


def test_point_path_never_has_day_gate():
    """点路径：到达任何数量都 ready，不进入 waiting/expired。"""
    for arrived in (0, 1, 100):
        result = fs.resolve_arrival_status("pv_point", arrived_points=arrived, waited_days=99)
        assert result["status"] == fs.STATUS_READY, arrived
    gate = fs.arrival_gate_for("pv_point")
    assert gate["min_points"] is None and gate["hold_days"] is None


def test_day_path_waits_then_expires_then_readies():
    """日路径：未到齐 waiting；超 hold_days 转 expired_incomplete；到齐 ready。"""
    below = OCCUPANCY_READY - 1

    assert fs.resolve_arrival_status("pv_day", arrived_points=below, waited_days=0)["status"] == fs.STATUS_WAITING
    expired = fs.resolve_arrival_status("pv_day", arrived_points=below, waited_days=HOLD_DAYS)
    assert expired["status"] == fs.STATUS_EXPIRED
    assert expired["reason"] == "expired_incomplete"
    assert fs.resolve_arrival_status("pv_day", arrived_points=OCCUPANCY_READY, waited_days=0)["status"] == fs.STATUS_READY
    assert fs.resolve_arrival_status("pv_day", arrived_points=OCCUPANCY_READY, waited_days=99)["status"] == fs.STATUS_READY


def test_tsc_requires_coverage_in_addition_to_occupancy():
    """TSC：occupancy 够但覆盖率不足仍 waiting；两者都满足才 ready。"""
    waiting = fs.resolve_arrival_status(
        "pv_tsc", arrived_points=EXPECTED_POINTS, waited_days=0, coverage=fs.TSC_MIN_COVERAGE - 0.01
    )
    assert waiting["status"] == fs.STATUS_WAITING
    assert waiting["reason"] == "incomplete_coverage"

    missing_coverage = fs.resolve_arrival_status("pv_tsc", arrived_points=EXPECTED_POINTS, waited_days=0)
    assert missing_coverage["status"] == fs.STATUS_WAITING

    ready = fs.resolve_arrival_status(
        "pv_tsc", arrived_points=EXPECTED_POINTS, waited_days=0, coverage=fs.TSC_MIN_COVERAGE
    )
    assert ready["status"] == fs.STATUS_READY
    assert ready["reason"] == "occupancy_and_coverage_met"

    expired = fs.resolve_arrival_status(
        "pv_tsc", arrived_points=EXPECTED_POINTS, waited_days=HOLD_DAYS, coverage=0.1
    )
    assert expired["status"] == fs.STATUS_EXPIRED


def test_missing_policy_differs_per_path():
    """缺失处置三条路径各不相同（设计意图，不是待办）。"""
    assert fs.missing_policy_for("pv_point")["policy"] == "point_absent"
    assert fs.missing_policy_for("pv_day")["policy"] == "wait_then_expire"
    assert fs.missing_policy_for("pv_tsc")["policy"] == "masked_is_measured"
    policies = {fs.missing_policy_for(s)["policy"] for s in fs.SUPPORTED_SLOTS}
    assert len(policies) == 3, "三条路径的缺失处置必须各自不同，被合并说明语义被抹平"


def test_unknown_slot_fails_closed():
    """未知 slot 必须报错，不猜默认语义。"""
    with pytest.raises(fs.FeedSemanticsError):
        fs.granularity_for("pv_unknown")
    with pytest.raises(fs.FeedSemanticsError):
        fs.describe_slot("")


def test_describe_all_covers_three_paths():
    described = fs.describe_all()
    assert set(described) == {"pv_day", "pv_point", "pv_tsc"}
    for slot, payload in described.items():
        assert payload["granularity"] in {fs.GRANULARITY_POINT, fs.GRANULARITY_DEVICE_DAY}
        assert payload["arrival_gate"]["threshold_source"]
        assert payload["missing_policy"]["note"]
