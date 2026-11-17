# @AI_GENERATED
"""pv_point 逐点回放会话 API（design D-PATH-01 / D-STATE-01；任务 6.1 / 6.2 / 6.3）。

路由：
- POST /api/pv-projects/{project_id}/slots/{slot}/point/sandboxes                创建 Sandbox 回放会话
- GET  /api/pv-projects/{project_id}/slots/{slot}/point/sandboxes/{sandbox_id}    读会话（刷新恢复）
- POST .../sandboxes/{sandbox_id}/predict-next   预测下一点（不推进 cursor）
- POST .../sandboxes/{sandbox_id}/commit         提交 outcome（推进 cursor）
- POST .../sandboxes/{sandbox_id}/step           单步（predict + commit）
- POST .../sandboxes/{sandbox_id}/advance        推进 N 点（step_size：1/10/50）
- POST .../sandboxes/{sandbox_id}/reset          Sandbox 局部 reset（不影响其他 Sandbox / production）
- GET  .../sandboxes/{sandbox_id}/metrics        点级指标（device-day 标签不进入真值）

红线：逐点严格因果；cursor 只在 outcome 提交后推进；reset 仅本 Sandbox；
loop_demo 为演示喂点，不写累计台账；production 不受影响。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, gate_error_to_http
from services.pv_projects.governance import GovernanceGateError
from services.pv_projects.sandbox_runtime import SandboxRuntime

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-point"])


class CreateSandboxRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    sandbox_id: str = Field(..., description="Sandbox 实例 ID")
    points: List[Dict[str, Any]] = Field(default_factory=list, description="源点（含 event_time / value）")
    model_ref: Optional[str] = Field(default=None, description="模型引用（演示可空）")
    session_source: str = Field(default="real_replay", description="real_replay / loop_demo（演示喂点，不写台账）")
    dataset_version_id: Optional[str] = Field(default=None, description="来源不可变数据版本 ID")


class AdvanceRequest(BaseModel):
    step_size: int = Field(default=1, description="推进点数（1 / 10 / 50）")


class CommitRequest(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, description="幂等键（避免重复提交推进）")


def _scope(project_id: str, slot: str, *, write: bool = False):
    return build_scope(project_id, slot, require_slot=True, allow_legacy=not write)


@router.post("/{project_id}/slots/{slot}/point/sandboxes", summary="创建 Sandbox 回放会话")
def post_create_sandbox(project_id: str, slot: str, req: CreateSandboxRequest) -> Dict[str, Any]:
    scope = _scope(project_id, slot, write=True)
    try:
        rec = SandboxRuntime.create(
            scope,
            sandbox_id=req.sandbox_id,
            points=req.points,
            model_ref=req.model_ref,
            session_source=req.session_source,
            dataset_version_id=req.dataset_version_id,
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "sandbox": rec}


@router.get("/{project_id}/slots/{slot}/point/sandboxes/{sandbox_id}", summary="读会话（刷新恢复）")
def get_sandbox(project_id: str, slot: str, sandbox_id: str) -> Dict[str, Any]:
    scope = _scope(project_id, slot)
    try:
        rec = SandboxRuntime.get(scope, sandbox_id)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "sandbox": rec}


@router.post("/{project_id}/slots/{slot}/point/sandboxes/{sandbox_id}/predict-next", summary="预测下一点（不推进 cursor）")
def post_predict_next(project_id: str, slot: str, sandbox_id: str) -> Dict[str, Any]:
    scope = _scope(project_id, slot, write=True)
    try:
        return {**scope.echo(), **SandboxRuntime.predict_next(scope, sandbox_id)}
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


@router.post("/{project_id}/slots/{slot}/point/sandboxes/{sandbox_id}/commit", summary="提交 outcome（推进 cursor）")
def post_commit(project_id: str, slot: str, sandbox_id: str, req: CommitRequest) -> Dict[str, Any]:
    scope = _scope(project_id, slot, write=True)
    try:
        return {**scope.echo(), **SandboxRuntime.commit_outcome(scope, sandbox_id, idempotency_key=req.idempotency_key)}
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


@router.post("/{project_id}/slots/{slot}/point/sandboxes/{sandbox_id}/step", summary="单步（predict + commit）")
def post_step(project_id: str, slot: str, sandbox_id: str) -> Dict[str, Any]:
    scope = _scope(project_id, slot, write=True)
    try:
        return {**scope.echo(), **SandboxRuntime.step(scope, sandbox_id)}
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


@router.post("/{project_id}/slots/{slot}/point/sandboxes/{sandbox_id}/advance", summary="推进 N 点")
def post_advance(project_id: str, slot: str, sandbox_id: str, req: AdvanceRequest) -> Dict[str, Any]:
    scope = _scope(project_id, slot, write=True)
    try:
        return {**scope.echo(), **SandboxRuntime.advance(scope, sandbox_id, req.step_size)}
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


@router.post("/{project_id}/slots/{slot}/point/sandboxes/{sandbox_id}/reset", summary="Sandbox 局部 reset")
def post_reset(project_id: str, slot: str, sandbox_id: str) -> Dict[str, Any]:
    scope = _scope(project_id, slot, write=True)
    try:
        rec = SandboxRuntime.reset(scope, sandbox_id)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {
        **scope.echo(),
        "sandbox": rec,
        "reset_scope": {"sandbox_id": sandbox_id, "current_cursor": rec.get("cursor", 0)},
        "production_unaffected": True,
        "statement": "仅重置该 Sandbox 的隔离结果（cursor / 历史 / 待定点），production 与其他 Sandbox 不受影响。",
    }


@router.get("/{project_id}/slots/{slot}/point/sandboxes/{sandbox_id}/metrics", summary="点级指标")
def get_metrics(project_id: str, slot: str, sandbox_id: str) -> Dict[str, Any]:
    scope = _scope(project_id, slot)
    try:
        return SandboxRuntime.metrics(scope, sandbox_id)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


# @AI_GENERATED: end
