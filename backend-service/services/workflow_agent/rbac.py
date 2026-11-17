# @AI_GENERATED: Kiro v1.0
"""
RBAC 权限控制 — 基于角色的 Skill 访问控制
"""
from fastapi import HTTPException
from models.workflow_agent_models import SkillContext, UserRole

# 角色层级：admin > engineer > user
ROLE_HIERARCHY = {
    UserRole.USER: 0,
    UserRole.ENGINEER: 1,
    UserRole.ADMIN: 2,
}

# Skill → 最低角色要求
SKILL_ROLE_MAP = {
    # 编排类 Skills — 所有用户可访问
    "scenario-match": UserRole.USER,
    "algorithm-compose": UserRole.USER,
    "workflow-generate": UserRole.USER,
    "workflow-validate": UserRole.USER,
    "template-manage": UserRole.USER,
    # 知识类 Skills — engineer 及以上
    "domain-constraint": UserRole.ENGINEER,
    "best-practice": UserRole.ENGINEER,
    "cross-scenario": UserRole.ENGINEER,
}


def check_permission(ctx: SkillContext, skill_name: str) -> None:
    """检查用户是否有权限访问指定 Skill，无权限抛出 HTTPException 403"""
    required_role = SKILL_ROLE_MAP.get(skill_name, UserRole.USER)
    user_level = ROLE_HIERARCHY.get(ctx.role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    if user_level < required_level:
        raise HTTPException(
            status_code=403,
            detail=f"权限不足：访问 {skill_name} 需要 {required_role.value} 角色，"
                   f"当前角色为 {ctx.role.value}",
        )
# @AI_GENERATED: end
