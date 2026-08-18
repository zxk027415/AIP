# Feature: pv-fault-dual-path-serving, Property 10: 完整性比例判定与阈值回退
# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
tests/pv_dual_path/test_prop_completeness_gate.py — Property 10 属性测试

覆盖 design.md Property 10「完整性比例判定与阈值回退」，对应需求：
  - Req4.1：is_complete 为真 当且仅当 point_count / expected_point_count >= 有效阈值 ratio。
  - Req4.2：completeness_ratio 越界（∉ [0.0, 1.0]）时 load_dual_path_config 回退默认 0.9。
  - Req4.5：expected_point_count 越界（<= 0）时 load_dual_path_config 回退默认 288。

策略：
  - 用 hypothesis（不自实现）单个属性测试，@settings(max_examples>=100)。
  - 判定分支：用 fake tracker 注入 query_device_day 返回，隔离 DB；
    直接构造 DualPathConfig 提供合法 ratio，断言 CompletenessGate.evaluate 的
    is_complete 与 (point_count / expected >= ratio) 逐例一致。
  - 回退分支：用环境变量注入越界 ratio / expected，调用 load_dual_path_config
    （指向不存在的配置文件以隔离真实 yaml），断言回退默认 0.9 / 288。

被测符号：
  - CompletenessGate.evaluate(site,device,branch,business_date) -> GateDecision
    输入设备-天，只读判定完整性；is_complete 依据 point_count/expected >= ratio。
  - load_dual_path_config(config_path) -> DualPathConfig
    按「环境变量 > 配置文件 > 默认」优先级加载，越界值回退默认。
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from services.scheduler.pv_dual_path.completeness_gate import CompletenessGate
from services.scheduler.pv_dual_path.config import (
    DualPathConfig,
    load_dual_path_config,
)

# --- 单一事实来源：与 config.py 内默认值保持一致，便于回退断言 ---
_DEFAULT_RATIO = 0.9
_DEFAULT_EXPECTED = 288
_ENV_RATIO = "PV_COMPLETENESS_RATIO"
_ENV_EXPECTED = "PV_EXPECTED_POINT_COUNT"

# 指向一个必然不存在的配置文件，隔离部署环境里的真实 pv_dual_path.yaml，
# 使 load_dual_path_config 只受本测试注入的环境变量影响。
_NONEXISTENT_CONFIG = Path(__file__).resolve().parent / "__no_such_pv_dual_path__.yaml"


class _FakeTracker:
    """最小 fake，仅实现 CompletenessGate 依赖的只读 query_device_day，隔离真实 DB。

    返回结构与 IngestionTrackerRepository._row_to_dict 的相关键一致
    （point_count / expected_point_count）。
    """

    def __init__(self, row: Optional[Dict[str, Any]]):
        self._row = row

    def query_device_day(self, site_id, device_id, branch_id, business_date):  # noqa: D401
        return self._row


@given(
    point_count=st.integers(min_value=0, max_value=288),
    expected_point_count=st.integers(min_value=1, max_value=288),
    ratio=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    bad_ratio=st.one_of(
        st.floats(min_value=-1000.0, max_value=-0.0001, allow_nan=False, allow_infinity=False),
        st.floats(min_value=1.0001, max_value=1000.0, allow_nan=False, allow_infinity=False),
    ),
    bad_expected=st.integers(min_value=-1000, max_value=0),
)
@settings(max_examples=100)
def test_property_completeness_ratio_and_threshold_fallback(
    point_count: int,
    expected_point_count: int,
    ratio: float,
    bad_ratio: float,
    bad_expected: int,
):
    """Property 10：比例判定 + 越界阈值回退。

    Validates: Requirements 4.1, 4.2, 4.5
    """
    # ---- 分支一：完整性比例判定（Req4.1）----
    # 合法 ratio 由构造函数直接注入（load 层已保证生产路径合法，这里只验判定逻辑）。
    config = DualPathConfig(
        completeness_ratio=ratio,
        expected_point_count=_DEFAULT_EXPECTED,
    )
    tracker = _FakeTracker(
        row={
            "point_count": point_count,
            "expected_point_count": expected_point_count,
        }
    )
    gate = CompletenessGate(tracker=tracker, config=config)  # type: ignore[arg-type]

    decision = gate.evaluate("site-A", "dev-1", "br-1", date(2021, 1, 5))

    actual_ratio = point_count / expected_point_count
    expected_complete = actual_ratio >= ratio

    assert decision.is_complete is expected_complete, (
        f"is_complete 应为 {expected_complete}: "
        f"{point_count}/{expected_point_count}={actual_ratio} vs ratio={ratio}"
    )
    # 比例与计数应如实透传，且为确定值。
    assert decision.point_count == point_count
    assert decision.expected_point_count == expected_point_count
    assert decision.ratio == actual_ratio
    assert decision.error is None

    # ---- 分支二：越界阈值回退默认（Req4.2 / Req4.5）----
    # 通过环境变量注入越界值，调用 load_dual_path_config（隔离真实 yaml），断言回退默认。
    saved_ratio = os.environ.get(_ENV_RATIO)
    saved_expected = os.environ.get(_ENV_EXPECTED)
    try:
        os.environ[_ENV_RATIO] = repr(bad_ratio)
        os.environ[_ENV_EXPECTED] = str(bad_expected)
        cfg = load_dual_path_config(config_path=_NONEXISTENT_CONFIG)
        assert cfg.completeness_ratio == _DEFAULT_RATIO, (
            f"越界 ratio={bad_ratio} 应回退默认 {_DEFAULT_RATIO}，实际 {cfg.completeness_ratio}"
        )
        assert cfg.expected_point_count == _DEFAULT_EXPECTED, (
            f"越界 expected={bad_expected} 应回退默认 {_DEFAULT_EXPECTED}，实际 {cfg.expected_point_count}"
        )
    finally:
        # 还原环境变量，避免污染其他测试。
        if saved_ratio is None:
            os.environ.pop(_ENV_RATIO, None)
        else:
            os.environ[_ENV_RATIO] = saved_ratio
        if saved_expected is None:
            os.environ.pop(_ENV_EXPECTED, None)
        else:
            os.environ[_ENV_EXPECTED] = saved_expected
# @AI_GENERATED: end
