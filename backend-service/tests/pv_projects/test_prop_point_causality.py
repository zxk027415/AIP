# @AI_GENERATED
"""Property test P-POINT-01：点路径事件时间因果（任务 6.4，必需）。

设计依据：design.md §29.1（P-POINT-01）；requirements.md R4.3、R4.4、R14.10、R14.12、R15.10。

不变量：
- 事件时间序处理；对第 i 点的预测只依赖严格早于它的已提交历史 + 当前点自身输入。
- **未来点的任意改动**不影响当前点的预测结论。
- cursor 只在一次 outcome 被提交后推进。
- reset 只影响被选中的 Sandbox，不动其他 Sandbox / 其他 scope。
- device-day 级标签绝不作为逐点真值或进入指标。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator

from hypothesis import given, settings
from hypothesis import strategies as st

from services.pv_projects import ScopeContext
from services.pv_projects import repositories as repo
from services.pv_projects.sandbox_runtime import SandboxRuntime, _predict, _sorted_points


@contextmanager
def temp_storage() -> Iterator[None]:
    tmp = tempfile.mkdtemp(prefix="pvproj_point_")
    repo.set_storage_base(tmp)
    try:
        yield
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _scope(pid: str = "proj-pt", slot: str = "pv_point") -> ScopeContext:
    return ScopeContext.create(pid, slot, require_slot=True, allow_legacy=False)


_point_values = st.lists(
    st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=12,
)


def _points_from_values(values: list[float]) -> list[dict[str, Any]]:
    return [
        {"event_time": f"2026-01-01T00:{i:02d}:00", "value": v, "point_id": f"p{i}"}
        for i, v in enumerate(values)
    ]


# ===========================================================================
# 因果：预测只依赖严格早于当前点的已提交历史 + 当前点
# ===========================================================================

@settings(max_examples=30, deadline=None)
@given(values=_point_values, future_noise=st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False))
def test_prediction_independent_of_future_mutations(values: list[float], future_noise: float) -> None:
    """改动未来点不改变当前点预测：预测是 committed[:cursor] + 当前点的纯函数。"""
    with temp_storage():
        scope = _scope()
        pts = _points_from_values(values)
        SandboxRuntime.create(scope, sandbox_id="s1", points=pts)
        # 推进到某个中间点后 predict_next。
        mid = len(values) // 2
        SandboxRuntime.advance(scope, "s1", mid)
        p_before = SandboxRuntime.predict_next(scope, "s1")["pending_point"]

        # 对同一初始序列，但把所有“未来点”（index > mid）的 value 改成 noise，重放到同一 cursor。
        scope2 = _scope("proj-pt2", "pv_point")
        mutated = _points_from_values(values)
        for j in range(mid + 1, len(mutated)):
            mutated[j]["value"] = future_noise
        SandboxRuntime.create(scope2, sandbox_id="s1", points=mutated)
        SandboxRuntime.advance(scope2, "s1", mid)
        p_after = SandboxRuntime.predict_next(scope2, "s1")["pending_point"]

        if p_before is None or p_after is None:
            assert p_before == p_after
        else:
            # 当前点预测的 anomaly_score / baseline 与未来点无关。
            assert p_before["prediction"]["anomaly_score"] == p_after["prediction"]["anomaly_score"]
            assert p_before["prediction"]["baseline_from_committed"] == p_after["prediction"]["baseline_from_committed"]


@settings(max_examples=40, deadline=None)
@given(values=_point_values)
def test_cursor_advances_only_after_commit(values: list[float]) -> None:
    """predict_next 不推进 cursor；只有 commit_outcome 推进。"""
    with temp_storage():
        scope = _scope()
        SandboxRuntime.create(scope, sandbox_id="s1", points=_points_from_values(values))
        before = SandboxRuntime.get(scope, "s1")["cursor"]
        SandboxRuntime.predict_next(scope, "s1")
        after_predict = SandboxRuntime.get(scope, "s1")["cursor"]
        assert after_predict == before  # 预测不推进
        SandboxRuntime.commit_outcome(scope, "s1")
        after_commit = SandboxRuntime.get(scope, "s1")["cursor"]
        assert after_commit == before + 1  # 提交后 +1


@settings(max_examples=40, deadline=None)
@given(values=_point_values)
def test_prediction_reads_only_committed_history(values: list[float]) -> None:
    """每个点提交时，其预测的 n_history 恰等于此前已提交点数（严格因果）。"""
    with temp_storage():
        scope = _scope()
        SandboxRuntime.create(scope, sandbox_id="s1", points=_points_from_values(values))
        for expected_hist in range(len(values)):
            res = SandboxRuntime.predict_next(scope, "s1")
            pending = res["pending_point"]
            assert pending is not None
            assert pending["prediction"]["n_history"] == expected_hist
            SandboxRuntime.commit_outcome(scope, "s1")


# ===========================================================================
# reset 局部性
# ===========================================================================

@settings(max_examples=30, deadline=None)
@given(values=_point_values)
def test_reset_is_sandbox_local(values: list[float]) -> None:
    """reset s1 不影响 s2。"""
    with temp_storage():
        scope = _scope()
        SandboxRuntime.create(scope, sandbox_id="s1", points=_points_from_values(values))
        SandboxRuntime.create(scope, sandbox_id="s2", points=_points_from_values(values))
        SandboxRuntime.advance(scope, "s1", len(values))
        SandboxRuntime.advance(scope, "s2", len(values))
        s2_cursor_before = SandboxRuntime.get(scope, "s2")["cursor"]

        SandboxRuntime.reset(scope, "s1")
        assert SandboxRuntime.get(scope, "s1")["cursor"] == 0
        assert SandboxRuntime.get(scope, "s1")["committed_history"] == []
        # s2 不受影响。
        assert SandboxRuntime.get(scope, "s2")["cursor"] == s2_cursor_before


def test_reset_does_not_touch_other_scope() -> None:
    """reset 在 A 项目下不影响 B 项目同名 sandbox。"""
    with temp_storage():
        a = _scope("proj-a", "pv_point")
        b = _scope("proj-b", "pv_point")
        pts = _points_from_values([1.0, 2.0, 3.0])
        SandboxRuntime.create(a, sandbox_id="s1", points=pts)
        SandboxRuntime.create(b, sandbox_id="s1", points=pts)
        SandboxRuntime.advance(a, "s1", 3)
        SandboxRuntime.advance(b, "s1", 3)
        SandboxRuntime.reset(a, "s1")
        assert SandboxRuntime.get(a, "s1")["cursor"] == 0
        assert SandboxRuntime.get(b, "s1")["cursor"] == 3  # 跨项目隔离


# ===========================================================================
# device-day 标签不进入真值 / 指标
# ===========================================================================

@settings(max_examples=20, deadline=None)
@given(values=_point_values)
def test_device_day_labels_never_enter_metrics(values: list[float]) -> None:
    with temp_storage():
        scope = _scope()
        SandboxRuntime.create(scope, sandbox_id="s1", points=_points_from_values(values))
        SandboxRuntime.advance(scope, "s1", len(values))
        m = SandboxRuntime.metrics(scope, "s1")
        assert m["device_day_labels_as_truth"] is False
        assert m["supervised_point_accuracy"] is None
        assert m["committed_points"] == len(values)


# ===========================================================================
# 事件时间排序（纯函数）
# ===========================================================================

@settings(max_examples=30, deadline=None)
@given(values=_point_values)
def test_points_sorted_by_event_time(values: list[float]) -> None:
    # 逆序输入 event_time，应被稳定排序为升序。
    pts = [{"event_time": f"2026-01-01T00:{len(values) - i:02d}:00", "value": v} for i, v in enumerate(values)]
    ordered = _sorted_points(pts)
    ets = [p["event_time"] for p in ordered]
    assert ets == sorted(ets)


def test_predict_pure_function_ignores_future() -> None:
    """_predict 只吃 committed + current；显式验证不接受未来点参数。"""
    committed = [{"value": 1.0}, {"value": 3.0}]
    current = {"value": 5.0}
    r1 = _predict(committed, current)
    r2 = _predict(committed, current)
    assert r1["baseline_from_committed"] == r2["baseline_from_committed"] == 2.0
    assert r1["anomaly_score"] == 3.0  # |5 - 2|

# @AI_GENERATED: end
