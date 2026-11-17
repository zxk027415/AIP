# @AI_GENERATED
"""数据接入 API：上传 / 平台资产 / 连接器（项目级数据资产）+ 物化任务。

设计依据：design.md §13、§26.2、§26.6；requirements.md R13.5、R13.7、R13.25、NFR1.*、NFR4.1–NFR4.3。

路由：
- POST /api/pv-projects/{project_id}/datasets                          登记数据资产（不接收服务器路径 / 凭据）
- GET  /api/pv-projects/{project_id}/datasets                          列出数据资产
- GET  /api/pv-projects/{project_id}/datasets/{dataset_id}/preview     有界预览
- POST /api/pv-projects/{project_id}/datasets/{dataset_id}/materialize 创建可恢复物化任务
- GET  /api/pv-projects/{project_id}/materialization-tasks/{task_id}   查询物化任务
- POST /api/pv-projects/{project_id}/materialization-tasks/{task_id}/cancel  取消物化任务
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, scope_error_to_http
from services.pv_projects import catalog as catalog_service
from services.pv_projects import datasets as dataset_service
from services.pv_projects import readiness as readiness_service
from services.pv_projects.errors import ScopeError

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-datasets"])


class RegisterDatasetRequest(BaseModel):
    # 注意：不包含任何凭据 / 连接串 / 服务器路径字段（结构上杜绝凭据泄漏）。
    source_kind: str = Field(..., description="upload | platform_asset | connector")
    file_name: Optional[str] = Field(default=None, description="上传文件名")
    upload_ref: Optional[str] = Field(default=None, description="上传后的相对引用（非机器绝对路径）")
    asset_id: Optional[str] = Field(default=None, description="平台数据资产 ID")
    connector_id: Optional[str] = Field(default=None, description="已授权连接器 ID")
    logical_object: Optional[str] = Field(default=None, description="逻辑对象名（如库表名），不含凭据")
    logical_description: Optional[str] = Field(default=None, description="逻辑描述，不含凭据 / 连接串")


class MaterializeRequest(BaseModel):
    time_range: Optional[str] = Field(default=None, description="物化时间范围")
    row_limit: Optional[int] = Field(default=None, description="物化行数上限")


class SaveProfileRequest(BaseModel):
    mapping: Dict[str, Any] = Field(..., description="字段映射（时间 / 实体 / 测量 / 标签 / 粒度 / 质量策略）")
    facts: Optional[Dict[str, Any]] = Field(default=None, description="画像事实（日期 / 设备 / 采样 / 标签分布 / i_cal 可用性）")
    label_policy: Optional[Dict[str, Any]] = Field(default=None, description="标签字典 / 未知策略 / 标签粒度")
    ical_contract: Optional[Dict[str, Any]] = Field(default=None, description="i_cal 校准合同（期望电流参照，非 ground truth）")


class PublishVersionRequest(BaseModel):
    dataset_id: str = Field(..., description="数据资产 ID")
    dataset_profile_id: str = Field(..., description="要发布的画像 / 映射版本 ID")


class MountCatalogEntryRequest(BaseModel):
    slot: str = Field(..., description="目标诊断路径（pv_day / pv_point / pv_tsc）")
    entry_id: str = Field(..., description="平台数据集目录条目 ID（dsc-…）")


@router.post("/{project_id}/datasets/mount", summary="挂载平台数据集目录条目")
def mount_catalog_entry(project_id: str, req: MountCatalogEntryRequest) -> Dict[str, Any]:
    """把已发布的目录条目挂载进项目：登记数据资产 + 画像 + 不可变版本（同内容幂等）。

    目录是**平台级**资产，但挂载结果**属于项目**，所以这里走 `build_scope`
    （要求项目已登记、slot 合法），与平台级 `/catalog` 路由刻意不同。
    """
    scope = build_scope(project_id, req.slot, require_slot=True, allow_legacy=False)
    try:
        return catalog_service.mount_into_project(scope, req.entry_id)
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.post("/{project_id}/datasets", summary="登记数据资产")
def register_dataset(project_id: str, req: RegisterDatasetRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        return dataset_service.register_dataset_asset(
            scope,
            source_kind=req.source_kind,
            file_name=req.file_name,
            upload_ref=req.upload_ref,
            asset_id=req.asset_id,
            connector_id=req.connector_id,
            logical_object=req.logical_object,
            logical_description=req.logical_description,
        )
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.get("/{project_id}/datasets", summary="列出数据资产")
def list_datasets(project_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    return {**scope.echo(), "assets": dataset_service.list_dataset_assets(scope)}


@router.get("/{project_id}/datasets/{dataset_id}/preview", summary="有界预览")
def preview_dataset(project_id: str, dataset_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    try:
        return dataset_service.get_preview(scope, dataset_id)
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.post("/{project_id}/datasets/{dataset_id}/materialize", summary="创建物化任务")
def materialize_dataset(project_id: str, dataset_id: str, req: MaterializeRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        return dataset_service.create_materialization_task(
            scope, dataset_id=dataset_id, time_range=req.time_range, row_limit=req.row_limit
        )
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.get("/{project_id}/materialization-tasks/{task_id}", summary="查询物化任务")
def get_materialization_task(project_id: str, task_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    task = dataset_service.get_materialization_task(scope, task_id)
    if task is None:
        return {**scope.echo(), "task_id": task_id, "empty": True, "diagnostic": "当前项目未找到该物化任务"}
    return {**scope.echo(), **task}


@router.post("/{project_id}/materialization-tasks/{task_id}/cancel", summary="取消物化任务")
def cancel_materialization_task(project_id: str, task_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        return dataset_service.cancel_materialization_task(scope, task_id)
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.post("/{project_id}/datasets/{dataset_id}/profile", summary="保存字段映射 / 画像版本")
def save_profile(project_id: str, dataset_id: str, req: SaveProfileRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        return dataset_service.save_dataset_profile(
            scope,
            dataset_id=dataset_id,
            mapping=req.mapping,
            facts=req.facts,
            label_policy=req.label_policy,
            ical_contract=req.ical_contract,
        )
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.post("/{project_id}/dataset-versions/publish", summary="发布不可变数据版本")
def publish_version(project_id: str, req: PublishVersionRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        return dataset_service.publish_dataset_version(
            scope, dataset_id=req.dataset_id, dataset_profile_id=req.dataset_profile_id
        )
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.get("/{project_id}/dataset-versions", summary="列出不可变数据版本")
def list_dataset_versions(project_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    return {**scope.echo(), "versions": dataset_service.list_dataset_versions(scope)}


@router.get("/{project_id}/dataset-versions/{dataset_version_id}/readiness", summary="三路径 readiness")
def dataset_version_readiness(project_id: str, dataset_version_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    try:
        return readiness_service.evaluate_all_paths(scope, dataset_version_id)
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


# @AI_GENERATED: end
