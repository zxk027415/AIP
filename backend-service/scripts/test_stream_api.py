# @AI_GENERATED: Kiro v1.0
"""
模拟前端调用流式 API 测试
"""
import asyncio
import sys
import os
import json

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


async def test_stream_endpoint():
    """直接测试 chat_stream 端点的 generate 函数"""
    from api.algorithm_agent import chat_stream, ChatRequest, SessionContext, sessions
    
    # 构造请求 - 使用 SessionContext 模型
    context = SessionContext(agent_type="curator")
    request = ChatRequest(
        session_id="test-stream-session-2",
        message="有哪些算法模板？",
        context=context,
        use_llm=True,
    )
    
    print("=" * 60)
    print("测试流式 API 端点")
    print("=" * 60)
    print(f"消息: {request.message}")
    print(f"context: {request.context}")
    print(f"agent_type: {request.context.agent_type if request.context else None}")
    print("-" * 60)
    
    # 调用端点
    response = await chat_stream(request)
    
    # 读取流式响应
    print("\n流式响应内容:")
    full_content = ""
    async for chunk in response.body_iterator:
        chunk_str = chunk.decode() if isinstance(chunk, bytes) else chunk
        
        # 解析 SSE 数据
        for line in chunk_str.split('\n'):
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])
                    if data.get('type') == 'chunk':
                        full_content += data.get('content', '')
                    elif data.get('type') == 'start':
                        print(f"  [START] session_id: {data.get('session_id')}")
                    elif data.get('type') == 'done':
                        print(f"  [DONE] llm_used: {data.get('llm_used')}")
                except:
                    pass
    
    print("\n" + "=" * 60)
    print("完整响应内容:")
    print("=" * 60)
    print(full_content)
    
    # 检查 session 中的 context
    session_id = "test-stream-session-2"
    if session_id in sessions:
        session = sessions[session_id]
        print(f"\nSession context: {session.get('context', {})}")


if __name__ == '__main__':
    asyncio.run(test_stream_endpoint())
# @AI_GENERATED: end
