# @AI_GENERATED
"""项目化 API 包（pv-three-chain-product-validation）。

聚合项目工作台的 scoped 路由。第一阶段包含治理（registry / rolling-model / promote）；
后续任务（2.1 项目 CRUD、2.3 数据接入、3.x 运行中心等）在此追加子路由。
"""

from __future__ import annotations

from fastapi import APIRouter

from api.pv_projects.catalog import router as catalog_router
from api.pv_projects.cross_dataset import router as cross_dataset_router
from api.pv_projects.cumulative import router as cumulative_router
from api.pv_projects.datasets import router as datasets_router
from api.pv_projects.day import router as day_router
from api.pv_projects.governance import router as governance_router
from api.pv_projects.point import router as point_router
from api.pv_projects.projects import router as projects_router
from api.pv_projects.reviews import router as reviews_router
from api.pv_projects.runs import router as runs_router
from api.pv_projects.tsc import router as tsc_router

# 聚合根路由；各子模块自带 `/api/pv-projects` 前缀，这里统一挂载。
# 先挂项目生命周期（POST/GET /api/pv-projects、/{id}/overview），再挂数据接入、运行中心、
# 治理、审核、累计冻结，以及日 / 点路径子路由。
router = APIRouter()
# 固定段（catalog）先于动态段（projects 的 /{project_id}/…）注册：动态段会贪婪匹配同段数的
# 路径，把 `/catalog` 当成 `project_id="catalog"`。
router.include_router(catalog_router)
router.include_router(projects_router)
router.include_router(datasets_router)
router.include_router(runs_router)
router.include_router(governance_router)
router.include_router(reviews_router)
router.include_router(cumulative_router)
router.include_router(day_router)
router.include_router(point_router)
router.include_router(tsc_router)
router.include_router(cross_dataset_router)

__all__ = ["router"]

# @AI_GENERATED: end
