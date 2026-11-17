# @AI_GENERATED: Kiro v1.0
"""
测试 LLM API 连接
"""
import httpx
import asyncio

# 你的配置
API_KEY = "sk-TXA85awOqEqrtf9cvQXoDX2a5LahvZd9qDubaVmkYiNX72lI"
API_BASE = "https://api.lkeap.cloud.tencent.com/v1"
MODEL = "deepseek-v3.1"

async def test_chat():
    """测试聊天接口"""
    url = f"{API_BASE}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    # 腾讯云 DeepSeek API 不支持 max_tokens 参数，需要去掉
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "你好，请简单介绍一下你自己。"}
        ],
        "temperature": 0.7,
    }
    
    print(f"请求 URL: {url}")
    print(f"模型: {MODEL}")
    print(f"Headers: Authorization: Bearer {API_KEY[:10]}...")
    print(f"Payload: {payload}")
    print("-" * 50)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            print(f"状态码: {response.status_code}")
            print(f"响应头: {dict(response.headers)}")
            print(f"响应内容: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"\n✅ 成功! 模型回复: {content}")
            else:
                print(f"\n❌ 失败! 状态码: {response.status_code}")
    except httpx.ConnectError as e:
        print(f"❌ 连接失败: {e}")
    except httpx.TimeoutException as e:
        print(f"❌ 超时: {e}")
    except Exception as e:
        print(f"❌ 异常: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_chat())
# @AI_GENERATED: end
