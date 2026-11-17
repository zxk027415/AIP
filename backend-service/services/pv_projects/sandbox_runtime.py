# @AI_GENERATED
"""pv_point 事件时间逐点回放的隔离 Sandbox 运行域（design D-PATH-01 / D-STATE-01；任务 6.1）。

按 `(project_id, sandbox_id, slot)` 保存隔离的 pending point / committed history / cursor / outcome，
是点路径“逐点因果回放”的项目内运行域实现。

诚实实现事实（红线）：
- 生产点路径由 `SeqDailyStrategy` 直接预测（见 `services/scheduler/pv_dual_path/seq_daily_strategy.py`），
  真实逐点因果内核在 `services/timeseries_point/replay_activity.py::_process_one_point()`；
  本 SandboxRuntime 是**项目内 Sandbox 隔离态**，不把逐点回放包装成日批，也不声称冻结工作流 provenance。

因果不变量（P-POINT-01 必须成立）：
1. 事件时间序：points 按 event_time 升序处理。
2. 严格因果：对第 i 个点的预测**只读**严格早于它的已提交历史（committed_history[:cursor]）+ 该点自身输入，
   不读任何未来点；未来点的任意改动都不影响当前预测。
3. cursor 只在一次 outcome 被提交后推进；未提交前 cursor 不动。
4. reset 只替换被选中的 Sandbox 状态，不动其他 Sandbox / 其他 scope。
5. device-day 级标签绝不作为逐点真值或进入指标（监督点真值只能是点/区间级）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects.governance import GovernanceGateError
from services.pv_projects.scope import ScopeContext
from services.pv_projects.stores import sandbox_runs as _sandbox_runs


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sorted_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 event_time 升序（稳定）；缺 event_time 的点排在最后并保序。"""
    def key(idx_pt: tuple[int, dict[str, Any]]):
        idx, pt = idx_pt
        et = str(pt.get("event_time") or "")
        return (et == "", et, idx)

    return [pt for _, pt in sorted(enumerate(points or []), key=key)]


def _predict(committed_history: list[dict[str, Any]], current_point: dict[str, Any]) -> dict[str, Any]:
    """确定性预测：**只依赖**已提交历史 + 当前点自身输入，绝不读未来点。

    这是 Sandbox 演示内核（非真实模型）：可复现、可验证因果。返回结论对未来点的任何改动不敏感。
    """
    values = [float(h.get("value") or 0.0) for h in committed_history]
    n = len(values)
    baseline = (sum(values) / n) if n > 0 else float(current_point.get("value") or 0.0)
    current_value = float(current_point.get("value") or 0.0)
    # 结论仅由 (历史均值, 当前点值) 决定。
    score = round(abs(current_value - baseline), 6)
    return {
        "n_history": n,
        "baseline_from_committed": round(baseline, 6),
        "current_value": current_value,
        "anomaly_score": score,
        "predicted_at": _now_iso(),
    }


def _require(scope: ScopeContext, sandbox_id: str) -> dict[str, Any]:
    rec = _sandbox_runs.find(scope, sandbox_id)
    if rec is None:
        raise GovernanceGateError(
            "sandbox_not_found",
            f"当前项目 / 路径下找不到 Sandbox {sandbox_id!r}。",
            category="business_gate_blocked",
            next_action="先创建该 Sandbox 回放会话",
        )
    return rec


