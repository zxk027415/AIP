# @AI_GENERATED: Kiro v1.0
"""
测试光伏发电预测工作流执行

验证 workflow-pv-power-demo.json 中的所有通用函数是否正确执行
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.pv_execution_service import PVExecutionService


def test_pv_workflow():
    """测试光伏预测工作流的完整执行流程"""
    service = PVExecutionService()
    
    print("=" * 60)
    print("光伏发电预测工作流测试")
    print("=" * 60)
    
    # 1. 加载数据集
    print("\n[1/9] 测试 load_dataset...")
    data = service.execute_function('load_dataset', {
        'dataset_id': 'pv-power-yinchuan',
        'time_column': 'timestamp',
        'target_column': 'power_actual'
    }, {})
    print(f"  ✓ 加载数据: {data['rows']} 行, {data['cols']} 列")
    print(f"  ✓ 数据源: {data.get('source', 'unknown')}")
    
    # 2. 缺失值处理
    print("\n[2/9] 测试 handle_missing...")
    cleaned = service.execute_function('handle_missing', {
        'method': 'interpolate'
    }, {'data': data})
    print(f"  ✓ 处理后: {cleaned['rows']} 行")
    print(f"  ✓ 填充缺失值: {cleaned.get('missing_filled', 0)} 个")
    
    # 3. 数据标准化
    print("\n[3/9] 测试 min_max_scale...")
    scaled = service.execute_function('min_max_scale', {
        'feature_range': [0, 1]
    }, {'data': cleaned})
    print(f"  ✓ 归一化完成: {scaled['rows']} 行")
    print(f"  ✓ 范围: {scaled.get('feature_range', [0, 1])}")
    
    # 4. 数据集划分
    print("\n[4/9] 测试 train_test_split...")
    split = service.execute_function('train_test_split', {
        'test_ratio': 0.2
    }, {'data': scaled})
    print(f"  ✓ 训练集: {split['train']['rows']} 行")
    print(f"  ✓ 测试集: {split['test']['rows']} 行")
    
    # 5. 线性回归预测
    print("\n[5/9] 测试 linear_regression...")
    prediction = service.execute_function('linear_regression', {
        'fit_intercept': True,
        'forecast_horizon': 4
    }, {'train_data': split['train']})
    print(f"  ✓ 预测样本数: {len(prediction.get('predictions', []))}")
    print(f"  ✓ 模型类型: {prediction.get('model', 'unknown')}")
    
    # 6. MAPE评估
    print("\n[6/9] 测试 mape_metric...")
    mape = service.execute_function('mape_metric', {}, {
        'y_true': prediction
    })
    print(f"  ✓ MAPE: {mape.get('mape', 0):.2f}%")
    
    # 7. RMSE评估
    print("\n[7/9] 测试 rmse_metric...")
    rmse = service.execute_function('rmse_metric', {}, {
        'y_true': prediction
    })
    print(f"  ✓ RMSE: {rmse.get('rmse', 0):.4f} {rmse.get('unit', '')}")
    
    # 8. R²评估
    print("\n[8/9] 测试 r2_metric...")
    r2 = service.execute_function('r2_metric', {}, {
        'y_true': prediction
    })
    print(f"  ✓ R²: {r2.get('r2', 0):.4f}")
    
    # 9. 可视化
    print("\n[9/9] 测试 forecast_plot...")
    chart = service.execute_function('forecast_plot', {
        'title': '光伏发电功率预测结果'
    }, {'actual': prediction})
    print(f"  ✓ 图表类型: {chart.get('type', 'unknown')}")
    print(f"  ✓ 数据点数: {len(chart.get('data', {}).get('actual', []))}")
    
    print("\n" + "=" * 60)
    print("测试完成！所有函数执行成功")
    print("=" * 60)
    
    # 汇总结果
    print("\n📊 模型评估汇总:")
    print(f"  - MAPE: {mape.get('mape', 0):.2f}%")
    print(f"  - RMSE: {rmse.get('rmse', 0):.4f}")
    print(f"  - R²: {r2.get('r2', 0):.4f}")
    
    return True


def test_additional_functions():
    """测试新增的通用函数"""
    service = PVExecutionService()
    
    print("\n" + "=" * 60)
    print("新增通用函数测试")
    print("=" * 60)
    
    # 加载数据
    data = service.execute_function('load_dataset', {
        'dataset_id': 'pv-power-yinchuan'
    }, {})
    
    # 测试 descriptive_stats
    print("\n[1/5] 测试 descriptive_stats...")
    stats = service.execute_function('descriptive_stats', {}, {'data': data})
    print(f"  ✓ 统计列数: {len(stats.get('statistics', {}))}")
    for col, s in list(stats.get('statistics', {}).items())[:2]:
        print(f"    - {col}: mean={s.get('mean', 0):.2f}, std={s.get('std', 0):.2f}")
    
    # 测试 random_forest_regression
    print("\n[2/5] 测试 random_forest_regression...")
    cleaned = service.execute_function('handle_missing', {'method': 'interpolate'}, {'data': data})
    scaled = service.execute_function('min_max_scale', {'feature_range': [0, 1]}, {'data': cleaned})
    rf_pred = service.execute_function('random_forest_regression', {
        'n_estimators': 10,
        'max_depth': 5
    }, {'train_data': scaled})
    print(f"  ✓ 模型: {rf_pred.get('model', 'unknown')}")
    print(f"  ✓ 预测数: {len(rf_pred.get('predictions', []))}")
    
    # 测试 xgboost_regression
    print("\n[3/5] 测试 xgboost_regression...")
    xgb_pred = service.execute_function('xgboost_regression', {
        'n_estimators': 50,
        'learning_rate': 0.1
    }, {'train_data': scaled})
    print(f"  ✓ 模型: {xgb_pred.get('model', 'unknown')}")
    
    # 测试 regression_metrics
    print("\n[4/5] 测试 regression_metrics...")
    metrics = service.execute_function('regression_metrics', {}, {'y_true': rf_pred})
    print(f"  ✓ RMSE: {metrics.get('rmse', 0):.4f}")
    print(f"  ✓ MAE: {metrics.get('mae', 0):.4f}")
    print(f"  ✓ R²: {metrics.get('r2', 0):.4f}")
    print(f"  ✓ MAPE: {metrics.get('mape', 0):.2f}%")
    
    # 测试 scatter_plot
    print("\n[5/5] 测试 scatter_plot...")
    scatter = service.execute_function('scatter_plot', {
        'title': '预测值 vs 实际值'
    }, {'y_true': rf_pred})
    print(f"  ✓ 图表类型: {scatter.get('type', 'unknown')}")
    
    print("\n" + "=" * 60)
    print("新增函数测试完成！")
    print("=" * 60)
    
    return True


if __name__ == '__main__':
    try:
        test_pv_workflow()
        test_additional_functions()
        print("\n✅ 所有测试通过！")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
# @AI_GENERATED: end
