# @AI_GENERATED: Kiro v1.0
"""测试 Skill 打包 API"""
import requests
import json

url = "http://localhost:8000/api/skills/package"

data = {
    "template_id": "test-001",
    "template_name": "测试模板",
    "template_version": "1.0.0",
    "skill_name": "测试 Skill",
    "skill_version": "1.0.0",
    "description": "测试描述",
    "training_config": {
        "enabled": True,
        "min_samples": 30,
        "default_epochs": 80,
        "default_batch_size": 32
    },
    "resource_config": {
        "cpu": "2",
        "memory": "4Gi",
        "gpu": "optional",
        "timeout_seconds": 300
    }
}

print("发送请求数据:")
print(json.dumps(data, indent=2, ensure_ascii=False))

try:
    response = requests.post(url, json=data)
    print(f"\n状态码: {response.status_code}")
    print(f"响应: {response.text}")
except Exception as e:
    print(f"错误: {e}")
# @AI_GENERATED: end
