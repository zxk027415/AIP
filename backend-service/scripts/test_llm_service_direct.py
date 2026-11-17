# @AI_GENERATED: Kiro v1.0
"""
直接测试 LLMService 类
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from services.llm_service import LLMService

async def test():
    config = {
        "provider": "deepseek",
        "api_key": "sk-TXA85awOqEqrtf9cvQXoDX2a5LahvZd9qDubaVmkYiNX72lI",
        "api_base": "https://api.lkeap.cloud.tencent.com/v1",
        "model": "deepseek-v3.1",
        "max_tokens": 100,
        "temperature": 0.7,
        "completion_mode": "chat",
    }
    
    print("创建 LLMService...")
    service = LLMService(config)
    
    print("测试连接...")
    result = await service.test_connection("你好")
    
    print(f"结果: {result}")

if __name__ == "__main__":
    asyncio.run(test())
# @AI_GENERATED: end
