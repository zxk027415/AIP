# @AI_GENERATED: Kiro v1.0
"""
业务约束注入 Skill — 查询/注入行业特定的业务约束
"""
import time
import logging
from typing import Any, Dict, List

from pydantic import BaseModel

from models.workflow_agent_models import (
    DomainConstraintQuery,
    SkillContext,
)
from services.workflow_agent.skills.base_skill import BaseSkill
from services.workflow_agent.knowledge.domain_constraints import (
    get_domain_constraints_library,
)

logger = logging.getLogger(__name__)


class DomainConstraintResponse(BaseModel):
    scenario_id: str
    scenario_name: str = ""
    parameter_constraints: Dict[str, Any] = {}
    evaluation_metrics: List[str] = []
    business_rules: List[Dict[str, str]] = []
    processing_time_ms: int = 0


class DomainConstraintSkill(BaseSkill):
    """业务约束注入 Skill"""

    skill_name = "domain-constraint"
    required_role = "engineer"

    async def validate_input(self, request: BaseModel) -> None:
        if isinstance(request, DomainConstraintQuery):
            if not request.scenario_id.strip():
                raise ValueError("scenario_id 不能为空")

    async def execute(
        self, request: BaseModel, context: SkillContext
    ) -> DomainConstraintResponse:
        if not isinstance(request, DomainConstraintQuery):
            raise ValueError("请求类型错误，期望 DomainConstraintQuery")

        start = time.time()
        lib = get_domain_constraints_library()
        data = lib.get_constraints(request.scenario_id)

        if not data:
            raise ValueError(
                f"场景 '{request.scenario_id}' 无约束定义"
            )

        return DomainConstraintResponse(
            scenario_id=request.scenario_id,
            scenario_name=data.get("scenario_name", ""),
            parameter_constraints=data.get("parameter_constraints", {}),
            evaluation_metrics=data.get("evaluation_metrics", []),
            business_rules=data.get("business_rules", []),
            processing_time_ms=int((time.time() - start) * 1000),
        )
# @AI_GENERATED: end
