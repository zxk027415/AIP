# @AI_GENERATED: Kiro v1.0
"""
测试 Curator Master Agent 架构
验证 Master + Sub-Agent 的意图分类和路由功能
"""
import asyncio
import sys
import os

# 添加 backend 目录到 path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


async def test_master_agent():
    """测试 Master Agent"""
    from services.curator_agent import get_curator_master_agent
    
    master = get_curator_master_agent()
    
    # 测试用例
    test_cases = [
        {
            "query": "光伏发电功率预测",
            "expected_intent": "solution_search",
            "description": "搜索解决方案场景",
        },
        {
            "query": "有哪些算法模板？",
            "expected_intent": "template_recommend",
            "description": "查询算法模板",
        },
        {
            "query": "我有私有模板吗？",
            "expected_intent": "template_recommend",
            "description": "查询私有模板",
        },
        {
            "query": "帮我分析一下负荷预测的需求",
            "expected_intent": "scenario_analyze",
            "description": "场景分析",
        },
        {
            "query": "推荐一个光伏功率预测的工作流模板",
            "expected_intent": "template_recommend",
            "description": "推荐模板（同时提到解决方案和模板）",
        },
    ]
    
    print("=" * 60)
    print("Curator Master Agent 测试")
    print("=" * 60)
    
    for i, tc in enumerate(test_cases, 1):
        print(f"\n--- 测试 {i}: {tc['description']} ---")
        print(f"查询: {tc['query']}")
        
        # 测试意图分类
        intent = master.classify_intent(tc["query"])
        print(f"意图分类: {intent['primary_intent']} (置信度: {intent['confidence']:.2f})")
        print(f"匹配关键词: {intent['keywords']}")
        
        if intent["primary_intent"] == tc["expected_intent"]:
            print("✅ 意图分类正确")
        else:
            print(f"❌ 意图分类错误，期望: {tc['expected_intent']}")
        
        # 测试完整处理流程
        print("\n处理中...")
        result = await master.process(tc["query"])
        
        print(f"响应长度: {len(result['response'])} 字符")
        print(f"建议操作: {[a['label'] for a in result['suggested_actions']]}")
        
        # 显示响应摘要
        response_preview = result["response"][:300] + "..." if len(result["response"]) > 300 else result["response"]
        print(f"\n响应预览:\n{response_preview}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


async def test_sub_agents():
    """单独测试各个子 Agent"""
    from services.curator_agent.sub_agents import (
        SolutionSearchAgent,
        TemplateRecommendAgent,
        ScenarioAnalyzeAgent,
    )
    
    print("\n" + "=" * 60)
    print("Sub-Agent 单独测试")
    print("=" * 60)
    
    # 测试 SolutionSearchAgent
    print("\n--- SolutionSearchAgent ---")
    solution_agent = SolutionSearchAgent()
    result = await solution_agent.search("光伏发电功率预测")
    print(f"搜索到 {len(result['solutions'])} 个解决方案")
    print(f"总共搜索 {result['total_searched']} 个")
    if result["solutions"]:
        print(f"Top 1: {result['solutions'][0]['name']} (score: {result['solutions'][0]['score']})")
    
    # 测试 TemplateRecommendAgent
    print("\n--- TemplateRecommendAgent ---")
    template_agent = TemplateRecommendAgent()
    result = await template_agent.recommend("光伏功率预测")
    print(f"推荐 {len(result['workflow_templates'])} 个工作流模板")
    print(f"推荐 {len(result['skills'])} 个 Skills")
    print(f"系统共有 {result['total_workflows']} 个工作流模板，{result['total_skills']} 个 Skills")
    
    # 测试列出所有模板
    print("\n--- TemplateRecommendAgent.list_all ---")
    all_templates = await template_agent.list_all()
    print(f"工作流模板: {all_templates['summary']['total_workflows']} 个")
    print(f"Skills: {all_templates['summary']['total_skills']} 个")
    
    # 测试 ScenarioAnalyzeAgent
    print("\n--- ScenarioAnalyzeAgent ---")
    scenario_agent = ScenarioAnalyzeAgent()
    result = await scenario_agent.analyze("我想做光伏发电功率的日前预测")
    print(f"场景类型: {result['scenario_type']}")
    print(f"能源类型: {result['energy_type']}")
    print(f"预测类型: {result['forecast_type']}")
    print(f"数据需求: {result['data_requirements'][:2]}...")
    print(f"推荐方案: {result['recommended_approach'][:100]}...")
    print(f"细化问题: {result['clarification_questions']}")


if __name__ == "__main__":
    print("开始测试 Curator Master Agent 架构\n")
    
    # 运行测试
    asyncio.run(test_master_agent())
    asyncio.run(test_sub_agents())
# @AI_GENERATED: end
