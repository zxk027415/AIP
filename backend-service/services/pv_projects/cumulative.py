# @AI_GENERATED
"""项目化累计入账与冻结（design §19；任务 4.3）。

三层结构（互不混淆）：
  1) 准入事件 admitted events — 来自审核 complete-and-admit 的 `cumulative_events(kind=admission)`。
  2) 冻结快照 frozen snapshots — 对某 `reviewed_at_cutoff` 之前准入事件做一次不可变冻结。
  3) 训练结果 training results — 基于快照的训练产物索引（冻结后可创建训练 run，仍须过候选治理）。

冻结确认区（design §19.2）：
- `reviewed_at_cutoff` 审核时间上界；included / excluded 事件；标签 / 设备 / 日期分布；
  输出快照类型；重复输入检测（同一 cutoff + 同一事件集合 → 幂等命中已有快照）。
- 路径特定备注：point 整日盒、TSC 288×3 合格、day device-day 可行性（只读提示，不改判定）。

红线：本模块只写 scoped 项目证据（snapshots / results），不触碰生产 registry / 指针；
冻结与训练结果登记不等于模型准入，Promote 仍需正式复验 + 生产授权。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects.governance import GovernanceGateError
from services.pv_projects.scope import ScopeContext
from services.pv_projects.stores import (
    cumulative_events as _cumulative_events,
    results as _results,
    snapshots as _snapshots,
)

#: 路径 → 输出快照类型 + 备注（只读提示）。
_SNAPSHOT_TYPE_BY_SLOT: dict[str, dict[str, str]] = {
    "pv_day": {"snapshot_type": "device_day_curve_set", "note": "day device-day 可行性：整设备日曲线集"},
    "pv_point": {"snapshot_type": "whole_day_point_box", "note": "point 整日盒：逐点真值需事件时间因果，过滤整日聚类盒"},
    "pv_tsc": {"snapshot_type": "tsc_288x3_grid", "note": "TSC 288×3：日×设备严格隔离，需满足合格通道与类别分布"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# 只读三层视图
# ---------------------------------------------------------------------------

def list_admissions(scope: ScopeContext) -> list[dict[str, Any]]:
    return [e for e in _cumulative_events.list(scope) if e.get("kind") == "admission"]


def list_snapshots(scope: ScopeContext) -> list[dict[str, Any]]:
    return _snapshots.list(scope)


def list_training_results(scope: ScopeContext) -> list[dict[str, Any]]:
    return _results.list(scope)


def cumulative_overview(scope: ScopeContext) -> dict[str, Any]:
    """三层视图 + lineage 回溯（数据版本 / 审核来源）。"""
    admissions = list_admissions(scope)
    return {
        **scope.echo(),
        "admitted_events": admissions,
        "frozen_snapshots": list_snapshots(scope),
        "training_results": list_training_results(scope),
        "summary": {
            "admission_count": len(admissions),
            "admitted_units": sum(int(e.get("admitted_count") or 0) for e in admissions),
            "snapshot_count": len(list_snapshots(scope)),
            "training_result_count": len(list_training_results(scope)),
        },
    }


# ---------------------------------------------------------------------------
# 冻结计划（预览，不写）
# ---------------------------------------------------------------------------

#: pv_point 冻结不接受的整日 / 设备日粒度（整日聚类盒不能作为逐点 / 区间真值来源）。
_WHOLE_DAY_GRANULARITIES: tuple[str, ...] = ("device_day", "whole_day", "day", "device-day", "whole-day")


def _is_whole_day_box(ev: dict[str, Any]) -> bool:
    return str(ev.get("unit_granularity") or "").strip().lower() in _WHOLE_DAY_GRANULARITIES


def _select_events(scope: ScopeContext, reviewed_at_cutoff: Optional[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 cutoff 切分 included / excluded 准入事件。

    pv_point 额外过滤：整日 / 设备日粒度的准入事件（整日聚类盒）不能进入点路径冻结输入
    （design §19.2、任务 6.3 边界）；这类事件被列入 excluded 并标注原因。
    """
    is_point = scope.slot == "pv_point"
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for ev in list_admissions(scope):
        admitted_at = str(ev.get("admitted_at") or "")
        if reviewed_at_cutoff and admitted_at and admitted_at > str(reviewed_at_cutoff):
            excluded.append({**ev, "exclude_reason": "after_cutoff"})
            continue
        if is_point and _is_whole_day_box(ev):
            # 整日盒不作为逐点真值来源，过滤出点路径冻结输入。
            excluded.append({**ev, "exclude_reason": "whole_day_box_not_point_truth"})
            continue
        included.append(ev)
    return included, excluded


def _distributions(events: list[dict[str, Any]]) -> dict[str, Any]:
    labels: dict[str, int] = {}
    devices: dict[str, int] = {}
    dates: dict[str, int] = {}
    for ev in events:
        for ref in ev.get("accepted_unit_refs") or []:
            key = str(ref)
            # unit_ref 约定形如 "device=D1;date=2026-01-01;label=fault"（可选片段）
            for part in key.split(";"):
                if part.startswith("device="):
                    devices[part[7:]] = devices.get(part[7:], 0) + 1
                elif part.startswith("date="):
                    dates[part[5:]] = dates.get(part[5:], 0) + 1
                elif part.startswith("label="):
                    labels[part[6:]] = labels.get(part[6:], 0) + 1
    return {"label_distribution": labels, "device_distribution": devices, "date_distribution": dates}


