# @AI_GENERATED: Kiro v1.0
"""
风电功率预测 Benchmark 脚本

使用风电分析工具进行日前预测，包含：
1. 从数据库加载风电场站数据
2. 时间序列拆分（训练集/验证集）
3. 特征工程
4. 模型训练（多种算法对比）
5. 日前预测评估

使用方法:
    python backend/scripts/wind_power_benchmark.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import logging
import json

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "frontend" / "src" / "solar_fcst" / "wind_power_analysis_tool-master"))

import pandas as pd
import numpy as np

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_wind_power_benchmark():
    """运行风电功率预测 benchmark"""
    
    print("=" * 80)
    print("风电功率预测 Benchmark")
    print("=" * 80)
    
    try:
        # 导入风电分析工具模块
        from backend.data_loader import DataLoader
        from backend.feature_engineer import PolarsFeatureEngineer
        from backend.models.linear_model_wrapper import LinearModelWrapper
        from backend.models.tree_model_wrapper import TreeModelWrapper
        
        logger.info("成功导入风电分析工具模块")
    except ImportError as e:
        logger.error(f"导入模块失败: {e}")
        logger.info("尝试安装缺失的依赖...")
        return None
    
    # ========== 配置参数 ==========
    # 场站配置
    station_id = 'WF0121'  # 使用示例场站
    
    # 日期配置 - 日前预测场景
    # 预测期: 2025年11月（1个月）
    # 训练期: 预测期之前300天
    predict_end_date = datetime(2025, 11, 30)
    predict_start_date = datetime(2025, 11, 1)
    train_end_date = predict_start_date - timedelta(days=1)
    train_start_date = train_end_date - timedelta(days=300)
    
    # 特征配置
    feature_groups = [
        'raw_meteorological',    # 原始气象要素
        'time_features',         # 时间特征
        'business_features',     # 业务特征
        'statistical_features'   # 统计特征
    ]
    
    # 气象源配置
    sources = ['EC_10D_WS', 'ENS_AVG_WS']
    
    # 模型配置
    models_to_test = [
        ('linear_regression', '线性回归'),
        ('ridge', 'Ridge回归'),
        ('random_forest', '随机森林'),
        ('gbdt', 'GBDT'),
    ]
    
    print(f"\n配置信息:")
    print(f"  场站ID: {station_id}")
    print(f"  训练期: {train_start_date.strftime('%Y-%m-%d')} ~ {train_end_date.strftime('%Y-%m-%d')}")
    print(f"  预测期: {predict_start_date.strftime('%Y-%m-%d')} ~ {predict_end_date.strftime('%Y-%m-%d')}")
    print(f"  气象源: {sources}")
    print(f"  特征组: {feature_groups}")
    
    # ========== 步骤1: 加载数据 ==========
    print("\n" + "-" * 40)
    print("步骤1: 加载数据")
    print("-" * 40)
    
    try:
        loader = DataLoader()
        
        # 获取场站容量
        station_capacity = loader.get_station_capacity(station_id)
        if station_capacity:
            print(f"  场站容量: {station_capacity} MW")
        else:
            print("  警告: 未获取到场站容量信息")
            station_capacity = 50.0  # 默认值
        
        # 加载数据
        raw_data = loader.load_station_data(
            station_id=station_id,
            start_date=train_start_date.strftime('%Y-%m-%d'),
            end_date=predict_end_date.strftime('%Y-%m-%d'),
            load_all=True
        )
        
        print(f"  NWP数据: {raw_data['nwp'].shape}")
        print(f"  真实数据: {raw_data['true'].shape}")
        
    except Exception as e:
        logger.error(f"数据加载失败: {e}")
        return None
    
    # ========== 步骤2: 数据预处理 ==========
    print("\n" + "-" * 40)
    print("步骤2: 数据预处理")
    print("-" * 40)
    
    # 过滤为1小时分辨率
    true_df = raw_data['true']
    true_df = true_df[true_df['timestamp'].dt.minute == 0]
    true_df.reset_index(inplace=True, drop=True)
    
    processed_data = {
        'nwp': raw_data['nwp'],
        'true': true_df,
    }
    
    print(f"  处理后NWP数据: {processed_data['nwp'].shape}")
    print(f"  处理后真实数据: {processed_data['true'].shape}")
    
    # ========== 步骤3: 特征工程 ==========
    print("\n" + "-" * 40)
    print("步骤3: 特征工程")
    print("-" * 40)
    
    try:
        engineer = PolarsFeatureEngineer(processed_data)
        feature_matrix = engineer.build_feature_matrix(feature_groups)
        features_train = [x for x in feature_matrix.columns if x not in ['timestamp', 'forecast_time']]
        
        print(f"  特征矩阵: {feature_matrix.shape}")
        print(f"  特征数量: {len(features_train)}")
        
    except Exception as e:
        logger.error(f"特征工程失败: {e}")
        return None
    
    # ========== 步骤4: 数据拆分 ==========
    print("\n" + "-" * 40)
    print("步骤4: 训练/验证数据拆分")
    print("-" * 40)
    
    train_start = pd.to_datetime(train_start_date)
    train_end = pd.to_datetime(train_end_date)
    pred_start = pd.to_datetime(predict_start_date)
    pred_end = pd.to_datetime(predict_end_date)
    
    # 训练数据
    train_mask = (processed_data['true']['timestamp'] >= train_start) & \
                 (processed_data['true']['timestamp'] <= train_end)
    
    train_data = pd.merge(
        processed_data['true'][train_mask], 
        feature_matrix, 
        on='timestamp', 
        how='outer'
    )
    
    X_train = train_data[features_train]
    y_train = train_data[['WS', 'WS_min', 'WS_median', 'WS_max', 'POWER']]
    
    print(f"  训练集大小: {len(X_train)}")
    
    # 预测数据
    predict_mask = (feature_matrix['timestamp'] >= pred_start) & \
                   (feature_matrix['timestamp'] <= pred_end)
    X_predict = feature_matrix[predict_mask][features_train]
    
    print(f"  预测集大小: {len(X_predict)}")
    
    if len(X_train) < 1500:
        logger.error(f"训练数据不足: {len(X_train)} < 1500")
        return None
    
    # ========== 步骤5: 模型训练与评估 ==========
    print("\n" + "-" * 40)
    print("步骤5: 模型训练与评估")
    print("-" * 40)
    
    results = []
    
    for model_type, model_name in models_to_test:
        print(f"\n  训练 {model_name}...")
        
        try:
            # 创建模型
            if model_type in ['linear_regression', 'ridge', 'lasso']:
                model_wrapper = LinearModelWrapper(
                    farm_id=station_id, 
                    capacity=station_capacity, 
                    model_type=model_type.replace('_regression', '')
                )
            else:
                model_wrapper = TreeModelWrapper(
                    farm_id=station_id, 
                    capacity=station_capacity, 
                    model_type=model_type
                )
            
            # 训练（五折交叉验证）
            model_wrapper.train(
                X_train, 
                y_train,
                param_grid=None,
                enable_search=True
            )
            
            # 预测
            predictions = model_wrapper.predict(X_predict)
            
            # 合并预测结果与真实值
            df_pred = pd.DataFrame({
                'timestamp': feature_matrix[predict_mask]['timestamp'],
                'prediction': predictions,
                'forecast_time': feature_matrix[predict_mask]['forecast_time']
            })
            
            # 仅使用24小时内的预测
            df_pred['dist'] = (df_pred['timestamp'] - df_pred['forecast_time']).dt.total_seconds() / 3600
            df_pred = df_pred[df_pred['dist'].isin(range(24))]
            
            # 合并真实值
            df_pred = pd.merge(
                df_pred, 
                processed_data['true'][['timestamp', 'POWER']], 
                on='timestamp', 
                how='left'
            )
            
            # 计算评估指标
            valid_mask = ~(pd.isna(df_pred['POWER']) | pd.isna(df_pred['prediction']))
            y_true = df_pred['POWER'][valid_mask]
            y_pred = df_pred['prediction'][valid_mask]
            
            if len(y_true) > 0:
                from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
                
                rmse = np.sqrt(mean_squared_error(y_true, y_pred))
                mae = mean_absolute_error(y_true, y_pred)
                r2 = r2_score(y_true, y_pred)
                
                # 计算准确率（基于容量的相对误差）
                accuracy = 1 - (mae / station_capacity)
                
                result = {
                    'model': model_name,
                    'model_type': model_type,
                    'rmse': rmse,
                    'mae': mae,
                    'r2': r2,
                    'accuracy': accuracy * 100,
                    'samples': len(y_true)
                }
                results.append(result)
                
                print(f"    RMSE: {rmse:.4f} MW")
                print(f"    MAE:  {mae:.4f} MW")
                print(f"    R²:   {r2:.4f}")
                print(f"    准确率: {accuracy*100:.2f}%")
            else:
                print(f"    警告: 无有效预测数据")
                
        except Exception as e:
            logger.error(f"  {model_name} 训练失败: {e}")
            continue
    
    # ========== 步骤6: 结果汇总 ==========
    print("\n" + "=" * 80)
    print("Benchmark 结果汇总")
    print("=" * 80)
    
    if results:
        # 按RMSE排序
        results_sorted = sorted(results, key=lambda x: x['rmse'])
        
        print(f"\n{'模型':<15} {'RMSE(MW)':<12} {'MAE(MW)':<12} {'R²':<10} {'准确率':<10}")
        print("-" * 60)
        
        for r in results_sorted:
            print(f"{r['model']:<15} {r['rmse']:<12.4f} {r['mae']:<12.4f} {r['r2']:<10.4f} {r['accuracy']:<10.2f}%")
        
        # 最佳模型
        best = results_sorted[0]
        print(f"\n最佳模型: {best['model']}")
        print(f"  RMSE: {best['rmse']:.4f} MW")
        print(f"  MAE:  {best['mae']:.4f} MW")
        print(f"  R²:   {best['r2']:.4f}")
        print(f"  准确率: {best['accuracy']:.2f}%")
        
        # 保存结果
        output_path = project_root / "backend" / "data" / "demo" / "wind_power_benchmark_results.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'benchmark_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'station_id': station_id,
                'station_capacity': station_capacity,
                'train_period': f"{train_start_date.strftime('%Y-%m-%d')} ~ {train_end_date.strftime('%Y-%m-%d')}",
                'predict_period': f"{predict_start_date.strftime('%Y-%m-%d')} ~ {predict_end_date.strftime('%Y-%m-%d')}",
                'results': results_sorted
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n结果已保存到: {output_path}")
        
        return results_sorted
    else:
        print("没有成功的模型训练结果")
        return None


if __name__ == "__main__":
    results = run_wind_power_benchmark()
    
    if results:
        print("\n" + "=" * 80)
        print("Benchmark 完成!")
        print("=" * 80)
    else:
        print("\nBenchmark 失败，请检查日志")
# @AI_GENERATED: end
