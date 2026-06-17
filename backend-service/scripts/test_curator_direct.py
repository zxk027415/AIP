# @AI_GENERATED: Kiro v1.0
"""
直接测试 Curator Agent 的 generate_llm_response 函数
"""
import asyncio
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


async def test():
    from api.algorithm_agent import generate_llm_response
    
    # 模拟 curator agent 的 session
    session = {
        'id': 'test',
        'messages': [],
        'context': {
            'agent_type': 'curator'
        }
    }
    
    query = '有哪些算法模板？'
    agent_type = session['context'].get('agent_type')
    
    print(f'测试查询: {query}')
    print(f'agent_type: {agent_type}')
    print('-' * 50)
    
    response = await generate_llm_response(query, session)
    
    print(f'\n响应长度: {len(response) if response else 0}')
    print(f'\n响应内容:\n{response if response else "无响应"}')


if __name__ == '__main__':
    asyncio.run(test())
# @AI_GENERATED: end
