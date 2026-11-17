# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
tests/pv_dual_path/test_prop_scheduler_dispatch.py — 调度分派 Property 1–3 属性测试

使用 Hypothesis 验证 DualPathScheduler 的纯分派契约。所有外部依赖均使用内存 fake 注入：
生产路径读取器、运行状态写入器与 DataWatermarkService 替身都不会访问数据库或文件系统。

被测符号：
  - DualPathScheduler.dispatch(slot) — 读取 production_path（生产路径），选择唯一策略并返回
    CycleResult（周期结果）。
  - CycleResult.points_detected / points_deferred — 本轮检测数 / 顺延数；两者应非负且守恒。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from services.scheduler.pv_dual_path.scheduler import DualPathScheduler
from services.scheduler.pv_dual_path.strategy_base import CycleContext, CycleResult

_VALID_PATHS = ("legacy_day", "seq_annotation")


def _valid_summary(modeling_path: str) -> Dict[str, Any]:
    return {
        "production_path": modeling_path,
        "active_activation_epoch_id": "epoch-test",
        "path_models": {modeling_path: {"model_ref": "data/models/champion.pkl"}},
    }


class _FakeWatermark:
    """DataWatermarkService 的无 I/O 身份替身；本组属性只验证注入与分派。"""


class _FakeStrategy:
    """记录 run_cycle 调用次数与上下文，并返回预设 CycleResult。"""

    def __init__(self, name: str, result: CycleResult) -> None:
        self.name = name
        self.result = result
        self.call_count = 0
        self.contexts: List[CycleContext] = []

    def run_cycle(self, ctx: CycleContext) -> CycleResult:
        self.call_count += 1
        self.contexts.append(ctx)
        return self.result


def _cycle_result(
    modeling_path: str,
    strategy_name: str,
    *,
    points_detected: int = 0,
    points_deferred: int = 0,
) -> CycleResult:
    """构造成功周期结果，供 fake 策略确定返回。"""
    return CycleResult(
        modeling_path=modeling_path,
        strategy_name=strategy_name,
        window_start="2021-01-01T00:00:00",
        window_end="2021-01-01T23:55:00",
        points_detected=points_detected,
        points_deferred=points_deferred,
        devices_processed=1,
        batch_ids=[],
        review_ids=[],
        status="success",
        skipped_reason=None,
    )


def _make_strategies() -> Dict[str, _FakeStrategy]:
    """构造两条独立 fake 策略，便于断言互斥调用。"""
    return {
        "legacy_day": _FakeStrategy(
            "LegacyDayStrategy",
            _cycle_result("legacy_day", "LegacyDayStrategy"),
        ),
        "seq_annotation": _FakeStrategy(
            "SeqDailyStrategy",
            _cycle_result("seq_annotation", "SeqDailyStrategy"),
        ),
    }


# Feature: pv-fault-dual-path-serving, Property 1: 分派正确且互斥
@given(
    modeling_path=st.sampled_from(_VALID_PATHS),
    slot=st.text(min_size=1, max_size=32),
)
@settings(max_examples=100)
def test_property_dispatches_exactly_one_matching_strategy(
    modeling_path: str,
    slot: str,
) -> None:
    """合法路径恰好调用对应策略一次，且从不调用另一条策略。

    Validates: Requirements 1.2, 1.3
    """
    watermark = _FakeWatermark()
    statuses: List[Dict[str, Any]] = []
    strategies = _make_strategies()
    scheduler = DualPathScheduler(
        strategies=strategies,  # type: ignore[arg-type]
        read_modeling_paths=lambda requested_slot: _valid_summary(modeling_path),
        status_writer=statuses.append,
        watermark=watermark,  # type: ignore[arg-type]
    )

    result = scheduler.dispatch(slot)

    other_path = "seq_annotation" if modeling_path == "legacy_day" else "legacy_day"
    selected = strategies[modeling_path]
    assert selected.call_count == 1
    assert strategies[other_path].call_count == 0
    assert result is selected.result
    assert len(selected.contexts) == 1
    assert selected.contexts[0].slot == slot
    assert selected.contexts[0].modeling_path == modeling_path
    assert selected.contexts[0].champion_model_ref == "data/models/champion.pkl"
    assert selected.contexts[0].activation_epoch_id == "epoch-test"
    assert len(statuses) == 1
    assert statuses[0]["slot"] == slot
    assert statuses[0]["modeling_path"] == modeling_path
    assert statuses[0]["strategy_name"] == selected.name


_invalid_pointer_values = st.one_of(
    st.none(),
    st.just(""),
    st.text(max_size=80).filter(lambda value: value.strip() not in _VALID_PATHS),
)


