# @AI_GENERATED: Kiro v1.0
"""测试PV预测修复效果"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pv_execution_service import PVExecutionService

def main():
    # 初始化服务
    service = PVExecutionService()

    # 1. 加载数据
    print('=== 1. 加载数据 ===')
    data = service._load_dataset({'dataset_id': 'pv-power-yinchuan'})
    print(f'数据行数: {data["rows"]}')
    print(f'数据列: {data["columns"]}')

    # 2. 缺失值处理
    print('\n=== 2. 缺失值处理 ===')
    cleaned = service._handle_missing({'data': data, 'method': 'interpolate'})
    print(f'填充缺失值: {cleaned["missing_filled"]}')

    # 3. 归一化
    print('\n=== 3. 数据归一化 ===')
    scaled = service._min_max_scale({'data': cleaned})
    print(f'归一化完成, 行数: {scaled["rows"]}')

    # 4. 数据划分 (改进版：随机划分+过滤有效数据)
    print('\n=== 4. 数据划分 (改进版) ===')
    split = service._train_test_split({
        'data': scaled, 
        'test_ratio': 0.2, 
        'shuffle': True, 
        'filter_valid': True
    })
    print(f'总样本数: {split["total_samples"]}')
    print(f'有效样本数 (power>0): {split["valid_samples"]}')
    print(f'训练集: {split["train_size"]}')
    print(f'测试集: {split["test_size"]}')

    # 5. 模型训练和预测
    print('\n=== 5. 模型训练和预测 ===')
    result = service._xgboost_forecast({'split_data': split})
    print(f'模型: {result["model"]}')
    print(f'训练样本: {result.get("train_size", "N/A")}')
    print(f'测试样本: {result.get("test_size", "N/A")}')
    print(f'特征数: {result["n_features"]}')
    print(f'权重: {[round(w, 4) for w in result["weights"]]}')

    # 6. 评估指标
    print('\n=== 6. 评估指标 ===')
    mape = service._mape_metric({
        'actuals': result['actuals'], 
        'predictions': result['predictions']
    })
    rmse = service._rmse_metric({
        'actuals': result['actuals'], 
        'predictions': result['predictions']
    })
    r2 = service._r2_metric({
        'actuals': result['actuals'], 
        'predictions': result['predictions']
    })

    print(f'MAPE: {mape["mape"]:.2f}%')
    print(f'RMSE: {rmse["rmse"]:.4f}')
    print(f'R²: {r2["r2"]:.4f}')

    # 7. 预测值范围检查
    print('\n=== 7. 预测值范围检查 ===')
    preds = result['predictions']
    actuals = result['actuals']
    print(f'预测值范围: [{min(preds):.4f}, {max(preds):.4f}]')
    print(f'实际值范围: [{min(actuals):.4f}, {max(actuals):.4f}]')

    # 8. 部分预测对比
    print('\n=== 8. 预测对比 (前10个样本) ===')
    for i in range(min(10, len(preds))):
        actual = actuals[i]
        pred = preds[i]
        error = abs(actual - pred) / actual * 100 if actual > 0 else 0
        print(f'  样本{i+1}: 实际={actual:.4f}, 预测={pred:.4f}, 误差={error:.1f}%')

    # 9. 与Kaggle参考对比
    print('\n=== 9. 与Kaggle参考对比 ===')
    print('| 指标 | Kaggle参考 | 本项目实际 | 状态 |')
    print('|------|------------|------------|------|')
    
    mape_val = mape["mape"]
    mape_status = '✅' if mape_val < 20 else ('⚠️' if mape_val < 50 else '❌')
    print(f'| MAPE | 5-15% | {mape_val:.2f}% | {mape_status} |')
    
    rmse_val = rmse["rmse"]
    rmse_status = '✅' if rmse_val < 0.15 else ('⚠️' if rmse_val < 0.3 else '❌')
    print(f'| RMSE | 0.05-0.15 | {rmse_val:.4f} | {rmse_status} |')
    
    r2_val = r2["r2"]
    r2_status = '✅' if r2_val > 0.85 else ('⚠️' if r2_val > 0.5 else '❌')
    print(f'| R² | 0.85-0.95 | {r2_val:.4f} | {r2_status} |')

    return {
        'mape': mape_val,
        'rmse': rmse_val,
        'r2': r2_val
    }

if __name__ == '__main__':
    main()
# @AI_GENERATED: end
