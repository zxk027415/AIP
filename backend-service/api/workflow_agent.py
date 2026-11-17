# @AI_GENERATED: Kiro v1.0
"""
Workflow Agent API 路由 — 8 个 Skill 端点 + 链式编排 + 状态仪表盘 + 审计日志 + RBAC
"""
from fastapi import APIRouter, HTTPException, Header
from typing import List, Optional
import logging
import json

from models.workflow_agent_models import (
    ScenarioMatchRequest,
    ScenarioMatchResponse,
    AlgorithmComposeRequest,
    AlgorithmComposeResponse,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
    WorkflowValidateRequest,
    WorkflowValidateResponse,
    DomainConstraintQuery,
    BestPracticeQuery,
    BestPracticeContribute,
    CrossScenarioRequest,
    MigrationReport,
    TemplateCreateRequest,
    TemplateSearchParams,
    SkillContext,
    SkillStep,
    ChainResult,
    SkillStatus,
    UserRole,
    AuditLogEntry,
    AuditLogQuery,
)
from services.auth_service import verify_token
from services.workflow_agent.skills.scenario_match import ScenarioMatchSkill
from services.workflow_agent.skills.algorithm_compose import AlgorithmComposeSkill
from services.workflow_agent.skills.workflow_generate import WorkflowGenerateSkill
from services.workflow_agent.skills.workflow_validate import WorkflowValidateSkill
from services.workflow_agent.skills.domain_constraint import DomainConstraintSkill
from services.workflow_agent.skills.template_manage import TemplateManageSkill
from services.workflow_agent.skills.best_practice import BestPracticeSkill
from services.workflow_agent.skills.cross_scenario import CrossScenarioSkill
from services.workflow_agent.orchestrator import SkillOrchestrator
from services.workflow_agent.audit import AuditLogger
from services.workflow_agent.rbac import check_permission
from utils.sanitize import sanitize_description, sanitize_id, validate_safe_input

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/workflow", tags=["Workflow Agent"])

# 初始化 Skills、编排器、审计日志
_scenario_match = ScenarioMatchSkill()
_algorithm_compose = AlgorithmComposeSkill()
_workflow_generate = WorkflowGenerateSkill()
_workflow_validate = WorkflowValidateSkill()
_domain_constraint = DomainConstraintSkill()
_template_manage = TemplateManageSkill()
_best_practice = BestPracticeSkill()
_cross_scenario = CrossScenarioSkill()

orchestrator = SkillOrchestrator()
for skill in [_scenario_match, _algorithm_compose, _workflow_generate,
              _workflow_validate, _domain_constraint, _template_manage,
              _best_practice, _cross_scenario]:
    orchestrator.register_skill(skill)

audit = AuditLogger()


def _get_context(authorization: Optional[str]) -> SkillContext:
    """从 JWT token 提取用户上下文"""
    if not authorization or not authorization.startswith("Bearer "):
        return SkillContext(user_id=0, username="anonymous", role=UserRole.USER)
    token = authorization.split(" ", 1)[1]
    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="无效的认证令牌")
    return SkillContext(
        user_id=token_data.user_id,
        username=token_data.username,
        role=UserRole.USER,
    )


