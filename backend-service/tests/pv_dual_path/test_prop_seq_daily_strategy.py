# -*- coding: utf-8 -*-
# @AI_GENERATED
"""SeqDailyStrategy 的 Property 8–9 属性测试。

本文件使用 Hypothesis 与纯内存 fake 验证两条生产契约：

- Property 8：SeqDailyStrategy 仅检测 ``event_date < device_watermark_date`` 且
  CompletenessGate 放行的设备整天；水位当天/未来日和完整性不足日均顺延。
- Property 9：单自然日始终按 5 分钟对齐为 288 个时钟槽；包含两个自然日的单批输入
  在网格对齐和模型推理前被 SeqAnnotationPredictor 明确拒绝，绝不覆盖到同一网格。

外部数据库、模型工件、批次文件与审核会话全部由内存 fake/patch 隔离，不产生持久化结果。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import numpy as np
import pandas as pd
from hypothesis import example, given, settings
from hypothesis import strategies as st

import services.scheduler.tasks.pv_fault_tasks as pv_fault_tasks
from services.iterative_labeling.seq_annotation.grid_align import SLOTS_PER_DAY
from services.iterative_labeling.seq_annotation.predictor import SeqAnnotationPredictor
from services.scheduler.pv_dual_path.completeness_gate import CompletenessGate
from services.scheduler.pv_dual_path.config import DualPathConfig
from services.scheduler.pv_dual_path.seq_daily_strategy import SeqDailyStrategy
from services.scheduler.pv_dual_path.strategy_base import CycleContext

_DEVICE = ("site-A", "device-1", "branch-1")
_WATERMARK_DAY = date(2021, 1, 10)
_COMPLETENESS_RATIO = 0.9
_EXPECTED_POINTS = 288


class _FakeTracker:
    """CompletenessGate 的内存数据源，支持按设备日切换到达计数。"""

    def __init__(self, point_count: int | Dict[date, int]) -> None:
        self._point_counts = (
            dict(point_count) if isinstance(point_count, dict) else point_count
        )
        self.calls: List[Tuple[Any, ...]] = []

    def set_point_count(self, business_date: date, point_count: int) -> None:
        """更新指定业务日计数，模拟下一轮晚到点补齐。"""
        if not isinstance(self._point_counts, dict):
            self._point_counts = {}
        self._point_counts[business_date] = point_count

    def query_device_day(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        business_date: date,
    ) -> Dict[str, int]:
        self.calls.append((site_id, device_id, branch_id, business_date))
        point_count = (
            self._point_counts.get(business_date, 0)
            if isinstance(self._point_counts, dict)
            else self._point_counts
        )
        return {
            "point_count": point_count,
            "expected_point_count": _EXPECTED_POINTS,
        }


class _FakeWatermark:
    """固定返回设备数据水位，供策略验证事件日严格边界。"""

    def __init__(self, value: datetime) -> None:
        self.value = value
        self.calls: List[Tuple[Any, ...]] = []

    def device_watermark(
        self, site_id: str, device_id: str, branch_id: str
    ) -> datetime:
        self.calls.append((site_id, device_id, branch_id))
        return self.value


class _FakeRepository:
    """SeqDailyStrategy 所需的最小内存仓储，不访问数据库。"""

    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows
        self.unlabeled_queries: List[Dict[str, Any]] = []
        self.measurement_queries: List[Dict[str, Any]] = []

    def query_unlabeled_by_point_labels(self, **kwargs: Any) -> List[Dict[str, Any]]:
        self.unlabeled_queries.append(kwargs)
        return list(self.rows)

    def query_device_measurements(self, **kwargs: Any) -> List[Dict[str, Any]]:
        self.measurement_queries.append(kwargs)
        time_start = pd.Timestamp(kwargs["time_start"])
        time_end = pd.Timestamp(kwargs["time_end"])
        return [
            row
            for row in self.rows
            if time_start <= pd.Timestamp(row["time"]) < time_end
        ]

    def get_model_version(self, model_id: str) -> object:
        return object()


class _FakePredictor:
    """只记录整日推理调用并返回满足策略持久化契约的确定结果。"""

    def __init__(self) -> None:
        self.frames: List[pd.DataFrame] = []

    def predict_device_day(
        self, frame: pd.DataFrame, include_night: bool = True
    ) -> Dict[str, Any]:
        self.frames.append(frame.copy())
        timestamps = [pd.Timestamp(value).isoformat() for value in frame["time"]]
        count = len(frame)
        return {
            "predicted_label": 0,
            "confidence": 1.0,
            "timestamps": timestamps,
            "point_predictions": [0] * count,
            "raw_point_predictions": [0] * count,
            "point_confidences": [1.0] * count,
            "segment_predictions": [],
            "postprocessing": {},
            "model_name": "in-memory-seq",
            "seq_len_used": SLOTS_PER_DAY,
            "trained_full_day": True,
            "error": None,
        }


class _InspectableSeqDailyStrategy(SeqDailyStrategy):
    """替换游标/批次 I/O 的可观察策略，保留真实日期与闸门分支。"""

    def __init__(self, repository: _FakeRepository) -> None:
        super().__init__(repository)  # type: ignore[arg-type]
        self.cursor: Optional[datetime] = None
        self.advanced: Dict[Tuple[Any, Any, Any], datetime] = {}

    def _read_partition_cursors(
        self, adapter: Any
    ) -> Tuple[List[Tuple[Any, Any, Any]], Dict[Tuple[Any, Any, Any], Optional[datetime]]]:
        return [_DEVICE], {_DEVICE: self.cursor}

    def _persist_new_predictions(self, **kwargs: Any):
        input_rows = kwargs["prediction_input_rows"]
        advance_time = max(pd.Timestamp(row["time"]).to_pydatetime() for row in input_rows)
        return (
            {"advance_times": {_DEVICE: advance_time}},
            {
                "batch_id": "batch-in-memory",
                "review_id": "review-in-memory",
                "prediction_count": len(kwargs["new_predictions"]),
                "inserted_count": len(kwargs["new_predictions"]),
                "recovered": False,
            },
        )

    def _advance_partition_cursors(
        self,
        adapter: Any,
        advance_times: Dict[Tuple[Any, Any, Any], datetime],
        model_ids: Dict[Tuple[Any, Any, Any], Optional[str]],
    ) -> None:
        self.advanced.update(advance_times)
        if advance_times:
            self.cursor = max(advance_times.values())


def _measurement_rows(day: date, point_count: int) -> List[Dict[str, Any]]:
    """构造同一自然日内的 5 分钟测点，最多覆盖完整 288 槽。"""
    timestamps = pd.date_range(day.isoformat(), periods=point_count, freq="5min")
    return [
        {
            "site_id": _DEVICE[0],
            "device_id": _DEVICE[1],
            "branch_id": _DEVICE[2],
            "time": timestamp.to_pydatetime(),
            "value": float(index),
            "i_cal": float(index + 1),
        }
        for index, timestamp in enumerate(timestamps)
    ]


def _identity_partition(
    repository: Any,
    model_ref: str,
    predictions: List[Dict[str, Any]],
    *,
    recovery_candidates: List[Dict[str, Any]],
):
    """把归一化预测全部视为本轮新结果，隔离真实恢复批次仓储。"""
    return predictions, {}


# Feature: pv-fault-dual-path-serving, Property 8: 序列仅检测水位前完整整天
@given(
    day_offset=st.sampled_from((-2, -1, 0, 1)),
    point_count=st.integers(min_value=1, max_value=_EXPECTED_POINTS),
)
@example(day_offset=-1, point_count=259)
@example(day_offset=-1, point_count=260)
@example(day_offset=0, point_count=288)
@settings(max_examples=120, deadline=None)
def test_property_seq_detects_only_complete_days_strictly_before_watermark(
    day_offset: int,
    point_count: int,
) -> None:
    """仅水位日前且完整性比例达 90% 的设备日被检测，其余全部顺延。

    **Validates: Requirements 3.1, 3.2, 3.3, 4.3**
    """
    event_day = _WATERMARK_DAY + timedelta(days=day_offset)
    rows = _measurement_rows(event_day, point_count)
    repository = _FakeRepository(rows)
    tracker = _FakeTracker(point_count)
    gate = CompletenessGate(
        tracker=tracker,  # type: ignore[arg-type]
        config=DualPathConfig(
            completeness_ratio=_COMPLETENESS_RATIO,
            expected_point_count=_EXPECTED_POINTS,
        ),
    )
    watermark_value = datetime.combine(_WATERMARK_DAY, datetime.max.time())
    watermark = _FakeWatermark(watermark_value)
    predictor = _FakePredictor()
    strategy = _InspectableSeqDailyStrategy(repository)
    context = CycleContext(
        slot="pv_fault",
        modeling_path="seq_annotation",
        model_ref="data/models/seq_annotation/in-memory",
        watermark=watermark,  # type: ignore[arg-type]
        started_at=datetime(2026, 1, 1),
    )

    expected_detected = (
        event_day < _WATERMARK_DAY
        and point_count / _EXPECTED_POINTS >= _COMPLETENESS_RATIO
    )

    with (
        patch.object(
            pv_fault_tasks,
            "_normalize_predictions",
            side_effect=lambda predictions: predictions,
        ),
        patch.object(
            pv_fault_tasks,
            "_partition_seq_predictions_for_recovery",
            side_effect=_identity_partition,
        ),
    ):
        result = strategy._run_with_resources(
            context,
            predictor,
            "model-in-memory",
            "data/models/seq_annotation/in-memory",
            object(),
            gate,
        )

    assert watermark.calls == [_DEVICE]
    assert repository.unlabeled_queries[0]["before_time"] == watermark_value
    assert len(predictor.frames) == (1 if expected_detected else 0)
    assert len(tracker.calls) == (1 if event_day < _WATERMARK_DAY else 0)

    if expected_detected:
        assert result.status == "success"
        assert result.points_detected == point_count
        assert result.points_deferred == 0
        assert result.devices_processed == 1
        assert set(pd.to_datetime(predictor.frames[0]["time"]).dt.date) == {event_day}
        assert strategy.advanced[_DEVICE].date() == event_day
    else:
        assert result.status == "skipped"
        assert result.skipped_reason == "no_complete_device_day"
        assert result.points_detected == 0
        assert result.points_deferred == point_count
        assert strategy.advanced == {}


# Feature: pv-fault-dual-path-serving, Property 8: 序列连续成功前沿不得跨越较早失败日
@given(
    first_day=st.dates(
        min_value=date(2020, 1, 1),
        max_value=date(2035, 12, 28),
    ),
    d1_incomplete_count=st.integers(min_value=1, max_value=258),
    d1_complete_count=st.integers(min_value=260, max_value=_EXPECTED_POINTS),
    d2_complete_count=st.integers(min_value=260, max_value=_EXPECTED_POINTS),
)
@settings(max_examples=110, deadline=None)
def test_property_seq_cursor_stops_at_first_incomplete_day_then_recovers_in_order(
    first_day: date,
    d1_incomplete_count: int,
    d1_complete_count: int,
    d2_complete_count: int,
) -> None:
    """D1 未完整时阻塞 D2；D1 补齐后的下一轮按 D1→D2 连续检测并推进。

    **Validates: Requirements 3.3, 3.9, 4.3**
    """
    second_day = first_day + timedelta(days=1)
    watermark_day = first_day + timedelta(days=2)
    d1_partial_rows = _measurement_rows(first_day, d1_incomplete_count)
    d1_complete_rows = _measurement_rows(first_day, d1_complete_count)
    d2_complete_rows = _measurement_rows(second_day, d2_complete_count)
    repository = _FakeRepository(d1_partial_rows + d2_complete_rows)
    tracker = _FakeTracker(
        {
            first_day: d1_incomplete_count,
            second_day: d2_complete_count,
        }
    )
    gate = CompletenessGate(
        tracker=tracker,  # type: ignore[arg-type]
        config=DualPathConfig(
            completeness_ratio=_COMPLETENESS_RATIO,
            expected_point_count=_EXPECTED_POINTS,
        ),
    )
    predictor = _FakePredictor()
    strategy = _InspectableSeqDailyStrategy(repository)
    context = CycleContext(
        slot="pv_fault",
        modeling_path="seq_annotation",
        model_ref="data/models/seq_annotation/in-memory",
        watermark=_FakeWatermark(
            datetime.combine(watermark_day, datetime.min.time())
        ),  # type: ignore[arg-type]
        started_at=datetime(2026, 1, 1),
    )

    with (
        patch.object(
            pv_fault_tasks,
            "_normalize_predictions",
            side_effect=lambda predictions: predictions,
        ),
        patch.object(
            pv_fault_tasks,
            "_partition_seq_predictions_for_recovery",
            side_effect=_identity_partition,
        ),
    ):
        blocked_result = strategy._run_with_resources(
            context,
            predictor,
            "model-in-memory",
            "data/models/seq_annotation/in-memory",
            object(),
            gate,
        )

        assert blocked_result.status == "skipped"
        assert blocked_result.skipped_reason == "no_complete_device_day"
        assert blocked_result.points_detected == 0
        assert blocked_result.points_deferred == (
            d1_incomplete_count + d2_complete_count
        )
        assert predictor.frames == []
        assert repository.measurement_queries == []
        assert [call[3] for call in tracker.calls] == [first_day]
        assert strategy.cursor is None
        assert strategy.advanced == {}

        # 下一轮 D1 晚到点补齐：同一路径游标仍在洞前，因此 D1、D2 均重新进入候选并依次成功。
        repository.rows = d1_complete_rows + d2_complete_rows
        tracker.set_point_count(first_day, d1_complete_count)
        tracker.calls.clear()
        repository.measurement_queries.clear()

        recovered_result = strategy._run_with_resources(
            context,
            predictor,
            "model-in-memory",
            "data/models/seq_annotation/in-memory",
            object(),
            gate,
        )

    assert recovered_result.status == "success"
    assert recovered_result.points_detected == d1_complete_count + d2_complete_count
    assert recovered_result.points_deferred == 0
    assert [call[3] for call in tracker.calls] == [first_day, second_day]
    assert [
        set(pd.to_datetime(frame["time"]).dt.date).pop()
        for frame in predictor.frames
    ] == [first_day, second_day]
    assert strategy.cursor is not None
    assert strategy.cursor.date() == second_day
    assert strategy.advanced[_DEVICE].date() == second_day


def _predictor_without_artifact() -> SeqAnnotationPredictor:
    """构造不加载模型文件的 predictor；Property 9 只走网格准备和跨日拒绝。"""
    predictor = object.__new__(SeqAnnotationPredictor)
    predictor._metadata = {
        "model_name": "in-memory-seq",
        "model_ref": "data/models/seq_annotation/in-memory",
        "trained_full_day": True,
        "daylight_start_hour": 0,
        "daylight_end_hour": 24,
    }
    predictor._measured_channels = ["value", "i_cal"]
    predictor._channels = ["value", "i_cal", "is_measured"]
    predictor._mask_channel_index = 2
    predictor._grid_aligned = True
    predictor._grid_contract = {
        "min_occupied_slots": SLOTS_PER_DAY,
        "min_daytime_occupancy": 1.0,
        "max_daytime_gap_slots": 0,
        "require_all_hours_covered": True,
    }
    predictor._postprocessing_contract = {}
    predictor._seq_len = SLOTS_PER_DAY
    predictor._daylight_start_hour = 0
    predictor._daylight_end_hour = 24
    return predictor


def _full_grid_frame(day: date, scale: float, offset: float) -> pd.DataFrame:
    """构造一个自然日恰好 288 个有限值时钟槽。"""
    timestamps = pd.date_range(day.isoformat(), periods=SLOTS_PER_DAY, freq="5min")
    slots = np.arange(SLOTS_PER_DAY, dtype=np.float64)
    return pd.DataFrame(
        {
            "time": timestamps,
            "value": slots * scale + offset,
            "i_cal": slots * (scale + 0.5) - offset,
        }
    )


# Feature: pv-fault-dual-path-serving, Property 9: 序列拒绝跨日网格
@given(
    first_day=st.dates(
        min_value=date(2020, 1, 1),
        max_value=date(2035, 12, 30),
    ),
    day_gap=st.integers(min_value=1, max_value=30),
    scale=st.floats(
        min_value=0.01,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    offset=st.floats(
        min_value=-10_000.0,
        max_value=10_000.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
@settings(max_examples=100, deadline=None)
def test_property_single_days_align_to_288_slots_and_cross_day_batch_is_rejected(
    first_day: date,
    day_gap: int,
    scale: float,
    offset: float,
) -> None:
    """逐日输入各自保持 288 槽；跨日单批被拒且不执行同网格覆盖。

    **Validates: Requirements 3.5, 3.6**
    """
    second_day = first_day + timedelta(days=day_gap)
    predictor = _predictor_without_artifact()
    first_frame = _full_grid_frame(first_day, scale, offset)
    second_frame = _full_grid_frame(second_day, scale, offset)

    for expected_day, frame in ((first_day, first_frame), (second_day, second_frame)):
        prepared = predictor._prepare_grid_input(frame, include_night=True)
        assert not isinstance(prepared, dict)
        grid, timestamps, report_indices, measured_flags = prepared
        assert grid.shape == (SLOTS_PER_DAY, 3)
        assert len(timestamps) == SLOTS_PER_DAY
        assert len(report_indices) == SLOTS_PER_DAY
        assert len(measured_flags) == SLOTS_PER_DAY
        assert set(pd.Timestamp(value).date() for value in timestamps) == {expected_day}
        assert measured_flags == [1] * SLOTS_PER_DAY
        np.testing.assert_array_equal(grid[:, 2], np.ones(SLOTS_PER_DAY))

    cross_day_frame = pd.concat([first_frame, second_frame], ignore_index=True)
    result = predictor.predict_device_day(cross_day_frame, include_night=True)

    assert result["n_points_predicted"] == 0
    assert result["timestamps"] == []
    assert result["point_predictions"] == []
    assert "单个自然日" in result["error"]
    assert "禁止把多天数据覆盖到同一时钟网格" in result["error"]
# @AI_GENERATED: end
