# @AI_GENERATED: Kiro v1.0
"""
测试 Algorithm Agent Chat API
"""
import httpx
import json

def test_chat():
    data = {
        'message': '你是什么大模型？',
        'use_llm': True
    }
    
    print("发送请求...")
    try:
        r = httpx.post(
            'http://localhost:8000/api/agent/algorithm/chat', 
            json=data, 
            timeout=60.0
        )
        print(f'Status: {r.status_code}')
        result = r.json()
        print(f'LLM Used: {result.get("llm_used")}')
        print(f'Response: {result.get("message", {}).get("content", "")[:500]}')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    test_chat()
# @AI_GENERATED: end
