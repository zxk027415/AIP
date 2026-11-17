# @AI_GENERATED: Kiro v1.0
"""
Skill 抽象基类 — 所有 Workflow Agent Skills 的基础
"""
from abc import ABC, abstractmethod
from pydantic import BaseModel
import time
import logging

from models.workflow_agent_models import SkillContext, SkillResult

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """所有 Skill 的抽象基类"""

    skill_name: str = ""
    required_role: str = "user"  # user | engineer | admin

    @abstractmethod
    async def execute(self, request: BaseModel, context: SkillContext) -> BaseModel:
        """执行 Skill 逻辑，子类必须实现"""
        ...

    async def validate_input(self, request: BaseModel) -> None:
        """输入校验，子类可覆盖。校验失败抛出 ValueError。"""
        pass

    async def safe_execute(self, request: BaseModel, context: SkillContext) -> SkillResult:
        """安全执行包装：校验输入 → 执行 → 捕获异常 → 返回 SkillResult"""
        start = time.time()
        try:
            await self.validate_input(request)
            result = await self.execute(request, context)
            duration_ms = int((time.time() - start) * 1000)
            return SkillResult(
                skill_name=self.skill_name,
                status="success",
                output=result.model_dump() if result else None,
                execution_duration_ms=duration_ms,
            )
        except ValueError as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.warning(f"Skill [{self.skill_name}] 输入校验失败: {e}")
            return SkillResult(
                skill_name=self.skill_name,
                status="failed",
                error=str(e),
                execution_duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"Skill [{self.skill_name}] 执行异常: {e}", exc_info=True)
            return SkillResult(
                skill_name=self.skill_name,
                status="failed",
                error=str(e),
                execution_duration_ms=duration_ms,
            )
# @AI_GENERATED: end
