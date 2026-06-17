# @AI_GENERATED: Kiro v1.0
"""
测试 Algorithm Recommend Service 完整实现
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.dirname(project_root))

from backend.services.algorithm_recommend_service import get_algorithm_recommend_service


async def test_recommend():
    """测试算法推荐"""
    service = get_algorithm_recommend_service()
    
    # 测试用例 1: 光伏功率预测
    print("=" * 60)
    print("测试用例 1: 光伏功率预测")
    print("=" * 60)
    result = await service.recommend(
        description="我需要做光伏发电功率预测，基于气象数据预测未来24小时的发电量",
        data_characteristics={"data_type": "时序", "data_volume": 50000},
        business_objective="预测",
    )
    
    print(f"匹配场景数: {len(result['matched_scenarios'])}")
    for s in result['matched_scenarios'][:3]:
        print(f"  - {s['scenario_name']} (置信度: {s['confidence_score']})")
    
    print(f"\n推荐算法数: {len(result['recommendations'])}")
    for r in result['recommendations'][:5]:
        print(f"  - [{r['score']}分] {r['algorithm_name']} ({r['source']})")
        print(f"    理由: {r['rationale'][:50]}...")
    
    print(f"\n搜索算法总数: {result['total_algorithms_searched']}")
    print(f"处理时间: {result['processing_time_ms']}ms")
    
    # 测试用例 2: 负荷预测
    print("\n" + "=" * 60)
    print("测试用例 2: 电网负荷预测")
    print("=" * 60)
    result = await service.recommend(
        description="电网负荷预测，需要预测未来一周的用电负荷",
        business_objective="预测",
    )
    
    print(f"匹配场景数: {len(result['matched_scenarios'])}")
    for s in result['matched_scenarios'][:3]:
        print(f"  - {s['scenario_name']} (置信度: {s['confidence_score']})")
    
    print(f"\n推荐算法数: {len(result['recommendations'])}")
    for r in result['recommendations'][:5]:
        print(f"  - [{r['score']}分] {r['algorithm_name']} ({r['source']})")
    
    # 测试用例 3: 设备故障检测
    print("\n" + "=" * 60)
    print("测试用例 3: 设备故障检测")
    print("=" * 60)
    result = await service.recommend(
        description="钢铁厂设备故障预测，需要检测设备异常",
        business_objective="异常检测",
    )
    
    print(f"匹配场景数: {len(result['matched_scenarios'])}")
    for s in result['matched_scenarios'][:3]:
        print(f"  - {s['scenario_name']} (置信度: {s['confidence_score']})")
    
    print(f"\n推荐算法数: {len(result['recommendations'])}")
    for r in result['recommendations'][:5]:
        print(f"  - [{r['score']}分] {r['algorithm_name']} ({r['source']})")
    
    # 测试用例 4: 质量分类
    print("\n" + "=" * 60)
    print("测试用例 4: 产品质量分类")
    print("=" * 60)
    result = await service.recommend(
        description="半导体晶圆缺陷检测，需要对产品进行质量分类",
        business_objective="分类",
    )
    
    print(f"匹配场景数: {len(result['matched_scenarios'])}")
    for s in result['matched_scenarios'][:3]:
        print(f"  - {s['scenario_name']} (置信度: {s['confidence_score']})")
    
    print(f"\n推荐算法数: {len(result['recommendations'])}")
    for r in result['recommendations'][:5]:
        print(f"  - [{r['score']}分] {r['algorithm_name']} ({r['source']})")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_recommend())
# @AI_GENERATED: end
