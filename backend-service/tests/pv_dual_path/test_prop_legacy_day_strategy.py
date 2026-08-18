# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
tests/pv_dual_path/test_prop_legacy_day_strategy.py — LegacyDayStrategy Property 4–7

使用 Hypothesis 验证传统按天策略的事件时间纯逻辑，不连接真实数据库：
  - Property 4：游标只推进到实际参与点的最大 Event_Time，且单调不减；无新点不推进。
  - Property 5：乱序/晚到但 Event_Time 大于当前游标的点，会在后续水位覆盖它时被纳入。
  - Property 6：检测点恒位于 `(cursor, watermark]`，并严格按 Event_Time 自然日分组。
  - Property 7：无效/不可解析 Event_Time 导致该设备本轮拒收且游标保持不变。

`select_device_event_window` — 单设备事件时间窗口选择与自然日分组纯函数；
`LegacyDayStrategy._advance_cursors` — 消费检测结果并调用分区登记推进设备游标的内部步骤。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from services.scheduler.pv_dual_path.legacy_day_strategy import (
    LegacyDayStrategy,
    select_device_event_window,
)

_DEVICE = ("site-a", "device-a", "branch-a")
_BASE = datetime(2021, 1, 1, 0, 0, 0)


class _MemoryCursorRegistry:
    """只记录游标推进的内存 fake，不访问 PathIsolationRegistry 或数据库。"""

    def __init__(self, initial: Optional[datetime]) -> None:
        self.cursor = initial
        self.calls: List[Dict[str, Any]] = []

    def advance_cursor(
        self,
        slot: str,
        modeling_path: str,
        site_id: str,
        device_id: str,
        branch_id: str,
        event_time: datetime,
        *,
        model_version_id: Optional[str] = None,
    ) -> datetime:
        self.calls.append(
            {
                "slot": slot,
                "modeling_path": modeling_path,
                "device": (site_id, device_id, branch_id),
                "event_time": event_time,
                "model_version_id": model_version_id,
            }
        )
        self.cursor = event_time
        return event_time


def _strategy() -> LegacyDayStrategy:
    """构造仅调用纯辅助步骤的策略实例；pv_repo 不会在这些属性中被访问。"""
    return LegacyDayStrategy(pv_repo=object())


def _row(event_time: Any, sequence: int = 0) -> Dict[str, Any]:
    """构造最小观测行；`time` — Event_Time（事件时间），其余字段只供身份断言。"""
    return {
        "time": event_time,
        "site_id": _DEVICE[0],
        "device_id": _DEVICE[1],
        "branch_id": _DEVICE[2],
        "sequence": sequence,
    }


def _predictions_for(times: List[pd.Timestamp]) -> List[Dict[str, Any]]:
    """为每个参与自然日构造一个最小预测，使推进逻辑能确认哪些日已完成检测。"""
    return [
        {
            "site_id": _DEVICE[0],
            "device_id": _DEVICE[1],
            "branch_id": _DEVICE[2],
            "time_window": event_day,
        }
        for event_day in sorted({timestamp.date().isoformat() for timestamp in times})
    ]


# Feature: pv-fault-dual-path-serving, Property 4: 游标单调不减
@given(
    old_offset_minutes=st.integers(min_value=0, max_value=365 * 24 * 60),
    point_offsets=st.lists(
        st.integers(min_value=1, max_value=7 * 24 * 60),
        min_size=0,
        max_size=40,
        unique=True,
    ),
)
@settings(max_examples=150, deadline=None)
def test_property_4_cursor_is_monotonic_and_no_new_points_do_not_advance(
    old_offset_minutes: int,
    point_offsets: List[int],
) -> None:
    """有参与点时推进到最大 Event_Time；无新点时保持旧游标且不发起写入。

    **Validates: Requirements 2.2, 2.6**
    """
    old_cursor = _BASE + timedelta(minutes=old_offset_minutes)
    event_times = [pd.Timestamp(old_cursor + timedelta(minutes=value)) for value in point_offsets]
    # 反序输入保证最大值选择不依赖仓储返回顺序。
    valid_rows = [(_row(timestamp, index), timestamp) for index, timestamp in enumerate(reversed(event_times))]
    device_valid = {_DEVICE: valid_rows} if valid_rows else {}
    registry = _MemoryCursorRegistry(old_cursor)

    detected, devices_advanced = _strategy()._advance_cursors(
        registry=registry,  # type: ignore[arg-type]
        slot="pv_fault",
        modeling_path="legacy_day",
        device_valid=device_valid,
        device_cursors={_DEVICE: old_cursor},
        predictions=_predictions_for(event_times),
        model_id="model-v1",
        review_unit_id=lambda value: str(value),
    )

    if not event_times:
        assert detected == []
        assert devices_advanced == 0
        assert registry.calls == []
        assert registry.cursor == old_cursor
        return

    expected_cursor = max(event_times).to_pydatetime()
    assert sorted(detected) == sorted(event_times)
    assert devices_advanced == 1
    assert len(registry.calls) == 1
    assert registry.calls[0]["event_time"] == expected_cursor
    assert registry.cursor == expected_cursor
    assert registry.cursor >= old_cursor


