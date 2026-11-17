# @AI_GENERATED
"""项目化统一审核 API（design §17、§18；任务 4.2）。

路由：
- GET  /api/pv-projects/{project_id}/slots/{slot}/reviews                  审核队列
- GET  /api/pv-projects/{project_id}/slots/{slot}/reviews/{review_id}      审核详情
- GET  /api/pv-projects/{project_id}/slots/{slot}/reviews/{review_id}/accuracy  精度表面（可空）
- POST /api/pv-projects/{project_id}/slots/{slot}/reviews                  登记审核会话（scoped 证据）
- POST .../reviews/{review_id}/verdict          动作①：保存裁定（CAS）
- POST .../reviews/{review_id}/complete         动作②：完成审核（CAS）
- POST .../reviews/{review_id}/complete-and-admit  动作③：完成并准入（CAS + 幂等）

三个动作分离：裁定 ≠ 完成 ≠ 准入。准入写 scoped 累计台账（非生产写入）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, gate_error_to_http
from services.pv_projects import review_service as rv
from services.pv_projects.governance import GovernanceGateError

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-reviews"])


class ReviewItemInput(BaseModel):
    item_id: Optional[str] = Field(default=None, description="条目 ID")
    unit_ref: Optional[str] = Field(default=None, description="审核单元引用（device=..;date=..;label=..）")
    proposed_label: Optional[str] = Field(default=None, description="模型建议标签")
    evidence: Optional[Dict[str, Any]] = Field(default=None, description="路径特定证据")


class CreateReviewRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    source_kind: str = Field(..., description="来源：label_proposal / detection_batch / model_assisted_label")
    unit_granularity: str = Field(..., description="审核单元粒度")
    items: List[ReviewItemInput] = Field(default_factory=list, description="待审核条目")
    dataset_version_id: Optional[str] = Field(default=None, description="来源不可变数据版本 ID")
    model_ref: Optional[str] = Field(default=None, description="模型引用")
    source_execution_id: Optional[str] = Field(default=None, description="来源 execution ID")


class ItemVerdictInput(BaseModel):
    item_id: str = Field(..., description="条目 ID")
    verdict: Optional[str] = Field(default=None, description="accept / reject / uncertain（空表示撤销裁定）")
    verdict_label: Optional[str] = Field(default=None, description="人工确认的标签")


class SaveVerdictRequest(BaseModel):
    expected_review_version: int = Field(..., description="调用方读取到的审核版本（乐观锁）")
    item_verdicts: List[ItemVerdictInput] = Field(default_factory=list, description="逐条裁定")


class CompleteReviewRequest(BaseModel):
    expected_review_version: int = Field(..., description="审核版本（乐观锁）")


class CompleteAndAdmitRequest(BaseModel):
    expected_review_version: int = Field(..., description="审核版本（乐观锁）")
    idempotency_key: str = Field(..., description="幂等键")
    operator: str = Field(..., description="操作者")


@router.get("/{project_id}/slots/{slot}/reviews", summary="审核队列")
def get_reviews(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return rv.queue_view(scope)


@router.get("/{project_id}/slots/{slot}/reviews/{review_id}", summary="审核详情")
def get_review(project_id: str, slot: str, review_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    try:
        review = rv.get_review(scope, review_id)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "review": review}


@router.get("/{project_id}/slots/{slot}/reviews/{review_id}/accuracy", summary="精度表面（可空，未产出而非 0%）")
def get_review_accuracy(project_id: str, slot: str, review_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    try:
        return rv.review_accuracy(scope, review_id)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


@router.post("/{project_id}/slots/{slot}/reviews", summary="登记审核会话（scoped 证据）")
def post_create_review(project_id: str, slot: str, req: CreateReviewRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        review = rv.create_review(
            scope,
            source_kind=req.source_kind,
            unit_granularity=req.unit_granularity,
            items=[it.model_dump() for it in req.items],
            dataset_version_id=req.dataset_version_id,
            model_ref=req.model_ref,
            source_execution_id=req.source_execution_id,
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "review": review}


@router.post("/{project_id}/slots/{slot}/reviews/{review_id}/verdict", summary="动作①：保存裁定（CAS）")
def post_verdict(project_id: str, slot: str, review_id: str, req: SaveVerdictRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        result = rv.save_verdict(
            scope,
            review_id,
            expected_review_version=req.expected_review_version,
            item_verdicts=[v.model_dump() for v in req.item_verdicts],
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), **result}


@router.post("/{project_id}/slots/{slot}/reviews/{review_id}/complete", summary="动作②：完成审核（CAS）")
def post_complete(project_id: str, slot: str, review_id: str, req: CompleteReviewRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        result = rv.complete_review(scope, review_id, expected_review_version=req.expected_review_version)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), **result}


@router.post("/{project_id}/slots/{slot}/reviews/{review_id}/complete-and-admit", summary="动作③：完成并准入（CAS + 幂等）")
def post_complete_and_admit(project_id: str, slot: str, review_id: str, req: CompleteAndAdmitRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        result = rv.complete_and_admit(
            scope,
            review_id,
            expected_review_version=req.expected_review_version,
            idempotency_key=req.idempotency_key,
            operator=req.operator,
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), **result}


# @AI_GENERATED: end
