"""
完全复制 train_model 的逻辑进行测试
与 routes.py 中的 train_model 函数逻辑一模一样
"""

import pandas as pd
import numpy as np
import logging
import uuid
import time
from datetime import datetime, timedelta

from backend.data_loader import DataLoader
from backend.feature_engineer import PolarsFeatureEngineer
from backend.models.linear_model_wrapper import LinearModelWrapper
from backend.models.tree_model_wrapper import TreeModelWrapper
from backend.models.custom_model_epf import CustomModelEpfWrapper
from backend.utils import resample_both_dimensions

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 模拟 session_store
session_store = {}


def train_model_test():
    """
    训练模型 - 直接从数据库加载训练和预测数据
    完全复制 routes.py 中的 train_model 函数逻辑
    """
    try:
        # 模拟请求参数（与 HTML 默认参数一致）
        # 计算日期
        predict_end_date = datetime(2025, 11, 30)
        predict_start_date = datetime(2025, 11, 1)
        train_end_date = predict_start_date - timedelta(days=1)
        train_start_date = train_end_date - timedelta(days=300)
        
        data = {
            'station_id': 'WF0121',
            # 'model_type': 'linear_regression',  # 默认使用线性回归
            # 'model_type': 'decision_tree',  # 默认使用线性回归
            'model_type': 'custom_ensemble_model',  # 默认使用线性回归
            'params': {
                'n_estimators': 100,
                'max_depth': 10,
                'test_size': 0.2
            },
            'param_grid': None,
            'enable_hyperparam_search': True,
            'train_start_date': train_start_date.strftime('%Y-%m-%d'),
            'train_end_date': train_end_date.strftime('%Y-%m-%d'),
            'predict_start_date': predict_start_date.strftime('%Y-%m-%d'),
            'predict_end_date': predict_end_date.strftime('%Y-%m-%d'),
            'resolution': '1H',
            'sources': ['EC_10D_WS', 'ENS_AVG_WS'],
            'feature_groups': ['raw_meteorological', 'time_features', 'business_features', 'statistical_features']
        }
        
        logger.info('=== Model Training Request (Direct Load) ===')
        logger.info(f'Request data: {data}')
        
        if not data:
            logger.error('请求体不能为空')
            return
        
        # 提取参数
        station_id = data.get('station_id')
        model_type = data.get('model_type', 'random_forest')
        param_grid = data.get('param_grid', None)  # 超参数搜索空间
        enable_hyperparam_search = data.get('enable_hyperparam_search', True)  # 是否启用超参数搜索
        train_start_date = data.get('train_start_date')
        train_end_date = data.get('train_end_date')
        predict_start_date = data.get('predict_start_date')
        predict_end_date = data.get('predict_end_date')
        resolution = data.get('resolution', '1H')
        sources = data.get('sources', [])
        feature_groups = data.get('feature_groups', ['raw_meteorological', 'time_features', 'business_features', 'statistical_features'])

        # 验证必需参数
        if not station_id:
            logger.error('缺少必需参数: station_id')
            return
        
        if not train_start_date or not train_end_date:
            logger.error('缺少必需参数: train_start_date 和 train_end_date')
            return
        
        if not sources or len(sources) == 0:
            logger.error('缺少必需参数: sources (至少选择一个气象源)')
            return
        
        logger.info(f'Station: {station_id}')
        logger.info(f'Train date range: {train_start_date} to {train_end_date}')
        if predict_start_date and predict_end_date:
            logger.info(f'Predict date range: {predict_start_date} to {predict_end_date}')
        logger.info(f'Resolution: {resolution}')
        logger.info(f'Sources: {sources}')
        logger.info(f'Feature groups: {feature_groups}')
        
        # ========== 步骤1: 加载训练数据 ==========
        logger.info('Step 1: Loading training data from database...')
        loader = DataLoader()
        
        # 获取场站容量信息
        station_capacity = loader.get_station_capacity(station_id)
        if station_capacity is None:
            logger.warning(f'场站 {station_id} 没有配置容量信息')
        else:
            logger.info(f'场站 {station_id} 容量: {station_capacity} MW')
        
        # 计算需要加载的完整日期范围（训练期 + 预测期）
        load_start_date = train_start_date
        load_end_date = predict_end_date if predict_end_date else train_end_date
        
        # 加载数据
        raw_data = loader.load_station_data(
            station_id=station_id,
            start_date=load_start_date,
            end_date=load_end_date,
            load_all=True
        )
        
        if raw_data is None:
            logger.error(f'无法加载场站 {station_id} 的数据')
            return
        
        logger.info(f"Loaded raw data, nwp data shape: {raw_data['nwp'].shape}, true data shape: {raw_data['true'].shape}")
         
        # ========== 步骤2: 处理数据, 仅使用1H的数据集 ==========
        logger.info('Step 2: Processing data...')

        # 对原始真实数据进行过滤，真实数据为15min分辨率数据
        true_df = raw_data['true']
        true_df = true_df[true_df['timestamp'].dt.minute == 0]
        true_df.reset_index(inplace=True, drop=True)

        processed_data = {
            'nwp': raw_data['nwp'],
            'true': true_df,
        }
        
        logger.info(f'Processed data - NWP shape: {processed_data["nwp"].shape}, True shape: {processed_data["true"].shape}')
        
        # 检查真实风速数据
        if processed_data['true'].empty:
            logger.error('缺少真实风速数据')
            return
        
        # ========== 步骤3: 过滤训练数据 ==========
        logger.info('Step 3: Filtering training data...')
        train_start = pd.to_datetime(train_start_date)
        train_end = pd.to_datetime(train_end_date)

        # 过滤训练期数据
        train_mask = (processed_data['true']['timestamp'] >= train_start) & (processed_data['true']['timestamp'] <= train_end)
        
        # 获取真实风速
        if 'WS' not in processed_data['true'].columns or 'POWER' not in processed_data['true'].columns:
            logger.error('真实风速或者真实功率不存在')
            return

        if len(processed_data['true']['WS'][train_mask]) < 1500:
            logger.error(f'训练数据点太少，请扩大日期范围。建议至少200天数据。')
            return
        
        # ========== 步骤4: 生成特征 ==========
        logger.info('Step 4: Generating features...')
        engineer = PolarsFeatureEngineer(processed_data)
        
        # 构建特征矩阵
        feature_matrix = engineer.build_feature_matrix(feature_groups)
        features_train = [x for x in feature_matrix.columns if x not in ['timestamp', 'forecast_time']]

        # 合并真实数据和特征数据，以防特征数据有多个重复时间戳导致与真实数据时间不对齐
        train_data = pd.merge(processed_data['true'][train_mask], feature_matrix, on='timestamp', how='outer')
        
        # 过滤训练期特征
        feature_matrix_train = train_data[features_train]
        target_train = train_data[['WS', 'WS_min', 'WS_median', 'WS_max', 'POWER']]
        
        logger.info(f'Aligned training data shape: features={feature_matrix_train.shape}, target={target_train.shape}')
        
        if len(feature_matrix_train) < 1500:
            logger.error(f'对齐后训练数据点太少（{len(feature_matrix_train)}条），请检查数据质量。')
            return
        
        # ========== 步骤5: 训练模型 ==========
        logger.info('Step 5: Training model...')
        
        # 根据模型类型创建模型包装器
        if model_type == 'linear_regression':
            model_wrapper = LinearModelWrapper(farm_id=station_id, capacity=station_capacity, model_type='linear')
        elif model_type == 'ridge':
            model_wrapper = LinearModelWrapper(farm_id=station_id, capacity=station_capacity, model_type='ridge')
        elif model_type == 'lasso':
            model_wrapper = LinearModelWrapper(farm_id=station_id, capacity=station_capacity, model_type='lasso')
        elif model_type == 'decision_tree':
            model_wrapper = TreeModelWrapper(farm_id=station_id, capacity=station_capacity, model_type='decision_tree')
        elif model_type == 'random_forest':
            model_wrapper = TreeModelWrapper(farm_id=station_id, capacity=station_capacity, model_type='random_forest')
        elif model_type == 'gbdt':
            model_wrapper = TreeModelWrapper(farm_id=station_id, capacity=station_capacity, model_type='gbdt')
        elif model_type == 'custom_ensemble_model':
            model_wrapper = CustomModelEpfWrapper(farm_id=station_id, capacity=station_capacity)
        else:
            logger.error(f'不支持的模型类型: {model_type}。支持的类型: linear_regression, ridge, lasso, decision_tree, random_forest, gbdt')
            return
        
        # 训练模型
        logger.info(f'训练 {model_type} 模型（五折交叉验证）')
        if enable_hyperparam_search:
            logger.info('启用超参数搜索')
        else:
            logger.info('使用默认参数，不进行超参数搜索')
        
        model_wrapper.train(
            feature_matrix_train, 
            target_train,
            param_grid=param_grid,
            enable_search=enable_hyperparam_search
        )
        
        logger.info(f'Model trained successfully')
        
        # 保存模型包装器
        result = {
            'model': model_wrapper
        }
        
        # ========== 步骤6: 预测（如果提供了预测日期范围）==========
        predictions = []
        actual_values = []
        timestamps = []
        metrics = {}
        
        if predict_start_date and predict_end_date:
            logger.info('Step 6: Making predictions on prediction period...')
            try:
                pred_start = pd.to_datetime(predict_start_date)
                pred_end = pd.to_datetime(predict_end_date)
                
                # 过滤预测期的特征数据
                predict_mask = (feature_matrix['timestamp'] >= pred_start) & (feature_matrix['timestamp'] <= pred_end)
                feature_matrix_predict = feature_matrix[predict_mask][features_train]
                
                logger.info(f'Prediction data shape: features={feature_matrix_predict.shape}')
                
                if len(feature_matrix_predict) > 0:
                    # 进行预测 - 使用训练好的模型
                    predictions_pred = model_wrapper.predict(feature_matrix_predict)
                    df_predictions = pd.DataFrame({'timestamp': feature_matrix[predict_mask]['timestamp'], 'prediction': predictions_pred, "forecast_time": feature_matrix[predict_mask]['forecast_time']})

                    # 仅提取24H
                    df_predictions = resample_both_dimensions(df_predictions, '15min')
                    df_predictions['dist'] = (df_predictions['timestamp'] - df_predictions[
                        'forecast_time']).dt.total_seconds() / 3600
                    df_predictions = df_predictions[df_predictions['dist'].isin(range(24))]
                    df_predictions = pd.merge(df_predictions, processed_data['true'][['timestamp', 'POWER']], on='timestamp', how='left')

                    predictions = df_predictions['prediction']
                    actual_values = df_predictions['POWER']
                    timestamps = df_predictions['timestamp'].tolist()
                    timestamps = [x.strftime('%Y-%m-%d %H:%M:%S') for x in timestamps]
                    
                    # 去除NaN值
                    valid_mask = ~(pd.isna(actual_values) | pd.isna(predictions))
                    target_predict_clean = actual_values[valid_mask]
                    predictions_pred_clean = predictions[valid_mask]
                    
                    if len(target_predict_clean) > 0:
                        from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
                        
                        rmse = np.sqrt(mean_squared_error(target_predict_clean, predictions_pred_clean))
                        mae = mean_absolute_error(target_predict_clean, predictions_pred_clean)
                        r2 = r2_score(target_predict_clean, predictions_pred_clean)
                        
                        metrics = {
                            'rmse': float(rmse),
                            'mae': float(mae),
                            'r2': float(r2)
                        }
                        
                        logger.info(f'Prediction metrics: RMSE={rmse:.4f}, MAE={mae:.4f}, R2={r2:.4f}')
                    else:
                        logger.warning('No valid prediction data after removing NaN values')
                else:
                    logger.warning('No prediction data available in the specified date range')
                    
            except Exception as e:
                logger.error(f'Prediction error: {str(e)}', exc_info=True)
                return
        else:
            logger.info('Step 6: No prediction period specified, skipping prediction')
        
        # ========== 步骤7: 保存模型到session（可选）==========
        model_id = str(uuid.uuid4())
        
        # 创建session（如果需要后续使用模型）
        if model_id not in session_store:
            session_store[model_id] = {
                'timestamp': time.time(),
                'station_id': station_id,
                'model_type': model_type,
                'model_wrapper': model_wrapper,
                'result': result,
                'feature_groups': feature_groups,
                'sources': sources,
                'capacity': station_capacity
            }
        
        logger.info(f'Model training completed successfully:')
        logger.info(f'  - Model ID: {model_id}')
        logger.info(f'  - Model type: {model_type}')
        logger.info(f'  - Train size: {len(feature_matrix_train)}')
        logger.info(f'  - Prediction size: {len(predictions)}')
        if metrics:
            logger.info(f'  - Prediction metrics: {metrics}')
        
        # 返回结果
        return {
            'status': 'success',
            'model_id': model_id,
            'model_type': model_type,
            'metrics': metrics,
            'predictions': predictions,
            'actual': actual_values,
            'timestamps': timestamps,
            'train_size': len(feature_matrix_train),
            'prediction_size': len(predictions),
            'capacity': station_capacity
        }
        
    except ValueError as e:
        logger.error(f'ValueError in model training: {str(e)}')
        return None
    except RuntimeError as e:
        logger.error(f'RuntimeError in model training: {str(e)}')
        return None
    except FileNotFoundError as e:
        logger.error(f'FileNotFoundError in model training: {str(e)}')
        return None
    except Exception as e:
        logger.error(f'Exception in model training: {str(e)}', exc_info=True)
        return None


if __name__ == "__main__":
    result = train_model_test()
    
    if result and result['status'] == 'success':
        print("\n" + "=" * 80)
        print("训练成功!")
        print("=" * 80)
        print(f"模型ID: {result['model_id']}")
        print(f"模型类型: {result['model_type']}")
        print(f"训练样本数: {result['train_size']}")
        print(f"预测样本数: {result['prediction_size']}")
        
        if result['metrics']:
            print(f"\n评估指标:")
            print(f"  RMSE: {result['metrics']['rmse']:.4f}")
            print(f"  MAE:  {result['metrics']['mae']:.4f}")
            print(f"  Spearman_corr:   {result['metrics']['Spearman_corr']:.4f}")
        
        print("=" * 80)
    else:
        print("\n训练失败，请查看日志")
