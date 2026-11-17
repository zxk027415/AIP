# @AI_GENERATED
"""pv_day 金路径 API（design D-PATH-01；任务 5.1 / 5.2）。

路由：
- GET  /api/pv-projects/{project_id}/slots/{slot}/day/production-fact         日路径生产事实（只读诚实标注）
- GET  /api/pv-projects/{project_id}/slots/{slot}/day/executions/{execution_id}/summary  device-day 汇总
- POST /api/pv-projects/{project_id}/slots/{slot}/day/sandbox-device-day       Sandbox 全设备日回放（隔离）
- GET  /api/pv-projects/{project_id}/slots/{slot}/day/sandbox-runs             列出 Sandbox 日级回放

红线：日路径生产由 LegacyDayStrategy 复用 quickval 预测工作流；本 API 不新建日级生产图，
Sandbox 回放隔离、不写生产指针。仅 slot=pv_day 有业务意义（其余 slot 也可读事实，但语义为空）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, gate_error_to_http
from services.pv_projects import day_adapter as day
from services.pv_projects.governance import GovernanceGateError

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-day"])


class SandboxDeviceDayRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    sandbox_id: str = Field(..., description="Sandbox 实例 ID")
    device_days: List[Dict[str, Any]] = Field(default_factory=list, description="待回放的 (device, date) 列表")
    model_ref: str | None = Field(default=None, description="模型引用（Sandbox 演示可空）")


@router.get("/{project_id}/slots/{slot}/day/production-fact", summary="日路径生产事实（只读）")
def get_day_production_fact(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return day.day_production_fact(scope)


@router.get("/{project_id}/slots/{slot}/day/executions/{execution_id}/summary", summary="device-day 汇总")
def get_day_execution_summary(project_id: str, slot: str, execution_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    try:
        return day.summarize_day_execution(scope, execution_id)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


@router.post("/{project_id}/slots/{slot}/day/sandbox-device-day", summary="Sandbox 全设备日回放（隔离）")
def post_sandbox_device_day(project_id: str, slot: str, req: SandboxDeviceDayRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        record = day.run_sandbox_device_day(
            scope, sandbox_id=req.sandbox_id, device_days=req.device_days, model_ref=req.model_ref
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "sandbox_run": record}


@router.get("/{project_id}/slots/{slot}/day/sandbox-runs", summary="列出 Sandbox 日级回放")
def get_day_sandbox_runs(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return {**scope.echo(), "sandbox_runs": day.list_sandbox_day_runs(scope)}


# @AI_GENERATED: end
