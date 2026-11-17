# @AI_GENERATED
"""项目化模型治理门控（scoped registry / rolling pointer / promote）。

设计依据：`design.md` §16（四层治理、直白动作、registry 单独真源）、§24.2（禁用原因分类）；
`requirements.md` R3.1–R3.9、R7.8–R7.12、R8.1–R8.9、R9.1–R9.10、R15.11、R15.12。

红线：
- 只有 provenance 完整、可治理的候选 + 同 scope 同候选 `passed=true` 的正式复验 +
  registry 版本匹配，才能设置滚动指针或 Promote。
- Promote 写入的是候选**自身**的 `source_workflow_id` 与 `model_artifact_ref`，
  绝不写 baseline 模板或跨 scope 工件。
- 跨项目 / 跨槽请求、非正式证据 ID（如跨数据集产品复验 ID）、
  non-governable execution、缺失 provenance 一律在写 registry 或 append-only 审计前拒绝。
- 本模块只做门控与 scoped 存储写入；真实 production 写入仍需上层显式授权（任务 1.3 API 层）。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from services.pv_projects.scope import ScopeContext
from services.pv_projects.stores import (
    candidates as _candidates,
    get_scoped_registry_store,
    promotions_log as _promotions_log,
    verifications as _verifications,
)

#: 候选可进入正式治理所必需的 provenance 字段（R3.3）。
REQUIRED_CANDIDATE_PROVENANCE_FIELDS: tuple[str, ...] = (
    "project_id",
    "slot",
    "source_dataset_version_id",
    "source_workflow_id",
    "source_execution_id",
    "source_snapshot_id",
    "model_artifact_ref",
    "evaluation_contract",
)

#: 跨数据集产品复验批次 ID 前缀；这类 ID 不具治理效力，不能当 verification_id（R8.8）。
PRODUCT_VALIDATION_ID_PREFIXES: tuple[str, ...] = ("cdpv-", "xdpv-")


class GovernanceGateError(Exception):
    """治理门控失败。`category` 用于 API 层区分 5 类禁用原因（design §24.2）。"""

    #: permission_denied | business_gate_blocked | read_only | sandbox_only | scope_mismatch
    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: str = "business_gate_blocked",
        next_action: Optional[str] = None,
        current_value: Any = None,
        required_value: Any = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.category = category
        self.next_action = next_action
        self.current_value = current_value
        self.required_value = required_value
        self.retryable = bool(retryable)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reason_code": self.code,
            "message": self.message,
            "category": self.category,
            "retryable": self.retryable,
        }
        if self.next_action:
            payload["next_action"] = self.next_action
        if self.current_value is not None:
            payload["current_value"] = self.current_value
        if self.required_value is not None:
            payload["required_value"] = self.required_value
        return payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# 只读
# ---------------------------------------------------------------------------

def read_registry(scope: ScopeContext) -> dict[str, Any]:
    """只读当前模型登记（Champion / Challenger / rolling / inherited baseline）。"""
    return get_scoped_registry_store().get(scope)


def _inheritance_link_id(scope: ScopeContext, entry: dict[str, Any]) -> str:
    """按项目 / 路径 / 挂载内容生成稳定关联 ID。"""
    basis = "|".join(
        (
            scope.project_id,
            scope.require_slot(),
            str(entry.get("content_digest") or entry.get("dataset_ref") or ""),
        )
    )
    return "iml-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def ensure_inherited_baseline(
    scope: ScopeContext,
    *,
    entry: dict[str, Any],
    asset: dict[str, Any],
    link_basis: str = "mount_time",
) -> dict[str, Any]:
    """累计快照挂载后，幂等关联该路径已有模型为项目只读 baseline。

    输入：可信目录条目 ``entry`` 与已落盘的项目数据资产 ``asset``。
    输出：``status``（linked / no_model_available / artifact_missing / not_applicable / error）、
    ``idempotent_hit`` 与 ``inherited_baseline``。

    语义红线：只写 project registry 的 ``inherited_baseline``，不创建 project candidate，
    不写 champion / challenger / rolling，不调用领域桥，因此不能绕过复验或 Promote。
    模型二进制不复制，只持久化原工件的**相对引用**。
    """
    if scope.read_only or scope.is_legacy:
        return {"status": "read_only", "idempotent_hit": False, "inherited_baseline": None}

    slot = scope.require_slot()
    origin = str(entry.get("origin") or "")
    origin_slot = str(entry.get("origin_slot") or "")
    if origin != "path_cumulative_snapshot" or origin_slot != slot:
        return {"status": "not_applicable", "idempotent_hit": False, "inherited_baseline": None}

    link_id = _inheritance_link_id(scope, entry)
    registry_store = get_scoped_registry_store()
    existing = read_registry(scope).get("inherited_baseline")
    if isinstance(existing, dict) and str(existing.get("link_id") or "") == link_id:
        return {"status": "linked", "idempotent_hit": True, "inherited_baseline": existing}

    try:
        from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model

        resolved = resolve_slot_scheduler_model(slot)
    except Exception as exc:  # noqa: BLE001 — 数据挂载主链不能被模型关联阻断
        return {
            "status": "error",
            "idempotent_hit": False,
            "inherited_baseline": None,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    source_candidate_id = str(resolved.get("model_candidate_id") or "").strip() or None
    raw_artifact = str(resolved.get("model_artifact_ref") or "").strip()
    if not raw_artifact:
        return {
            "status": "no_model_available",
            "idempotent_hit": False,
            "inherited_baseline": None,
            "source_role": resolved.get("source"),
        }

    try:
        from services.pv_projects.paths import assert_relative_ref, resolve_for_io

        artifact_ref = assert_relative_ref(raw_artifact, field="model_artifact_ref")
        resolve_for_io(artifact_ref, must_exist=True, field="model_artifact_ref")
    except Exception as exc:  # noqa: BLE001 — 如实回显失效模型，不写悬空关联
        return {
            "status": "artifact_missing",
            "idempotent_hit": False,
            "inherited_baseline": None,
            "source_model_candidate_id": source_candidate_id,
            "model_artifact_ref": raw_artifact.replace("\\", "/"),
            "reason": f"{getattr(exc, 'code', None) or type(exc).__name__}: {exc}",
        }

    candidate = resolved.get("candidate") if isinstance(resolved.get("candidate"), dict) else {}
    producer = None
    if candidate:
        try:
            from services.slot_governance.project_attribution import resolve_candidate_project

            producer = resolve_candidate_project(candidate, slot=slot)
        except Exception:  # noqa: BLE001 — 生产者归属缺失不影响模型关联
            producer = None

    linked_at = _now_iso()
    source_lineage = {
        "source_kind": candidate.get("source_kind"),
        "source_workflow_id": candidate.get("source_workflow_id"),
        "source_workflow_version": candidate.get("source_workflow_version"),
        "source_execution_id": candidate.get("source_execution_id"),
        "source_snapshot_id": candidate.get("source_snapshot_id"),
        "source_retrain_request_id": candidate.get("source_retrain_request_id"),
        "source_project_candidate_id": candidate.get("source_project_candidate_id")
        or (candidate.get("model_ref") if str(candidate.get("model_ref") or "").startswith("cand-") else None),
        "evaluation_contract": candidate.get("evaluation_contract"),
        "registered_at": candidate.get("registered_at"),
    }
    pointer: dict[str, Any] = {
        "link_id": link_id,
        "association_kind": "inherited_from_slot",
        "slot": slot,
        "catalog_entry_id": entry.get("entry_id"),
        "dataset_id": asset.get("dataset_id"),
        "dataset_version_id": asset.get("dataset_version_id"),
        "mount_content_digest": entry.get("content_digest"),
        "source_slot": slot,
        "source_slot_registry_version": resolved.get("registry_version"),
        "source_role": resolved.get("source"),
        "source_model_candidate_id": source_candidate_id,
        "source_model_id": resolved.get("model_id"),
        "model_ref": candidate.get("model_ref") or source_candidate_id or artifact_ref,
        "model_artifact_ref": artifact_ref,
        "producer_project_id": (producer or {}).get("project_id"),
        "producer_project_name": (producer or {}).get("project_name"),
        "source_lineage": source_lineage,
        "governance_effect": "none",
        "governance_eligible": False,
        "promotable": False,
        "binary_copied": False,
        "link_basis": str(link_basis or "mount_time"),
        "linked_at": linked_at,
    }
    if str(link_basis).startswith("lazy_backfill"):
        pointer["backfilled_at"] = linked_at

    outcome: dict[str, Any] = {"idempotent_hit": False}

    def _merge(current: dict[str, Any]) -> Optional[dict[str, Any]]:
        previous = current.get("inherited_baseline")
        if isinstance(previous, dict) and str(previous.get("link_id") or "") == link_id:
            outcome["idempotent_hit"] = True
            return None
        next_pointer = dict(pointer)
        if isinstance(previous, dict) and previous.get("link_id"):
            next_pointer["supersedes_link_id"] = previous.get("link_id")
        current["inherited_baseline"] = next_pointer
        current["registry_version"] = int(current.get("registry_version") or 0) + 1
        current["inheritance_note"] = "累计训练快照继承 baseline；仅供展示 / 对照，不具治理效力。"
        return current

    try:
        saved = registry_store.update(scope, _merge)
    except Exception as exc:  # noqa: BLE001 — 数据挂载成功优先，模型关联错误单独返回
        return {
            "status": "error",
            "idempotent_hit": False,
            "inherited_baseline": None,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    inherited = saved.get("inherited_baseline")
    return {
        "status": "linked",
        "idempotent_hit": bool(outcome.get("idempotent_hit")),
        "inherited_baseline": inherited if isinstance(inherited, dict) else pointer,
    }


def ensure_inherited_baseline_from_mounted(
    scope: ScopeContext,
    *,
    link_basis: str = "lazy_backfill_current_slot_model",
) -> dict[str, Any]:
    """为历史项目按已挂载累计快照补继承关联；仅在明确 overview GET 组合层调用。"""
    if scope.read_only or scope.is_legacy:
        return {"status": "read_only", "idempotent_hit": False, "inherited_baseline": None}
    slot = scope.require_slot()
    try:
        from services.pv_projects import catalog as catalog_service
        from services.pv_projects import datasets as dataset_service

        catalog_by_id = {
            str(entry.get("entry_id") or ""): entry
            for entry in catalog_service.list_catalog()
            if isinstance(entry, dict)
        }
        catalog_by_ref = {
            str(entry.get("dataset_ref") or ""): entry
            for entry in catalog_by_id.values()
            if entry.get("dataset_ref")
        }
        assets = list(reversed(dataset_service.list_dataset_assets(scope)))
        for asset in assets:
            if str(asset.get("source_kind") or "") != "catalog":
                continue
            entry = catalog_by_id.get(str(asset.get("catalog_entry_id") or "")) or catalog_by_ref.get(
                str(asset.get("dataset_ref") or "")
            )
            if not entry:
                continue
            if (
                str(entry.get("origin") or "") == "path_cumulative_snapshot"
                and str(entry.get("origin_slot") or "") == slot
            ):
                return ensure_inherited_baseline(
                    scope,
                    entry=entry,
                    asset=asset,
                    link_basis=link_basis,
                )
    except Exception as exc:  # noqa: BLE001 — 只读组合视图不能因补链失败整体 500
        return {
            "status": "error",
            "idempotent_hit": False,
            "inherited_baseline": None,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {"status": "not_applicable", "idempotent_hit": False, "inherited_baseline": None}


def find_candidate(scope: ScopeContext, model_candidate_id: str) -> Optional[dict[str, Any]]:
    """在当前 scope 内按 ID 查找候选（不跨项目 / 不跨槽）。"""
    return _candidates.find(scope, model_candidate_id)


def candidate_provenance_gaps(candidate: dict[str, Any]) -> list[str]:
    """返回候选缺失的 provenance 字段名（空表示完整）。"""
    gaps: list[str] = []
    for field in REQUIRED_CANDIDATE_PROVENANCE_FIELDS:
        value = candidate.get(field)
        if value in (None, "", [], {}):
            gaps.append(field)
    return gaps


# ---------------------------------------------------------------------------
# 门控
# ---------------------------------------------------------------------------

def _assert_not_product_validation_id(verification_id: str) -> None:
    vid = str(verification_id or "").strip()
    if any(vid.startswith(prefix) for prefix in PRODUCT_VALIDATION_ID_PREFIXES):
        raise GovernanceGateError(
            "product_validation_no_governance_effect",
            "跨数据集产品复验只证明迁移 / 交互 / 隔离，不具模型治理效力，不能作为正式复验证据。",
            category="business_gate_blocked",
            next_action="改用同 scope 同候选、passed=true 的正式候选复验 verification_id",
        )


def _assert_candidate_governable(scope: ScopeContext, candidate: dict[str, Any]) -> None:
    """候选必须 provenance 完整且未被标记为不可治理（validation execution）。"""
    if candidate.get("governance_eligible") is False:
        raise GovernanceGateError(
            "candidate_not_governable",
            "该候选来自 validation / 非可治理 execution（governance_eligible=false），不能进入正式治理。",
            category="business_gate_blocked",
            next_action="使用来自成功且可治理 production execution 的候选",
        )
    gaps = candidate_provenance_gaps(candidate)
    if gaps:
        raise GovernanceGateError(
            "candidate_provenance_incomplete",
            f"候选缺少 provenance 字段：{gaps}；不能正式复验、设滚动指针或 Promote。",
            category="business_gate_blocked",
            current_value=f"missing={gaps}",
            required_value="完整 provenance",
            next_action="补齐候选来源（数据版本 / 工作流 / execution / snapshot / 工件 / 评测合同）",
        )


def assert_formal_verification(
    scope: ScopeContext,
    model_candidate_id: str,
    verification_id: str,
) -> dict[str, Any]:
    """校验同 scope、同候选、passed=true 的正式复验存在，返回该记录。"""
    _assert_not_product_validation_id(verification_id)
    record = _verifications.find(scope, verification_id)
    if record is None:
        raise GovernanceGateError(
            "verification_not_found",
            f"当前项目 / 路径下找不到正式复验 verification_id={verification_id!r}。",
            category="business_gate_blocked",
            next_action="先在当前项目对该候选发起正式复验并等待通过",
        )
    if str(record.get("model_candidate_id") or "") != str(model_candidate_id):
        raise GovernanceGateError(
            "verification_candidate_mismatch",
            "verification 绑定的候选与目标候选不一致。",
            category="business_gate_blocked",
        )
    if record.get("passed") is not True:
        raise GovernanceGateError(
            "verification_not_passed",
            "该正式复验尚未通过（passed != true），不能设滚动指针或 Promote。",
            category="business_gate_blocked",
            next_action="等待正式复验通过后再操作",
        )
    return record


def _assert_registry_version(scope: ScopeContext, expected_registry_version: int) -> dict[str, Any]:
    registry = read_registry(scope)
    current = int(registry.get("registry_version") or 0)
    if current != int(expected_registry_version):
        raise GovernanceGateError(
            "registry_version_conflict",
            "registry 版本已变化，可能有人并发写入；请重新读取后再确认。",
            category="business_gate_blocked",
            current_value=current,
            required_value=int(expected_registry_version),
            next_action="重新读取当前 registry 版本后重试",
            retryable=True,
        )
    return registry


def _resolve_target_slot(scope: ScopeContext, candidate: dict[str, Any], production_slot: Optional[str]) -> str:
    cand_slot = str(candidate.get("slot") or "").strip()
    target = str(production_slot or "").strip() or scope.require_slot()
    if target != scope.require_slot():
        raise GovernanceGateError(
            "cross_slot_write_forbidden",
            f"目标槽位 {target!r} 与当前 scope 槽位 {scope.slot!r} 不一致，禁止跨槽写入。",
            category="scope_mismatch",
        )
    if cand_slot and cand_slot != target:
        raise GovernanceGateError(
            "candidate_slot_mismatch",
            f"候选自身槽位 {cand_slot!r} 与目标槽位 {target!r} 不一致。",
            category="scope_mismatch",
        )
    return target


# ---------------------------------------------------------------------------
# 写入：滚动指针 / Promote
# ---------------------------------------------------------------------------

def set_rolling_detect_model(
    scope: ScopeContext,
    *,
    model_candidate_id: str,
    verification_id: str,
    expected_registry_version: int,
    operator: str,
    reason: str,
) -> dict[str, Any]:
    """设置下一轮检测消费的模型指针（需通过全部门控）。"""
    scope.assert_writable()
    candidate = find_candidate(scope, model_candidate_id)
    if candidate is None:
        raise GovernanceGateError(
            "candidate_not_found",
            f"当前项目 / 路径下找不到候选 {model_candidate_id!r}。",
            category="business_gate_blocked",
        )
    _assert_candidate_governable(scope, candidate)
    assert_formal_verification(scope, model_candidate_id, verification_id)
    registry = dict(_assert_registry_version(scope, expected_registry_version))

    registry["rolling_detect_model"] = {
        "model_candidate_id": model_candidate_id,
        "model_artifact_ref": candidate.get("model_artifact_ref"),
        "source_workflow_id": candidate.get("source_workflow_id"),
        "verification_id": verification_id,
        "set_at": _now_iso(),
        "operator": operator,
        "reason": reason,
    }
    registry["registry_version"] = int(registry.get("registry_version") or 0) + 1
    registry["note"] = reason
    saved = get_scoped_registry_store().save(scope, registry)
    return {"registry": saved, "rolling_detect_model": saved.get("rolling_detect_model")}


def promote(
    scope: ScopeContext,
    *,
    model_candidate_id: str,
    verification_id: str,
    expected_registry_version: int,
    operator: str,
    reason: str,
    idempotency_key: str,
    set_as_production: bool = False,
    production_slot: Optional[str] = None,
) -> dict[str, Any]:
    """Promote 候选（可选同步写生产 Champion），需通过全部门控 + 幂等。"""
    scope.assert_writable()
    if not str(idempotency_key or "").strip():
        raise GovernanceGateError("missing_idempotency_key", "缺少 idempotency_key。", category="business_gate_blocked")
    if not str(operator or "").strip():
        raise GovernanceGateError("missing_operator", "缺少 operator。", category="business_gate_blocked")
    if not str(reason or "").strip():
        raise GovernanceGateError("missing_reason", "缺少 reason。", category="business_gate_blocked")

    # 幂等命中：返回已有事件与当前 registry。
    existing = _promotions_log.find_by_idempotency(scope, idempotency_key)
    if existing is not None:
        return {"promotion": existing, "registry": read_registry(scope), "idempotent_replay": True}

    candidate = find_candidate(scope, model_candidate_id)
    if candidate is None:
        raise GovernanceGateError(
            "candidate_not_found",
            f"当前项目 / 路径下找不到候选 {model_candidate_id!r}。",
            category="business_gate_blocked",
        )
    _assert_candidate_governable(scope, candidate)
    target_slot = _resolve_target_slot(scope, candidate, production_slot)
    verification = assert_formal_verification(scope, model_candidate_id, verification_id)
    registry = dict(_assert_registry_version(scope, expected_registry_version))

    current_version = int(registry.get("registry_version") or 0)
    next_version = current_version + 1
    adopted_ref = candidate.get("model_ref") or model_candidate_id
    champion_before = registry.get("champion") or {}
    previous_champion_ref = champion_before.get("champion_model_ref")

    if set_as_production:
        # 写入候选自身来源，绝不写 baseline / 跨 scope 工件（R9.5）。
        registry["champion"] = {
            "champion_model_ref": adopted_ref,
            "source_model_candidate_id": model_candidate_id,
            "source_workflow_id": candidate.get("source_workflow_id"),
            "source_workflow_version": candidate.get("source_workflow_version"),
            "source_execution_id": candidate.get("source_execution_id"),
            "model_artifact_ref": candidate.get("model_artifact_ref"),
            "verification_id": verification_id,
            "set_at": _now_iso(),
        }
        registry["challenger"] = None
        champion_changed = True
        resulting_champion_ref = adopted_ref
        new_champion_ref = adopted_ref
    else:
        registry["challenger"] = {
            "challenger_model_ref": adopted_ref,
            "challenger_model_candidate_id": model_candidate_id,
            "challenger_source_workflow_id": candidate.get("source_workflow_id"),
            "challenger_source_execution_id": candidate.get("source_execution_id"),
            "challenger_model_artifact_ref": candidate.get("model_artifact_ref"),
            "challenger_verification_id": verification_id,
            "set_at": _now_iso(),
        }
        champion_changed = False
        resulting_champion_ref = previous_champion_ref
        new_champion_ref = None

    registry["registry_version"] = next_version
    registry["note"] = reason
    saved_registry = get_scoped_registry_store().save(scope, registry)

    event = {
        "promotion_id": f"prom-{uuid.uuid4().hex[:12]}",
        "project_id": scope.project_id,
        "model_candidate_id": model_candidate_id,
        "verification_id": verification_id,
        "production_slot": target_slot,
        "set_as_production": bool(set_as_production),
        "operator": operator,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "adopted_model_ref": adopted_ref,
        "previous_champion_model_ref": previous_champion_ref,
        "new_champion_model_ref": new_champion_ref,
        "resulting_champion_model_ref": resulting_champion_ref,
        "champion_changed": champion_changed,
        "registry_version_before": current_version,
        "registry_version_after": next_version,
        "promoted_at": _now_iso(),
    }
    _promotions_log.append(scope, event)
    return {"promotion": event, "registry": saved_registry, "idempotent_replay": False}


def list_candidates(scope: ScopeContext) -> list[dict[str, Any]]:
    """只读列出当前 scope 的候选（不跨项目 / 不跨槽 / 不 fallback）。"""
    return _candidates.list(scope)


def list_promotions(scope: ScopeContext) -> list[dict[str, Any]]:
    return _promotions_log.list(scope)


def list_verifications(scope: ScopeContext) -> list[dict[str, Any]]:
    return _verifications.list(scope)


# ---------------------------------------------------------------------------
# 候选登记 / 正式复验（scoped 证据写入；非 production 指针写入）
# ---------------------------------------------------------------------------

def register_candidate(
    scope: ScopeContext,
    *,
    source_execution_id: str,
    model_artifact_ref: str,
    model_ref: Optional[str] = None,
    source_workflow_id: Optional[str] = None,
    source_workflow_version: Optional[str] = None,
    source_dataset_version_id: Optional[str] = None,
    source_snapshot_id: Optional[str] = None,
    evaluation_contract: Optional[dict[str, Any]] = None,
    governance_eligible: Optional[bool] = None,
) -> dict[str, Any]:
    """登记一条候选；**全部血缘与治理资格从来源 execution 派生**，不采信客户端传入（P0-2）。

    门禁（任一不满足即拒，理由码稳定可断言）：
    1. `source_execution_id` 必填，且执行必须在当前 scope 存在
       （`candidate_source_execution_not_found`）。
    2. 执行必须 `status == "success"`（失败 / 运行中 / 已取消不产候选，
       `candidate_source_execution_not_successful`）。
    3. 执行引用的项目工作流必须在当前 scope 存在（`candidate_source_workflow_not_found`）。
    4. 训练工作流必须绑定冻结快照；快照须在当前 scope 存在
       （`candidate_snapshot_not_found`）且类型与本路径匹配
       （`candidate_snapshot_type_mismatch`，禁止跨路径复用）。
    5. 绑定的数据版本（若有）必须在当前 scope 存在
       （`candidate_dataset_version_not_found`）。

    治理资格由执行侧派生：
    `exec.governance_eligible and status==success and workflow_kind==training
     and run_mode==training and run_domain!=sandbox`
    → validation / experiment / sandbox **恒为 false**，客户端无法覆盖。

    保留 `source_*` / `governance_eligible` 形参仅为**调用方兼容**：传入值一律被派生值覆盖，
    与派生值冲突的字段会记入 `client_supplied_lineage_ignored` 供审计。绝不臆造缺失字段。
    """
    scope.assert_writable()
    from services.pv_projects.stores import dataset_versions as _dataset_versions
    from services.pv_projects.stores import executions as _executions
    from services.pv_projects.stores import project_workflows as _project_workflows
    from services.pv_projects.stores import snapshots as _snapshots
    from services.pv_projects.workflows import EXPECTED_SNAPSHOT_TYPE_BY_SLOT

    if not str(source_execution_id or "").strip():
        raise GovernanceGateError(
            "candidate_source_execution_required",
            "登记候选必须提供 source_execution_id；候选血缘只能从成功执行派生。",
            category="business_gate_blocked",
            next_action="先在本路径跑一次成功的 training 执行，再用其 execution_id 登记候选",
        )

    exec_rec = _executions.find(scope, source_execution_id)
    if exec_rec is None:
        raise GovernanceGateError(
            "candidate_source_execution_not_found",
            f"当前项目 / 路径下找不到来源执行 {source_execution_id!r}；拒绝登记候选。",
            category="business_gate_blocked",
            next_action="确认 execution_id 属于当前项目 / 路径，或先完成一次执行",
        )
    exec_status = str(exec_rec.get("status") or "")
    if exec_status != "success":
        raise GovernanceGateError(
            "candidate_source_execution_not_successful",
            f"来源执行 {source_execution_id!r} 状态为 {exec_status!r}；只有成功的执行才能产出候选。",
            category="business_gate_blocked",
            current_value=exec_status,
            required_value="success",
            next_action="等待执行成功，或修复失败原因后重跑",
        )

    workflow_id = str(exec_rec.get("project_workflow_id") or "").strip()
    pwf = _project_workflows.find(scope, workflow_id) if workflow_id else None
    if pwf is None:
        raise GovernanceGateError(
            "candidate_source_workflow_not_found",
            f"来源执行引用的项目工作流 {workflow_id!r} 在当前 scope 不存在；拒绝登记候选。",
            category="business_gate_blocked",
        )
    kind = str(pwf.get("workflow_kind") or "training")
    slot = scope.require_slot()

    snapshot_id = str(pwf.get("bound_snapshot_id") or "").strip()
    expected_snapshot_type = EXPECTED_SNAPSHOT_TYPE_BY_SLOT.get(slot)
    if snapshot_id:
        snap = _snapshots.find(scope, snapshot_id)
        if snap is None:
            raise GovernanceGateError(
                "candidate_snapshot_not_found",
                f"工作流绑定的冻结快照 {snapshot_id!r} 在当前 scope 不存在。",
                category="business_gate_blocked",
            )
        actual_type = str(snap.get("snapshot_type") or "")
        if expected_snapshot_type and actual_type != expected_snapshot_type:
            raise GovernanceGateError(
                "candidate_snapshot_type_mismatch",
                f"快照类型 {actual_type!r} 与路径 {slot} 期望 {expected_snapshot_type!r} 不匹配；"
                "禁止跨路径复用快照作为训练输入。",
                category="business_gate_blocked",
                current_value=actual_type,
                required_value=expected_snapshot_type,
            )
    elif kind == "training":
        raise GovernanceGateError(
            "candidate_snapshot_missing",
            "训练工作流未绑定冻结快照，其产出不能成为可治理候选。",
            category="business_gate_blocked",
            required_value="source_snapshot_id",
            next_action="先在累计阶段冻结快照并绑定到该训练工作流",
        )

    dataset_version_id = str(
        exec_rec.get("dataset_version_id") or pwf.get("bound_dataset_version_id") or ""
    ).strip() or None
    if dataset_version_id and _dataset_versions.find(scope, dataset_version_id) is None:
        raise GovernanceGateError(
            "candidate_dataset_version_not_found",
            f"来源数据版本 {dataset_version_id!r} 在当前 scope 不存在。",
            category="business_gate_blocked",
        )

    derived_eligible = bool(
        exec_rec.get("governance_eligible")
        and exec_status == "success"
        and kind == "training"
        and str(exec_rec.get("run_mode") or "") == "training"
        and str(exec_rec.get("run_domain") or "") != "sandbox"
    )

    candidate = {
        "model_candidate_id": f"cand-{uuid.uuid4().hex[:12]}",
        "project_id": scope.project_id,
        "slot": slot,
        "source_execution_id": source_execution_id,
        "source_workflow_id": workflow_id,
        "source_workflow_version": pwf.get("version"),
        "source_dataset_version_id": dataset_version_id,
        "source_snapshot_id": snapshot_id or None,
        "model_artifact_ref": model_artifact_ref,
        "model_ref": model_ref or model_artifact_ref,
        "evaluation_contract": exec_rec.get("evaluation_contract") or {},
        "governance_eligible": derived_eligible,
        "registered_at": _now_iso(),
    }

    # 审计：记录被忽略的客户端血缘（不静默吞掉调用方意图）。
    ignored: list[str] = []
    supplied: dict[str, Any] = {
        "source_workflow_id": source_workflow_id,
        "source_workflow_version": source_workflow_version,
        "source_dataset_version_id": source_dataset_version_id,
        "source_snapshot_id": source_snapshot_id,
        "evaluation_contract": evaluation_contract,
        "governance_eligible": governance_eligible,
    }
    for field, value in supplied.items():
        if value is None:
            continue
        if candidate.get(field) != value:
            ignored.append(field)
    if ignored:
        candidate["client_supplied_lineage_ignored"] = ignored

    candidate["provenance_gaps"] = candidate_provenance_gaps(candidate)
    stored = _candidates.append(scope, candidate)
    # 领域桥：把候选派发到**领域侧对应诊断路径 slot** 的模型登记（本领域 = pv_fault 的三路径
    # slot 下的 registry）。壳不依赖领域：无桥时 no-op；同步失败不阻断候选登记。
    from services.pv_projects.domain_bridge import sync_candidate_to_domain

    sync_result = sync_candidate_to_domain(project_id=scope.project_id, slot=slot, candidate=stored)
    # 同步结果**落盘**（而不只是回显）：否则持久化记录里没有 domain_sync，事后无从审计。
    return _candidates.replace(
        scope, str(stored.get("model_candidate_id")), {**stored, "domain_sync": sync_result}
    )


def start_verification(
    scope: ScopeContext,
    *,
    model_candidate_id: str,
    evaluation_contract: Optional[dict[str, Any]] = None,
    aggregate_method: str = "mean",
    min_windows_challenger_better: int = 3,
    score_margin: float = 0.0,
) -> dict[str, Any]:
    """对一个可治理候选发起正式复验，落 `pending` 记录（不臆造通过）。

    真实多窗复验引擎（AutoResearch compare）不在本环境执行；记录 `comparison_id` 供轮询，
    `passed=None`（未决），四层页据此显示"复验进行中 / 待接入引擎"，不能据此 Promote。
    """
    scope.assert_writable()
    candidate = find_candidate(scope, model_candidate_id)
    if candidate is None:
        raise GovernanceGateError(
            "candidate_not_found",
            f"当前项目 / 路径下找不到候选 {model_candidate_id!r}。",
            category="business_gate_blocked",
        )
    _assert_candidate_governable(scope, candidate)
    record = {
        "verification_id": f"ver-{uuid.uuid4().hex[:12]}",
        "model_candidate_id": model_candidate_id,
        "project_id": scope.project_id,
        "slot": scope.require_slot(),
        "comparison_id": f"cmp-{uuid.uuid4().hex[:12]}",
        "status": "pending",
        "passed": None,
        "aggregate_method": aggregate_method,
        "min_windows_challenger_better": int(min_windows_challenger_better),
        "score_margin": float(score_margin),
        "evaluation_contract": evaluation_contract or candidate.get("evaluation_contract") or {},
        "started_at": _now_iso(),
        "engine_note": "真实多窗复验引擎未在本环境执行；记录为未决，不能据此设指针 / Promote。",
    }
    return _verifications.append(scope, record)


def complete_verification(
    scope: ScopeContext,
    *,
    verification_id: str,
    passed: bool,
    aggregate_method: Optional[str] = None,
    score_margin: Optional[float] = None,
    failure_reason: Optional[str] = None,
) -> dict[str, Any]:
    """完成正式复验：写终态；**passed=True 时把候选升级为对应路径槽的挑战者**。

    这是「一套逻辑」的收口：模型在项目里被考察通过 → 升级为 challenger → 与在岗的 champion 竞争。
    `passed=False` 只落终态，不动任何身份。重复完成返回既有记录（幂等）。
    升级失败不阻断复验落库，结果如实回显在 `domain_sync`。
    """
    scope.assert_writable()
    rec = _verifications.find(scope, verification_id)
    if rec is None:
        raise GovernanceGateError(
            "verification_not_found",
            f"当前项目 / 路径下找不到复验记录 {verification_id!r}。",
            category="business_gate_blocked",
        )
    if str(rec.get("status")) in ("passed", "failed"):
        return rec  # 幂等：已完成不再改写

    updated: dict[str, Any] = {
        **rec,
        "status": "passed" if passed else "failed",
        "passed": bool(passed),
        "completed_at": _now_iso(),
        "engine_note": "复验由调用方判定完成（本环境无自动 compare 引擎）；结果如实落库，不臆造指标。",
    }
    if aggregate_method is not None:
        updated["aggregate_method"] = aggregate_method
    if score_margin is not None:
        updated["score_margin"] = float(score_margin)
    if failure_reason:
        updated["failure_reason"] = str(failure_reason)
    stored = _verifications.replace(scope, verification_id, updated)

    if not passed:
        return stored

    # 考察通过 → 升级挑战者（领域桥）。失败不阻断复验落库。
    candidate = find_candidate(scope, str(rec.get("model_candidate_id") or "")) or {}
    from services.pv_projects.domain_bridge import sync_verification_passed_to_domain

    sync = sync_verification_passed_to_domain(
        project_id=scope.project_id,
        slot=scope.require_slot(),
        candidate=candidate,
        verification=stored,
    )
    return _verifications.replace(scope, verification_id, {**stored, "domain_sync": sync})


def governance_overview(scope: ScopeContext) -> dict[str, Any]:
    """四层治理视图 + 随累计快照继承的只读 baseline。"""
    model_inheritance = ensure_inherited_baseline_from_mounted(scope)
    registry = read_registry(scope)
    all_candidates = list_candidates(scope)
    # 待复验候选：可治理（governance_eligible=true）
    pending = [c for c in all_candidates if c.get("governance_eligible") is True]
    # 实验结果：非可治理（governance_eligible=false）
    experiment_results = [c for c in all_candidates if c.get("governance_eligible") is not True]
    inherited = registry.get("inherited_baseline") if isinstance(registry.get("inherited_baseline"), dict) else None
    association_kinds: list[str] = []
    if pending or experiment_results or any(
        registry.get(key) for key in ("rolling_detect_model", "champion", "challenger")
    ):
        association_kinds.append("trained_in_project")
    if inherited:
        association_kinds.append("inherited_from_slot")
    primary_kind = (
        "trained_in_project"
        if "trained_in_project" in association_kinds
        else ("inherited_from_slot" if inherited else None)
    )
    return {
        **scope.echo(),
        "current_detection_model": {
            "rolling_detect_model": registry.get("rolling_detect_model"),
            "champion": registry.get("champion"),
            "challenger": registry.get("challenger"),
            "inherited_baseline": inherited,
            "registry_version": registry.get("registry_version", 0),
            "read_only": registry.get("read_only", scope.read_only),
            "empty": registry.get("empty", False),
        },
        "model_inventory": {
            "trained_in_project_count": len(all_candidates),
            "inherited_from_slot_count": 1 if inherited else 0,
            "association_kinds": association_kinds,
            "primary_association_kind": primary_kind,
        },
        "model_inheritance": model_inheritance,
        "pending_candidates": pending,
        "experiment_results": experiment_results,
        "verifications": list_verifications(scope),
        "governance_history": list_promotions(scope),
    }


# @AI_GENERATED: end