# Feature: pv-fault-dual-path-serving, Property 2: 非法路径一律跳过
@given(
    pointer_value=_invalid_pointer_values,
    reader_raises=st.booleans(),
)
@settings(max_examples=150)
def test_property_invalid_or_unreadable_path_is_always_skipped(
    pointer_value: Optional[str],
    reader_raises: bool,
) -> None:
    """非法、空、None 或读取异常均不调用策略，并返回统一跳过原因。

    Validates: Requirements 1.4
    """
    statuses: List[Dict[str, Any]] = []
    strategies = _make_strategies()

    def read_modeling_paths(slot: str) -> Dict[str, Any]:
        if reader_raises:
            raise RuntimeError("synthetic pointer read failure")
        return {"production_path": pointer_value}

    scheduler = DualPathScheduler(
        strategies=strategies,  # type: ignore[arg-type]
        read_modeling_paths=read_modeling_paths,
        status_writer=statuses.append,
        watermark=_FakeWatermark(),  # type: ignore[arg-type]
    )

    result = scheduler.dispatch("pv_fault")

    assert strategies["legacy_day"].call_count == 0
    assert strategies["seq_annotation"].call_count == 0
    assert result.status == "skipped"
    assert result.skipped_reason == "invalid_modeling_path"
    assert result.points_detected == 0
    assert result.points_deferred == 0
    assert len(statuses) == 1
    assert statuses[0]["status"] == "skipped"
    assert statuses[0]["reason"] == "invalid_modeling_path"


# Feature: pv-fault-dual-path-serving, Property 3: 周期结果条数守恒
@given(
    modeling_path=st.sampled_from(_VALID_PATHS),
    points_detected=st.integers(min_value=0, max_value=100_000),
    points_deferred=st.integers(min_value=0, max_value=100_000),
)
@settings(max_examples=150)
def test_property_cycle_result_counts_are_preserved_and_conserved(
    modeling_path: str,
    points_detected: int,
    points_deferred: int,
) -> None:
    """dispatch 原样返回策略的非负条数，且检测数加顺延数等于候选总数。

    Validates: Requirements 1.6, 1.7
    """
    strategy_name = (
        "LegacyDayStrategy" if modeling_path == "legacy_day" else "SeqDailyStrategy"
    )
    expected_result = _cycle_result(
        modeling_path,
        strategy_name,
        points_detected=points_detected,
        points_deferred=points_deferred,
    )
    selected_strategy = _FakeStrategy(strategy_name, expected_result)
    statuses: List[Dict[str, Any]] = []
    scheduler = DualPathScheduler(
        strategies={modeling_path: selected_strategy},  # type: ignore[arg-type]
        read_modeling_paths=lambda slot: _valid_summary(modeling_path),
        status_writer=statuses.append,
        watermark=_FakeWatermark(),  # type: ignore[arg-type]
    )
    candidate_total = points_detected + points_deferred

    result = scheduler.dispatch("pv_fault")

    assert selected_strategy.call_count == 1
    assert result is expected_result
    assert result.points_detected == points_detected
    assert result.points_deferred == points_deferred
    assert result.points_detected >= 0
    assert result.points_deferred >= 0
    assert result.points_detected + result.points_deferred == candidate_total
    assert statuses[0]["points_detected"] == points_detected
    assert statuses[0]["points_deferred"] == points_deferred


def test_missing_champion_or_epoch_skips_without_guessing() -> None:
    strategies = _make_strategies()
    statuses: List[Dict[str, Any]] = []
    scheduler = DualPathScheduler(
        strategies=strategies,  # type: ignore[arg-type]
        read_modeling_paths=lambda slot: {"production_path": "legacy_day"},
        status_writer=statuses.append,
        watermark=_FakeWatermark(),  # type: ignore[arg-type]
    )
    result = scheduler.dispatch("pv_fault")
    assert result.status == "skipped"
    assert result.skipped_reason == "missing_champion_model_ref"
    assert strategies["legacy_day"].call_count == 0

    statuses.clear()
    scheduler = DualPathScheduler(
        strategies=strategies,  # type: ignore[arg-type]
        read_modeling_paths=lambda slot: {
            "production_path": "legacy_day",
            "path_models": {"legacy_day": {"model_ref": "data/models/a.pkl"}},
        },
        status_writer=statuses.append,
        watermark=_FakeWatermark(),  # type: ignore[arg-type]
    )
    result = scheduler.dispatch("pv_fault")
    assert result.status == "skipped"
    assert result.skipped_reason == "missing_activation_epoch"
    assert strategies["legacy_day"].call_count == 0


def test_second_dispatch_rereads_registry_snapshot() -> None:
    """下一轮实时读新路径；已完成轮次只使用启动时快照。"""
    calls = {"n": 0}
    captured: List[CycleContext] = []

    class _Capture(_FakeStrategy):
        def run_cycle(self, ctx: CycleContext) -> CycleResult:
            captured.append(ctx)
            return super().run_cycle(ctx)

    def reader(_slot: str) -> Dict[str, Any]:
        calls["n"] += 1
        path = "legacy_day" if calls["n"] == 1 else "seq_annotation"
        return _valid_summary(path)

    strategies = {
        "legacy_day": _Capture("LegacyDayStrategy", _cycle_result("legacy_day", "LegacyDayStrategy")),
        "seq_annotation": _Capture("SeqDailyStrategy", _cycle_result("seq_annotation", "SeqDailyStrategy")),
    }
    scheduler = DualPathScheduler(
        strategies=strategies,  # type: ignore[arg-type]
        read_modeling_paths=reader,
        status_writer=lambda _payload: None,
        watermark=_FakeWatermark(),  # type: ignore[arg-type]
    )
    first = scheduler.dispatch("pv_fault")
    second = scheduler.dispatch("pv_fault")
    assert first.modeling_path == "legacy_day"
    assert second.modeling_path == "seq_annotation"
    assert captured[0].modeling_path == "legacy_day"
    assert captured[1].modeling_path == "seq_annotation"
# @AI_GENERATED: end
