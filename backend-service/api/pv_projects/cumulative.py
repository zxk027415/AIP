# @AI_GENERATED
"""项目化累计入账与冻结 API（design §19；任务 4.3）。

路由：
- GET  /api/pv-projects/{project_id}/slots/{slot}/cumulative              三层视图
- POST /api/pv-projects/{project_id}/slots/{slot}/cumulative/freeze-plan  冻结计划预览（不写）
- POST /api/pv-projects/{project_id}/slots/{slot}/cumulative/freeze       执行冻结（写 scoped 快照，幂等）
- POST /api/pv-projects/{project_id}/slots/{slot}/cumulative/training-results  登记训练结果索引（第三层）

冻结与训练结果登记只写 scoped 项目证据，不触碰生产 registry / 指针；不等于模型准入。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, gate_error_to_http
from services.pv_projects import cumulative as cum
from services.pv_projects.governance import GovernanceGateError

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-cumulative"])


class FreezePlanRequest(BaseModel):
    reviewed_at_cutoff: Optional[str] = Field(default=None, description="审核时间上界（ISO）；晚于该时刻的准入事件被排除")


class FreezeRequest(BaseModel):
    reviewed_at_cutoff: Optional[str] = Field(default=None, description="审核时间上界（ISO）")
    idempotency_key: str = Field(..., description="幂等键")
    operator: str = Field(..., description="操作者")


class RegisterTrainingResultRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    snapshot_id: str = Field(..., description="来源冻结快照 ID")
    source_execution_id: str = Field(..., description="训练 execution ID")
    model_artifact_ref: str = Field(..., description="相对模型工件引用")
    metrics: Optional[Dict[str, Any]] = Field(default=None, description="训练指标（仅索引）")


@router.get("/{project_id}/slots/{slot}/cumulative", summary="累计三层视图")
def get_cumulative(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return cum.cumulative_overview(scope)


@router.post("/{project_id}/slots/{slot}/cumulative/freeze-plan", summary="冻结计划预览（不写）")
def post_freeze_plan(project_id: str, slot: str, req: FreezePlanRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return cum.freeze_plan(scope, reviewed_at_cutoff=req.reviewed_at_cutoff)


@router.post("/{project_id}/slots/{slot}/cumulative/freeze", summary="执行冻结（写 scoped 快照，幂等）")
def post_freeze(project_id: str, slot: str, req: FreezeRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        result = cum.execute_freeze(
            scope,
            reviewed_at_cutoff=req.reviewed_at_cutoff,
            idempotency_key=req.idempotency_key,
            operator=req.operator,
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), **result}


@router.post("/{project_id}/slots/{slot}/cumulative/training-results", summary="登记训练结果索引（第三层）")
def post_training_result(project_id: str, slot: str, req: RegisterTrainingResultRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        result = cum.register_training_result(
            scope,
            snapshot_id=req.snapshot_id,
            source_execution_id=req.source_execution_id,
            model_artifact_ref=req.model_artifact_ref,
            metrics=req.metrics,
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "training_result": result}


# @AI_GENERATED: end
