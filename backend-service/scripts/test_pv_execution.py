# @AI_GENERATED: Kiro v1.0
"""
测试光伏预测执行服务
"""
import sys
import os

# 添加backend目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pv_execution_service import PVExecutionService

def test_pv_execution():
    """测试完整的执行流程"""
    service = PVExecutionService()
    
    print("=" * 60)
    print("光伏功率预测工作流执行测试")
    print("=" * 60)
    
    # 1. 加载数据
    print("\n1. 加载光伏数据...")
    data = service.execute_function('load_pv_demo', {}, {})
    print(f"   加载成功: {data['rows']} 行, {data['cols']} 列")
    print(f"   列名: {data['columns']}")
    
    # 2. 处理缺失值
    print("\n2. 处理缺失值...")
    processed = service.execute_function('handle_missing', {'method': 'interpolate'}, {'data': data})
    print(f"   处理完成: 填充了 {processed['missing_filled']} 个缺失值")
    
    # 3. Z-Score标准化
    print("\n3. Z-Score标准化...")
    scaled = service.execute_function('z_score_scale', {}, {'data': processed})
    print(f"   标准化完成")
    print(f"   均值示例: {list(scaled['means'].items())[:3]}")
    print(f"   标准差示例: {list(scaled['stds'].items())[:3]}")
    
    # 4. XGBoost预测
    print("\n4. XGBoost预测...")
    predictions = service.execute_function('xgboost_forecast', {'forecast_horizon': 4}, {'train_data': scaled})
    print(f"   预测完成: {len(predictions['predictions'])} 个预测值")
    print(f"   样本数: {predictions['n_samples']}")
    print(f"   特征数: {predictions['n_features']}")
    print(f"   模型权重: {[round(w, 4) for w in predictions['weights'][:4]]}...")
    
    # 显示部分预测结果
    print("\n   预测结果示例 (前5个):")
    for i in range(min(5, len(predictions['predictions']))):
        actual = predictions['actuals'][i]
        pred = predictions['predictions'][i]
        ts = predictions['timestamps'][i]
        print(f"     {ts}: 实际={actual:.2f}, 预测={pred:.2f}")
    
    # 5. 评估指标
    print("\n5. 计算评估指标...")
    mape = service.execute_function('mape_metric', {}, {'y_true': predictions})
    rmse = service.execute_function('rmse_metric', {}, {'y_true': predictions})
    r2 = service.execute_function('r2_metric', {}, {'y_true': predictions})
    print(f"   MAPE: {mape['mape']}%")
    print(f"   RMSE: {rmse['rmse']} kW")
    print(f"   R²: {r2['r2']}")
    
    # 6. 可视化
    print("\n6. 生成可视化...")
    plot = service.execute_function('forecast_plot', {'title': '光伏功率预测'}, {'actual': predictions})
    print(f"   图表类型: {plot['type']}")
    print(f"   数据点数: {len(plot['data']['actual'])}")
    
    print("\n" + "=" * 60)
    print("✅ 所有函数执行成功!")
    print("=" * 60)
    
    return {
        'mape': mape['mape'],
        'rmse': rmse['rmse'],
        'r2': r2['r2'],
        'predictions_count': len(predictions['predictions'])
    }

if __name__ == '__main__':
    result = test_pv_execution()
    print(f"\n最终结果: {result}")
# @AI_GENERATED: end
