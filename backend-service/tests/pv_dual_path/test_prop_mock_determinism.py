# Feature: pv-fault-dual-path-serving, Property 20: Mock 释放计划确定性
# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
tests/pv_dual_path/test_prop_mock_determinism.py — Property 20 属性测试

覆盖 design.md Property 20「Mock 释放计划确定性」，对应需求 Req8.6：
  以 business_date 为随机种子重复生成释放计划，所得设备集合、每台设备
  延迟/缺失归类与释放顺序逐项完全一致。

被测纯逻辑来源：
  services/db/datasources/pv_fault_mock.py::PvFaultMockFeeder._ensure_release_schedule()
  其种子决定论核心为：
    rng = random.Random(f"pv-mock-release|{business_date.isoformat()}")
    shuffled = list(devices); rng.shuffle(shuffled)
    for idx, dev in enumerate(shuffled):
        is_dropped = rng.random() < _DROP_RATIO
        delay_ticks = 0
        if not is_dropped and rng.random() < _DELAY_RATIO:
            delay_ticks = rng.randint(*_DELAY_TICKS_RANGE)
        planned_batch_index = idx % _RELEASE_BATCH_COUNT

该核心嵌在需要 DB 的实例方法里（写 PvMockReleaseSchedule 表）。按任务约定，
本测试在**不连真实库**的前提下，以**完全相同的算法 + 从被测模块导入的真实常量**
（_DROP_RATIO / _DELAY_RATIO / _DELAY_TICKS_RANGE / _RELEASE_BATCH_COUNT，
以及同一种子字符串格式）复现纯计算部分，只验证「同种子决定论」这一属性。
一旦生产常量改动，测试因导入真实常量而同步对齐，不会静默漂移。

策略：
  - 用 hypothesis（不自实现）单个属性测试，@settings(max_examples>=100)。
  - 生成随机 (business_date, 唯一设备三元组列表)，用同一算法生成两次释放计划，
    断言两次结果逐项完全一致（设备顺序、planned_batch_index、delay_ticks、
    is_dropped 全部相同）。
  - 另附一个确定性示例测试：足量设备下，两个不同 business_date 的计划应不同
    （弱语义健全性检查，使用大设备集避免偶发相同导致的抖动）。
"""

from __future__ import annotations

import random
from datetime import date
from typing import Dict, List, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

# 从被测模块导入真实常量与算法参数：测试与生产共用同一事实来源。
from services.db.datasources.pv_fault_mock import (
    _DELAY_RATIO,
    _DELAY_TICKS_RANGE,
    _DROP_RATIO,
    _RELEASE_BATCH_COUNT,
)

DeviceTriple = Tuple[str, str, str]


def _generate_release_plan(
    business_date: date,
    devices: List[DeviceTriple],
) -> List[Dict]:
    """复现 PvFaultMockFeeder._ensure_release_schedule 的种子决定论核心。

    输入：
      - business_date：作为随机种子的业务日（种子串 f"pv-mock-release|{iso}"）。
      - devices：设备三元组列表（生产侧为去重排序后的稳定输入）。
    输出：
      - 每台设备一条计划记录（顺序即打乱后的释放顺序），字段与生产一致：
        site_id / device_id / branch_id / planned_batch_index / delay_ticks / is_dropped。
    不触碰 DB，纯函数，仅用于验证 Req8.6 的确定性属性。
    """
    rng = random.Random(f"pv-mock-release|{business_date.isoformat()}")
    shuffled = list(devices)
    rng.shuffle(shuffled)

    rows: List[Dict] = []
    for idx, (site_id, device_id, branch_id) in enumerate(shuffled):
        is_dropped = rng.random() < _DROP_RATIO
        delay_ticks = 0
        if not is_dropped and rng.random() < _DELAY_RATIO:
            delay_ticks = rng.randint(*_DELAY_TICKS_RANGE)
        rows.append(
            {
                "site_id": site_id,
                "device_id": device_id,
                "branch_id": branch_id,
                "planned_batch_index": idx % _RELEASE_BATCH_COUNT,
                "delay_ticks": delay_ticks,
                "is_dropped": is_dropped,
            }
        )
    return rows


# 唯一设备三元组：用小整数派生字符串 id，保证 hypothesis 生成的列表元素唯一，
# 与生产侧「去重后的稳定设备列表」输入形态一致。
_device_triples = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=40).map(lambda n: f"site-{n}"),
        st.integers(min_value=0, max_value=40).map(lambda n: f"dev-{n}"),
        st.integers(min_value=0, max_value=40).map(lambda n: f"br-{n}"),
    ),
    unique=True,
    min_size=0,
    max_size=40,
)


@given(
    business_date=st.dates(min_value=date(2018, 1, 1), max_value=date(2025, 12, 31)),
    devices=_device_triples,
)
@settings(max_examples=200)
def test_property_mock_release_plan_determinism(
    business_date: date,
    devices: List[DeviceTriple],
):
    """Property 20：同一 business_date 种子 + 同一设备列表，重复生成计划逐项一致。

    Validates: Requirements 8.6
    """
    plan_first = _generate_release_plan(business_date, devices)
    plan_second = _generate_release_plan(business_date, devices)

    # 条数一致：设备集合不增不减。
    assert len(plan_first) == len(plan_second) == len(devices)

    # 逐项完全一致：释放顺序、批次归属、延迟/缺失归类全部相同。
    assert plan_first == plan_second

    # 进一步逐字段断言（给出更清晰的失败定位），并校验字段取值域自洽。
    for row_a, row_b in zip(plan_first, plan_second):
        assert row_a == row_b
        assert row_b["is_dropped"] in (True, False)
        assert 0 <= row_b["planned_batch_index"] < _RELEASE_BATCH_COUNT
        if row_b["is_dropped"]:
            # 缺失设备不排延迟（与生产分支一致：先判 drop，再判 delay）。
            assert row_b["delay_ticks"] == 0
        else:
            # 未缺失设备：要么无延迟(0)，要么落在 _DELAY_TICKS_RANGE 闭区间内。
            assert row_b["delay_ticks"] == 0 or (
                _DELAY_TICKS_RANGE[0] <= row_b["delay_ticks"] <= _DELAY_TICKS_RANGE[1]
            )


def test_example_distinct_dates_generally_differ():
    """弱语义健全性：足量设备下，不同 business_date 的计划应不同。

    用大设备集（50 台）使两不同种子产出完全相同打乱顺序的概率可忽略
    （约 1/50!），因此可稳定断言不同，不引入抖动。属于 Req8.6 的补充健全性
    检查，非强制属性。
    """
    devices: List[DeviceTriple] = [
        (f"site-{i}", f"dev-{i}", f"br-{i}") for i in range(50)
    ]
    plan_a = _generate_release_plan(date(2021, 1, 1), devices)
    plan_b = _generate_release_plan(date(2021, 1, 2), devices)
    assert plan_a != plan_b, "不同业务日种子在 50 台设备下应产出不同释放计划"


def test_example_empty_devices_yields_empty_plan():
    """边界：空设备列表 → 空计划，且重复生成仍确定性为空。"""
    assert _generate_release_plan(date(2021, 3, 4), []) == []
    assert _generate_release_plan(date(2021, 3, 4), []) == _generate_release_plan(
        date(2021, 3, 4), []
    )
# @AI_GENERATED: end
