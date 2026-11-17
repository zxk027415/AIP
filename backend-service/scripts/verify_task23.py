# @AI_GENERATED: Kiro v1.0
"""
验证 Task 23 — 端到端集成、Redis 缓存、输入 Sanitize
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name} — {detail}")
        failed += 1


# ============ 23.3 输入 Sanitize ============
print("\n=== 23.3 输入 Sanitize 与安全加固 ===")

from utils.sanitize import (
    sanitize_text, sanitize_description, sanitize_id,
    check_sql_injection, check_cmd_injection, check_xss,
    validate_safe_input,
)

# 基本清理
check("sanitize_text 截断", len(sanitize_text("a" * 1000, 100)) == 100)
check("sanitize_text None", sanitize_text(None) is None)
check("sanitize_text HTML转义", "&lt;" in sanitize_text("<script>"))

# 描述清理
check("sanitize_description 移除script", "<script>" not in sanitize_description("<script>alert(1)</script>正常文本"))
check("sanitize_description 保留正常文本", "正常文本" in sanitize_description("<script>alert(1)</script>正常文本"))
check("sanitize_description 截断", len(sanitize_description("a" * 3000)) <= 2000)

# ID 清理
check("sanitize_id 只保留安全字符", sanitize_id("renewable-energy") == "renewable-energy")
check("sanitize_id 移除特殊字符", ";" not in sanitize_id("test;DROP TABLE"))
check("sanitize_id 支持中文", "新能源" in sanitize_id("新能源场景"))

# SQL 注入检测
check("SQL注入检测 SELECT", check_sql_injection("SELECT * FROM users"))
check("SQL注入检测 正常文本", not check_sql_injection("新能源发电功率预测"))
check("SQL注入检测 DROP", check_sql_injection("DROP TABLE users"))

# 命令注入检测
check("命令注入检测 rm", check_cmd_injection("rm -rf /"))
check("命令注入检测 正常文本", not check_cmd_injection("光伏功率预测"))

# XSS 检测
check("XSS检测 script", check_xss("<script>alert(1)</script>"))
check("XSS检测 正常文本", not check_xss("新能源发电功率预测"))

# 综合校验
check("validate_safe_input 正常", validate_safe_input("光伏功率预测") == "光伏功率预测")
try:
    validate_safe_input("SELECT * FROM users")
    check("validate_safe_input SQL注入拦截", False, "应抛出异常")
except ValueError:
    check("validate_safe_input SQL注入拦截", True)

try:
    validate_safe_input("<script>alert(1)</script>")
    check("validate_safe_input XSS拦截", False, "应抛出异常")
except ValueError:
    check("validate_safe_input XSS拦截", True)


# ============ 23.2 Redis 缓存 ============
print("\n=== 23.2 Redis 缓存（降级为内存缓存） ===")

from utils.cache import CacheService

cache = CacheService(prefix="test_cache", ttl=60)

# 基本 set/get
cache.set("key1", {"data": "hello"})
check("缓存 set/get", cache.get("key1") == {"data": "hello"})

# 不存在的 key
check("缓存 miss", cache.get("nonexistent") is None)

# 删除
cache.set("key2", "value2")
cache.delete("key2")
check("缓存 delete", cache.get("key2") is None)

# 中文值
cache.set("cn_key", {"场景": "新能源", "描述": "光伏功率预测"})
result = cache.get("cn_key")
check("缓存中文值", result and result["场景"] == "新能源")

# 清除前缀
cache.set("sub:a", 1)
cache.set("sub:b", 2)
count = cache.clear_prefix("sub:")
check("缓存 clear_prefix", count >= 2)

# 场景缓存和约束缓存实例
from utils.cache import scenario_cache, constraint_cache
check("scenario_cache 实例", scenario_cache.prefix == "wf_agent:scenarios")
check("constraint_cache 实例", constraint_cache.prefix == "wf_agent:constraints")


# ============ 23.1 链式流程集成（后端 chain 端点） ============
print("\n=== 23.1 链式流程集成（后端验证） ===")

from services.workflow_agent.orchestrator import SkillOrchestrator
from services.workflow_agent.skills.scenario_match import ScenarioMatchSkill
from services.workflow_agent.skills.algorithm_compose import AlgorithmComposeSkill
from services.workflow_agent.skills.workflow_generate import WorkflowGenerateSkill
from services.workflow_agent.skills.workflow_validate import WorkflowValidateSkill

orch = SkillOrchestrator()
orch.register_skill(ScenarioMatchSkill())
orch.register_skill(AlgorithmComposeSkill())
orch.register_skill(WorkflowGenerateSkill())
orch.register_skill(WorkflowValidateSkill())

check("编排器注册4个Skill", len(orch.list_skills()) >= 4)
check("编排器包含scenario-match", "scenario-match" in orch.list_skills())
check("编排器包含algorithm-compose", "algorithm-compose" in orch.list_skills())
check("编排器包含workflow-generate", "workflow-generate" in orch.list_skills())
check("编排器包含workflow-validate", "workflow-validate" in orch.list_skills())

# API 路由检查
from api.workflow_agent import router
routes = [r.path for r in router.routes]
check("API /scenario-match 端点", "/scenario-match" in str(routes))
check("API /algorithm-compose 端点", "/algorithm-compose" in str(routes))
check("API /workflow-generate 端点", "/workflow-generate" in str(routes))
check("API /workflow-validate 端点", "/workflow-validate" in str(routes))
check("API /chain 端点", "/chain" in str(routes))
check("API /skills/status 端点", "/skills/status" in str(routes))

# Sanitize 集成到 API
import inspect
src = inspect.getsource(router.routes[0].endpoint) if router.routes else ""
# 检查 workflow_agent.py 中是否导入了 sanitize
from api import workflow_agent as wa_module
wa_src = inspect.getsource(wa_module)
check("API 层集成 sanitize", "sanitize_description" in wa_src)
check("API 层集成 validate_safe_input", "validate_safe_input" in wa_src)
check("API 层集成 sanitize_id", "sanitize_id" in wa_src)


# ============ 汇总 ============
print(f"\n{'='*50}")
print(f"总计: {passed + failed} 项 | ✅ 通过: {passed} | ❌ 失败: {failed}")
if failed == 0:
    print("🎉 Task 23 全部验证通过！")
else:
    print(f"⚠️ 有 {failed} 项未通过")
sys.exit(0 if failed == 0 else 1)
# @AI_GENERATED: end
