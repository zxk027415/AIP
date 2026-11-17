# @AI_GENERATED: Kiro v1.0
"""
测试 Algorithm Recommend API 端点
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.dirname(project_root))

from pydantic import BaseModel
from typing import Optional, Dict, Any


class AlgorithmRecommendRequest(BaseModel):
    description: str
    data_characteristics: Optional[Dict[str, Any]] = None
    business_objective: Optional[str] = None


async def test_api():
    """测试 API 端点"""
    # 导入 API 函数
    from backend.api.algorithm_agent import recommend_algorithm
    
    print("=" * 60)
    print("测试 Algorithm Recommend API")
    print("=" * 60)
    
    # 测试用例 1
    request = AlgorithmRecommendRequest(
        description="我需要做光伏发电功率预测，基于气象数据预测未来24小时的发电量",
        data_characteristics={"data_type": "时序", "data_volume": 50000},
        business_objective="预测",
    )
    
    result = await recommend_algorithm(request)
    
    print(f"\n请求: {request.description[:50]}...")
    print(f"匹配场景数: {len(result.get('matched_scenarios', []))}")
    print(f"推荐算法数: {len(result.get('recommendations', []))}")
    print(f"搜索算法总数: {result.get('total_algorithms_searched', 0)}")
    print(f"处理时间: {result.get('processing_time_ms', 0)}ms")
    
    print("\n推荐结果:")
    for i, rec in enumerate(result.get('recommendations', [])[:5], 1):
        print(f"  {i}. [{rec['score']}分] {rec['algorithm_name']}")
        print(f"     来源: {rec['source']}")
        if rec.get('scenario_name'):
            print(f"     场景: {rec['scenario_name']}")
        print(f"     理由: {rec['rationale'][:60]}...")
    
    print("\n" + "=" * 60)
    print("API 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_api())
# @AI_GENERATED: end
