# @AI_GENERATED: Kiro v1.0
"""
测试后端 LLM API 接口
"""
import httpx
import asyncio

BACKEND_URL = "http://localhost:8000"

async def test_backend_api():
    """测试后端 API"""
    
    # 1. 获取配置列表
    print("1. 获取配置列表...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{BACKEND_URL}/llm/configs")
            print(f"   状态码: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                configs = data.get("configs", [])
                print(f"   配置数量: {len(configs)}")
                for cfg in configs:
                    print(f"   - {cfg.get('credentialName')}: {cfg.get('model')}")
                
                # 2. 测试第二个配置（ren）
                if len(configs) >= 2:
                    config_id = configs[1].get("id")
                    print(f"\n2. 测试配置 ID: {config_id}")
                    
                    test_resp = await client.post(
                        f"{BACKEND_URL}/llm/test",
                        json={
                            "config_id": config_id,
                            "prompt": "你好"
                        }
                    )
                    print(f"   状态码: {test_resp.status_code}")
                    print(f"   响应: {test_resp.text}")
            else:
                print(f"   错误: {resp.text}")
        except httpx.ConnectError as e:
            print(f"   ❌ 无法连接到后端服务: {e}")
            print("   请确保后端服务正在运行: uvicorn main:app --reload")
        except Exception as e:
            print(f"   ❌ 异常: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_backend_api())
# @AI_GENERATED: end
