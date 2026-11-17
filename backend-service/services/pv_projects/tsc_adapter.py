# @AI_GENERATED
"""pv_tsc canonical 打标 / strict-10 证据 / 只读生产观测 / 门禁适配器（design D-PATH-01；任务 7.1–7.4）。

诚实实现事实（红线，不得改写）：
- canonical TSC 模型辅助打标工作流是 `workflow-pv-tsc-label-v1`，其画布链路为
  `tsc_predict → emit_tsc_label_proposal`（见 `services/operator_backends/emit_tsc_label_proposal.py`、
  `services/scheduler/pv_dual_path/tsc_strategy.py`）。失败不产出提案（fail-closed）。
- 历史 KMeans REST 聚类是 `labeling_mode=shortcut`（见 `api/iterative_labeling.py`），
  **不是** canonical TSC 模型辅助打标；`preferred_labeling_workflow_id` 仅为元数据指引。
- strict-10 真证据来自 `exec-validation-d741dc207593`（288×3、10 splits、固定标签空间、
  日×设备严格隔离），其 `governance_eligible=false`；`production_contract_valid` 仅表示
  **合同完整**，不表示精度达标或可治理。所有 validation execution 恒为非可治理。
- TSC 生产观测**只读**：缺当前回执即“未产出”，失败日不推进游标；水位 / 游标 / 审核 / 精度
  的手工写入一律拒绝（本环境 production_writes_authorized=false）。

本模块只做 scoped 读写与只读展示；不执行真实生产写入、不伪造精度、不把 shortcut 当 canonical。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects.governance import GovernanceGateError
from services.pv_projects.scope import ScopeContext
from services.pv_projects.stores import executions as _executions, results as _results

#: 各槽 canonical 打标工作流（与 api/iterative_labeling.py 的 _LABEL_WORKFLOW_BY_SLOT 一致）。
CANONICAL_LABEL_WORKFLOW_BY_SLOT: dict[str, str] = {
    "pv_point": "workflow-pv-point-label-v1",
    "pv_day": "workflow-pv-day-label-v1",
    "pv_tsc": "workflow-pv-tsc-label-v1",
}

#: canonical TSC 打标画布链路（只读展示）。
TSC_CANONICAL_LINEAGE: tuple[str, ...] = ("tsc_predict", "emit_tsc_label_proposal")

#: strict-10 契约（288×3、10 splits、固定标签空间、日×设备严格隔离）。
TSC_STRICT10_CONTRACT: dict[str, Any] = {
    "grid": "288x3",
    "channels": ["value", "i_cal", "measurement_mask"],
    "splits": 10,
    "isolation": "date_x_device_strict",
    "label_space": "fixed",
    "metric": "macro_f1",
    "known_validation_execution": "exec-validation-d741dc207593",
    "trusted_discrete_dates": 35,
    "note": "production_contract_valid 仅表示合同完整，不代表精度达标 / 可治理；validation execution 恒非可治理。",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# 7.1 canonical 打标入口 / shortcut 区分
# ---------------------------------------------------------------------------

def canonical_labeling_entry(scope: ScopeContext) -> dict[str, Any]:
    """返回当前槽的 canonical 打标入口（工作流 ID + 画布链路 + fail-closed 说明）。"""
    slot = scope.require_slot()
    workflow_id = CANONICAL_LABEL_WORKFLOW_BY_SLOT.get(slot)
    return {
        **scope.echo(),
        "canonical_workflow_id": workflow_id,
        "lineage": list(TSC_CANONICAL_LINEAGE) if slot == "pv_tsc" else [],
        "launch_hint": "直接在数据页对 needs_labels 版本发起 canonical 打标工作流，不经日/点标注 tab。",
        "fail_closed": "canonical 打标失败不产出任何提案（proposal fail-closed）。",
        "ui_acceptance_pending": True,  # 真实浏览器 E2E 通过前，UI 标注“TSC canonical 打标 UI 待验收”
    }


def shortcut_distinction(scope: ScopeContext) -> dict[str, Any]:
    """解释 shortcut（KMeans REST）与 canonical 的区别（只读，不改判定）。"""
    slot = scope.require_slot()
    return {
        **scope.echo(),
        "labeling_mode": "shortcut",
        "is_canonical": False,
        "preferred_labeling_workflow_id": CANONICAL_LABEL_WORKFLOW_BY_SLOT.get(slot),
        "explanation": (
            "历史 KMeans REST 聚类为 shortcut 快捷模式，不是 canonical TSC 模型辅助打标；"
            "preferred_labeling_workflow_id 仅为指向 canonical 工作流的元数据。"
        ),
    }


# ---------------------------------------------------------------------------
# 7.2 strict-10 / 累计 / 指标证据适配器
# ---------------------------------------------------------------------------

def register_strict10_evidence(
    scope: ScopeContext,
    *,
    source_execution_id: str,
    macro_f1: Optional[float] = None,
    production_contract_valid: bool = False,
    qualified_device_days: Optional[int] = None,
    rejected_device_days: Optional[int] = None,
    class_distribution: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    """登记一条 strict-10 证据（scoped）。绝不放宽 split 隔离 / repeat 次数；validation 恒非可治理。

    `macro_f1` 缺失时诚实置空（不臆造）；`production_contract_valid` 仅表示合同完整。
    """
    scope.assert_writable()
    exec_rec = _executions.find(scope, source_execution_id) if source_execution_id else None
    # validation execution 恒非可治理（红线）。
    governance_eligible = False
    evidence = {
        "result_id": f"tsc-strict10-{uuid.uuid4().hex[:12]}",
        "kind": "tsc_strict10_evidence",
        "slot": scope.require_slot(),
        "source_execution_id": source_execution_id,
        "contract": dict(TSC_STRICT10_CONTRACT),
        "macro_f1": macro_f1,  # 可空
        "macro_f1_display": "未产出" if macro_f1 is None else round(float(macro_f1), 6),
        "production_contract_valid": bool(production_contract_valid),
        "production_contract_note": "合同完整，不等于精度达标 / 可治理。",
        "qualified_device_days": qualified_device_days,
        "rejected_device_days": rejected_device_days,
        "class_distribution": class_distribution or {},
        "governance_eligible": governance_eligible,
        "source_execution_governance_eligible": bool(exec_rec.get("governance_eligible")) if exec_rec else False,
        "registered_at": _now_iso(),
    }
    return _results.append(scope, evidence)


def list_strict10_evidence(scope: ScopeContext) -> list[dict[str, Any]]:
    return [r for r in _results.list(scope) if r.get("kind") == "tsc_strict10_evidence"]


def strict10_evidence_view(scope: ScopeContext) -> dict[str, Any]:
    """strict-10 证据视图（含契约 + 非可治理声明）。"""
    items = list_strict10_evidence(scope)
    return {
        **scope.echo(),
        "contract": dict(TSC_STRICT10_CONTRACT),
        "evidence": items,
        "all_validation_non_governable": all(e.get("governance_eligible") is False for e in items),
    }


# ---------------------------------------------------------------------------
# 7.3 只读生产观测
# ---------------------------------------------------------------------------

def tsc_production_status(scope: ScopeContext) -> dict[str, Any]:
    """只读 TSC 生产状态：device-day / 多窗 / 调度回执证据；缺回执即“未产出”，失败日不推进游标。

    只读展示：不从其他项目 / 槽 / 设备 / 日期 / legacy 借证据（scoped，不 fallback）。
    """
    receipts = [r for r in _results.list(scope) if r.get("kind") == "tsc_production_receipt"]
    latest = receipts[-1] if receipts else None
    has_receipt = latest is not None
    return {
        **scope.echo(),
        "read_only": True,
        "has_current_receipt": has_receipt,
        "status_display": "未产出" if not has_receipt else latest.get("status", "unknown"),
        "device_day_evidence": (latest or {}).get("device_day_evidence"),
        "multi_window_evidence": (latest or {}).get("multi_window_evidence"),
        "scheduler_receipt": (latest or {}).get("scheduler_receipt"),
        "cursor_advances_on_failed_day": False,  # 失败日不推进游标（红线）
        "manual_advance_allowed": False,
        "note": "TSC 生产观测只读；失败日不推进游标；手工推进 / 补检 / 水位 / 游标 / 审核 / 精度写入一律拒绝。",
    }


def assert_no_manual_production_write(scope: ScopeContext, action: str) -> None:
    """拒绝一切 TSC 生产观测写入（手工推进 / 补检 / 水位 / 游标 / 审核 / 精度）。"""
    raise GovernanceGateError(
        "tsc_production_observability_read_only",
        f"TSC 生产观测只读，动作 {action!r} 不允许写入（水位 / 游标 / 审核 / 精度均只读）。",
        category="read_only",
        next_action="仅查看只读证据；生产推进由调度按回执驱动，不接受手工写入",
    )


# ---------------------------------------------------------------------------
# 7.4 TSC 候选 / 复验门禁（复用 governance，附 TSC 语义）
# ---------------------------------------------------------------------------

def assert_tsc_candidate_governable(scope: ScopeContext, candidate: dict[str, Any]) -> None:
    """TSC 候选门禁：validation execution / 缺 provenance / 离线 / 产品证据 ID 一律拒绝进入正式治理。

    复用 governance 的 provenance 与可治理判定；不合成缺失字段、不强推历史候选过复验。
    """
    from services.pv_projects import governance as gov

    if candidate.get("governance_eligible") is False:
        raise GovernanceGateError(
            "tsc_candidate_not_governable",
            "TSC validation execution（含 strict-10）恒非可治理，不能进入正式治理。",
            category="business_gate_blocked",
            next_action="使用来自成功且可治理 production 训练 execution 的候选",
        )
    gaps = gov.candidate_provenance_gaps(candidate)
    if gaps:
        raise GovernanceGateError(
            "tsc_candidate_provenance_incomplete",
            f"历史 TSC 候选 provenance 不完整：{gaps}；保持可见且不可变，不合成来源字段。",
            category="business_gate_blocked",
            current_value=f"missing={gaps}",
            next_action="补齐真实来源后再复验，或保留为不可治理历史候选",
        )


# @AI_GENERATED: end