def freeze_plan(scope: ScopeContext, *, reviewed_at_cutoff: Optional[str] = None) -> dict[str, Any]:
    """冻结计划预览：included/excluded、分布、输出快照类型、重复输入检测。不写任何数据。"""
    included, excluded = _select_events(scope, reviewed_at_cutoff)
    included_ids = sorted(str(e.get("event_id")) for e in included)
    plan_fingerprint = _digest({"cutoff": reviewed_at_cutoff, "event_ids": included_ids})
    duplicate = next(
        (s for s in list_snapshots(scope) if s.get("plan_fingerprint") == plan_fingerprint),
        None,
    )
    slot = scope.require_slot()
    snap_meta = _SNAPSHOT_TYPE_BY_SLOT.get(slot, {"snapshot_type": "generic_snapshot", "note": ""})
    return {
        **scope.echo(),
        "reviewed_at_cutoff": reviewed_at_cutoff,
        "included_events": included_ids,
        "excluded_events": sorted(str(e.get("event_id")) for e in excluded),
        "included_count": len(included),
        "excluded_count": len(excluded),
        **_distributions(included),
        "output_snapshot_type": snap_meta["snapshot_type"],
        "path_note": snap_meta["note"],
        "plan_fingerprint": plan_fingerprint,
        "duplicate_input_detected": duplicate is not None,
        "duplicate_snapshot_id": duplicate.get("snapshot_id") if duplicate else None,
        "freezable": len(included) > 0 and duplicate is None,
    }


# ---------------------------------------------------------------------------
# 执行冻结（写 scoped 快照，幂等）
# ---------------------------------------------------------------------------

def execute_freeze(
    scope: ScopeContext,
    *,
    reviewed_at_cutoff: Optional[str],
    idempotency_key: str,
    operator: str,
) -> dict[str, Any]:
    """执行一次冻结，产出不可变快照（scoped）。幂等：同 plan_fingerprint / key 命中已有快照。"""
    scope.assert_writable()
    if not str(idempotency_key or "").strip():
        raise GovernanceGateError("missing_idempotency_key", "缺少 idempotency_key。", category="business_gate_blocked")
    if not str(operator or "").strip():
        raise GovernanceGateError("missing_operator", "缺少 operator。", category="business_gate_blocked")

    plan = freeze_plan(scope, reviewed_at_cutoff=reviewed_at_cutoff)

    # 幂等命中（重复输入或相同 idempotency_key）。
    for s in list_snapshots(scope):
        if s.get("plan_fingerprint") == plan["plan_fingerprint"] or s.get("idempotency_key") == idempotency_key:
            return {"snapshot": s, "idempotent_replay": True}

    if plan["included_count"] == 0:
        raise GovernanceGateError(
            "no_admitted_events",
            "该 cutoff 下没有可冻结的准入事件。",
            category="business_gate_blocked",
            next_action="先在审核队列完成裁定并准入，或调整审核时间上界",
        )

    snapshot = {
        "snapshot_id": f"snap-{uuid.uuid4().hex[:12]}",
        "slot": scope.require_slot(),
        "reviewed_at_cutoff": reviewed_at_cutoff,
        "included_events": plan["included_events"],
        "included_count": plan["included_count"],
        "excluded_count": plan["excluded_count"],
        "label_distribution": plan["label_distribution"],
        "device_distribution": plan["device_distribution"],
        "date_distribution": plan["date_distribution"],
        "snapshot_type": plan["output_snapshot_type"],
        "path_note": plan["path_note"],
        "plan_fingerprint": plan["plan_fingerprint"],
        "content_digest": _digest(plan),
        "immutable": True,
        "idempotency_key": idempotency_key,
        "operator": operator,
        "frozen_at": _now_iso(),
    }
    saved = _snapshots.append(scope, snapshot)
    return {"snapshot": saved, "idempotent_replay": False}


def register_training_result(
    scope: ScopeContext,
    *,
    snapshot_id: str,
    source_execution_id: str,
    model_artifact_ref: str,
    metrics: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """登记基于快照的训练结果索引（第三层）。

    仅记录 lineage，**不**代表模型准入；要成为候选并 Promote 仍须经候选治理 + 正式复验 + 生产授权。
    """
    scope.assert_writable()
    snapshot = _snapshots.find(scope, snapshot_id)
    if snapshot is None:
        raise GovernanceGateError(
            "snapshot_not_found",
            f"当前 scope 下找不到冻结快照 {snapshot_id!r}。",
            category="business_gate_blocked",
        )
    result = {
        "result_id": f"trn-{uuid.uuid4().hex[:12]}",
        "kind": "training_result",
        "slot": scope.require_slot(),
        "source_snapshot_id": snapshot_id,
        "source_execution_id": source_execution_id,
        "model_artifact_ref": model_artifact_ref,
        "metrics": metrics or {},
        "governance_note": "训练结果登记不等于模型准入；成为候选并 Promote 仍需正式复验 + 生产授权。",
        "registered_at": _now_iso(),
    }
    return _results.append(scope, result)


# @AI_GENERATED: end
