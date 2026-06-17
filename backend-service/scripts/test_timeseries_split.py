# @AI_GENERATED: Kiro v1.0
"""
测试时序数据划分函数

验证 timeseries_split, timeseries_normalize, walk_forward_split 函数
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.pv_execution_service import PVExecutionService


def test_timeseries_split():
    """测试时序划分函数"""
    print("=" * 70)
    print("测试 timeseries_split 函数")
    print("=" * 70)
    
    service = PVExecutionService()
    
    # 加载数据
    data = service._load_pv_demo()
    print(f"\n原始数据: {data['rows']} 行")
    
    # 测试时序划分（不打乱）
    result = service._timeseries_split({
        'data': data,
        'test_ratio': 0.2,
        'filter_valid': True,
        'shuffle': False  # 关键：不打乱
    })
    
    print(f"\n时序划分结果:")
    print(f"  训练集: {result['train_size']} 样本")
    print(f"  测试集: {result['test_size']} 样本")
    print(f"  划分方法: {result['split_method']}")
    print(f"  是否打乱: {result['shuffle']}")
    
    if 'train_time_range' in result:
        print(f"  训练集时间: {result['train_time_range'][0]} ~ {result['train_time_range'][1]}")
    if 'test_time_range' in result:
        print(f"  测试集时间: {result['test_time_range'][0]} ~ {result['test_time_range'][1]}")
    
    return result


def test_timeseries_normalize(split_result):
    """测试时序归一化函数"""
    print("\n" + "=" * 70)
    print("测试 timeseries_normalize 函数")
    print("=" * 70)
    
    service = PVExecutionService()
    
    # 测试归一化（仅用训练集统计量）
    result = service._timeseries_normalize({
        'train_data': split_result['train'],
        'test_data': split_result['test'],
        'method': 'minmax',
        'feature_range': [0, 1]
    })
    
    print(f"\n归一化结果:")
    print(f"  方法: {result['method']}")
    print(f"  训练集: {result['train_normalized']['rows']} 样本")
    
    if 'test_normalized' in result:
        print(f"  测试集: {result['test_normalized']['rows']} 样本")
        print(f"  测试集超出范围的值: {result.get('test_out_of_range_count', 0)} 个")
    
    # 显示统计量
    print(f"\n统计量（仅从训练集计算）:")
    columns = split_result['train']['columns']
    for col_idx, stats in result['stats'].items():
        col_name = columns[col_idx] if col_idx < len(columns) else f"col_{col_idx}"
        if 'min' in stats:
            print(f"  {col_name}: min={stats['min']:.4f}, max={stats['max']:.4f}")
        else:
            print(f"  {col_name}: mean={stats['mean']:.4f}, std={stats['std']:.4f}")
    
    return result


def test_walk_forward_split():
    """测试滚动窗口划分函数"""
    print("\n" + "=" * 70)
    print("测试 walk_forward_split 函数")
    print("=" * 70)
    
    service = PVExecutionService()
    
    # 加载数据
    data = service._load_pv_demo()
    
    # 测试滚动窗口划分
    result = service._walk_forward_split({
        'data': data,
        'n_splits': 3,
        'expanding': True
    })
    
    print(f"\n滚动窗口划分结果:")
    print(f"  总样本数: {result['total_samples']}")
    print(f"  划分次数: {result['n_splits']}")
    print(f"  测试窗口大小: {result['test_size']}")
    print(f"  扩展窗口: {result['expanding']}")
    
    print(f"\n各折详情:")
    for split in result['splits']:
        print(f"  Fold {split['fold']}: 训练 {split['train_size']} 样本, 测试 {split['test_size']} 样本")
        print(f"    训练索引: {split['train_indices']}")
        print(f"    测试索引: {split['test_indices']}")
    
    return result


def test_full_pipeline():
    """测试完整的无泄露流程"""
    print("\n" + "=" * 70)
    print("测试完整的无泄露流程")
    print("=" * 70)
    
    service = PVExecutionService()
    
    # 1. 加载数据
    print("\n1. 加载数据...")
    data = service._load_pv_demo()
    
    # 2. 时序划分（不打乱）
    print("2. 时序划分...")
    split_result = service._timeseries_split({
        'data': data,
        'test_ratio': 0.2,
        'filter_valid': True,
        'shuffle': False
    })
    
    # 3. 归一化（仅用训练集统计量）
    print("3. 归一化（仅用训练集统计量）...")
    norm_result = service._timeseries_normalize({
        'train_data': split_result['train'],
        'test_data': split_result['test'],
        'method': 'minmax'
    })
    
    # 4. 训练模型
    print("4. 训练模型...")
    # 提取特征和目标
    train_data = norm_result['train_normalized']['data']
    test_data = norm_result['test_normalized']['data']
    columns = norm_result['train_normalized']['columns']
    
    # 找到目标列
    power_col_idx = -1
    for i, col in enumerate(columns):
        if 'power' in col.lower():
            power_col_idx = i
            break
    
    # 准备训练数据
    X_train = [[row[i] for i in range(1, power_col_idx)] for row in train_data]
    y_train = [row[power_col_idx] for row in train_data]
    X_test = [[row[i] for i in range(1, power_col_idx)] for row in test_data]
    y_test = [row[power_col_idx] for row in test_data]
    
    # 使用 Ridge 回归
    forecast_result = service._xgboost_forecast({
        'train_data': {
            'columns': columns,
            'data': train_data,
            'rows': len(train_data)
        },
        'split_data': {
            'train': norm_result['train_normalized'],
            'test': norm_result['test_normalized']
        }
    })
    
    # 5. 评估
    print("5. 评估模型...")
    if forecast_result.get('predictions') and forecast_result.get('actuals'):
        mape_result = service._mape_metric({
            'y_true': forecast_result['actuals'],
            'y_pred': forecast_result['predictions']
        })
        r2_result = service._r2_metric({
            'y_true': forecast_result['actuals'],
            'y_pred': forecast_result['predictions']
        })
        
        print(f"\n测试集评估结果（无数据泄露）:")
        print(f"  R²: {r2_result['r2']}")
        print(f"  MAPE: {mape_result['mape']}%")
        print(f"  样本数: {mape_result['n_samples']}")
    else:
        print("  无测试集预测结果")
    
    print("\n✅ 完整流程测试完成")


def main():
    # 测试各个函数
    split_result = test_timeseries_split()
    test_timeseries_normalize(split_result)
    test_walk_forward_split()
    
    # 测试完整流程
    test_full_pipeline()
    
    print("\n" + "=" * 70)
    print("所有测试完成")
    print("=" * 70)


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
