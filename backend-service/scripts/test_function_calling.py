# @AI_GENERATED: Kiro v1.0
"""
测试 Function Calling 功能
验证 LLM 能否自动调用工具查询算法库
"""
import asyncio
import sys
import os

# 添加 backend 目录到 path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from services.llm_service import get_llm_service
from services.agent_tools import get_tools_definition, get_tool_executor
import json


async def test_tool_executor():
    """测试工具执行器"""
    print("=" * 60)
    print("测试工具执行器")
    print("=" * 60)
    
    executor = get_tool_executor()
    
    # 测试 query_algorithm_library
    print("\n1. 测试 query_algorithm_library:")
    result = await executor.execute("query_algorithm_library", {"include_details": False})
    print(f"   行业场景: {result['summary']['industry_scenarios']}")
    print(f"   算法方案: {result['summary']['algorithm_solutions']}")
    print(f"   行业模板: {result['summary']['industry_templates']}")
    print(f"   工作流模板: {result['summary']['workflow_templates']}")
    print(f"   Skills: {result['summary']['skills_total']}")
    
    # 测试 get_skill_list
    print("\n2. 测试 get_skill_list:")
    result = await executor.execute("get_skill_list", {})
    print(f"   Skills 总数: {result['total']}")
    for s in result['skills'][:3]:
        print(f"   - {s['name']} (v{s['version']}) [{s['status']}]")
    
    # 测试 search_templates
    print("\n3. 测试 search_templates (keyword='光伏'):")
    result = await executor.execute("search_templates", {"keyword": "光伏", "max_results": 3})
    print(f"   找到: {result['total_found']} 个模板")
    for t in result['templates']:
        print(f"   - {t['name']}")


async def test_llm_with_tools():
    """测试 LLM Function Calling"""
    print("\n" + "=" * 60)
    print("测试 LLM Function Calling")
    print("=" * 60)
    
    llm_service = await get_llm_service()
    if not llm_service:
        print("❌ LLM 服务不可用，跳过测试")
        return
    
    print(f"✅ LLM 服务可用: {llm_service.provider} / {llm_service.model}")
    
    tools = get_tools_definition()
    print(f"   已定义工具: {[t['function']['name'] for t in tools]}")
    
    # 测试消息
    test_messages = [
        "算法模板有哪些？",
        "平台有多少个Skill？",
        "帮我找一下光伏相关的模板",
    ]
    
    for msg in test_messages:
        print(f"\n--- 测试: '{msg}' ---")
        
        messages = [
            {"role": "system", "content": "你是算法平台助手，可以调用工具查询算法库信息。"},
            {"role": "user", "content": msg}
        ]
        
        try:
            response = await llm_service.chat(messages, tools=tools)
            
            if response.get("tool_calls"):
                print(f"✅ LLM 请求调用工具:")
                for tc in response["tool_calls"]:
                    func_name = tc["function"]["name"]
                    func_args = tc["function"].get("arguments", "{}")
                    print(f"   - {func_name}({func_args})")
                
                # 执行工具
                executor = get_tool_executor()
                tool_results = []
                for tc in response["tool_calls"]:
                    func_name = tc["function"]["name"]
                    func_args = json.loads(tc["function"]["arguments"]) if tc["function"].get("arguments") else {}
                    result = await executor.execute(func_name, func_args)
                    tool_results.append({
                        "tool_call_id": tc["id"],
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False)
                    })
                
                # 第二次调用获取最终响应
                messages.append({
                    "role": "assistant",
                    "content": response.get("content", ""),
                    "tool_calls": response["tool_calls"]
                })
                messages.extend(tool_results)
                
                final_response = await llm_service.chat(messages)
                print(f"   最终响应 ({len(final_response.get('content', ''))} 字符):")
                print(f"   {final_response.get('content', '')[:200]}...")
            else:
                print(f"⚠️ LLM 未调用工具，直接响应:")
                print(f"   {response.get('content', '')[:200]}...")
                
        except Exception as e:
            print(f"❌ 错误: {e}")


async def main():
    await test_tool_executor()
    await test_llm_with_tools()
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
# @AI_GENERATED: end
