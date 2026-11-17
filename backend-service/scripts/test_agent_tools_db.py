# @AI_GENERATED: Kiro v1.0
"""
测试 Agent Tools 从数据库读取数据
"""
import asyncio
import sys
import os
import io

# 设置输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.agent_tools import get_tool_executor, get_tools_definition


async def test_tools():
    executor = get_tool_executor()
    
    print("=" * 60)
    print("测试 1: 查询算法库概览")
    print("=" * 60)
    result = await executor.execute("query_algorithm_library", {})
    print(f"行业场景: {result['summary']['industry_scenarios']}")
    print(f"工作流模板: {result['summary']['workflow_templates']}")
    print(f"Skills: {result['summary']['skills_total']}")
    print(f"\n工作流模板列表:")
    for w in result.get("workflow_templates", [])[:3]:
        print(f"  - {w['name']} ({w['status']})")
    print(f"\nSkills 列表:")
    for s in result.get("skills", [])[:3]:
        print(f"  - {s['skill_name']} v{s['skill_version']} ({s['status']})")
    
    print("\n" + "=" * 60)
    print("测试 2: 获取工作流模板列表")
    print("=" * 60)
    result = await executor.execute("get_workflow_templates", {})
    print(f"总数: {result['total']}")
    for t in result["templates"]:
        print(f"  - {t['name']} | {t['status']} | {t['category']} | 节点:{t['node_count']}")
    
    print("\n" + "=" * 60)
    print("测试 3: 获取 Skills 列表")
    print("=" * 60)
    result = await executor.execute("get_skill_list", {})
    print(f"总数: {result['total']}")
    for s in result["skills"]:
        print(f"  - {s['name']} v{s['version']} | {s['status']} | 来源:{s['source_template']}")
    
    print("\n" + "=" * 60)
    print("测试 4: 场景推荐 - 光伏发电功率预测")
    print("=" * 60)
    result = await executor.execute("recommend_templates_for_scenario", {
        "scenario_description": "光伏发电功率预测，需要基于气象数据预测未来24小时的发电功率"
    })
    print(f"匹配场景: {result.get('matched_scenario')}")
    print(f"匹配预测类型: {result.get('matched_forecast_type')}")
    print(f"是否有私有模板: {result.get('has_private_templates')}")
    print(f"推荐摘要: {result['recommendation_summary']}")
    print(f"\n🔧 推荐工作流模板（私有）:")
    for w in result["recommended_workflow_templates"]:
        print(f"  ⭐ {w['name']} (匹配度:{w['score']}%) - {w['status']}")
        print(f"     {w['description'][:60]}...")
    print(f"\n⚡ 推荐 Skills（私有）:")
    for s in result["recommended_skills"]:
        print(f"  ⭐ {s['name']} v{s['version']} (匹配度:{s['score']}%) - {s['status']}")
    if result.get("fallback_action"):
        print(f"\n⚠️ 降级操作: {result['fallback_action']['message']}")
    
    print("\n" + "=" * 60)
    print("测试 5: 场景推荐 - 设备故障诊断")
    print("=" * 60)
    result = await executor.execute("recommend_templates_for_scenario", {
        "scenario_description": "设备振动故障诊断，需要分析振动信号识别故障类型"
    })
    print(f"匹配场景: {result.get('matched_scenario')}")
    print(f"是否有私有模板: {result.get('has_private_templates')}")
    print(f"推荐摘要: {result['recommendation_summary']}")
    print(f"\n🔧 推荐工作流模板:")
    for w in result["recommended_workflow_templates"]:
        print(f"  ⭐ {w['name']} (匹配度:{w['score']}%)")
    
    print("\n" + "=" * 60)
    print("测试 6: 场景推荐 - 无匹配场景")
    print("=" * 60)
    result = await executor.execute("recommend_templates_for_scenario", {
        "scenario_description": "图像分类任务，识别猫和狗"
    })
    print(f"匹配场景: {result.get('matched_scenario')}")
    print(f"是否有私有模板: {result.get('has_private_templates')}")
    print(f"推荐摘要: {result['recommendation_summary']}")
    if result.get("fallback_action"):
        print(f"⚠️ 降级操作: {result['fallback_action']['message']}")
        print(f"   跳转链接: {result['fallback_action']['url']}")
    
    print("\n" + "=" * 60)
    print("工具定义列表")
    print("=" * 60)
    tools = get_tools_definition()
    for t in tools:
        print(f"  - {t['function']['name']}: {t['function']['description'][:60]}...")


if __name__ == "__main__":
    asyncio.run(test_tools())
# @AI_GENERATED: end
