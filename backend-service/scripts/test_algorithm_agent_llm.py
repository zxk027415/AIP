# @AI_GENERATED: Kiro v1.0
"""
测试 Algorithm Agent 的 LLM 集成
"""
import asyncio
import sys
import os

# 添加 backend 目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm_service import get_llm_service


async def test_llm_service():
    """测试 LLM 服务是否可用"""
    print("=" * 50)
    print("测试 LLM 服务")
    print("=" * 50)
    
    llm_service = await get_llm_service()
    
    if llm_service is None:
        print("❌ LLM 服务不可用 - 未找到配置")
        return False
    
    print(f"✅ LLM 服务已加载")
    print(f"   Provider: {llm_service.provider}")
    print(f"   Model: {llm_service.model}")
    print(f"   API Base: {llm_service.api_base}")
    
    # 测试连接
    print("\n测试连接...")
    result = await llm_service.test_connection("你好，请简短回复")
    
    if result["success"]:
        print(f"✅ 连接成功")
        print(f"   延迟: {result['latencyMs']}ms")
        print(f"   响应: {result['response'][:100]}...")
        return True
    else:
        print(f"❌ 连接失败: {result['error']}")
        return False


async def test_algorithm_agent_chat():
    """测试 Algorithm Agent 的 LLM 对话"""
    print("\n" + "=" * 50)
    print("测试 Algorithm Agent LLM 对话")
    print("=" * 50)
    
    from api.algorithm_agent import generate_llm_response
    
    # 模拟会话
    session = {
        "messages": [],
        "context": {},
    }
    
    test_message = "我需要做光伏发电功率预测，请给我一些建议"
    print(f"\n用户消息: {test_message}")
    
    response = await generate_llm_response(test_message, session)
    
    if response:
        print(f"\n✅ LLM 响应成功")
        print(f"响应内容:\n{response[:500]}...")
        return True
    else:
        print(f"\n❌ LLM 响应失败，将使用规则响应")
        return False


async def main():
    print("Algorithm Agent LLM 集成测试")
    print("=" * 50)
    
    # 测试 LLM 服务
    llm_ok = await test_llm_service()
    
    if llm_ok:
        # 测试 Agent 对话
        await test_algorithm_agent_chat()
    
    print("\n" + "=" * 50)
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
# @AI_GENERATED: end
