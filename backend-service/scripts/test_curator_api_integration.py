# @AI_GENERATED: Kiro v1.0
"""
测试 Curator Agent API 集成
模拟实际 API 调用流程，验证 Master Agent 架构在 API 层面的工作
"""
import asyncio
import sys
import os

# 添加 backend 目录到 path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


async def test_generate_llm_response():
    """测试 generate_llm_response 函数对 curator agent 的处理"""
    from api.algorithm_agent import generate_llm_response
    
    print("=" * 60)
    print("测试 generate_llm_response 对 Curator Agent 的处理")
    print("=" * 60)
    
    # 模拟 session
    session = {
        "id": "test-session",
        "messages": [],
        "context": {
            "agent_type": "curator",  # 关键：设置为 curator
        },
    }
    
    test_queries = [
        "光伏发电功率预测",
        "有哪些算法模板？",
        "推荐一个负荷预测的工作流模板",
    ]
    
    for query in test_queries:
        print(f"\n--- 查询: {query} ---")
        
        response = await generate_llm_response(query, session)
        
        if response:
            print(f"✅ 响应成功，长度: {len(response)} 字符")
            # 显示响应摘要
            preview = response[:400] + "..." if len(response) > 400 else response
            print(f"响应预览:\n{preview}")
        else:
            print("❌ 响应失败")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


async def test_non_curator_agent():
    """测试非 curator agent 类型仍然使用原有逻辑"""
    from api.algorithm_agent import generate_llm_response
    
    print("\n" + "=" * 60)
    print("测试非 Curator Agent 类型（应使用 LLM + Function Calling）")
    print("=" * 60)
    
    # 模拟 session - sandbox agent
    session = {
        "id": "test-session-2",
        "messages": [],
        "context": {
            "agent_type": "sandbox",  # 非 curator
        },
    }
    
    query = "帮我训练一个光伏预测模型"
    print(f"\n查询: {query}")
    print(f"Agent 类型: sandbox")
    
    response = await generate_llm_response(query, session)
    
    if response:
        print(f"✅ 响应成功，长度: {len(response)} 字符")
        preview = response[:300] + "..." if len(response) > 300 else response
        print(f"响应预览:\n{preview}")
    else:
        print("⚠️ LLM 服务不可用（这是预期的，如果没有配置 LLM）")


if __name__ == "__main__":
    print("开始测试 Curator Agent API 集成\n")
    
    asyncio.run(test_generate_llm_response())
    asyncio.run(test_non_curator_agent())
# @AI_GENERATED: end
