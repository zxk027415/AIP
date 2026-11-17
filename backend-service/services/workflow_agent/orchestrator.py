# @AI_GENERATED: Kiro v1.0
"""
Skill 编排器 — 链式执行、并发控制、错误恢复
"""
import asyncio
import time
import logging
from typing import Dict, List, Optional

from pydantic import BaseModel

from models.workflow_agent_models import (
    SkillContext, SkillStep, SkillResult, ChainResult, SkillName,
)
from services.workflow_agent.skills.base_skill import BaseSkill

logger = logging.getLogger(__name__)

# 重试配置 (NFR-2.1)
MAX_RETRIES = 3
BACKOFF_BASE = 1.0
BACKOFF_MULTIPLIER = 2.0
RETRYABLE_ERRORS = ("ConnectionError", "TimeoutError", "RedisConnectionError")


class SkillOrchestrator:
    """Skill 链式编排器"""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register_skill(self, skill: BaseSkill) -> None:
        """注册一个 Skill 实例"""
        self._skills[skill.skill_name] = skill

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """获取已注册的 Skill"""
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        """列出所有已注册的 Skill 名称"""
        return list(self._skills.keys())

    async def execute_chain(
        self,
        steps: List[SkillStep],
        context: SkillContext,
    ) -> ChainResult:
        """按顺序执行 Skill 链，支持错误恢复和重试"""
        results: List[SkillResult] = []
        chain_start = time.time()
        previous_output: Optional[Dict] = None

        for step in steps:
            skill = self._skills.get(step.skill_name.value
                                     if isinstance(step.skill_name, SkillName)
                                     else step.skill_name)
            if skill is None:
                results.append(SkillResult(
                    skill_name=step.skill_name if isinstance(step.skill_name, str)
                    else step.skill_name.value,
                    status="failed",
                    error=f"Skill '{step.skill_name}' 未注册",
                ))
                return ChainResult(
                    steps=results,
                    overall_status="failed",
                    total_duration_ms=int((time.time() - chain_start) * 1000),
                )

            # 合并上一步输出到当前输入
            input_data = {**step.input_data}
            if previous_output and step.depends_on:
                input_data["_previous"] = previous_output

            # 构造请求对象（传 dict 给 safe_execute 时用 BaseModel 包装）
            request = _dict_to_model(input_data)

            result = await self._execute_with_retry(skill, request, context)
            results.append(result)

            if result.status == "failed":
                return ChainResult(
                    steps=results,
                    overall_status="partial" if len(results) > 1 else "failed",
                    total_duration_ms=int((time.time() - chain_start) * 1000),
                )

            previous_output = result.output

        return ChainResult(
            steps=results,
            overall_status="success",
            total_duration_ms=int((time.time() - chain_start) * 1000),
        )

    async def execute_parallel(
        self,
        steps: List[SkillStep],
        context: SkillContext,
    ) -> List[SkillResult]:
        """并发执行独立 Skills"""
        tasks = []
        for step in steps:
            skill = self._skills.get(
                step.skill_name.value
                if isinstance(step.skill_name, SkillName)
                else step.skill_name
            )
            if skill is None:
                tasks.append(_make_failed_result(step.skill_name))
            else:
                request = _dict_to_model(step.input_data)
                tasks.append(self._execute_with_retry(skill, request, context))
        return list(await asyncio.gather(*tasks))

    async def _execute_with_retry(
        self,
        skill: BaseSkill,
        request: BaseModel,
        context: SkillContext,
    ) -> SkillResult:
        """带指数退避重试的执行"""
        last_result: Optional[SkillResult] = None
        for attempt in range(MAX_RETRIES + 1):
            result = await skill.safe_execute(request, context)
            if result.status == "success":
                return result
            last_result = result
            # 判断是否可重试
            if result.error and any(e in result.error for e in RETRYABLE_ERRORS):
                if attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE * (BACKOFF_MULTIPLIER ** attempt)
                    logger.info(
                        f"Skill [{skill.skill_name}] 重试 {attempt+1}/{MAX_RETRIES}，"
                        f"等待 {wait:.1f}s"
                    )
                    await asyncio.sleep(wait)
                    continue
            break
        return last_result or SkillResult(
            skill_name=skill.skill_name, status="failed", error="未知错误"
        )


class _DictModel(BaseModel):
    """将 dict 包装为 BaseModel 以兼容 Skill 接口"""
    data: Dict

    class Config:
        arbitrary_types_allowed = True


def _dict_to_model(d: Dict) -> BaseModel:
    return _DictModel(data=d)


async def _make_failed_result(skill_name) -> SkillResult:
    name = skill_name.value if isinstance(skill_name, SkillName) else str(skill_name)
    return SkillResult(
        skill_name=name,
        status="failed",
        error=f"Skill '{name}' 未注册",
    )
# @AI_GENERATED: end