# Feature: pv-fault-dual-path-serving, Property 5: 晚到点最终被纳入
@given(
    initial_offsets=st.lists(
        st.integers(min_value=1, max_value=3 * 24 * 60),
        min_size=1,
        max_size=30,
        unique=True,
    ),
    late_gap_minutes=st.integers(min_value=1, max_value=2 * 24 * 60),
)
@settings(max_examples=150, deadline=None)
def test_property_5_late_arrival_after_cursor_is_included_in_next_window(
    initial_offsets: List[int],
    late_gap_minutes: int,
) -> None:
    """到达顺序不改变事件时间判定：水位覆盖晚到点后的下一轮必定纳入它。

    **Validates: Requirements 2.3, 2.7**
    """
    initial_times = [_BASE + timedelta(minutes=value) for value in initial_offsets]
    first_watermark = max(initial_times)
    # 首轮输入故意乱序；游标应由实际参与点的最大事件时间决定。
    first = select_device_event_window(
        [_row(value, index) for index, value in enumerate(reversed(initial_times))],
        _BASE,
        first_watermark,
    )
    first_detected = [timestamp for _, timestamp in first.flattened()]
    current_cursor = max(first_detected).to_pydatetime()

    late_event = current_cursor + timedelta(minutes=late_gap_minutes)
    # 第二轮混入已消费旧点，纯逻辑必须只选严格大于游标且不超过新水位的晚到点。
    second = select_device_event_window(
        [_row(initial_times[0], 0), _row(late_event, 1)],
        current_cursor,
        late_event,
    )
    second_detected = [timestamp.to_pydatetime() for _, timestamp in second.flattened()]

    assert second.invalid_count == 0
    assert second_detected == [late_event]
    assert second_detected[0] > current_cursor
    assert second_detected[0] <= late_event


@st.composite
def _event_window_cases(st_draw):
    """生成跨日前后、含游标前点和水位后点的乱序候选窗口。"""
    cursor = st_draw(
        st.datetimes(
            min_value=datetime(2019, 1, 1),
            max_value=datetime(2024, 12, 20, 23, 59, 59),
            timezones=st.none(),
        )
    )
    watermark_offset = st_draw(st.integers(min_value=1, max_value=4 * 24 * 60))
    offsets = st_draw(
        st.lists(
            st.integers(min_value=-2 * 24 * 60, max_value=6 * 24 * 60),
            min_size=0,
            max_size=60,
        )
    )
    watermark = cursor + timedelta(minutes=watermark_offset)
    rows = [
        _row(
            (cursor + timedelta(minutes=offset)).isoformat()
            if index % 2
            else cursor + timedelta(minutes=offset),
            index,
        )
        for index, offset in enumerate(reversed(offsets))
    ]
    expected = sorted(
        pd.Timestamp(cursor + timedelta(minutes=offset))
        for offset in offsets
        if 0 < offset <= watermark_offset
    )
    return cursor, watermark, rows, expected


# Feature: pv-fault-dual-path-serving, Property 6: 事件时间上界且不跨日拼接
@given(case=_event_window_cases())
@settings(max_examples=200, deadline=None)
def test_property_6_window_is_watermark_bounded_and_partitioned_by_event_day(
    case: Tuple[datetime, datetime, List[Dict[str, Any]], List[pd.Timestamp]],
) -> None:
    """所有入选点都在 `(cursor, watermark]`，每个分组只含同一自然日且日内有序。

    **Validates: Requirements 2.5, 2.9**
    """
    cursor, watermark, rows, expected = case

    selection = select_device_event_window(rows, cursor, watermark)
    flattened = [timestamp for _, timestamp in selection.flattened()]

    assert selection.invalid_count == 0
    assert flattened == expected
    assert all(pd.Timestamp(cursor) < timestamp <= pd.Timestamp(watermark) for timestamp in flattened)
    for event_day, day_rows in selection.rows_by_day.items():
        day_times = [timestamp for _, timestamp in day_rows]
        assert day_times == sorted(day_times)
        assert {timestamp.date().isoformat() for timestamp in day_times} == {event_day}


_INVALID_EVENT_TIMES = st.sampled_from(
    [None, "", "not-a-date", "2021-02-30T10:00:00", "NaT", "--"]
)


# Feature: pv-fault-dual-path-serving, Property 7: 无效事件时间被拒且不推进
@given(
    invalid_values=st.lists(_INVALID_EVENT_TIMES, min_size=1, max_size=8),
    valid_offsets=st.lists(
        st.integers(min_value=1, max_value=2 * 24 * 60),
        min_size=0,
        max_size=20,
        unique=True,
    ),
)
@settings(max_examples=150, deadline=None)
def test_property_7_invalid_event_time_rejects_device_window_and_holds_cursor(
    invalid_values: List[Any],
    valid_offsets: List[int],
) -> None:
    """任一无效 Event_Time 都拒绝该设备本轮窗口，并保证推进步骤不写游标。

    **Validates: Requirements 2.8**
    """
    old_cursor = _BASE
    valid_times = [_BASE + timedelta(minutes=value) for value in valid_offsets]
    rows = [_row(value, index) for index, value in enumerate(valid_times)]
    rows.extend(_row(value, len(rows) + index) for index, value in enumerate(invalid_values))
    watermark = max(valid_times, default=_BASE + timedelta(days=1))

    selection = select_device_event_window(rows, old_cursor, watermark)

    assert selection.invalid_count == len(invalid_values)
    assert selection.rows_by_day == {}
    assert selection.flattened() == []

    registry = _MemoryCursorRegistry(old_cursor)
    detected, devices_advanced = _strategy()._advance_cursors(
        registry=registry,  # type: ignore[arg-type]
        slot="pv_fault",
        modeling_path="legacy_day",
        device_valid={_DEVICE: selection.flattened()} if selection.flattened() else {},
        device_cursors={_DEVICE: old_cursor},
        predictions=_predictions_for([pd.Timestamp(value) for value in valid_times]),
        model_id="model-v1",
        review_unit_id=lambda value: str(value),
    )

    assert detected == []
    assert devices_advanced == 0
    assert registry.calls == []
    assert registry.cursor == old_cursor
# @AI_GENERATED: end
