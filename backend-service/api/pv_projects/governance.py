# @AI_GENERATED
"""项目化模型治理 API：只读 registry + 受门控的滚动指针 / Promote。

设计依据：`design.md` §16、§26.2；`requirements.md` R3.1–R3.9、R8.1–R8.9、R9.1–R9.10。

路由（对齐 §26.2 合同方向）：
- GET  /api/pv-projects/{project_id}/slots/{slot}/registry        只读当前模型登记
- GET  /api/pv-projects/{project_id}/slots/{slot}/governance-overview 四层治理视图（当前检测模型 / 待复验 / 实验结果 / 治理历史）
- GET  /api/pv-projects/{project_id}/slots/{slot}/candidates       只读候选列表
- GET  /api/pv-projects/{project_id}/slots/{slot}/verifications     只读正式复验记录
- GET  /api/pv-projects/{project_id}/slots/{slot}/promotions-log   只读 Promote 审计
- POST /api/pv-projects/{project_id}/slots/{slot}/candidates        登记候选（scoped 证据写入，非生产写入）
- POST /api/pv-projects/{project_id}/slots/{slot}/candidates/{model_candidate_id}/verifications  发起正式复验（scoped 证据写入，落 pending）
- PUT  /api/pv-projects/{project_id}/slots/{slot}/rolling-model     设下一轮检测模型（受门控 + 生产授权）
- POST /api/pv-projects/{project_id}/slots/{slot}/candidates/{model_candidate_id}/promote  Promote（受门控 + 生产授权）

写入分级：
- 候选登记 / 发起复验 → scoped 项目证据（`model_candidates.json` / `verifications.json`，与生产 registry 指针分离）；
  只走 `assert_writable()`（拒 legacy），**不**要求 production 授权。
- 滚动指针 / Promote → 触碰生产真源，额外要求 `assert_production_writes_authorized()`。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import (
    assert_production_writes_authorized,
    build_scope,
    gate_error_to_http,
)
from services.pv_projects import governance as gov

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-governance"])


class SetRollingModelRequest(BaseModel):
    # model_candidate_id 与 pydantic 保护命名空间 model_ 冲突，显式放开避免告警。
    model_config = {"protected_namespaces": ()}

    model_candidate_id: str = Field(..., description="要设为下一轮检测模型的候选 ID")
    verification_id: str = Field(..., description="同 scope 同候选、passed=true 的正式复验 ID")
    expected_registry_version: int = Field(..., description="调用方读取到的 registry 版本（乐观锁）")
    operator: str = Field(..., description="操作者")
    reason: str = Field(..., description="操作原因")


class PromoteRequest(BaseModel):
    verification_id: str = Field(..., description="已通过的正式复验证据 ID")
    expected_registry_version: int = Field(..., description="写入前读取的 registry 版本")
    operator: str = Field(..., description="操作者")
    reason: str = Field(..., description="操作原因")
    idempotency_key: str = Field(..., description="幂等键")
    set_as_production: bool = Field(default=False, description="是否同步写 Champion 生产登记")
    production_slot: Optional[str] = Field(default=None, description="生产目标槽位，默认候选自身 slot")


class RegisterCandidateRequest(BaseModel):
    """登记候选（scoped 证据写入）。

    **血缘与治理资格一律由服务端从来源 execution 派生**（P0-2）：
    `governance_eligible` 已从本请求模型移除——客户端无法再自授治理资格。
    下方 `source_*` / `evaluation_contract` 仅为调用方提示字段，与派生值冲突时被忽略，
    并记入候选的 `client_supplied_lineage_ignored` 供审计。
    """

    model_config = {"protected_namespaces": ()}

    source_execution_id: str = Field(..., description="候选来源 execution ID（必须状态为 success）")
    model_artifact_ref: str = Field(..., description="相对模型工件引用")
    source_workflow_id: Optional[str] = Field(
        default=None, description="仅提示；服务端以 execution 引用的工作流为准"
    )
    source_workflow_version: Optional[str] = Field(
        default=None, description="仅提示；服务端以工作流持久化版本为准"
    )
    source_dataset_version_id: Optional[str] = Field(
        default=None, description="仅提示；服务端以 execution 绑定版本为准"
    )
    source_snapshot_id: Optional[str] = Field(
        default=None, description="仅提示；服务端以工作流绑定的冻结快照为准"
    )
    evaluation_contract: Optional[Dict[str, Any]] = Field(
        default=None, description="仅提示；服务端以 execution 记录的评测合同为准"
    )
    model_ref: Optional[str] = Field(default=None, description="模型引用，缺省用工件引用")


class StartVerificationRequest(BaseModel):
    """对可治理候选发起正式复验（落 pending，不臆造通过）。"""

    evaluation_contract: Optional[Dict[str, Any]] = Field(default=None, description="评测合同，缺省用候选自身合同")
    aggregate_method: str = Field(default="mean", description="跨窗聚合方式（mean/median）")
    min_windows_challenger_better: int = Field(default=3, description="最少优胜窗数")
    score_margin: float = Field(default=0.0, description="分差门槛")


@router.get("/{project_id}/slots/{slot}/registry", summary="只读当前模型登记")
def get_registry(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    # 历史项目可能已挂累计快照但从未重新 mount；明确 GET 组合层做幂等补链。
    model_inheritance = gov.ensure_inherited_baseline_from_mounted(scope)
    registry = gov.read_registry(scope)
    return {
        **scope.echo(),
        "champion": registry.get("champion"),
        "challenger": registry.get("challenger"),
        "rolling_detect_model": registry.get("rolling_detect_model"),
        "inherited_baseline": registry.get("inherited_baseline"),
        "model_inheritance": model_inheritance,
        "registry_version": registry.get("registry_version", 0),
        "updated_at": registry.get("updated_at"),
        "note": registry.get("note"),
        "empty": registry.get("empty", False),
        "read_only": registry.get("read_only", scope.read_only),
    }


@router.get("/{project_id}/slots/{slot}/governance-overview", summary="四层治理视图")
def get_governance_overview(project_id: str, slot: str) -> Dict[str, Any]:
    # 四层：当前检测模型 / 待复验候选 / 实验结果（非可治理）/ 治理历史 + 复验记录。
    scope = build_scope(project_id, slot, require_slot=True)
    return gov.governance_overview(scope)


@router.get("/{project_id}/slots/{slot}/candidates", summary="只读候选列表")
def get_candidates(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    items = gov.list_candidates(scope)  # scoped list, no fallback
    return {**scope.echo(), "candidates": items}


@router.get("/{project_id}/slots/{slot}/verifications", summary="只读正式复验记录")
def get_verifications(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return {**scope.echo(), "verifications": gov.list_verifications(scope)}


@router.post("/{project_id}/slots/{slot}/candidates", summary="登记候选（scoped 证据写入）")
def post_register_candidate(project_id: str, slot: str, req: RegisterCandidateRequest) -> Dict[str, Any]:
    # scoped 证据写入：拒 legacy，但不触碰生产真源，故不要求 production 授权。
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        candidate = gov.register_candidate(
            scope,
            source_execution_id=req.source_execution_id,
            model_artifact_ref=req.model_artifact_ref,
            source_workflow_id=req.source_workflow_id,
            source_workflow_version=req.source_workflow_version,
            source_dataset_version_id=req.source_dataset_version_id,
            source_snapshot_id=req.source_snapshot_id,
            evaluation_contract=req.evaluation_contract,
            model_ref=req.model_ref,
        )
    except gov.GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "candidate": candidate}


@router.post(
    "/{project_id}/slots/{slot}/candidates/{model_candidate_id}/verifications",
    summary="发起正式复验（scoped 证据写入，落 pending）",
)
def post_start_verification(
    project_id: str, slot: str, model_candidate_id: str, req: StartVerificationRequest
) -> Dict[str, Any]:
    # scoped 证据写入：只创建 pending/passed=None，不臆造通过，不设指针 / Promote。
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        record = gov.start_verification(
            scope,
            model_candidate_id=model_candidate_id,
            evaluation_contract=req.evaluation_contract,
            aggregate_method=req.aggregate_method,
            min_windows_challenger_better=req.min_windows_challenger_better,
            score_margin=req.score_margin,
        )
    except gov.GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "verification": record}


class CompleteVerificationRequest(BaseModel):
    passed: bool = Field(..., description="考察是否通过；通过则把该候选升级为对应路径槽的挑战者")
    aggregate_method: Optional[str] = Field(default=None, description="聚合口径（可选，落库留痕）")
    score_margin: Optional[float] = Field(default=None, description="得分余量（可选，落库留痕）")
    failure_reason: Optional[str] = Field(default=None, description="未通过原因（passed=false 时）")


@router.post(
    "/{project_id}/slots/{slot}/verifications/{verification_id}/complete",
    summary="完成正式复验（通过则升级为挑战者）",
)
def post_complete_verification(
    project_id: str, slot: str, verification_id: str, req: CompleteVerificationRequest
) -> Dict[str, Any]:
    """考察收口：写复验终态；**通过时把候选升级为挑战者**，与生产（champion）竞争。

    不直接改写生产身份 —— 那仍走 Promote / 换将门禁（本环境未授权时 403）。
    """
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        record = gov.complete_verification(
            scope,
            verification_id=verification_id,
            passed=req.passed,
            aggregate_method=req.aggregate_method,
            score_margin=req.score_margin,
            failure_reason=req.failure_reason,
        )
    except gov.GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "verification": record}


@router.get("/{project_id}/slots/{slot}/promotions-log", summary="只读 Promote 审计日志")
def get_promotions_log(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return {**scope.echo(), "events": gov.list_promotions(scope)}


@router.put("/{project_id}/slots/{slot}/rolling-model", summary="设下一轮检测模型（受门控）")
def put_rolling_model(project_id: str, slot: str, req: SetRollingModelRequest) -> Dict[str, Any]:
    # 写入路径不允许 legacy；先校验 scope，再校验生产授权，最后走治理门控。
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    assert_production_writes_authorized(scope.echo())
    try:
        result = gov.set_rolling_detect_model(
            scope,
            model_candidate_id=req.model_candidate_id,
            verification_id=req.verification_id,
            expected_registry_version=req.expected_registry_version,
            operator=req.operator,
            reason=req.reason,
        )
    except gov.GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), **result}


@router.post("/{project_id}/slots/{slot}/candidates/{model_candidate_id}/promote", summary="Promote 候选（受门控）")
def post_promote(project_id: str, slot: str, model_candidate_id: str, req: PromoteRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    assert_production_writes_authorized(scope.echo())
    try:
        result = gov.promote(
            scope,
            model_candidate_id=model_candidate_id,
            verification_id=req.verification_id,
            expected_registry_version=req.expected_registry_version,
            operator=req.operator,
            reason=req.reason,
            idempotency_key=req.idempotency_key,
            set_as_production=req.set_as_production,
            production_slot=req.production_slot,
        )
    except gov.GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), **result}


# @AI_GENERATED: end
