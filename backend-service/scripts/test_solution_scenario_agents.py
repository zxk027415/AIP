# @AI_GENERATED: Kiro v1.0
"""
单独测试 SolutionSearchAgent 和 ScenarioAnalyzeAgent
"""
import asyncio
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


async def test_solution_search_agent():
    """测试 SolutionSearchAgent - 搜索解决方案库"""
    from services.curator_agent.sub_agents import SolutionSearchAgent
    
    print("=" * 60)
    print("测试 SolutionSearchAgent - 搜索解决方案库")
    print("=" * 60)
    
    agent = SolutionSearchAgent()
    
    test_queries = [
        "光伏发电功率预测",
        "负荷预测",
        "设备故障诊断",
        "储能SOC估计",
        "碳排放核算",
    ]
    
    for query in test_queries:
        print(f"\n--- 查询: {query} ---")
        result = await agent.search(query)
        
        print(f"匹配场景: {result.get('matched_scenario')}")
        print(f"关键词: {result.get('keywords')}")
        print(f"搜索总数: {result.get('total_searched')}")
        print(f"匹配结果: {len(result.get('solutions', []))} 个")
        
        if result.get('solutions'):
            print("\nTop 3 解决方案:")
            for i, sol in enumerate(result['solutions'][:3], 1):
                print(f"  {i}. {sol['name']} (score: {sol['score']}, scenario: {sol['scenario_id']})")


async def test_scenario_analyze_agent():
    """测试 ScenarioAnalyzeAgent - 分析业务场景"""
    from services.curator_agent.sub_agents import ScenarioAnalyzeAgent
    
    print("\n" + "=" * 60)
    print("测试 ScenarioAnalyzeAgent - 分析业务场景")
    print("=" * 60)
    
    agent = ScenarioAnalyzeAgent()
    
    test_queries = [
        "我想做光伏发电功率的日前预测",
        "帮我分析一下负荷预测的需求",
        "设备振动故障诊断怎么做",
        "储能电池SOC估计",
        "我需要做产品质量检测",
    ]
    
    for query in test_queries:
        print(f"\n--- 查询: {query} ---")
        result = await agent.analyze(query)
        
        print(f"场景类型: {result.get('scenario_type')}")
        print(f"能源类型: {result.get('energy_type')}")
        print(f"预测类型: {result.get('forecast_type')}")
        print(f"数据需求: {result.get('data_requirements', [])[:2]}...")
        print(f"推荐方案: {result.get('recommended_approach', '')[:80]}...")
        print(f"细化问题: {result.get('clarification_questions', [])}")


async def test_via_master_agent():
    """通过 Master Agent 测试路由到这两个子 Agent"""
    from services.curator_agent import get_curator_master_agent
    
    print("\n" + "=" * 60)
    print("通过 Master Agent 测试路由")
    print("=" * 60)
    
    master = get_curator_master_agent()
    
    test_cases = [
        {
            "query": "光伏发电功率预测怎么做",
            "expected_intent": "solution_search",
        },
        {
            "query": "帮我分析一下负荷预测的需求",
            "expected_intent": "scenario_analyze",
        },
        {
            "query": "设备故障诊断",
            "expected_intent": "solution_search",
        },
    ]
    
    for tc in test_cases:
        print(f"\n--- 查询: {tc['query']} ---")
        print(f"期望意图: {tc['expected_intent']}")
        
        result = await master.process(tc['query'])
        
        intent = result.get('intent', {})
        print(f"实际意图: {intent.get('primary_intent')} (置信度: {intent.get('confidence', 0):.2f})")
        
        if intent.get('primary_intent') == tc['expected_intent']:
            print("✅ 意图分类正确")
        else:
            print("❌ 意图分类错误")
        
        # 显示响应摘要
        response = result.get('response', '')
        print(f"响应长度: {len(response)} 字符")
        print(f"响应预览: {response[:200]}...")


if __name__ == '__main__':
    print("开始测试 SolutionSearchAgent 和 ScenarioAnalyzeAgent\n")
    
    asyncio.run(test_solution_search_agent())
    asyncio.run(test_scenario_analyze_agent())
    asyncio.run(test_via_master_agent())
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
# @AI_GENERATED: end
