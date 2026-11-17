# @AI_GENERATED: Kiro v1.0
"""检查点 16 验证脚本 — 审计日志与 RBAC"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

errors = []

# 1. 验证 AuditLogger 导入与实例化
try:
    from services.workflow_agent.audit.audit_logger import AuditLogger
    logger = AuditLogger()
    assert logger.retention_days == 365, f"retention_days={logger.retention_days}"
    print("[PASS] AuditLogger imported and instantiated OK")
except Exception as e:
    errors.append(f"AuditLogger: {e}")
    print(f"[FAIL] AuditLogger: {e}")

# 2. 验证 audit __init__ 导出
try:
    from services.workflow_agent.audit import AuditLogger as AL2
    assert AL2 is AuditLogger
    print("[PASS] audit __init__ exports AuditLogger correctly")
except Exception as e:
    errors.append(f"audit __init__: {e}")
    print(f"[FAIL] audit __init__: {e}")

# 3. 验证 RBAC 模块
try:
    from services.workflow_agent.rbac import check_permission, SKILL_ROLE_MAP, ROLE_HIERARCHY
    from models.workflow_agent_models import SkillContext, UserRole

    # 编排类 Skills 应允许 USER 角色
    user_ctx = SkillContext(user_id=1, username="test", role=UserRole.USER)
    for skill in ["scenario-match", "algorithm-compose", "workflow-generate",
                   "workflow-validate", "template-manage"]:
        check_permission(user_ctx, skill)  # 不应抛异常
    print("[PASS] RBAC allows USER role for orchestration skills")

    # 知识类 Skills 应拒绝 USER 角色
    blocked = 0
    for skill in ["domain-constraint", "best-practice", "cross-scenario"]:
        try:
            check_permission(user_ctx, skill)
        except Exception as ex:
            if "403" in str(ex.status_code) if hasattr(ex, "status_code") else "403" in str(ex):
                blocked += 1
    assert blocked == 3, f"Expected 3 blocked, got {blocked}"
    print("[PASS] RBAC blocks USER role for knowledge skills (403)")

    # 知识类 Skills 应允许 ENGINEER 角色
    eng_ctx = SkillContext(user_id=2, username="eng", role=UserRole.ENGINEER)
    for skill in ["domain-constraint", "best-practice", "cross-scenario"]:
        check_permission(eng_ctx, skill)
    print("[PASS] RBAC allows ENGINEER role for knowledge skills")

except Exception as e:
    errors.append(f"RBAC: {e}")
    print(f"[FAIL] RBAC: {e}")

# 4. 验证 sanitize 工具
try:
    from utils.sanitize import sanitize_description, sanitize_id, validate_safe_input
    assert sanitize_id("test-id_123") == "test-id_123"
    assert len(sanitize_description("x" * 3000)) <= 2000
    print("[PASS] sanitize utilities OK")
except Exception as e:
    errors.append(f"sanitize: {e}")
    print(f"[FAIL] sanitize: {e}")

# 结果汇总
print()
if errors:
    print(f"Checkpoint 16 FAILED — {len(errors)} error(s):")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)
else:
    print("Checkpoint 16 PASSED — 审计日志和 RBAC 验证全部通过")
# @AI_GENERATED: end
