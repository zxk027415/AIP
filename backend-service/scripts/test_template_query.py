# @AI_GENERATED: Kiro v1.0
"""
测试算法模板查询是否返回格式化的模板列表
"""
import asyncio
import sys
import os

# 添加 backend 目录到 path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from api.algorithm_agent import should_use_rule_response, generate_response

def test_keyword_detection():
    """测试关键词检测"""
    print("=" * 60)
    print("测试关键词检测")
    print("=" * 60)
    
    test_cases = [
        ("算法模板有哪些", True),
        ("有哪些模板", True),
        ("模板列表", True),
        ("查看模板", True),
        ("行业模板", True),
        ("工作流模板", True),
        ("skill列表", True),
        ("平台有什么模板", True),
        ("光伏预测", False),  # 这个应该用 LLM
        ("帮我训练模型", False),  # 这个应该用 LLM
        ("漂移检测", False),  # 这个应该用 LLM
    ]
    
    for message, expected in test_cases:
        result = should_use_rule_response(message)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{message}' -> force_rule={result} (expected={expected})")

def test_template_response():
    """测试模板查询响应"""
    print("\n" + "=" * 60)
    print("测试模板查询响应")
    print("=" * 60)
    
    test_messages = [
        "算法模板有哪些",
        "有哪些模板",
        "模板列表",
    ]
    
    for message in test_messages:
        print(f"\n--- 查询: '{message}' ---")
        content, skill_name, suggested_actions, context_update = generate_response(message, {})
        
        # 检查响应是否包含关键信息
        has_overview = "算法库总览" in content
        has_workflow = "工作流模板" in content
        has_skills = "Skills" in content
        has_table = "|" in content  # 包含表格
        
        print(f"包含算法库总览: {'✅' if has_overview else '❌'}")
        print(f"包含工作流模板: {'✅' if has_workflow else '❌'}")
        print(f"包含 Skills: {'✅' if has_skills else '❌'}")
        print(f"包含表格: {'✅' if has_table else '❌'}")
        print(f"响应长度: {len(content)} 字符")
        
        # 打印响应的前 500 字符
        print(f"\n响应预览:\n{content[:500]}...")

if __name__ == "__main__":
    test_keyword_detection()
    test_template_response()
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
# @AI_GENERATED: end
