# @AI_GENERATED: Kiro v1.0
"""
模板管理 Skill — 保存/加载/搜索/版本管理算法模板
当前使用内存存储，后续可切换到数据库
"""
import time
import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel

from models.workflow_agent_models import (
    TemplateCreateRequest,
    TemplateSearchParams,
    TemplateVisibility,
    SkillContext,
)
from services.workflow_agent.skills.base_skill import BaseSkill

logger = logging.getLogger(__name__)


class TemplateRecord(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    scenario_id: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = []
    visibility: TemplateVisibility = TemplateVisibility.PRIVATE
    workflow_data: Dict[str, Any] = {}
    version: int = 1
    parent_version_id: Optional[str] = None
    creator_id: int = 0
    load_count: int = 0
    fork_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class TemplateManageResponse(BaseModel):
    action: str  # created|loaded|updated|deleted|search
    template: Optional[TemplateRecord] = None
    templates: List[TemplateRecord] = []
    total: int = 0
    processing_time_ms: int = 0


# 内存存储（MVP阶段）
_templates: Dict[str, TemplateRecord] = {}


class TemplateManageSkill(BaseSkill):
    """模板管理 Skill"""

    skill_name = "template-manage"
    required_role = "user"

    async def validate_input(self, request: BaseModel) -> None:
        if isinstance(request, TemplateCreateRequest):
            if not request.name.strip():
                raise ValueError("模板名称不能为空")
            if not request.workflow_data:
                raise ValueError("workflow_data 不能为空")

    async def execute(
        self, request: BaseModel, context: SkillContext
    ) -> TemplateManageResponse:
        start = time.time()

        if isinstance(request, TemplateCreateRequest):
            return self._create(request, context, start)
        elif isinstance(request, TemplateSearchParams):
            return self._search(request, context, start)
        else:
            raise ValueError("请求类型错误")

    def _create(
        self, req: TemplateCreateRequest, ctx: SkillContext, start: float
    ) -> TemplateManageResponse:
        now = datetime.utcnow().isoformat()
        record = TemplateRecord(
            id=f"tpl-{uuid.uuid4().hex[:12]}",
            name=req.name,
            description=req.description,
            scenario_id=req.scenario_id,
            category=req.category,
            tags=req.tags,
            visibility=req.visibility,
            workflow_data=req.workflow_data,
            version=1,
            creator_id=ctx.user_id,
            created_at=now,
            updated_at=now,
        )
        _templates[record.id] = record
        return TemplateManageResponse(
            action="created",
            template=record,
            total=1,
            processing_time_ms=int((time.time() - start) * 1000),
        )

    def _search(
        self, req: TemplateSearchParams, ctx: SkillContext, start: float
    ) -> TemplateManageResponse:
        results = list(_templates.values())

        # 可见性过滤：private 仅创建者可见
        results = [
            t for t in results
            if t.visibility != TemplateVisibility.PRIVATE
            or t.creator_id == ctx.user_id
        ]

        if req.scenario_id:
            results = [t for t in results if t.scenario_id == req.scenario_id]
        if req.name:
            results = [t for t in results if req.name.lower() in t.name.lower()]
        if req.tags:
            results = [
                t for t in results
                if any(tag in t.tags for tag in req.tags)
            ]
        if req.creator_id:
            results = [t for t in results if t.creator_id == req.creator_id]

        total = len(results)
        offset = (req.page - 1) * req.page_size
        page_results = results[offset : offset + req.page_size]

        return TemplateManageResponse(
            action="search",
            templates=page_results,
            total=total,
            processing_time_ms=int((time.time() - start) * 1000),
        )
# @AI_GENERATED: end