async def _execute_skill(skill, request, ctx: SkillContext, action: str,
                         workflow_id: Optional[str] = None):
    """统一执行 Skill：RBAC 检查 → 执行 → 审计日志"""
    check_permission(ctx, skill.skill_name)
    try:
        result = await skill.execute(request, ctx)
        audit.log(
            user_id=ctx.user_id,
            skill_name=skill.skill_name,
            action=action,
            status="success",
            workflow_id=workflow_id,
            input_summary=_safe_summary(request),
        )
        return result
    except ValueError as e:
        audit.log(
            user_id=ctx.user_id,
            skill_name=skill.skill_name,
            action=action,
            status="failed",
            workflow_id=workflow_id,
            error_message=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        audit.log(
            user_id=ctx.user_id,
            skill_name=skill.skill_name,
            action=action,
            status="failed",
            workflow_id=workflow_id,
            error_message=str(e),
        )
        logger.error(f"{skill.skill_name} 异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"{skill.skill_name} 服务异常")


def _safe_summary(obj) -> Optional[str]:
    """安全提取请求摘要"""
    try:
        if hasattr(obj, 'model_dump'):
            d = obj.model_dump()
            return json.dumps(d, ensure_ascii=False, default=str)[:500]
        return str(obj)[:500]
    except Exception:
        return None


# ---- 编排类 Skills（所有用户可访问）----

# @AI_GENERATED: Kiro v1.0
@router.post("/scenario-match", response_model=ScenarioMatchResponse)
async def scenario_match(
    request: ScenarioMatchRequest,
    authorization: Optional[str] = Header(None),
):
    """行业场景匹配"""
    ctx = _get_context(authorization)
    # 输入 sanitize
    request.description = sanitize_description(request.description)
    validate_safe_input(request.description, "description")
    return await _execute_skill(_scenario_match, request, ctx, "match")
# @AI_GENERATED: end


@router.post("/algorithm-compose", response_model=AlgorithmComposeResponse)
async def algorithm_compose(
    request: AlgorithmComposeRequest,
    authorization: Optional[str] = Header(None),
):
    """算法组合推荐"""
    ctx = _get_context(authorization)
    return await _execute_skill(_algorithm_compose, request, ctx, "compose")


@router.post("/workflow-generate", response_model=WorkflowGenerateResponse)
async def workflow_generate(
    request: WorkflowGenerateRequest,
    authorization: Optional[str] = Header(None),
):
    """工作流自动生成"""
    ctx = _get_context(authorization)
    return await _execute_skill(_workflow_generate, request, ctx, "generate")


@router.post("/workflow-validate", response_model=WorkflowValidateResponse)
async def workflow_validate(
    request: WorkflowValidateRequest,
    authorization: Optional[str] = Header(None),
):
    """工作流合理性验证"""
    ctx = _get_context(authorization)
    return await _execute_skill(_workflow_validate, request, ctx, "validate")


# ---- 知识类 Skills（engineer 及以上角色可访问）----

# @AI_GENERATED: Kiro v1.0
@router.get("/domain-constraint")
async def query_domain_constraint(
    scenario_id: str,
    authorization: Optional[str] = Header(None),
):
    """查询业务约束"""
    ctx = _get_context(authorization)
    scenario_id = sanitize_id(scenario_id)
    req = DomainConstraintQuery(scenario_id=scenario_id)
    return await _execute_skill(_domain_constraint, req, ctx, "query")
# @AI_GENERATED: end


# @AI_GENERATED: Kiro v1.0
@router.post("/template-manage/create")
async def create_template(
    request: TemplateCreateRequest,
    authorization: Optional[str] = Header(None),
):
    """创建工作流模板"""
    ctx = _get_context(authorization)
    # 输入 sanitize
    request.name = sanitize_description(request.name)
    validate_safe_input(request.name, "template name")
    if request.description:
        request.description = sanitize_description(request.description)
    if request.scenario_id:
        request.scenario_id = sanitize_id(request.scenario_id)
    return await _execute_skill(_template_manage, request, ctx, "create")
# @AI_GENERATED: end


@router.post("/template-manage/search")
async def search_templates(
    request: TemplateSearchParams,
    authorization: Optional[str] = Header(None),
):
    """搜索工作流模板"""
    ctx = _get_context(authorization)
    return await _execute_skill(_template_manage, request, ctx, "search")


@router.get("/best-practice")
async def query_best_practices(
    scenario_id: str,
    limit: int = 10,
    authorization: Optional[str] = Header(None),
):
    """查询最佳实践"""
    ctx = _get_context(authorization)
    req = BestPracticeQuery(scenario_id=scenario_id, limit=limit)
    return await _execute_skill(_best_practice, req, ctx, "query")


# @AI_GENERATED: Kiro v1.0
@router.post("/best-practice/contribute")
async def contribute_best_practice(
    request: BestPracticeContribute,
    authorization: Optional[str] = Header(None),
):
    """贡献最佳实践"""
    ctx = _get_context(authorization)
    # 输入 sanitize
    request.title = sanitize_description(request.title)
    validate_safe_input(request.title, "title")
    if request.description:
        request.description = sanitize_description(request.description)
    request.scenario_id = sanitize_id(request.scenario_id)
    return await _execute_skill(_best_practice, request, ctx, "contribute")
# @AI_GENERATED: end


# @AI_GENERATED: Kiro v1.0
@router.post("/cross-scenario", response_model=MigrationReport)
async def cross_scenario_migrate(
    request: CrossScenarioRequest,
    authorization: Optional[str] = Header(None),
):
    """跨场景迁移"""
    ctx = _get_context(authorization)
    # 输入 sanitize
    request.source_scenario_id = sanitize_id(request.source_scenario_id)
    request.target_scenario_id = sanitize_id(request.target_scenario_id)
    return await _execute_skill(_cross_scenario, request, ctx, "migrate")
# @AI_GENERATED: end


# ---- 编排与状态 ----

@router.post("/chain", response_model=ChainResult)
async def execute_chain(
    steps: List[SkillStep],
    authorization: Optional[str] = Header(None),
):
    """链式编排执行"""
    ctx = _get_context(authorization)
    try:
        result = await orchestrator.execute_chain(steps, ctx)
        audit.log(
            user_id=ctx.user_id,
            skill_name="orchestrator",
            action="chain",
            status=result.overall_status,
            execution_duration_ms=result.total_duration_ms,
        )
        return result
    except Exception as e:
        audit.log(
            user_id=ctx.user_id,
            skill_name="orchestrator",
            action="chain",
            status="failed",
            error_message=str(e),
        )
        logger.error(f"chain 异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="链式编排服务异常")


@router.get("/skills/status", response_model=List[SkillStatus])
async def skills_status():
    """Skill 状态仪表盘（从审计日志聚合统计）"""
    skill_names = orchestrator.list_skills()
    result = []
    for name in skill_names:
        stats = audit.get_skill_stats(name)
        result.append(SkillStatus(
            skill_name=name,
            available=True,
            recent_execution_count=stats["recent_execution_count"],
            avg_execution_time_ms=stats["avg_execution_time_ms"],
            error_rate=stats["error_rate"],
        ))
    return result


@router.get("/audit-logs", response_model=List[AuditLogEntry])
async def query_audit_logs(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user_id: Optional[int] = None,
    skill_name: Optional[str] = None,
    workflow_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    authorization: Optional[str] = Header(None),
):
    """查询审计日志"""
    ctx = _get_context(authorization)
    # 审计日志查询需要 engineer 角色
    check_permission(ctx, "best-practice")
    params = AuditLogQuery(
        start_time=start_time,
        end_time=end_time,
        user_id=user_id,
        skill_name=skill_name,
        workflow_id=workflow_id,
        page=page,
        page_size=page_size,
    )
    return audit.query(params)
# @AI_GENERATED: end
