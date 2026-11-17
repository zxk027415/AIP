# @AI_GENERATED: Kiro v1.0
"""
测试 list_private_templates 工具
验证能否正确查询数据库中的私有算法模板
"""
import asyncio
import sys
import os

# 添加 backend 目录到 path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from services.agent_tools import get_tool_executor
import json


async def test_list_private_templates():
    """测试 list_private_templates 工具"""
    print("=" * 60)
    print("测试 list_private_templates 工具")
    print("=" * 60)
    
    executor = get_tool_executor()
    result = await executor.list_private_templates()
    
    print(f"\n📋 查询结果:")
    print(f"  - 是否有私有模板: {result['has_private_templates']}")
    print(f"  - 摘要: {result['summary']}")
    
    print(f"\n📦 工作流模板:")
    print(f"  - 总数: {result['workflow_templates']['total']}")
    print(f"  - 状态统计: {result['workflow_templates']['status_counts']}")
    
    if result['workflow_templates']['templates']:
        print(f"\n  模板列表:")
        for t in result['workflow_templates']['templates']:
            print(f"    - {t['name']} ({t['status']}) - {t['scenario_name'] or '通用'}")
    
    print(f"\n🔧 Skills:")
    print(f"  - 总数: {result['skills']['total']}")
    print(f"  - 状态统计: {result['skills']['status_counts']}")
    
    if result['skills']['templates']:
        print(f"\n  Skill 列表:")
        for s in result['skills']['templates']:
            print(f"    - {s['name']} v{s['version']} ({s['status']})")
    
    print(f"\n✅ 测试完成!")
    return result


async def test_tool_execution():
    """测试通过 execute 方法调用工具"""
    print("\n" + "=" * 60)
    print("测试通过 execute 方法调用 list_private_templates")
    print("=" * 60)
    
    executor = get_tool_executor()
    result = await executor.execute("list_private_templates", {})
    
    print(f"\n执行结果: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}...")
    print(f"\n✅ execute 方法测试完成!")


if __name__ == "__main__":
    asyncio.run(test_list_private_templates())
    asyncio.run(test_tool_execution())
# @AI_GENERATED: end
