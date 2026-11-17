# @AI_GENERATED
"""平台级数据集目录 API（数据集切片第 2b 收尾）。

目录是**平台级资产**：数据集由多个项目共享，因此这里**不**走 `api.pv_projects.common.build_scope`
——后者默认要求 `project_id` 已登记，语义上属于项目级 scoped 存储；目录条目不属于任何项目。

路由：
- GET  /api/pv-projects/catalog                     列出已发布条目
- GET  /api/pv-projects/catalog/available-sources    可检测的来源（路径累计快照 + 可发现数据集单元）
- GET  /api/pv-projects/catalog/entries/{entry_id}   单条已发布条目详情
- POST /api/pv-projects/catalog/inspect              质量检测（**只读，不落盘**）
- POST /api/pv-projects/catalog/publish              检测 + 发布不可变条目（同内容幂等命中）

注册顺序：本 router 在 `api/pv_projects/__init__.py` 里被 include 在 `projects.py` **之前**。
当前 `projects.py` 只有三段路径（`/{project_id}/overview`），两段的 `/catalog` 不会撞车；
前置是对「未来有人新增两段 `/{project_id}` 路由」的防御——固定段必须先于动态段匹配。

形状约定：`/catalog/entries/{entry_id}` 刻意用三段而非两段 `/catalog/{entry_id}`，
以免与两段的 `/catalog/available-sources` 产生歧义（后者依赖注册顺序才不会被吃掉）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import scope_error_to_http
from services.pv_projects import catalog as catalog_service
from services.pv_projects import source_resolver as source_service
from services.pv_projects.errors import ScopeError

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-catalog"])


class InspectRequest(BaseModel):
    """质量检测入参。

    `mapping` 至少含 `time_col` / `device_col` / `value_col`；带 `label_col` 时才能检出标签粒度
    （粒度决定「适用路径」——`facts.compute_dataset_facts` 的 `REQUIRED_MAPPING_FIELDS`）。
    """

    dataset_ref: str = Field(
        ..., description="数据集引用：`<来源根别名>/…`（如 uploads/x.csv）或 slot_datasets/<slot>/snapshots/<file>"
    )
    mapping: Dict[str, Any] = Field(
        ..., description="字段映射（time_col / device_col / value_col 必填，label_col 可选）"
    )
    label_policy: Optional[Dict[str, Any]] = Field(
        default=None, description="标签策略（如 granularity）；影响声明的标签粒度"
    )
    origin_slot: Optional[str] = Field(
        default=None, description="来源路径（pv_day/pv_point/pv_tsc）；不传则从引用推断"
    )
    display_name: Optional[str] = Field(default=None, description="可读展示名；缺省用 dataset_ref")
    origin: str = Field(default="manual", description="来源类型（manual / path_cumulative_snapshot）")


class PublishRequest(InspectRequest):
    """发布入参：与检测一致——先检测再发布，避免「发布了但没检测」。"""


@router.get("/catalog/available-sources", summary="可检测 / 可挂载的数据来源")
def list_available_sources(limit: int = 200) -> Dict[str, Any]:
    """回答「现在有哪些可检测的来源」。

    - `path_cumulative`：三条路径的累计训练数据集（`data/slot_datasets/<slot>/snapshots/` 冻结快照）。
    - `discoverable`：按 `DATASET_UNIT_SPECS` 收敛后的数据集单元（文件 / 目录分片组），
      刻意不含 `benchmark_raw` 里的研究产物（见 `source_resolver.DATASET_UNIT_SPECS`）。
    """
    path_cumulative = catalog_service.discover_path_cumulative_datasets()
    discoverable = source_service.discover_datasets(limit=limit)
    return {
        "path_cumulative": path_cumulative,
        "discoverable": discoverable,
        "path_cumulative_count": len(path_cumulative),
        "discoverable_count": len(discoverable),
    }


@router.get("/catalog", summary="列出已发布数据集条目")
def list_catalog_entries() -> Dict[str, Any]:
    entries = catalog_service.list_catalog()
    return {"entries": entries, "total": len(entries)}


@router.get("/catalog/entries/{entry_id}", summary="数据集条目详情")
def get_catalog_entry_detail(entry_id: str) -> Dict[str, Any]:
    entry = catalog_service.get_catalog_entry(entry_id)
    if entry is None:
        raise scope_error_to_http(
            ScopeError(
                "catalog_entry_not_found",
                f"目录里没有条目 {entry_id!r}。",
                next_action="先 GET /api/pv-projects/catalog 列出可用条目",
            )
        )
    return entry


@router.post("/catalog/inspect", summary="数据集质量检测（只读，不落盘）")
def inspect_catalog_dataset(req: InspectRequest) -> Dict[str, Any]:
    try:
        return catalog_service.inspect_dataset(
            req.dataset_ref,
            mapping=req.mapping,
            label_policy=req.label_policy,
            origin_slot=req.origin_slot,
            origin=req.origin,
            display_name=req.display_name,
        )
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


@router.post("/catalog/publish", summary="检测并发布不可变数据集条目")
def publish_catalog_dataset(req: PublishRequest) -> Dict[str, Any]:
    try:
        draft = catalog_service.inspect_dataset(
            req.dataset_ref,
            mapping=req.mapping,
            label_policy=req.label_policy,
            origin_slot=req.origin_slot,
            origin=req.origin,
            display_name=req.display_name,
        )
        return catalog_service.publish_dataset(draft)
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc


# @AI_GENERATED: end
