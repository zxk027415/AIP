# @AI_GENERATED
"""项目生命周期 API：创建 / 列表 / 总览。

设计依据：design.md §12、§14、§26.2；requirements.md R1.1–R1.12、R2.1–R2.13。

路由（对齐 §26.2 合同方向）：
- POST /api/pv-projects                          创建空项目（不继承 legacy 状态）
- GET  /api/pv-projects                          跨领域项目列表
- GET  /api/pv-projects/{project_id}/overview     三路径生命周期总览
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, scope_error_to_http
from services.pv_projects import projects as project_service
from services.pv_projects.errors import ScopeError

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects"])


class CreateProjectRequest(BaseModel):
    project_name: str = Field(..., description="用户可读项目名称")
    owner: Optional[str] = Field(default=None, description="项目负责人")
    scenario_id: Optional[str] = Field(default=None, description="行业场景")
    solution_id: Optional[str] = Field(default=None, description="算法方案")
    copy_from_project_id: Optional[str] = Field(default=None, description="从现有项目复制结构（不复制数据/状态）")
    catalog_entry_id: Optional[str] = Field(
        default=None,
        description="创建时挂载的平台目录条目（dsc-…）；先选数据集再推导路径",
    )
    mount_slot: Optional[str] = Field(
        default=None,
        description="挂载到哪条诊断路径；缺省用来源路径 origin_slot 或唯一适用路径",
    )


@router.post("", summary="创建项目（可选同时挂载目录数据集）")
def create_project(req: CreateProjectRequest) -> Dict[str, Any]:
    try:
        return project_service.create_project(
            project_name=req.project_name,
            owner=req.owner,
            scenario_id=req.scenario_id,
            solution_id=req.solution_id,
            copy_from_project_id=req.copy_from_project_id,
            catalog_entry_id=req.catalog_entry_id,
            mount_slot=req.mount_slot,
        )
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.get("", summary="跨领域项目列表")
def list_projects(include_legacy: bool = True) -> Dict[str, Any]:
    projects: List[Dict[str, Any]] = project_service.list_projects(include_legacy=include_legacy)
    return {"projects": projects, "total": len(projects)}


@router.get("/{project_id}/overview", summary="三路径生命周期总览")
def project_overview(project_id: str) -> Dict[str, Any]:
    # 校验 project_id（fail-closed），再计算总览。
    scope = build_scope(project_id)
    return project_service.project_overview(scope.project_id)


class SetEnabledSlotsRequest(BaseModel):
    """确认项目启用的诊断路径（intent）。

    约定在 readiness 出来之后确认，避免盲选；传 `null` 表示撤销确认（回到未确认，总览展示三条）。
    只校验取值合法性；可行性由 readiness 逐路径判定，两者在总览叠加展示。
    """

    enabled_slots: Optional[List[str]] = Field(
        default=None, description="启用的诊断路径列表（pv_day/pv_point/pv_tsc）；null=撤销确认"
    )


@router.put("/{project_id}/enabled-slots", summary="确认项目启用的诊断路径")
def set_enabled_slots(project_id: str, req: SetEnabledSlotsRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        record = project_service.set_enabled_slots(scope.project_id, req.enabled_slots)
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc
    return {**scope.echo(), "project": record}


# @AI_GENERATED: end
