# @AI_GENERATED: Kiro v1.0
"""
测试 LLM 是否能正确调用 recommend_templates_for_scenario 工具
模拟用户描述业务场景的情况
"""
import asyncio
import sys
import os
import json

# 添加 backend 目录到 path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from services.llm_service import get_llm_service
from services.agent_tools import get_tools_definition, get_tool_executor


async def test_scenario_recommendation():
    """测试场景推荐"""
    print("=" * 60)
    print("测试 LLM Function Calling - 场景推荐")
    print("=" * 60)
    
    llm_service = await get_llm_service()
    if not llm_service:
        print("❌ LLM 服务不可用")
        return
    
    print(f"✅ LLM 服务可用: {llm_service.provider} / {llm_service.model}")
    
    # 获取工具定义
    tools = get_tools_definition()
    print(f"\n📋 可用工具数量: {len(tools)}")
    
    # 系统提示词
    system_prompt = """你是 Curator Agent（算法策划助手），专门帮助用户搜索和推荐AI解决方案。

**最重要的规则：当用户描述业务场景时，必须立即调用 recommend_templates_for_scenario 工具！**

例如用户说：
- "帮我搜索适合光伏发电功率预测的AI解决方案" → 立即调用 recommend_templates_for_scenario(scenario_description="光伏发电功率预测")
- "我需要做负荷预测" → 立即调用 recommend_templates_for_scenario(scenario_description="负荷预测")

**工具调用规则**：
| 用户意图 | 必须调用的工具 |
|---------|--------------|
| 描述具体业务场景 | recommend_templates_for_scenario |
| 问"我有私有模板吗？" | list_private_templates |

不要编造数据，必须从工具返回的结果中获取。"""
    
    # 用户消息
    user_message = "帮我搜索适合光伏发电功率预测的AI解决方案"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    print(f"\n🗣️ 用户问题: {user_message}")
    print("\n⏳ 调用 LLM (with tools)...")
    
    # 第一次调用 LLM
    response = await llm_service.chat(messages, tools=tools)
    
    print(f"\n📤 LLM 响应:")
    print(f"  - content: {response.get('content', '')[:100]}...")
    print(f"  - tool_calls: {response.get('tool_calls')}")
    
    # 检查是否有工具调用
    tool_calls = response.get("tool_calls")
    if tool_calls:
        print(f"\n✅ LLM 请求调用工具!")
        
        tool_executor = get_tool_executor()
        tool_results = []
        
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            func_args = json.loads(tc["function"]["arguments"]) if tc["function"].get("arguments") else {}
            
            print(f"\n🔧 执行工具: {func_name}")
            print(f"   参数: {func_args}")
            result = await tool_executor.execute(func_name, func_args)
            
            print(f"   结果摘要: {result.get('recommendation_summary', result.get('summary', str(result)[:100]))}")
            
            if result.get('recommended_workflow_templates'):
                print(f"   推荐的工作流模板:")
                for t in result['recommended_workflow_templates'][:3]:
                    print(f"     - {t['name']} (匹配度: {t['score']}%)")
            
            if result.get('recommended_skills'):
                print(f"   推荐的 Skills:")
                for s in result['recommended_skills'][:3]:
                    print(f"     - {s['name']} (匹配度: {s['score']}%)")
            
            tool_results.append({
                "tool_call_id": tc["id"],
                "role": "tool",
                "content": json.dumps(result, ensure_ascii=False)
            })
        
        # 将工具调用结果添加到消息中
        messages.append({
            "role": "assistant",
            "content": response.get("content", ""),
            "tool_calls": tool_calls
        })
        messages.extend(tool_results)
        
        # 第二次调用 LLM
        print("\n⏳ 基于工具结果生成最终响应...")
        final_response = await llm_service.chat(messages)
        final_content = final_response.get("content", "")
        
        print(f"\n📝 最终响应:\n{final_content[:1000]}...")
    else:
        print(f"\n⚠️ LLM 没有调用工具，直接返回了响应:")
        print(response.get("content", "")[:500])


if __name__ == "__main__":
    asyncio.run(test_scenario_recommendation())
# @AI_GENERATED: end