class SandboxRuntime:
    """按 `(project_id, sandbox_id, slot)` 隔离的事件时间逐点回放运行域。"""

    # -- 创建 / 读取 -------------------------------------------------------

    @staticmethod
    def create(
        scope: ScopeContext,
        *,
        sandbox_id: str,
        points: list[dict[str, Any]],
        model_ref: Optional[str] = None,
        session_source: str = "real_replay",
        dataset_version_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """创建 Sandbox 回放会话。`session_source`：real_replay / loop_demo（演示喂点，不写台账）。"""
        scope.assert_writable()
        if not str(sandbox_id or "").strip():
            raise GovernanceGateError("missing_sandbox_id", "缺少 sandbox_id。", category="business_gate_blocked")
        ordered = _sorted_points(points)
        for i, pt in enumerate(ordered):
            pt.setdefault("point_index", i)
        record = {
            "sandbox_id": sandbox_id,
            "slot": scope.require_slot(),
            "run_domain": "sandbox",
            "session_source": session_source,
            "model_ref": model_ref,
            "dataset_version_id": dataset_version_id,
            "source_points": ordered,
            "committed_history": [],
            "cursor": 0,
            "pending_point": None,
            "production_unaffected": True,
            "writes_cumulative_ledger": False,  # loop_demo / sandbox 都不写累计台账
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        return _sandbox_runs.replace(scope, sandbox_id, record)

    @staticmethod
    def get(scope: ScopeContext, sandbox_id: str) -> dict[str, Any]:
        return _require(scope, sandbox_id)

    # -- 逐点因果推进 ------------------------------------------------------

    @staticmethod
    def predict_next(scope: ScopeContext, sandbox_id: str) -> dict[str, Any]:
        """对 cursor 处的点做预测，写入 pending_point（**不推进 cursor**）。

        预测只读 committed_history[:cursor]（严格早于当前点）+ 当前点自身输入。
        """
        scope.assert_writable()
        rec = _require(scope, sandbox_id)
        if rec.get("pending_point"):
            # 已有未提交的 pending，返回它（幂等：不重复预测覆盖未决 outcome）。
            return {"sandbox": rec, "pending_point": rec["pending_point"], "already_pending": True}
        cursor = int(rec.get("cursor") or 0)
        points = rec.get("source_points") or []
        if cursor >= len(points):
            return {"sandbox": rec, "pending_point": None, "caught_up": True}
        current = points[cursor]
        committed = rec.get("committed_history") or []
        # 严格因果：只取严格早于当前点的已提交历史。
        prediction = _predict(committed[:cursor], current)
        pending = {
            "point_index": cursor,
            "event_time": current.get("event_time"),
            "input_point": current,
            "prediction": prediction,
            "committed": False,
        }
        rec["pending_point"] = pending
        rec["updated_at"] = _now_iso()
        saved = _sandbox_runs.replace(scope, sandbox_id, rec)
        return {"sandbox": saved, "pending_point": pending, "already_pending": False}

    @staticmethod
    def commit_outcome(
        scope: ScopeContext,
        sandbox_id: str,
        *,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """提交 pending_point 的 outcome → 追加历史并推进 cursor（**cursor 只在此推进**）。"""
        scope.assert_writable()
        rec = _require(scope, sandbox_id)
        pending = rec.get("pending_point")
        if not pending:
            raise GovernanceGateError(
                "no_pending_point",
                "没有待提交的点；请先 predict_next。",
                category="business_gate_blocked",
            )
        # 幂等：同 key 已提交则不重复推进。
        if idempotency_key:
            for h in rec.get("committed_history") or []:
                if str(h.get("idempotency_key") or "") == str(idempotency_key):
                    return {"sandbox": rec, "committed": h, "idempotent_replay": True}
        committed_entry = {
            "point_index": pending["point_index"],
            "event_time": pending.get("event_time"),
            "value": (pending.get("input_point") or {}).get("value"),
            "prediction": pending.get("prediction"),
            "committed_at": _now_iso(),
            "idempotency_key": idempotency_key,
        }
        history = list(rec.get("committed_history") or [])
        history.append(committed_entry)
        rec["committed_history"] = history
        rec["cursor"] = int(rec.get("cursor") or 0) + 1  # 只在 outcome 提交后推进
        rec["pending_point"] = None
        rec["updated_at"] = _now_iso()
        saved = _sandbox_runs.replace(scope, sandbox_id, rec)
        return {"sandbox": saved, "committed": committed_entry, "idempotent_replay": False}

    @staticmethod
    def step(scope: ScopeContext, sandbox_id: str, *, idempotency_key: Optional[str] = None) -> dict[str, Any]:
        """单步：predict_next + commit_outcome（推进一个点）。"""
        SandboxRuntime.predict_next(scope, sandbox_id)
        return SandboxRuntime.commit_outcome(scope, sandbox_id, idempotency_key=idempotency_key)

    @staticmethod
    def advance(scope: ScopeContext, sandbox_id: str, n: int) -> dict[str, Any]:
        """推进 n 个点（每个点都严格因果）。返回推进后的会话与已处理计数。"""
        scope.assert_writable()
        processed = 0
        for _ in range(max(0, int(n))):
            rec = _require(scope, sandbox_id)
            if int(rec.get("cursor") or 0) >= len(rec.get("source_points") or []) and not rec.get("pending_point"):
                break
            SandboxRuntime.step(scope, sandbox_id)
            processed += 1
        return {"sandbox": _require(scope, sandbox_id), "processed": processed}

    # -- reset（Sandbox 局部） ---------------------------------------------

    @staticmethod
    def reset(scope: ScopeContext, sandbox_id: str) -> dict[str, Any]:
        """只重置被选中的 Sandbox 状态（cursor / history / pending），不动其他 Sandbox。"""
        scope.assert_writable()
        rec = _require(scope, sandbox_id)
        rec["committed_history"] = []
        rec["cursor"] = 0
        rec["pending_point"] = None
        rec["reset_at"] = _now_iso()
        rec["updated_at"] = _now_iso()
        return _sandbox_runs.replace(scope, sandbox_id, rec)

    # -- 指标（点/区间级真值；device-day 标签绝不进入） ---------------------

    @staticmethod
    def metrics(scope: ScopeContext, sandbox_id: str) -> dict[str, Any]:
        """只统计已提交点级 outcome；不接受 device-day 级标签作为真值。"""
        rec = _require(scope, sandbox_id)
        committed = rec.get("committed_history") or []
        return {
            **scope.echo(),
            "sandbox_id": sandbox_id,
            "committed_points": len(committed),
            "cursor": int(rec.get("cursor") or 0),
            "total_points": len(rec.get("source_points") or []),
            "device_day_labels_as_truth": False,  # 红线：日级标签不作为逐点真值
            "supervised_point_accuracy": None,     # 无点级真值时诚实置空
            "note": "Sandbox 逐点指标仅基于点/区间级已提交结论；device-day 标签不进入真值 / 指标。",
        }


# @AI_GENERATED: end
