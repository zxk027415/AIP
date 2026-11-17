# @AI_GENERATED: Kiro v1.0
"""
最佳实践推荐 Skill — 查询/推荐/贡献行业最佳实践
"""
import time
import uuid
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from models.workflow_agent_models import (
    BestPracticeQuery,
    BestPracticeContribute,
    SkillContext,
)
from services.workflow_agent.skills.base_skill import BaseSkill
from services.workflow_agent.knowledge.best_practices import (
    get_best_practices_library,
)

logger = logging.getLogger(__name__)


class BestPracticeItem(BaseModel):
    id: str
    scenario_id: str
    title: str
    description: Optional[str] = None
    algorithm_combination: Dict[str, Any] = {}
    key_parameters: Dict[str, Any] = {}
    achieved_metrics: Dict[str, Any] = {}
    applicability_notes: Optional[str] = None
    is_system: bool = True


class BestPracticeResponse(BaseModel):
    scenario_id: str
    practices: List[BestPracticeItem] = []
    total: int = 0
    processing_time_ms: int = 0


# 用户贡献的最佳实践（内存存储，MVP阶段）
_user_practices: List[Dict[str, Any]] = []


class BestPracticeSkill(BaseSkill):
    """最佳实践推荐 Skill"""

    skill_name = "best-practice"
    required_role = "engineer"

    async def validate_input(self, request: BaseModel) -> None:
        if isinstance(request, BestPracticeQuery):
            if not request.scenario_id.strip():
                raise ValueError("scenario_id 不能为空")
        elif isinstance(request, BestPracticeContribute):
            if not request.scenario_id.strip():
                raise ValueError("scenario_id 不能为空")
            if not request.title.strip():
                raise ValueError("title 不能为空")

    async def execute(
        self, request: BaseModel, context: SkillContext
    ) -> BestPracticeResponse:
        start = time.time()

        if isinstance(request, BestPracticeQuery):
            return self._query(request, start)
        elif isinstance(request, BestPracticeContribute):
            return self._contribute(request, context, start)
        else:
            raise ValueError("请求类型错误")

    def _query(
        self, req: BestPracticeQuery, start: float
    ) -> BestPracticeResponse:
        lib = get_best_practices_library()
        system_items = lib.get_by_scenario(req.scenario_id)
        user_items = [
            p for p in _user_practices
            if p.get("scenario_id") == req.scenario_id
        ]

        all_items = []
        for item in system_items + user_items:
            all_items.append(BestPracticeItem(
                id=item.get("id", ""),
                scenario_id=item.get("scenario_id", ""),
                title=item.get("title", ""),
                description=item.get("description"),
                algorithm_combination=item.get("algorithm_combination", {}),
                key_parameters=item.get("key_parameters", {}),
                achieved_metrics=item.get("achieved_metrics", {}),
                applicability_notes=item.get("applicability_notes"),
                is_system=item.get("is_system", False),
            ))

        limited = all_items[: req.limit]
        return BestPracticeResponse(
            scenario_id=req.scenario_id,
            practices=limited,
            total=len(all_items),
            processing_time_ms=int((time.time() - start) * 1000),
        )

    def _contribute(
        self, req: BestPracticeContribute, ctx: SkillContext, start: float
    ) -> BestPracticeResponse:
        new_practice = {
            "id": f"bp-user-{uuid.uuid4().hex[:8]}",
            "scenario_id": req.scenario_id,
            "title": req.title,
            "description": req.description,
            "algorithm_combination": req.algorithm_combination,
            "key_parameters": req.key_parameters,
            "achieved_metrics": req.achieved_metrics,
            "applicability_notes": req.applicability_notes,
            "is_system": False,
            "contributor_id": ctx.user_id,
        }
        _user_practices.append(new_practice)

        item = BestPracticeItem(**{
            k: v for k, v in new_practice.items()
            if k != "contributor_id"
        })
        return BestPracticeResponse(
            scenario_id=req.scenario_id,
            practices=[item],
            total=1,
            processing_time_ms=int((time.time() - start) * 1000),
        )
# @AI_GENERATED: end
