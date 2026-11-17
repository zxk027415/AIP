# @AI_GENERATED
"""pv_day 金路径适配器（design D-PATH-01；任务 5.1）。

诚实实现事实（红线，不得改写）：
- 日路径**生产检测**由 `LegacyDayStrategy` 调用共享预测工作流
  `workflow-pv-fault-diag-quickval-predict-v1` 完成（见
  `services/scheduler/pv_dual_path/legacy_day_strategy.py`）。**不存在**专用的“日级生产图”，
  本适配器只如实展示该事实，不迁移、不改写、不声称新建了日级生产管线。
- 项目内的日级实验 / 验证 / Sandbox 结果都经共享 `ScopedWorkflowRunner` 持久化（scoped 证据），
  不写生产 registry / 指针；Sandbox 全设备日回放产出**隔离**结果，明确 production 不受影响。
- 本模块只做 scoped 读写与 device-day 汇总；device-day 真值绝不由日级标签臆造，
  准入 / 冻结 / 快照 lineage 仍走审核 + 累计模块的门控。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects.governance import GovernanceGateError
from services.pv_projects.scope import ScopeContext
from services.pv_projects.stores import executions as _executions, sandbox_runs as _sandbox_runs

#: 日路径生产事实（只读诚实标注）。
DAY_PRODUCTION_FACT: dict[str, Any] = {
    "production_strategy": "LegacyDayStrategy",
    "production_workflow_id": "workflow-pv-fault-diag-quickval-predict-v1",
    "dedicated_day_production_graph": False,
    "statement": (
        "日路径生产检测复用 quickval 预测工作流（LegacyDayStrategy 调用 "
        "workflow-pv-fault-diag-quickval-predict-v1）；本工作台不新建日级生产图，"
        "项目内运行仅产出 scoped 实验 / 验证 / Sandbox 证据。"
    ),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def day_production_fact(scope: ScopeContext) -> dict[str, Any]:
    """返回日路径生产事实（携 scope 回显）。"""
    return {**scope.echo(), **DAY_PRODUCTION_FACT}


def _device_day_key(rec: dict[str, Any]) -> str:
    dev = str(rec.get("device") or rec.get("device_id") or "?")
    day = str(rec.get("date") or rec.get("day") or "?")
    return f"device={dev};date={day}"


def summarize_day_execution(scope: ScopeContext, execution_id: str) -> dict[str, Any]:
    """汇总一次日级 execution 的 device-day 结果：接收 / 拒收计数、来源 / 标签分布、相对工件。

    只读 scoped execution 记录里已存的 `device_day_results`；不重算、不臆造。
    """
    rec = _executions.find(scope, execution_id)
    if rec is None:
        raise GovernanceGateError(
            "execution_not_found",
            f"当前项目 / 路径下找不到 execution {execution_id!r}。",
            category="business_gate_blocked",
        )
    results = rec.get("device_day_results") or []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    source_dist: dict[str, int] = {}
    label_dist: dict[str, int] = {}
    for r in results:
        if r.get("accepted") is True:
            accepted.append(r)
            label = str(r.get("label") or "unknown")
            label_dist[label] = label_dist.get(label, 0) + 1
        else:
            rejected.append(r)
        src = str(r.get("source") or "unknown")
        source_dist[src] = source_dist.get(src, 0) + 1
    return {
        **scope.echo(),
        "execution_id": execution_id,
        "run_mode": rec.get("run_mode"),
        "run_domain": rec.get("run_domain"),
        "governance_eligible": rec.get("governance_eligible", False),
        "accepted_device_days": len(accepted),
        "rejected_device_days": len(rejected),
        "accepted_device_day_keys": [_device_day_key(r) for r in accepted],
        "source_distribution": source_dist,
        "label_distribution": label_dist,
        "artifact_ref": rec.get("artifact_ref"),
        "production_fact": DAY_PRODUCTION_FACT,
    }


def run_sandbox_device_day(
    scope: ScopeContext,
    *,
    sandbox_id: str,
    device_days: list[dict[str, Any]],
    model_ref: Optional[str] = None,
) -> dict[str, Any]:
    """Sandbox 全设备日回放：对每个 device-day 产出**隔离**结果（不影响 production）。

    这是 Sandbox 演示 / 回放，不连接真实生产模型；结果落 scoped `sandbox_runs`，
    带 `run_domain=sandbox` 与 `production_unaffected=true`。全设备日=对传入的每个
    (device, date) 都产出一条结果，不做部分丢弃（如实反映“全设备日”覆盖）。
    """
    scope.assert_writable()
    if not str(sandbox_id or "").strip():
        raise GovernanceGateError("missing_sandbox_id", "缺少 sandbox_id。", category="business_gate_blocked")
    processed: list[dict[str, Any]] = []
    for idx, dd in enumerate(device_days or []):
        processed.append(
            {
                "device_day_key": _device_day_key(dd),
                "device": dd.get("device") or dd.get("device_id"),
                "date": dd.get("date") or dd.get("day"),
                # Sandbox 演示占位结论：确定性、可复现，明确非生产判定。
                "sandbox_outcome": "replayed",
                "order": idx,
            }
        )
    record = {
        "sandbox_id": sandbox_id,
        "slot": scope.require_slot(),
        "run_domain": "sandbox",
        "model_ref": model_ref,
        "device_day_count": len(processed),
        "device_day_results": processed,
        "production_unaffected": True,
        "result_id": f"sbx-day-{uuid.uuid4().hex[:12]}",
        "governance_eligible": False,
        "note": "Sandbox 全设备日回放，隔离结果，不写生产指针 / 不产出可治理证据。",
        "created_at": _now_iso(),
    }
    return _sandbox_runs.append(scope, record)


def list_sandbox_day_runs(scope: ScopeContext) -> list[dict[str, Any]]:
    """列出当前 scope 的 Sandbox 日级回放（不跨项目 / 不跨槽）。"""
    return [r for r in _sandbox_runs.list(scope) if (r.get("device_day_results") is not None)]


# @AI_GENERATED: end
