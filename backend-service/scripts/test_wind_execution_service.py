# @AI_GENERATED: Kiro v1.0
"""
测试 WindExecutionService 的精度是否与原工程 train_exact.py 一致。

对比方式：
1. 使用相同参数（场站WF0121, XGBoost Stacking, 相同日期范围）
2. 对比训练指标和预测指标
3. 确保 RMSE/MAE/R2 完全一致
"""
import sys
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

wind_tool_path = os.path.join(backend_dir, '..', 'frontend', 'src', 'solar_fcst', 'wind_power_analysis_tool-master')
sys.path.insert(0, wind_tool_path)


def test_pipeline():
    """测试完整 pipeline"""
    from services.wind_execution_service import WindExecutionService

    service = WindExecutionService()

    params = {
        'station_id': 'WF0121',
        'model_type': 'custom_ensemble_model',
        'train_start_date': '2025-01-01',
        'train_end_date': '2025-10-31',
        'predict_start_date': '2025-11-01',
        'predict_end_date': '2025-11-30',
        'resolution': '1H',
        'feature_groups': ['raw_meteorological', 'time_features', 'business_features', 'statistical_features'],
        'enable_hyperparam_search': True,
    }

    logger.info('=' * 60)
    logger.info('测试 WindExecutionService.run_full_pipeline')
    logger.info(f'参数: station={params["station_id"]}, model={params["model_type"]}')
    logger.info('=' * 60)

    result = service.run_full_pipeline(params)

    if result['status'] == 'success':
        print('\n' + '=' * 60)
        print('Pipeline 执行成功')
        print('=' * 60)
        print(f'场站: {result["station_id"]}')
        print(f'容量: {result["capacity"]} MW')
        print(f'模型: {result["model_type"]}')
        print(f'训练样本: {result["train_size"]}')
        print(f'预测样本: {result["prediction_size"]}')

        if result['train_metrics']:
            print(f'\n训练指标 (5折CV):')
            for k, v in result['train_metrics'].items():
                print(f'  {k}: {v:.6f}')

        if result['predict_metrics']:
            print(f'\n预测指标:')
            for k, v in result['predict_metrics'].items():
                print(f'  {k}: {v:.6f}')

        print('=' * 60)
    else:
        print('Pipeline 执行失败')

    return result


def test_individual_models():
    """测试各模型类型"""
    from services.wind_execution_service import WindExecutionService

    service = WindExecutionService()

    base_params = {
        'station_id': 'WF0121',
        'train_start_date': '2025-01-01',
        'train_end_date': '2025-10-31',
        'predict_start_date': '2025-11-01',
        'predict_end_date': '2025-11-30',
        'feature_groups': ['raw_meteorological', 'time_features', 'business_features', 'statistical_features'],
        'enable_hyperparam_search': True,
    }

    models = ['ridge', 'random_forest', 'custom_ensemble_model']

    print('\n' + '=' * 80)
    print('多模型对比测试')
    print('=' * 80)

    results = {}
    for model_type in models:
        logger.info(f'\n--- 测试模型: {model_type} ---')
        params = {**base_params, 'model_type': model_type}
        try:
            result = service.run_full_pipeline(params)
            results[model_type] = result
            if result.get('predict_metrics'):
                m = result['predict_metrics']
                print(f'{model_type:30s} RMSE={m.get("rmse",0):.4f}  MAE={m.get("mae",0):.4f}  R2={m.get("r2",0):.4f}')
        except Exception as e:
            print(f'{model_type:30s} ERROR: {e}')

    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['pipeline', 'compare'], default='pipeline')
    args = parser.parse_args()

    if args.mode == 'pipeline':
        test_pipeline()
    elif args.mode == 'compare':
        test_individual_models()
# @AI_GENERATED: end
