# @AI_GENERATED: Kiro v1.0
"""
风电功率预测执行服务

架构参考 kaggle_solar_execution_service（通用函数ID + pipeline），
算法层直接复用 wind_power_analysis_tool-master 的原始实现，
确保精度与原工程完全一致。

支持的模型：LinearRegression/Ridge/Lasso, DecisionTree/RandomForest/GBDT, XGBoost Stacking
支持的特征：时间特征、业务特征、统计特征、差值特征、交互特征
支持的评估：相关性分析、误差指标、分布统计、缺失率、风速区间、季节分析、偏差分析
"""
import os
import sys
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 将原工程路径加入 sys.path，直接复用原始代码
WIND_TOOL_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'solar_fcst', 'wind_power_analysis_tool-master'
)
if WIND_TOOL_PATH not in sys.path:
    sys.path.insert(0, WIND_TOOL_PATH)


class WindExecutionService:
    """
    风电功率预测执行服务
    
    直接复用 wind_power_analysis_tool-master 的算法实现，
    通过平台统一的函数ID接口暴露能力。
    """

    SUPPORTED_FUNCTIONS = {
        # 数据源
        'load_dataset', 'wind_station_scanner',
        # 数据处理
        'wind_data_processor', 'wind_missing_cleaner',
        # 特征工程
        'wind_time_features', 'wind_business_features',
        'wind_statistical_features', 'wind_difference_features',
        'wind_interaction_features',
        # 模型训练
        'wind_tree_model', 'wind_linear_model', 'wind_xgboost_stacking',
        # 评估指标
        'wind_correlation_analysis', 'wind_error_metrics',
        'wind_distribution_stats', 'wind_missing_rate',
        'wind_range_analysis', 'wind_seasonal_analysis', 'wind_bias_analysis',
        # Pipeline
        # Pipeline
        'wind_full_pipeline',
        # 拆解后的工作流节点
        'wind_feature_build', 'wind_train_split',
        'wind_ws_xgb_train', 'wind_power_xgb_train', 'wind_fusion_train',
        'wind_ws_xgb_predict', 'wind_power_xgb_predict', 'wind_fusion_predict',
        'wind_evaluate',
    }

    def __init__(self):
        self._loader = None
        self._processor = None
        self._engineer = None
        self._analyzer = None

    def _get_loader(self):
        """延迟加载 DataLoader（避免无数据库时报错）"""
        if self._loader is None:
            from backend.data_loader import DataLoader
            self._loader = DataLoader()
        return self._loader

    def can_handle(self, function_id: str, params: Dict) -> bool:
        if function_id == 'load_dataset':
            dataset_id = params.get('dataset_id', '')
            return 'wind' in dataset_id.lower()
        return function_id in self.SUPPORTED_FUNCTIONS

    def execute_function(self, function_id: str, params: Dict, inputs: Dict) -> Any:
        all_params = {**params, **inputs}

        # 数据源
        if function_id == 'load_dataset':
            return self._load_wind_data(all_params)
        elif function_id == 'wind_station_scanner':
            return self._scan_stations(all_params)

        # 数据处理
        elif function_id == 'wind_data_processor':
            return self._process_data(all_params)
        elif function_id == 'wind_missing_cleaner':
            return self._clean_missing(all_params)

        # 特征工程
        elif function_id in ('wind_time_features', 'wind_business_features',
                             'wind_statistical_features', 'wind_difference_features',
                             'wind_interaction_features'):
            return self._build_features(function_id, all_params)

        # 模型训练
        elif function_id in ('wind_tree_model', 'wind_linear_model', 'wind_xgboost_stacking'):
            return self._train_model(function_id, all_params)

        # 拆解后的工作流节点
        elif function_id == 'wind_feature_build':
            return self._wf_feature_build(all_params)
        elif function_id == 'wind_train_split':
            return self._wf_train_split(all_params)
        elif function_id == 'wind_ws_xgb_train':
            return self._wf_ws_xgb_train(all_params)
        elif function_id == 'wind_power_xgb_train':
            return self._wf_power_xgb_train(all_params)
        elif function_id == 'wind_fusion_train':
            return self._wf_fusion_train(all_params)
        elif function_id == 'wind_ws_xgb_predict':
            return self._wf_ws_xgb_predict(all_params)
        elif function_id == 'wind_power_xgb_predict':
            return self._wf_power_xgb_predict(all_params)
        elif function_id == 'wind_fusion_predict':
            return self._wf_fusion_predict(all_params)
        elif function_id == 'wind_evaluate':
            return self._wf_evaluate(all_params)

        # 评估指标
        elif function_id in ('wind_correlation_analysis', 'wind_error_metrics',
                             'wind_distribution_stats', 'wind_missing_rate',
                             'wind_range_analysis', 'wind_seasonal_analysis',
                             'wind_bias_analysis'):
            return self._evaluate(function_id, all_params)

        # Pipeline
        elif function_id == 'wind_full_pipeline':
            return self.run_full_pipeline(all_params)

        else:
            raise ValueError(f'未实现的函数: {function_id}')

    # ==================== 数据源 ====================

    def _load_wind_data(self, params: Dict) -> Dict:
        """加载风电场站数据（复用原工程 DataLoader）"""
        station_id = params.get('station_id')
        start_date = params.get('start_date', '')
        end_date = params.get('end_date', '')
        load_all = params.get('load_all_nwp', True)

        if not station_id:
            raise ValueError('缺少必需参数: station_id')

        loader = self._get_loader()

        # 获取场站信息
        capacity = loader.get_station_capacity(station_id)
        sources = loader.get_station_sources(station_id)
        logger.info(f'场站 {station_id}: 容量={capacity}MW, 气象源={sources}')

        # 加载数据
        raw_data = loader.load_station_data(
            station_id=station_id,
            start_date=start_date,
            end_date=end_date,
            load_all=load_all
        )

        if raw_data is None:
            raise ValueError(f'无法加载场站 {station_id} 的数据')

        # 真实数据过滤为整点（原工程逻辑）
        true_df = raw_data['true']
        true_df = true_df[true_df['timestamp'].dt.minute == 0]
        true_df.reset_index(inplace=True, drop=True)

        logger.info(f'数据加载完成: NWP={raw_data["nwp"].shape}, True={true_df.shape}')

        return {
            'nwp': raw_data['nwp'],
            'true': true_df,
            'station_id': station_id,
            'capacity': capacity,
            'sources': sources,
            'data_type': 'wind_farm_data',
        }

    def _scan_stations(self, params: Dict) -> Dict:
        """扫描可用场站列表"""
        loader = self._get_loader()
        validate = params.get('validate_data', False)
        stations = loader.scan_stations()

        result = []
        for sid in stations:
            info = {'station_id': sid}
            try:
                cap = loader.get_station_capacity(sid)
                srcs = loader.get_station_sources(sid)
                info['capacity'] = cap
                info['sources'] = srcs
                if validate:
                    info['validation'] = loader.validate_data_files(sid)
            except Exception as e:
                info['error'] = str(e)
            result.append(info)

        return {'stations': result, 'count': len(result)}

    # ==================== 数据处理 ====================

    def _process_data(self, params: Dict) -> Dict:
        """数据处理（时间对齐+插值），复用原工程 DataProcessor"""
        from backend.data_processor import DataProcessor

        nwp = params.get('nwp')
        true = params.get('true')
        resolution = params.get('resolution', '1H')
        method = params.get('interpolate_method', 'linear')

        if nwp is None or true is None:
            raise ValueError('缺少 nwp 或 true 数据')

        processor = DataProcessor(nwp, true)
        processor.align_timestamps(resolution=resolution)
        processor.interpolate_data(method=method)

        processed = processor.get_processed_data()
        removed = processor.get_removed_columns_info()
        meteorological_sources = processor.get_meteorological_sources()

        return {
            **params,
            'nwp': processed['nwp'],
            'true': processed['true'],
            'removed_columns': removed,
            'meteorological_sources': meteorological_sources,
            'resolution': resolution,
        }

    def _clean_missing(self, params: Dict) -> Dict:
        """缺失值清洗"""
        data = params.get('data')
        threshold = params.get('missing_threshold', 0.5)
        fill_method = params.get('fill_method', 'interpolate')

        if data is None:
            raise ValueError('缺少 data 参数')

        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)

        # 删除缺失率超过阈值的列
        missing_rates = df.isnull().mean()
        cols_to_drop = missing_rates[missing_rates > threshold].index.tolist()
        if cols_to_drop:
            logger.info(f'删除缺失率>{threshold}的列: {cols_to_drop}')
            df = df.drop(columns=cols_to_drop)

        # 填充
        if fill_method == 'ffill':
            df = df.ffill()
        elif fill_method == 'bfill':
            df = df.bfill()
        elif fill_method == 'interpolate':
            df = df.interpolate(method='linear', limit_direction='both')
        elif fill_method == 'mean':
            df = df.fillna(df.mean())
        elif fill_method == 'median':
            df = df.fillna(df.median())

        return {**params, 'data': df, 'dropped_columns': cols_to_drop}

    # ==================== 特征工程 ====================

    def _build_features(self, function_id: str, params: Dict) -> Dict:
        """构建特征（复用原工程 PolarsFeatureEngineer）"""
        from backend.feature_engineer import PolarsFeatureEngineer

        processed_data = {
            'nwp': params.get('nwp'),
            'true': params.get('true'),
        }

        if processed_data['nwp'] is None or processed_data['true'] is None:
            raise ValueError('缺少 nwp 或 true 数据')

        engineer = PolarsFeatureEngineer(processed_data)

        # 根据函数ID选择特征组
        group_map = {
            'wind_time_features': ['time_features'],
            'wind_business_features': ['business_features'],
            'wind_statistical_features': ['statistical_features'],
            'wind_difference_features': ['difference_features'],
            'wind_interaction_features': ['interaction_features'],
        }

        groups = group_map.get(function_id, [])
        # 始终包含 raw_meteorological 作为基础
        all_groups = ['raw_meteorological'] + groups

        feature_matrix = engineer.build_feature_matrix(all_groups)
        feature_groups_info = engineer.get_feature_groups()

        return {
            **params,
            'feature_matrix': feature_matrix,
            'feature_groups': all_groups,
            'feature_columns': [c for c in feature_matrix.columns if c not in ['timestamp', 'forecast_time']],
            'feature_groups_info': {g: feature_groups_info.get(g, []) for g in all_groups},
        }

    # ==================== 模型训练 ====================

    def _train_model(self, function_id: str, params: Dict) -> Dict:
        """
        训练模型（复用原工程模型包装器）
        
        完全复制 train_exact.py 的训练流程，确保精度一致。
        """
        from backend.models.linear_model_wrapper import LinearModelWrapper
        from backend.models.tree_model_wrapper import TreeModelWrapper
        from backend.models.custom_model_epf import CustomModelEpfWrapper

        station_id = params.get('station_id', 'unknown')
        capacity = params.get('capacity')
        model_type = params.get('model_type', 'random_forest')
        param_grid = params.get('param_grid', None)
        enable_search = params.get('enable_hyperparam_search', True)
        feature_groups = params.get('feature_groups', [
            'raw_meteorological', 'time_features', 'business_features', 'statistical_features'
        ])

        # 日期参数
        train_start = params.get('train_start_date')
        train_end = params.get('train_end_date')
        predict_start = params.get('predict_start_date')
        predict_end = params.get('predict_end_date')

        # 数据
        nwp = params.get('nwp')
        true_data = params.get('true')

        if nwp is None or true_data is None:
            raise ValueError('缺少 nwp 或 true 数据')

        # 根据 function_id 映射模型类型
        if function_id == 'wind_linear_model':
            model_type = params.get('model_type', 'ridge')
        elif function_id == 'wind_tree_model':
            model_type = params.get('model_type', 'random_forest')
        elif function_id == 'wind_xgboost_stacking':
            model_type = 'custom_ensemble_model'

        # ===== 复制 train_exact.py 的完整流程 =====

        processed_data = {'nwp': nwp, 'true': true_data}

        # 特征工程（使用 Polars 高性能实现）
        from backend.feature_engineer import PolarsFeatureEngineer
        engineer = PolarsFeatureEngineer(processed_data)
        feature_matrix = engineer.build_feature_matrix(feature_groups)
        features_train = [x for x in feature_matrix.columns if x not in ['timestamp', 'forecast_time']]

        # 过滤训练期数据
        if train_start and train_end:
            ts = pd.to_datetime(train_start)
            te = pd.to_datetime(train_end)
            train_mask = (true_data['timestamp'] >= ts) & (true_data['timestamp'] <= te)
        else:
            train_mask = pd.Series([True] * len(true_data), index=true_data.index)

        if 'WS' not in true_data.columns or 'POWER' not in true_data.columns:
            raise ValueError('真实数据缺少 WS 或 POWER 列')

        # 合并特征和真实数据（原工程逻辑）
        train_data = pd.merge(
            true_data[train_mask], feature_matrix, on='timestamp', how='outer'
        )
        feature_matrix_train = train_data[features_train]
        target_train = train_data[['WS', 'WS_min', 'WS_median', 'WS_max', 'POWER']]

        logger.info(f'训练数据: features={feature_matrix_train.shape}, target={target_train.shape}')

        if len(feature_matrix_train) < 100:
            raise ValueError(f'训练数据太少（{len(feature_matrix_train)}条），请扩大日期范围')

        # 创建模型包装器
        if model_type in ('linear', 'linear_regression'):
            wrapper = LinearModelWrapper(farm_id=station_id, capacity=capacity, model_type='linear')
        elif model_type == 'ridge':
            wrapper = LinearModelWrapper(farm_id=station_id, capacity=capacity, model_type='ridge')
        elif model_type == 'lasso':
            wrapper = LinearModelWrapper(farm_id=station_id, capacity=capacity, model_type='lasso')
        elif model_type == 'decision_tree':
            wrapper = TreeModelWrapper(farm_id=station_id, capacity=capacity, model_type='decision_tree')
        elif model_type == 'random_forest':
            wrapper = TreeModelWrapper(farm_id=station_id, capacity=capacity, model_type='random_forest')
        elif model_type == 'gbdt':
            wrapper = TreeModelWrapper(farm_id=station_id, capacity=capacity, model_type='gbdt')
        elif model_type == 'custom_ensemble_model':
            wrapper = CustomModelEpfWrapper(farm_id=station_id, capacity=capacity)
        else:
            raise ValueError(f'不支持的模型类型: {model_type}')

        # 训练（5折交叉验证 + 超参数搜索）
        logger.info(f'训练 {model_type} 模型, enable_search={enable_search}')
        train_result = wrapper.train(
            feature_matrix_train, target_train,
            param_grid=param_grid, enable_search=enable_search
        )

        result = {
            'model_type': model_type,
            'station_id': station_id,
            'capacity': capacity,
            'train_metrics': train_result.get('metrics', {}),
            'train_size': len(feature_matrix_train),
            'feature_names': wrapper.feature_names,
            'feature_groups': feature_groups,
            '_model_wrapper': wrapper,
            '_feature_matrix': feature_matrix,
            '_features_train': features_train,
        }

        # 预测期（如果提供）
        if predict_start and predict_end:
            result.update(self._predict_period(
                wrapper, feature_matrix, features_train,
                processed_data, predict_start, predict_end, capacity
            ))

        return result

    def _predict_period(self, wrapper, feature_matrix, features_train,
                        processed_data, predict_start, predict_end, capacity) -> Dict:
        """预测期评估（复制 train_exact.py 的预测逻辑）"""
        from backend.utils import resample_both_dimensions
        from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

        pred_start = pd.to_datetime(predict_start)
        pred_end = pd.to_datetime(predict_end)

        predict_mask = (
            (feature_matrix['timestamp'] >= pred_start) &
            (feature_matrix['timestamp'] <= pred_end)
        )
        feature_matrix_predict = feature_matrix[predict_mask][features_train]

        if len(feature_matrix_predict) == 0:
            return {'predict_metrics': {}, 'predictions': [], 'actual': [], 'timestamps': []}

        predictions_raw = wrapper.predict(feature_matrix_predict)

        # predict() 输出是原始功率值（MW）
        # clip 到合理范围 [0, capacity]
        if capacity and capacity > 0:
            predictions_raw = np.clip(predictions_raw, 0, capacity)

        # 构建预测 DataFrame
        df_pred = pd.DataFrame({
            'timestamp': feature_matrix[predict_mask]['timestamp'],
            'prediction': predictions_raw,
            'forecast_time': feature_matrix[predict_mask]['forecast_time'],
        })

        # 重采样到15min + 仅提取24H（原工程逻辑）
        df_pred = resample_both_dimensions(df_pred, '15min')
        df_pred['dist'] = (df_pred['timestamp'] - df_pred['forecast_time']).dt.total_seconds() / 3600
        df_pred = df_pred[df_pred['dist'].isin(range(24))]

        # 合并真实值
        df_pred = pd.merge(
            df_pred, processed_data['true'][['timestamp', 'POWER']],
            on='timestamp', how='left'
        )

        # 计算指标
        valid = ~(pd.isna(df_pred['POWER']) | pd.isna(df_pred['prediction']))
        actual_clean = df_pred['POWER'][valid]
        pred_clean = df_pred['prediction'][valid]

        metrics = {}
        if len(actual_clean) > 0:
            metrics = {
                'rmse': float(np.sqrt(mean_squared_error(actual_clean, pred_clean))),
                'mae': float(mean_absolute_error(actual_clean, pred_clean)),
                'r2': float(r2_score(actual_clean, pred_clean)),
            }
            if capacity and capacity > 0:
                metrics['rmse_normalized'] = metrics['rmse'] / capacity
                metrics['mae_normalized'] = metrics['mae'] / capacity
            logger.info(f'预测指标: RMSE={metrics["rmse"]:.4f}, MAE={metrics["mae"]:.4f}, R2={metrics["r2"]:.4f}')

        return {
            'predict_metrics': metrics,
            'predictions': df_pred['prediction'].tolist(),
            'actual': df_pred['POWER'].tolist(),
            'timestamps': df_pred['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            'prediction_size': len(df_pred),
        }

    # ==================== 评估指标 ====================

    def _evaluate(self, function_id: str, params: Dict) -> Dict:
        """统计分析（复用原工程 StatisticalAnalyzer）"""
        from backend.statistical_analyzer import StatisticalAnalyzer

        processed_data = {
            'nwp': params.get('nwp'),
            'true': params.get('true'),
        }
        sources = params.get('sources', [])

        if processed_data['nwp'] is None or processed_data['true'] is None:
            raise ValueError('缺少 nwp 或 true 数据')

        analyzer = StatisticalAnalyzer(processed_data)

        if function_id == 'wind_correlation_analysis':
            matrix = analyzer.calculate_correlation_matrix(sources)
            return {'correlation_matrix': matrix.to_dict() if hasattr(matrix, 'to_dict') else matrix}

        elif function_id == 'wind_error_metrics':
            metrics = analyzer.calculate_error_metrics(sources)
            return {'error_metrics': metrics.to_dict() if hasattr(metrics, 'to_dict') else metrics}

        elif function_id == 'wind_distribution_stats':
            data_series = params.get('data')
            if data_series is None:
                # 默认分析真实风速
                ws_col = analyzer._get_true_ws_column()
                data_series = processed_data['true'][ws_col] if ws_col else pd.Series()
            stats = analyzer.calculate_distribution_stats(data_series)
            return {'distribution_stats': stats}

        elif function_id == 'wind_missing_rate':
            rates = analyzer.calculate_missing_rate(sources)
            return {'missing_rate': rates.to_dict() if hasattr(rates, 'to_dict') else rates}

        elif function_id == 'wind_range_analysis':
            ranges = params.get('wind_speed_ranges', [0, 3, 6, 9, 12, float('inf')])
            result = analyzer.analyze_wind_speed_ranges(sources, ranges)
            return {'range_analysis': result}

        elif function_id == 'wind_seasonal_analysis':
            result = analyzer.analyze_seasonal_performance(sources)
            return {'seasonal_analysis': result}

        elif function_id == 'wind_bias_analysis':
            result = analyzer.analyze_bias_distribution(sources)
            return {'bias_analysis': result}

        else:
            raise ValueError(f'未实现的评估函数: {function_id}')

    # ==================== Pipeline ====================

    def run_full_pipeline(self, params: Dict) -> Dict:
        """
        运行完整的风电预测流水线
        
        复制 train_exact.py 的完整流程，确保精度一致。
        
        参数:
            station_id: 场站ID
            train_start_date / train_end_date: 训练期
            predict_start_date / predict_end_date: 预测期
            model_type: 模型类型 (linear/ridge/lasso/decision_tree/random_forest/gbdt/custom_ensemble_model)
            resolution: 时间分辨率 (1H)
            sources: 气象源列表
            feature_groups: 特征组列表
            enable_hyperparam_search: 是否启用超参数搜索
        """
        station_id = params.get('station_id')
        if not station_id:
            raise ValueError('缺少 station_id')

        model_type = params.get('model_type', 'custom_ensemble_model')
        resolution = params.get('resolution', '1H')
        feature_groups = params.get('feature_groups', [
            'raw_meteorological', 'time_features', 'business_features', 'statistical_features'
        ])

        # Step 1: 加载数据
        logger.info('Pipeline Step 1: 加载数据')
        load_result = self._load_wind_data({
            'station_id': station_id,
            'start_date': params.get('train_start_date', ''),
            'end_date': params.get('predict_end_date', params.get('train_end_date', '')),
            'load_all_nwp': True,
        })

        # Step 2: 训练模型（内部包含特征工程+训练+预测）
        logger.info('Pipeline Step 2: 特征工程 + 训练 + 预测')

        # 映射 function_id
        if model_type in ('linear', 'linear_regression', 'ridge', 'lasso'):
            func_id = 'wind_linear_model'
        elif model_type in ('decision_tree', 'random_forest', 'gbdt'):
            func_id = 'wind_tree_model'
        elif model_type == 'custom_ensemble_model':
            func_id = 'wind_xgboost_stacking'
        else:
            func_id = 'wind_tree_model'

        train_params = {
            **load_result,
            'model_type': model_type,
            'feature_groups': feature_groups,
            'train_start_date': params.get('train_start_date'),
            'train_end_date': params.get('train_end_date'),
            'predict_start_date': params.get('predict_start_date'),
            'predict_end_date': params.get('predict_end_date'),
            'param_grid': params.get('param_grid'),
            'enable_hyperparam_search': params.get('enable_hyperparam_search', True),
        }

        train_result = self._train_model(func_id, train_params)

        # Step 3: 统计分析（如果有气象源）
        sources = load_result.get('sources', [])
        analysis = {}
        if sources and load_result.get('nwp') is not None:
            logger.info('Pipeline Step 3: 统计分析')
            try:
                analysis['error_metrics'] = self._evaluate('wind_error_metrics', {
                    **load_result, 'sources': sources
                })
                analysis['correlation'] = self._evaluate('wind_correlation_analysis', {
                    **load_result, 'sources': sources
                })
            except Exception as e:
                logger.warning(f'统计分析失败: {e}')

        # 汇总结果
        result = {
            'status': 'success',
            'station_id': station_id,
            'model_type': model_type,
            'capacity': load_result.get('capacity'),
            'train_metrics': train_result.get('train_metrics', {}),
            'predict_metrics': train_result.get('predict_metrics', {}),
            'train_size': train_result.get('train_size', 0),
            'prediction_size': train_result.get('prediction_size', 0),
            'predictions': train_result.get('predictions', []),
            'actual': train_result.get('actual', []),
            'timestamps': train_result.get('timestamps', []),
            'feature_groups': feature_groups,
            'feature_names': train_result.get('feature_names', []),
            'analysis': analysis,
        }

        logger.info(f'Pipeline 完成: train_metrics={result["train_metrics"]}, predict_metrics={result["predict_metrics"]}')
        return result

    # ==================== 拆解后的工作流节点 ====================

    def _wf_feature_build(self, params: Dict) -> Dict:
        """统一特征矩阵构建"""
        from backend.feature_engineer import PolarsFeatureEngineer
        nwp = params.get('nwp')
        true_data = params.get('true_data') if params.get('true_data') is not None else params.get('true')
        fg = params.get('feature_groups', ['raw_meteorological', 'time_features', 'business_features', 'statistical_features'])
        if nwp is None or true_data is None:
            raise ValueError('缺少 nwp 或 true 数据')
        eng = PolarsFeatureEngineer({'nwp': nwp, 'true': true_data})
        fm = eng.build_feature_matrix(fg)
        fcols = [c for c in fm.columns if c not in ['timestamp', 'forecast_time']]
        logger.info(f'特征矩阵: {fm.shape}, 特征列: {len(fcols)}')
        return {**params, 'feature_matrix': fm, 'feature_columns': fcols}

    def _wf_train_split(self, params: Dict) -> Dict:
        """训练/预测集划分"""
        fm = params.get('feature_matrix')
        true_data = params.get('true_data') if params.get('true_data') is not None else params.get('true')
        fcols = params.get('feature_columns')
        ts, te = pd.to_datetime(params['train_start']), pd.to_datetime(params['train_end'])
        tmask = (true_data['timestamp'] >= ts) & (true_data['timestamp'] <= te)
        td = pd.merge(true_data[tmask], fm, on='timestamp', how='outer')
        X_train = td[fcols]
        y_train = td[['WS', 'WS_min', 'WS_median', 'WS_max', 'POWER']]
        result = {**params, 'X_train': X_train, 'y_train': y_train}
        ps = params.get('predict_start')
        pe = params.get('predict_end')
        if ps and pe:
            pstart, pend = pd.to_datetime(ps), pd.to_datetime(pe)
            pmask = (fm['timestamp'] >= pstart) & (fm['timestamp'] <= pend)
            result['X_predict'] = fm[pmask][fcols]
            result['predict_timestamps'] = fm[pmask]['timestamp']
        logger.info(f'训练: {X_train.shape}, 预测: {result.get("X_predict", pd.DataFrame()).shape}')
        return result

    def _wf_ws_xgb_train(self, params: Dict) -> Dict:
        """第一层：风速 XGBoost 训练"""
        import xgboost as xgb
        from backend.models.model_wrapper import _ParameterSampler
        X = params.get('X_train')
        y = params.get('y_train')
        src = params.get('nwp_source')
        if X is None or y is None or not src:
            raise ValueError('缺少 X_train/y_train/nwp_source')
        # 提取该源的输入特征
        input_cols = [c for c in X.columns if c.startswith(src + '_') or c in ['hour', 'day_of_week', 'month', 'season', 'is_weekend', 'hour_sin', 'hour_cos', 'i.set']]
        if not input_cols:
            raise ValueError(f'未找到气象源 {src} 的特征列')
        x_src = X[input_cols]
        # 清洗
        valid = x_src.notnull().all(axis=1) & y['WS'].notnull()
        x_clean, y_clean = x_src[valid], y[valid]
        # CV index
        i_set = x_clean.get('i.set', pd.Series(range(len(x_clean))))
        cv_idx = np.zeros(len(x_clean), dtype=int)
        unique_sets = np.unique(i_set.values)
        np.random.seed(2026)
        np.random.shuffle(unique_sets)
        for k in range(5):
            for m in unique_sets[k::5]:
                cv_idx[i_set.values == m] = k
        feat_cols = [c for c in input_cols if c != 'i.set']
        x_feat = x_clean[feat_cols]
        # 超参数搜索 + 训练 4 个风速目标
        grid = {'seed': [2020], 'eta': [0.00075, 0.05, 0.01, 0.1, 0.3], 'max_depth': list(range(2, 4)),
                'alpha': [0.3, 1, 3, 5, 10], 'min_child_weight': [0.1, 0.3, 3],
                'subsample': [0.6, 0.7, 0.8], 'lambda': [0.1, 0.3, 1, 3]}
        ws_models = {}
        ws_oof = {}
        targets = {'mean': 'WS', 'min': 'WS_min', 'median': 'WS_median', 'max': 'WS_max'}
        # 先搜索 mean 的超参数
        y_ws = np.log1p(y_clean['WS'].values)
        X_tr, y_tr = x_feat[cv_idx != 0], y_ws[cv_idx != 0]
        X_va, y_va = x_feat[cv_idx == 0], y_ws[cv_idx == 0]
        best_score, best_param, best_ntree = float('inf'), {}, 100
        for p in _ParameterSampler(grid, 32):
            dtrain = xgb.DMatrix(X_tr, y_tr)
            dval = xgb.DMatrix(X_va, y_va)
            bst = xgb.train(p, dtrain, 800, evals=[(dval, 'eval')], early_stopping_rounds=8, verbose_eval=False)
            score = float(bst.eval(dval).split(':')[1])
            if score < best_score:
                best_score, best_param, best_ntree = score, p, bst.best_ntree_limit or bst.num_boosted_rounds()
        logger.info(f'{src} WS best: score={best_score:.4f}, ntree={best_ntree}, param={best_param}')
        # 用最优参数训练 4 个目标
        for suffix, col in targets.items():
            y_t = np.log1p(y_clean[col].values)
            oof = np.zeros(len(y_t)) * np.nan
            for k in range(5):
                dt = xgb.DMatrix(x_feat[cv_idx != k], y_t[cv_idx != k])
                dv = xgb.DMatrix(x_feat[cv_idx == k])
                bst = xgb.train(best_param, dt, best_ntree)
                oof[cv_idx == k] = bst.predict(dv)
            # 全量训练
            dt_all = xgb.DMatrix(x_feat, y_t)
            bst_all = xgb.train(best_param, dt_all, best_ntree)
            key = f'{src}.final_rho_{suffix}'
            ws_models[key] = bst_all
            ws_oof[key] = np.expm1(oof)
        logger.info(f'{src} 风速训练完成, 4个模型')
        return {**params, f'ws_models_{src}': ws_models, f'ws_oof_{src}': ws_oof,
                f'ws_feat_cols_{src}': feat_cols, f'ws_cv_idx_{src}': cv_idx,
                f'ws_valid_{src}': valid, f'ws_best_param_{src}': best_param, f'ws_best_ntree_{src}': best_ntree}

    def _wf_power_xgb_train(self, params: Dict) -> Dict:
        """第二层：功率 XGBoost 训练"""
        import xgboost as xgb
        from backend.models.model_wrapper import _ParameterSampler
        from backend.models.custom_model_epf import CustomModelEpfWrapper
        src = params.get('nwp_source')
        capacity = params.get('capacity')
        X = params.get('X_train')
        y = params.get('y_train')
        ws_models = params.get(f'ws_models_{src}')
        ws_oof = params.get(f'ws_oof_{src}')
        valid = params.get(f'ws_valid_{src}')
        cv_idx = params.get(f'ws_cv_idx_{src}')
        feat_cols = params.get(f'ws_feat_cols_{src}')
        x_clean = X[valid][feat_cols]
        y_clean = y[valid]
        # 拼接风速 OOF 预测
        ws_feat = pd.DataFrame({k: v for k, v in ws_oof.items()}, index=x_clean.index)
        x_pw = pd.concat([x_clean, ws_feat], axis=1)
        # 添加 rho_crossed 特征
        x_pw = CustomModelEpfWrapper.add_feature_rho_crossed(x_pw, src)
        _, _, output_pw, _ = CustomModelEpfWrapper._2st_stacking_feature(None, src)
        pw_input_cols = [c for c in x_pw.columns if c.startswith(f'{src}.final_rho')]
        # 功率目标归一化
        y_pw = (y_clean['POWER'] / capacity).values
        X_tr, y_tr = x_pw[pw_input_cols].iloc[cv_idx != 0], y_pw[cv_idx != 0]
        X_va, y_va = x_pw[pw_input_cols].iloc[cv_idx == 0], y_pw[cv_idx == 0]
        grid_pw = {'seed': [2020], 'eta': [0.01, 0.05, 0.1, 0.3, 0.5], 'max_depth': list(range(2, 4)),
                   'alpha': [0.3, 1, 3, 5, 10], 'min_child_weight': [0.1, 0.3, 3],
                   'subsample': [0.6, 0.7, 0.8], 'lambda': [0.3, 1, 3]}
        best_score, best_param, best_ntree = float('inf'), {}, 100
        for p in _ParameterSampler(grid_pw, 32):
            dt = xgb.DMatrix(X_tr, y_tr)
            dv = xgb.DMatrix(X_va, y_va)
            bst = xgb.train(p, dt, 800, evals=[(dv, 'eval')], early_stopping_rounds=8, verbose_eval=False)
            score = float(bst.eval(dv).split(':')[1])
            if score < best_score:
                best_score, best_param, best_ntree = score, p, bst.best_ntree_limit or bst.num_boosted_rounds()
        logger.info(f'{src} Power best: score={best_score:.4f}')
        # OOF 预测
        pw_oof = np.zeros(len(y_pw)) * np.nan
        for k in range(5):
            dt = xgb.DMatrix(x_pw[pw_input_cols].iloc[cv_idx != k], y_pw[cv_idx != k])
            dv = xgb.DMatrix(x_pw[pw_input_cols].iloc[cv_idx == k])
            bst = xgb.train(best_param, dt, best_ntree)
            pw_oof[cv_idx == k] = bst.predict(dv)
        # 全量
        dt_all = xgb.DMatrix(x_pw[pw_input_cols], y_pw)
        pw_model = xgb.train(best_param, dt_all, best_ntree)
        logger.info(f'{src} 功率训练完成')
        return {**params, f'pw_model_{src}': pw_model, f'pw_oof_{src}': pw_oof,
                f'pw_input_cols_{src}': pw_input_cols}

    def _wf_fusion_train(self, params: Dict) -> Dict:
        """第三层：多源融合训练"""
        from sklearn.linear_model import LinearRegression
        sources = params.get('sources', [])
        y = params.get('y_train')
        capacity = params.get('capacity')
        # 收集各源的 OOF 功率预测
        pw_dict = {}
        for src in sources:
            oof = params.get(f'pw_oof_{src}')
            valid = params.get(f'ws_valid_{src}')
            if oof is not None:
                full_oof = np.full(len(y), np.nan)
                full_oof[valid] = oof
                pw_dict[f'{src}.final_pw'] = full_oof
        pw_df = pd.DataFrame(pw_dict)
        # 清洗
        y_power = y['POWER'].values
        valid_mask = pw_df.notnull().all(axis=1) & ~np.isnan(y_power)
        pw_clean = pw_df[valid_mask]
        y_clean = y_power[valid_mask]
        lr = LinearRegression()
        lr.fit(pw_clean, y_clean)
        fusion_pred = lr.predict(pw_clean)
        rmse = np.sqrt(np.mean((y_clean - fusion_pred) ** 2))
        logger.info(f'融合训练: coef={lr.coef_}, intercept={lr.intercept_:.2f}, RMSE={rmse:.2f}')
        return {**params, 'fusion_model': lr, 'fusion_train_rmse': rmse}

    def _wf_ws_xgb_predict(self, params: Dict) -> Dict:
        """第一层预测：风速"""
        import xgboost as xgb
        src = params.get('nwp_source')
        X = params.get('X_predict')
        ws_models = params.get(f'ws_models_{src}')
        feat_cols = params.get(f'ws_feat_cols_{src}')
        x_src = X[feat_cols]
        ws_pred = {}
        for key, model in ws_models.items():
            raw = model.predict(xgb.DMatrix(x_src))
            ws_pred[key] = np.expm1(raw)
        logger.info(f'{src} 风速预测完成')
        return {**params, f'ws_pred_{src}': ws_pred}

    def _wf_power_xgb_predict(self, params: Dict) -> Dict:
        """第二层预测：功率"""
        import xgboost as xgb
        from backend.models.custom_model_epf import CustomModelEpfWrapper
        src = params.get('nwp_source')
        X = params.get('X_predict')
        feat_cols = params.get(f'ws_feat_cols_{src}')
        pw_model = params.get(f'pw_model_{src}')
        pw_input_cols = params.get(f'pw_input_cols_{src}')
        ws_pred = params.get(f'ws_pred_{src}')
        x_src = X[feat_cols]
        ws_df = pd.DataFrame(ws_pred, index=x_src.index)
        x_pw = pd.concat([x_src, ws_df], axis=1)
        x_pw = CustomModelEpfWrapper.add_feature_rho_crossed(x_pw, src)
        pw_pred = pw_model.predict(xgb.DMatrix(x_pw[pw_input_cols]))
        logger.info(f'{src} 功率预测完成: [{pw_pred.min():.4f}, {pw_pred.max():.4f}]')
        return {**params, f'pw_pred_{src}': pw_pred}

    def _wf_fusion_predict(self, params: Dict) -> Dict:
        """第三层预测：融合"""
        sources = params.get('sources', [])
        fusion_model = params.get('fusion_model')
        capacity = params.get('capacity', 1.0)
        pw_dict = {}
        for src in sources:
            pred = params.get(f'pw_pred_{src}')
            if pred is not None:
                pw_dict[f'{src}.final_pw'] = pred
        pw_df = pd.DataFrame(pw_dict)
        final = fusion_model.predict(pw_df)
        final = np.clip(final, 0, capacity)
        logger.info(f'融合预测: [{final.min():.1f}, {final.max():.1f}]')
        return {**params, 'final_predictions': final}

    def _wf_evaluate(self, params: Dict) -> Dict:
        """评估"""
        from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
        pred = params.get('predictions') or params.get('final_predictions')
        actual = params.get('actuals')
        capacity = params.get('capacity', 1.0)
        label = params.get('label', 'eval')
        if pred is None or actual is None:
            raise ValueError('缺少 predictions 或 actuals')
        pred, actual = np.array(pred), np.array(actual)
        valid = ~(np.isnan(pred) | np.isnan(actual))
        p, a = pred[valid], actual[valid]
        rmse = np.sqrt(mean_squared_error(a, p))
        mae = mean_absolute_error(a, p)
        r2 = r2_score(a, p)
        metrics = {'rmse': float(rmse), 'mae': float(mae), 'r2': float(r2), 'rmse_pct': float(rmse / capacity * 100)}
        logger.info(f'{label}: RMSE={rmse:.2f} MAE={mae:.2f} R2={r2:.4f} RMSE%={metrics["rmse_pct"]:.2f}%')
        return {**params, 'metrics': metrics}
# @AI_GENERATED: end
