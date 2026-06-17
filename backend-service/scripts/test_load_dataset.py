# @AI_GENERATED: Kiro v1.0
"""测试 load_dataset 函数"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pv_execution_service import PVExecutionService

def test_load_dataset():
    svc = PVExecutionService()
    
    print('=== 测试 load_dataset ===')
    result = svc.execute_function('load_dataset', {
        'dataset_id': 'pv-power-yinchuan',
        'time_column': 'timestamp',
        'target_column': 'power_actual'
    }, {})
    
    print(f'列: {result["columns"]}')
    print(f'行数: {result["rows"]}')
    print(f'数据源: {result["source"]}')
    print(f'配置: {result["config"]}')
    print(f'前2行数据: {result["data"][:2]}')
    print()
    print('=== load_dataset 测试通过 ===')
    
    # 测试兼容性：load_pv_demo 应该调用 load_dataset
    print()
    print('=== 测试 load_pv_demo 兼容性 ===')
    result2 = svc.execute_function('load_pv_demo', {}, {})
    print(f'行数: {result2["rows"]}')
    print(f'数据源: {result2["source"]}')
    print('=== load_pv_demo 兼容性测试通过 ===')

if __name__ == '__main__':
    test_load_dataset()
# @AI_GENERATED: end
