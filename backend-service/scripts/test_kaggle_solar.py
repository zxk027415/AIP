# @AI_GENERATED: Kiro v1.0
"""
测试 Kaggle 太阳能预测执行服务 - 使用通用函数ID

运行方式: python scripts/test_kaggle_solar.py
"""
import sys
import os

# 添加 backend 目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.kaggle_solar_execution_service import KaggleSolarExecutionService


def test_full_pipeline():
    """测试完整的 ML 流水线 - 使用通用函数ID"""
    print("=" * 60)
    print("Kaggle 太阳能预测 - 完整 ML 流水线测试")
    print("使用基础算法库通用函数ID")
    print("=" * 60)
    
    service = KaggleSolarExecutionService()
    
    # 1. 加载数据 - 使用通用 load_dataset
    print("\n1. 加载数据 (load_dataset)...")
    data_result = service.execute_function('load_dataset', {
        'dataset_id': 'kaggle-solar-india',
        'time_column': 'DATE_TIME',
        'target_column': 'DC_POWER'
    }, {})
    print(f"   加载 {data_result['rows']} 条记录")
    print(f"   列: {data_result['columns']}")
    
    # 2. 数据探索 - 使用通用 descriptive_stats
    print("\n2. 数据探索 (descriptive_stats)...")
    exploration = service.execute_function('descriptive_stats', {}, {'data': data_result})
    print(f"   统计列: {list(exploration['statistics'].keys())}")
    for col, stats in list(exploration['statistics'].items())[:3]:
        print(f"   {col}: mean={stats['mean']:.2f}, std={stats['std']:.2f}")
    
    # 3. 特征工程 - 使用通用 extract_time_features
    print("\n3. 特征工程 (extract_time_features)...")
    feature_result = service.execute_function('extract_time_features', {
        'time_column': 'DATE_TIME',
        'add_time_features': True,
        'add_cyclic_features': True
    }, {'data': data_result})
    print(f"   新增特征: {feature_result['features_added']}")
    print(f"   总列数: {len(feature_result['columns'])}")
    
    # 4. 数据划分 - 使用通用 train_test_split
    print("\n4. 数据划分 (train_test_split)...")
    split_result = service.execute_function('train_test_split', {
        'test_ratio': 0.2,
        'target_column': 'DC_POWER',
        'feature_columns': ['IRRADIATION', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE',
                           'HOUR_SIN', 'HOUR_COS', 'TEMP_DIFF']
    }, {'data': feature_result})
    print(f"   训练集: {split_result['train_size']} 样本")
    print(f"   测试集: {split_result['test_size']} 样本")
    print(f"   特征: {split_result['feature_columns']}")
    
    # 5. 训练模型 - 使用通用回归函数
    print("\n5. 训练模型...")
    
    # 线性回归 - 使用通用 linear_regression
    print("   5.1 线性回归 (linear_regression)...")
    lr_result = service.execute_function('linear_regression', {'regularization': 'none'}, split_result)
    lr_eval = service.execute_function('regression_metrics', {}, lr_result)
    print(f"       训练集 R²: {lr_eval['train_metrics']['r2']:.4f}")
    print(f"       测试集 R²: {lr_eval['test_metrics']['r2']:.4f}")
    
    # 随机森林 - 使用通用 random_forest_regression
    print("   5.2 随机森林 (random_forest_regression)...")
    rf_result = service.execute_function('random_forest_regression', {
        'n_estimators': 20,
        'max_depth': 8
    }, split_result)
    rf_eval = service.execute_function('regression_metrics', {}, rf_result)
    print(f"       训练集 R²: {rf_eval['train_metrics']['r2']:.4f}")
    print(f"       测试集 R²: {rf_eval['test_metrics']['r2']:.4f}")
    
    # XGBoost - 使用通用 xgboost_regression
    print("   5.3 XGBoost (xgboost_regression)...")
    xgb_result = service.execute_function('xgboost_regression', {
        'n_estimators': 100,
        'learning_rate': 0.1,
        'max_depth': 5
    }, split_result)
    xgb_eval = service.execute_function('regression_metrics', {}, xgb_result)
    print(f"       训练集 R²: {xgb_eval['train_metrics']['r2']:.4f}")
    print(f"       测试集 R²: {xgb_eval['test_metrics']['r2']:.4f}")
    
    # 6. 模型比较
    print("\n6. 模型比较:")
    print("-" * 50)
    print(f"{'模型':<20} {'训练R²':<12} {'测试R²':<12} {'测试RMSE':<12}")
    print("-" * 50)
    print(f"{'线性回归':<20} {lr_eval['train_metrics']['r2']:<12.4f} {lr_eval['test_metrics']['r2']:<12.4f} {lr_eval['test_metrics']['rmse']:<12.2f}")
    print(f"{'随机森林':<20} {rf_eval['train_metrics']['r2']:<12.4f} {rf_eval['test_metrics']['r2']:<12.4f} {rf_eval['test_metrics']['rmse']:<12.2f}")
    print(f"{'XGBoost':<20} {xgb_eval['train_metrics']['r2']:<12.4f} {xgb_eval['test_metrics']['r2']:<12.4f} {xgb_eval['test_metrics']['rmse']:<12.2f}")
    print("-" * 50)
    
    # 7. 可视化测试 - 使用通用图表函数
    print("\n7. 可视化测试...")
    scatter_plot = service.execute_function('scatter_plot', {
        'title': 'XGBoost预测结果'
    }, xgb_result)
    print(f"   散点图数据点: {scatter_plot['data']['n_samples']}")
    
    importance_plot = service.execute_function('bar_chart', {
        'title': '随机森林特征重要性',
        'feature_columns': split_result['feature_columns']
    }, rf_result)
    print(f"   特征重要性: {importance_plot['data']['feature_names']}")
    
    # 8. 结果总结
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    # 检查是否达到目标
    best_r2 = max(lr_eval['test_metrics']['r2'], 
                  rf_eval['test_metrics']['r2'], 
                  xgb_eval['test_metrics']['r2'])
    
    if best_r2 >= 0.90:
        print(f"\n✅ 最佳测试集 R² = {best_r2:.4f} (目标: ≥0.90)")
        print("   已达到 Kaggle 论文参考指标！")
    else:
        print(f"\n⚠️ 最佳测试集 R² = {best_r2:.4f} (目标: ≥0.90)")
        print("   需要进一步优化模型参数")
    
    return {
        'linear_regression': lr_eval['test_metrics'],
        'random_forest': rf_eval['test_metrics'],
        'xgboost': xgb_eval['test_metrics']
    }


if __name__ == '__main__':
    results = test_full_pipeline()
# @AI_GENERATED: end
