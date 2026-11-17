"""
Flask API路由模块
提供所有API端点的实现
"""

from flask import Blueprint, jsonify, request, send_file, current_app
import logging

logger = logging.getLogger(__name__)
from backend.data_loader import DataLoader
from backend.data_processor import DataProcessor
from backend.statistical_analyzer import StatisticalAnalyzer
from backend.feature_engineer import FeatureEngineer, PolarsFeatureEngineer
from backend.models.linear_model_wrapper import LinearModelWrapper
from backend.models.tree_model_wrapper import TreeModelWrapper
from backend.models.custom_model_epf import CustomModelEpfWrapper
from backend.utils import resample_both_dimensions
import uuid
import time
import io
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error
from datetime import timedelta

# 创建蓝图
api_bp = Blueprint('api', __name__)

# 会话存储（生产环境应使用Redis等持久化存储）
session_store = {}

# 会话清理函数
def cleanup_expired_sessions():
    """清理过期的会话数据"""
    current_time = time.time()
    timeout = current_app.config.get('SESSION_TIMEOUT', 3600)
    
    expired_keys = []
    for key, value in session_store.items():
        if current_time - value.get('timestamp', 0) > timeout:
            expired_keys.append(key)
    
    for key in expired_keys:
        del session_store[key]


# ============================================================================
# 场站管理相关API
# ============================================================================

@api_bp.route('/stations', methods=['GET'])
def get_stations():
    """
    获取所有可用场站列表
    
    Returns:
        JSON响应，包含场站列表
        {
            "status": "success",
            "stations": ["42ApNwtb", "2teqaOf0", ...]
        }
    """
    try:
        logger.info('Fetching station list')
        loader = DataLoader()
        stations = loader.scan_stations()
        
        logger.info(f'Found {len(stations)} stations')
        return jsonify({
            'status': 'success',
            'stations': stations,
            'count': len(stations)
        }), 200
        
    except FileNotFoundError as e:
        return jsonify({
            'status': 'error',
            'message': f'数据目录不存在: {str(e)}'
        }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'获取场站列表失败: {str(e)}'
        }), 500


@api_bp.route('/stations/<station_id>/info', methods=['GET'])
def get_station_info(station_id):
    """
    获取指定场站的信息
    
    Args:
        station_id: 场站ID
    
    Returns:
        JSON响应，包含场站信息
        {
            "status": "success",
            "station_id": "42ApNwtb",
            "files": {"nwp": true, "true": true},
            "data_range": {"start": "...", "end": "..."},
            "available_sources": [...]
        }
    """
    try:
        loader = DataLoader()
        
        # 验证文件完整性
        validation = loader.validate_data_files(station_id)
        
        # 检查是否所有文件都存在
        all_files_exist = all(validation.values())
        
        if not all_files_exist:
            return jsonify({
                'status': 'error',
                'message': f'场站 {station_id} 的数据文件不完整',
                'files': validation
            }), 404
        
        # 加载数据以获取更多信息
        data = loader.load_station_data(station_id)
        
        # 创建临时处理器以获取气象源信息
        processor = DataProcessor(data['nwp'], data['true'])
        sources = processor.get_meteorological_sources()
        
        # 获取数据时间范围
        nwp_index = data['nwp'].iloc[:, 0]
        nwp_dates = pd.to_datetime(nwp_index)
        
        return jsonify({
            'status': 'success',
            'station_id': station_id,
            'files': validation,
            'data_range': {
                'start': nwp_dates.min().strftime('%Y-%m-%d %H:%M:%S'),
                'end': nwp_dates.max().strftime('%Y-%m-%d %H:%M:%S'),
                'total_records': len(nwp_dates)
            },
            'available_sources': sources
        }), 200
        
    except FileNotFoundError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'获取场站信息失败: {str(e)}'
        }), 500


# ============================================================================
# 数据加载和获取相关API
# ============================================================================

@api_bp.route('/data/load', methods=['POST'])
def load_data():
    """
    加载和处理场站数据
    
    请求体:
        {
            "station_id": "42ApNwtb",
            "resolution": "1H",
            "start_date": "2024-06-01",
            "end_date": "2024-06-15"
        }
    
    Returns:
        JSON响应，包含会话ID
        {
            "status": "success",
            "data_id": "session_key",
            "message": "数据加载成功"
        }
    """
    try:
        # 清理过期会话
        cleanup_expired_sessions()
        
        # 获取请求参数
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        station_id = data.get('station_id')
        resolution = data.get('resolution', current_app.config.get('DEFAULT_RESOLUTION', '1H'))
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # 验证必需参数
        if not station_id:
            logger.warning('Load data request missing station_id')
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: station_id'
            }), 400
        
        logger.info(f'Loading data for station: {station_id}, resolution: {resolution}')
        
        # 验证分辨率
        allowed_resolutions = current_app.config.get('ALLOWED_RESOLUTIONS', ['15min', '30min', '1H', '3H'])
        if resolution not in allowed_resolutions:
            logger.warning(f'Invalid resolution: {resolution}')
            return jsonify({
                'status': 'error',
                'message': f'无效的时间分辨率: {resolution}，允许的值: {allowed_resolutions}'
            }), 400
        
        # 加载数据
        loader = DataLoader()
        
        # 获取场站容量信息
        station_capacity = loader.get_station_capacity(station_id)
        if station_capacity is None:
            logger.warning(f'场站 {station_id} 没有配置容量信息')
        else:
            logger.info(f'场站 {station_id} 容量: {station_capacity} MW')
        
        # 传递日期范围给DataLoader（如果没有指定，DataLoader会使用默认的2个月）
        raw_data = loader.load_station_data(station_id, start_date, end_date)
        logger.debug(f'Raw data loaded for station {station_id}')
        
        # 处理数据
        processor = DataProcessor(raw_data['nwp'], raw_data['true'])
        
        # 获取被删除的列信息
        removed_columns_info = processor.get_removed_columns_info()
        if removed_columns_info:
            logger.warning(f'数据处理时删除了 {len(removed_columns_info)} 个气象源的部分要素')
        
        processor.align_timestamps(resolution)
        processor.interpolate_data()
        
        # 如果指定了日期范围，进行过滤
        if start_date and end_date:
            try:
                processor.filter_by_date_range(start_date, end_date)
            except ValueError as e:
                return jsonify({
                    'status': 'error',
                    'message': f'日期范围错误: {str(e)}'
                }), 400
        elif not start_date and not end_date:
            # 如果没有指定日期范围，使用默认范围（数据截止时间之前的10天）
            default_days = 10  # 改为10天
            processed_data = processor.get_processed_data()
            end = processed_data['nwp'].index.max()
            start = end - timedelta(days=default_days)
            logger.info(f'Using default date range: {start} to {end} (last {default_days} days)')
            processor.filter_by_date_range(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
        
        # 获取处理后的数据
        processed_data = processor.get_processed_data()
        
        # 获取气象源列表
        sources = processor.get_meteorological_sources()
        
        # 生成会话ID
        session_id = str(uuid.uuid4())
        
        # 存储到会话
        session_store[session_id] = {
            'station_id': station_id,
            'resolution': resolution,
            'raw_data': raw_data,
            'processor': processor,
            'processed_data': processed_data,
            'sources': sources,
            'capacity': station_capacity,
            'timestamp': time.time()
        }
        
        # 详细日志
        logger.info(f'Data loaded successfully:')
        logger.info(f'  - Session ID: {session_id}')
        logger.info(f'  - Station: {station_id}')
        logger.info(f'  - Resolution: {resolution}')
        logger.info(f'  - Data points: {len(processed_data["nwp"])}')
        logger.info(f'  - Sources count: {len(sources)}')
        logger.info(f'  - Sources: {", ".join(sources)}')
        logger.info(f'  - Date range: {processed_data["nwp"].index.min()} to {processed_data["nwp"].index.max()}')
        
        response_data = {
            'status': 'success',
            'data_id': session_id,
            'message': '数据加载成功',
            'info': {
                'station_id': station_id,
                'resolution': resolution,
                'data_points': len(processed_data['nwp']),
                'sources': sources,
                'capacity': station_capacity,
                'date_range': {
                    'start': processed_data['nwp'].index.min().strftime('%Y-%m-%d %H:%M:%S'),
                    'end': processed_data['nwp'].index.max().strftime('%Y-%m-%d %H:%M:%S')
                },
                'removed_columns': removed_columns_info if removed_columns_info else []
            }
        }
        
        logger.debug(f'Response data: {response_data}')
        
        return jsonify(response_data), 200
        
    except FileNotFoundError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 404
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'数据加载失败: {str(e)}'
        }), 500


@api_bp.route('/data/timeseries', methods=['POST'])
def get_timeseries():
    """
    获取时间序列数据
    
    请求体:
        {
            "data_id": "session_key",
            "sources": ["DWD", "EC_10D"],
            "include_true": true
        }
    
    Returns:
        JSON响应，包含时间序列数据
        {
            "status": "success",
            "timestamps": [...],
            "series": {
                "DWD_WS": [...],
                "EC_10D_WS": [...],
                "true": [...]
            }
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        data_id = data.get('data_id')
        sources = data.get('sources', [])
        include_true = data.get('include_true', False)
        
        # 验证必需参数
        if not data_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data_id'
            }), 400
        
        # 检查会话是否存在
        if data_id not in session_store:
            return jsonify({
                'status': 'error',
                'message': '会话不存在或已过期，请重新加载数据'
            }), 401
        
        # 获取会话数据
        session = session_store[data_id]
        processed_data = session['processed_data']
        processor = session['processor']
        
        # 构建时间序列响应
        timestamps = processed_data['nwp'].index.strftime('%Y-%m-%d %H:%M:%S').tolist()
        series = {}
        
        # 添加选定的气象源数据
        logger.info(f'Processing {len(sources)} sources for timeseries')
        for source in sources:
            try:
                ws_data = processor.extract_feature_by_source(source, 'WS')
                key = f'{source}_WS'
                series[key] = ws_data.tolist()
                logger.info(f'Added source: {source} as {key}, data points: {len(ws_data)}')
            except ValueError as e:
                # 气象源不存在，跳过
                logger.warning(f'Source {source} not found: {e}')
                continue

        # 添加真实风速数据
        if include_true:
            if 'WS' in processed_data['true'].columns:
                series['true'] = processed_data['true']['WS'].tolist()
                logger.info(f'Added true, data points: {len(series["true"])}')
            else:
                logger.warning('true column not found')
        
        logger.info(f'Timeseries response: {len(timestamps)} timestamps, {len(series)} series')
        logger.info(f'Series keys: {list(series.keys())}')
        
        return jsonify({
            'status': 'success',
            'timestamps': timestamps,
            'series': series,
            'count': len(timestamps)
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'获取时间序列数据失败: {str(e)}'
        }), 500


# ============================================================================
# 统计分析相关API
# ============================================================================

@api_bp.route('/analysis/correlation', methods=['POST'])
def analyze_correlation():
    """
    计算相关性分析
    
    请求体:
        {
            "data_id": "session_key",
            "sources": ["DWD", "EC_10D", "GFS"]
        }
    
    Returns:
        JSON响应，包含相关性分析结果
        {
            "status": "success",
            "correlations": [
                {"source": "DWD", "correlation": 0.95},
                ...
            ],
            "matrix": [[1.0, 0.9, ...], ...]
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        data_id = data.get('data_id')
        sources = data.get('sources', [])
        
        # 验证必需参数
        if not data_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data_id'
            }), 400
        
        # 检查会话是否存在
        if data_id not in session_store:
            return jsonify({
                'status': 'error',
                'message': '会话不存在或已过期，请重新加载数据'
            }), 401
        
        # 获取会话数据
        session = session_store[data_id]
        processed_data = session['processed_data']
        
        # 如果没有指定sources，使用所有可用的气象源
        if not sources:
            sources = session['sources']
        
        # 创建统计分析器
        analyzer = StatisticalAnalyzer(processed_data)
        
        # 计算相关性矩阵
        try:
            correlation_matrix_df = analyzer.calculate_correlation_matrix(sources)
            correlation_matrix = correlation_matrix_df.values.tolist()
            matrix_labels = correlation_matrix_df.columns.tolist()

            # 计算相关性
            correlations_df = pd.DataFrame(correlation_matrix_df['WS']).reset_index()
            correlations_df.columns = ['source', 'correlation']
            correlations_df = correlations_df[~ correlations_df['source'].isin(['WS'])]
            correlations_df = correlations_df.sort_values("correlation", ascending=False, na_position='last')
            correlations_df = correlations_df.reset_index(drop=True)
            correlations = correlations_df.to_dict('records')
        except ValueError:
            # 气象源不足，无法计算矩阵
            correlations = pd.DataFrame()
            correlation_matrix = []
            matrix_labels = []
        
        return jsonify({
            'status': 'success',
            'correlations': correlations,
            'matrix': correlation_matrix,
            'matrix_labels': matrix_labels
        }), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'相关性分析失败: {str(e)}'
        }), 500


@api_bp.route('/analysis/error_metrics', methods=['POST'])
def analyze_error_metrics():
    """
    计算误差指标
    
    请求体:
        {
            "data_id": "session_key",
            "sources": ["DWD", "EC_10D", "GFS"]
        }
    
    Returns:
        JSON响应，包含误差指标
        {
            "status": "success",
            "metrics": [
                {"source": "DWD", "RMSE": 1.23, "MAE": 0.98},
                ...
            ]
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        logger.info('=== Error Metrics Analysis Request ===')
        logger.info(f'Request data: {data}')
        
        if not data:
            logger.warning('Empty request body')
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        data_id = data.get('data_id')
        sources = data.get('sources', [])
        
        logger.info(f'Data ID: {data_id}')
        logger.info(f'Requested sources: {sources}')
        
        # 验证必需参数
        if not data_id:
            logger.warning('Missing data_id parameter')
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data_id'
            }), 400
        
        # 检查会话是否存在
        if data_id not in session_store:
            logger.warning(f'Session not found: {data_id}')
            logger.info(f'Available sessions: {list(session_store.keys())}')
            return jsonify({
                'status': 'error',
                'message': '会话不存在或已过期，请重新加载数据'
            }), 401
        
        # 获取会话数据
        session = session_store[data_id]
        processed_data = session['processed_data']
        available_sources = session['sources']
        
        logger.info(f'Session found - Available sources: {available_sources}')
        
        # 如果没有指定sources，使用所有可用的气象源
        if not sources:
            sources = available_sources
            logger.info(f'No sources specified, using all available: {sources}')
        
        # 创建统计分析器
        analyzer = StatisticalAnalyzer(processed_data)
        
        # 计算误差指标
        logger.info(f'Calculating error metrics for sources: {sources}')
        metrics_df = analyzer.calculate_error_metrics(sources)
        metrics = metrics_df.to_dict('records')
        
        logger.info(f'Error metrics calculated successfully:')
        for metric in metrics:
            logger.info(f'  - {metric.get("source")}: RMSE={metric.get("RMSE")}, MAE={metric.get("MAE")}')
        
        response_data = {
            'status': 'success',
            'metrics': metrics
        }
        
        logger.debug(f'Response: {response_data}')
        
        return jsonify(response_data), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'误差指标计算失败: {str(e)}'
        }), 500


@api_bp.route('/analysis/distribution', methods=['POST'])
def analyze_distribution():
    """
    计算数据分布统计
    
    请求体:
        {
            "data_id": "session_key",
            "data_type": "true"  // 可选: "true",  或气象源名称
        }
    
    Returns:
        JSON响应，包含分布统计
        {
            "status": "success",
            "stats": {
                "mean": 5.2,
                "median": 5.0,
                "std": 2.1,
                ...
            },
            "histogram": {
                "bins": [...],
                "counts": [...]
            }
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        data_id = data.get('data_id')
        data_type = data.get('data_type', 'true')
        
        # 验证必需参数
        if not data_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data_id'
            }), 400
        
        # 检查会话是否存在
        if data_id not in session_store:
            return jsonify({
                'status': 'error',
                'message': '会话不存在或已过期，请重新加载数据'
            }), 401
        
        # 获取会话数据
        session = session_store[data_id]
        processed_data = session['processed_data']
        
        # 创建统计分析器
        analyzer = StatisticalAnalyzer(processed_data)
        
        # 根据data_type获取相应的数据
        if data_type == 'true':
            if 'WS' not in processed_data['true'].columns:
                raise ValueError('真实风速数据不存在')
            data_series = processed_data['true']['WS']
        else:
            # 假设是气象源名称
            ws_col = f'{data_type}_WS'
            if ws_col not in processed_data['nwp'].columns:
                raise ValueError(f'气象源 {data_type} 不存在')
            data_series = processed_data['nwp'][ws_col]
        
        # 计算统计量
        stats = analyzer.calculate_distribution_stats(data_series)
        
        # 计算直方图数据
        valid_data = data_series.dropna()
        hist_counts, hist_bins = pd.cut(valid_data, bins=20, retbins=True)
        histogram = {
            'bins': hist_bins.tolist(),
            'counts': hist_counts.value_counts().sort_index().tolist()
        }
        
        return jsonify({
            'status': 'success',
            'stats': stats,
            'histogram': histogram
        }), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'分布统计计算失败: {str(e)}'
        }), 500


@api_bp.route('/analysis/wind_speed_range', methods=['POST'])
def analyze_wind_speed_range():
    """
    分析不同风速区间的预测表现
    
    请求体:
        {
            "data_id": "session_key",
            "sources": ["DWD", "EC_10D", "GFS"]
        }
    
    Returns:
        JSON响应，包含风速区间分析结果
        {
            "status": "success",
            "range_analysis": {
                "DWD": {
                    "0-3": {"rmse": 1.2, "mae": 0.9, "count": 100},
                    "3-6": {"rmse": 1.5, "mae": 1.1, "count": 200},
                    ...
                },
                ...
            },
            "ranges": ["0-3", "3-6", "6-10", "10-15", "15+"]
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        logger.info('=== Wind Speed Range Analysis Request ===')
        logger.info(f'Request data: {data}')
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        data_id = data.get('data_id')
        sources = data.get('sources', [])
        
        # 验证必需参数
        if not data_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data_id'
            }), 400
        
        # 检查会话是否存在
        if data_id not in session_store:
            return jsonify({
                'status': 'error',
                'message': '会话不存在或已过期，请重新加载数据'
            }), 401
        
        # 获取会话数据
        session = session_store[data_id]
        processed_data = session['processed_data']
        available_sources = session['sources']
        
        # 如果没有指定sources，使用所有可用的气���源
        if not sources:
            sources = available_sources
        
        logger.info(f'Analyzing wind speed ranges for sources: {sources}')
        
        # 创建统计分析器
        analyzer = StatisticalAnalyzer(processed_data)
        
        # 分析风速区间
        range_analysis = analyzer.analyze_wind_speed_ranges(sources)
        
        # 获取区间标签
        ranges = list(next(iter(range_analysis.values())).keys()) if range_analysis else []
        
        logger.info(f'Wind speed range analysis completed for {len(sources)} sources')
        
        return jsonify({
            'status': 'success',
            'range_analysis': range_analysis,
            'ranges': ranges
        }), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f'Wind speed range analysis failed: {str(e)}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'风速区间分析失败: {str(e)}'
        }), 500


@api_bp.route('/analysis/seasonal', methods=['POST'])
def analyze_seasonal():
    """
    分析不同季节的预测表现
    
    请求体:
        {
            "data_id": "session_key",
            "sources": ["DWD", "EC_10D", "GFS"]
        }
    
    Returns:
        JSON响应，包含季节性分析结果
        {
            "status": "success",
            "seasonal_analysis": {
                "DWD": {
                    "春季": {"rmse": 1.2, "mae": 0.9, "count": 100},
                    "夏季": {"rmse": 1.5, "mae": 1.1, "count": 200},
                    "秋季": {"rmse": 1.3, "mae": 1.0, "count": 150},
                    "冬季": {"rmse": 1.4, "mae": 1.0, "count": 180}
                },
                ...
            }
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        logger.info('=== Seasonal Analysis Request ===')
        logger.info(f'Request data: {data}')
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        data_id = data.get('data_id')
        sources = data.get('sources', [])
        
        # 验证必需参数
        if not data_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data_id'
            }), 400
        
        # 检查会话是否存在
        if data_id not in session_store:
            return jsonify({
                'status': 'error',
                'message': '会话不存在或已过期，请重新加载数据'
            }), 401
        
        # 获取会话数据
        session = session_store[data_id]
        processed_data = session['processed_data']
        available_sources = session['sources']
        
        # 如果没有指定sources，使用所有可用的气象源
        if not sources:
            sources = available_sources
        
        logger.info(f'Analyzing seasonal performance for sources: {sources}')
        
        # 创建统计分析器
        analyzer = StatisticalAnalyzer(processed_data)
        
        # 分析季节性表现
        seasonal_analysis = analyzer.analyze_seasonal_performance(sources)
        
        logger.info(f'Seasonal analysis completed for {len(sources)} sources')
        
        return jsonify({
            'status': 'success',
            'seasonal_analysis': seasonal_analysis
        }), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f'Seasonal analysis failed: {str(e)}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'季节性分析失败: {str(e)}'
        }), 500


@api_bp.route('/analysis/bias_distribution', methods=['POST'])
def analyze_bias_distribution():
    """
    分析不同气象源与真实风速的单点偏差分布
    
    请求体:
        {
            "data_id": "session_key",
            "sources": ["DWD", "EC_10D", "GFS"]
        }
    
    Returns:
        JSON响应，包含偏差分布分析结果
        {
            "status": "success",
            "bias_distribution": {
                "DWD": {
                    "bias": [0.5, -0.3, 1.2, ...],
                    "mean_bias": 0.2,
                    "std_bias": 1.1,
                    "min_bias": -3.5,
                    "max_bias": 4.2,
                    "q25": -0.5,
                    "q50": 0.1,
                    "q75": 0.8,
                    "count": 1000
                },
                ...
            }
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        logger.info('=== Bias Distribution Analysis Request ===')
        logger.info(f'Request data: {data}')
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        data_id = data.get('data_id')
        sources = data.get('sources', [])
        
        # 验证必需参数
        if not data_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data_id'
            }), 400
        
        # 检查会话是否存在
        if data_id not in session_store:
            return jsonify({
                'status': 'error',
                'message': '会话不存在或已过期，请重新加载数据'
            }), 401
        
        # 获取会话数据
        session = session_store[data_id]
        processed_data = session['processed_data']
        available_sources = session['sources']
        
        # 如果没有指定sources，使用所有可用的气象源
        if not sources:
            sources = available_sources
        
        logger.info(f'Analyzing bias distribution for sources: {sources}')
        
        # 创建统计分析器
        analyzer = StatisticalAnalyzer(processed_data)
        
        # 分析偏差分布
        bias_distribution = analyzer.analyze_bias_distribution(sources)
        
        logger.info(f'Bias distribution analysis completed for {len(sources)} sources')
        
        return jsonify({
            'status': 'success',
            'bias_distribution': bias_distribution
        }), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f'Bias distribution analysis failed: {str(e)}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'偏差分布分析失败: {str(e)}'
        }), 500


# ============================================================================
# 特征工程相关API
# ============================================================================

@api_bp.route('/features/groups', methods=['GET'])
def get_feature_groups():
    """
    获取特征分组信息
    
    Returns:
        JSON响应，包含特征分组
        {
            "status": "success",
            "groups": {
                "raw_meteorological": [...],
                "time_features": [...],
                "statistical_features": [...],
                "difference_features": [...],
                "interaction_features": [...]
            }
        }
    """
    try:
        # 返回特征分组的描述信息
        groups_info = {
            'raw_meteorological': {
                'name': '原始气象要素',
                'description': '包含所有气象源的原始预测数据（风速、风向、温度、气压等）',
                'features': ['所有NWP列']
            },
            'time_features': {
                'name': '时间特征',
                'description': '基于时间戳生成的特征（小时、星期、月份、季节等）',
                'features': ['hour', 'day_of_week', 'month', 'season', 'is_weekend', 'hour_sin', 'hour_cos', 'month_sin', 'month_cos']
            },
            'business_features': {
                'name': '业务特征',
                'description': '基于业务逻辑生成的特征（前后时刻风速、风向、空气密度、风速分量、趋势等）',
                'features': ['WS_p1-3', 'WS_n1-3', 'WD_p1', 'WD_n1', 'DENSITY', 'u', 'v', 'u_p1', 'v_p1', 'u_n1', 'v_n1', 'trend_n1', 'trend_p1', 'trend_13']
            },
            'statistical_features': {
                'name': '统计特征',
                'description': '滚动窗口统计特征（均值、标准差、最小值、最大值）',
                'features': ['rolling_mean_*', 'rolling_std_*', 'rolling_min_*', 'rolling_max_*']
            },
            'difference_features': {
                'name': '差值特征',
                'description': '不同气象源之间的差值特征',
                'features': ['source1_minus_source2']
            },
            'interaction_features': {
                'name': '交互特征',
                'description': '气象要素之间的交互特征（乘积、平方等）',
                'features': ['WS_squared', 'WS_x_WD', 'WS_x_TMP', 'WS_x_PRES', 'WD_sin', 'WD_cos']
            }
        }
        
        return jsonify({
            'status': 'success',
            'groups': groups_info
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'获取特征分组失败: {str(e)}'
        }), 500


@api_bp.route('/features/create', methods=['POST'])
def create_features():
    """
    创建特征矩阵
    
    请求体:
        {
            "data_id": "session_key",
            "feature_groups": ["raw_meteorological", "time_features"]
        }
    
    Returns:
        JSON响应，包含特征ID和特征信息
        {
            "status": "success",
            "feature_id": "feature_key",
            "feature_names": [...],
            "groups": {...},
            "shape": [rows, cols]
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        data_id = data.get('data_id')
        feature_groups = data.get('feature_groups', ['raw_meteorological'])
        
        # 验证必需参数
        if not data_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data_id'
            }), 400
        
        # 检查会话是否存在
        if data_id not in session_store:
            return jsonify({
                'status': 'error',
                'message': '会话不存在或已过期，请重新加载数据'
            }), 401
        
        # 获取会话数据
        session = session_store[data_id]
        processed_data = session['processed_data']
        
        # 创建特征工程器
        engineer = FeatureEngineer(processed_data)
        
        # 构建特征矩阵
        feature_matrix = engineer.build_feature_matrix(feature_groups)
        # 获取特征分组信息
        groups = engineer.get_feature_groups()
        
        # 生成特征ID
        feature_id = str(uuid.uuid4())
        
        # 存储特征到会话
        session['features'] = {
            feature_id: {
                'engineer': engineer,
                'feature_matrix': feature_matrix,
                'feature_groups': feature_groups,
                'groups': groups
            }
        }
        
        return jsonify({
            'status': 'success',
            'feature_id': feature_id,
            'feature_names': feature_matrix.columns.tolist(),
            'groups': groups,
            'shape': list(feature_matrix.shape),
            'message': f'成功创建 {feature_matrix.shape[1]} 个特征'
        }), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'特征创建失败: {str(e)}'
        }), 500


# ============================================================================
# 模型训练相关API
# ============================================================================

@api_bp.route('/model/train', methods=['POST'])
def train_model():
    """
    训练模型 - 直接从数据库加载训练和预测数据
    
    请求体:
        {
            "station_id": "42ApNwtb",
            "model_type": "random_forest",
            "params": {
                "n_estimators": 100,
                "max_depth": 10,
                "test_size": 0.2
            },
            "train_start_date": "2025-03-03",
            "train_end_date": "2025-12-31",
            "predict_start_date": "2026-01-01",
            "predict_end_date": "2026-01-31",
            "resolution": "1H",
            "sources": ["EC_10D_WS", "ENS_AVG_WS"],
            "feature_groups": ["raw_meteorological", "time_features", "statistical_features"]
        }
    
    Returns:
        JSON响应，包含模型ID和评估结果
        {
            "status": "success",
            "model_id": "model_key",
            "metrics": {"rmse": ..., "mae": ..., "spearnman_corr": ...},
            "predictions": [...],
            "actual": [...],
            "timestamps": [...],
            "train_size": 240,
            "test_size": 60
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        logger.info('=== Model Training Request (Direct Load) ===')
        logger.info(f'Request data: {data}')
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
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
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: station_id'
            }), 400
        
        if not train_start_date or not train_end_date:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: train_start_date 和 train_end_date'
            }), 400
        
        if not sources or len(sources) == 0:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: sources (至少选择一个气象源)'
            }), 400
        
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
            return jsonify({
                'status': 'error',
                'message': f'无法加载场站 {station_id} 的数据'
            }), 404
        
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
            return jsonify({
                'status': 'error',
                'message': '缺少真实风速数据'
            }), 400
        
        # ========== 步骤3: 过滤训练数据 ==========
        logger.info('Step 3: Filtering training data...')
        train_start = pd.to_datetime(train_start_date)
        train_end = pd.to_datetime(train_end_date)

        # 过滤训练期数据
        train_mask = (processed_data['true']['timestamp'] >= train_start) & (processed_data['true']['timestamp'] <= train_end)
        
        # 获取真实风速
        if 'WS' not in processed_data['true'].columns or 'POWER' not in processed_data['true'].columns:
            return jsonify({
                'status': 'error',
                'message': '真实风速或者真实功率不存在'
            }), 400

        if len(processed_data['true']['WS'][train_mask]) < 1500:
            return jsonify({
                'status': 'error',
                'message': f'训练数据点太少，请扩大日期范围。建议至少200天数据。'
            }), 400
        
        # ========== 步骤4: 生成特征 ==========
        logger.info('Step 4: Generating features...')
        engineer = PolarsFeatureEngineer(processed_data)
        
        # 构建特征矩阵
        feature_matrix = engineer.build_feature_matrix(feature_groups)
        features_train = [x for x in feature_matrix.columns if x not in ['timestamp', 'forecast_time']]
        logger.info(f'Feature columns: {list(feature_matrix.columns)}')

        # 合并真实数据和特征数据，以防特征数据有多个重复时间戳导致与真实数据时间不对齐
        train_data = pd.merge(processed_data['true'][train_mask], feature_matrix, on='timestamp', how='outer')
        
        # 过滤训练期特征
        feature_matrix_train = train_data[features_train]
        target_train = train_data[['WS', 'WS_min', 'WS_median', 'WS_max', 'POWER']]
        
        logger.info(f'Aligned training data shape: features={feature_matrix_train.shape}, target={target_train.shape}')
        
        if len(feature_matrix_train) < 1500:
            return jsonify({
                'status': 'error',
                'message': f'对齐后训练数据点太少（{len(feature_matrix_train)}条），请检查数据质量。'
            }), 400
        
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
            return jsonify({
                'status': 'error',
                'message': f'不支持的模型类型: {model_type}。支持的类型: linear_regression, ridge, lasso, decision_tree, random_forest, gbdt'
            }), 400
        
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
                    df_predictions = pd.DataFrame(
                        {'timestamp': feature_matrix[predict_mask]['timestamp'], 'prediction': predictions_pred,
                         "forecast_time": feature_matrix[predict_mask]['forecast_time']})

                    # 仅提取24H
                    df_predictions = resample_both_dimensions(df_predictions, '15min')
                    df_predictions['dist'] = (df_predictions['timestamp'] - df_predictions[
                        'forecast_time']).dt.total_seconds() / 3600
                    df_predictions = df_predictions[df_predictions['dist'].isin(range(24))]
                    df_predictions = pd.merge(df_predictions, processed_data['true'][['timestamp', 'POWER']],
                                              on='timestamp', how='left')
                    df_predictions.loc[df_predictions["prediction"] < 0, "prediction"] = 0
                    df_predictions.loc[df_predictions["prediction"] > station_capacity, "prediction"] = station_capacity

                    predictions = df_predictions['prediction'].values
                    actual_values = df_predictions['POWER'].values
                    timestamps = df_predictions['timestamp'].tolist()
                    timestamps = [x.strftime('%Y-%m-%d %H:%M:%S') for x in timestamps]

                    # 去除NaN值
                    valid_mask = ~(pd.isna(actual_values) | pd.isna(predictions))
                    target_predict_clean = actual_values[valid_mask]
                    predictions_pred_clean = predictions[valid_mask]
                    
                    if len(target_predict_clean) > 0:
                        rmse = (1 - np.sqrt(mean_squared_error(target_predict_clean, predictions_pred_clean)) / station_capacity) * 100
                        mae = (1 - mean_absolute_error(target_predict_clean, predictions_pred_clean) / station_capacity) * 100
                        spearman_corr = np.corrcoef(target_predict_clean, predictions_pred_clean)[0, 1]
                        
                        metrics = {
                            'rmse': float(rmse),
                            'mae': float(mae),
                            'spearman_corr': float(spearman_corr)
                        }
                        
                        logger.info(f'Prediction metrics: RMSE={rmse:.4f}, MAE={mae:.4f}, R2={spearman_corr:.4f}')
                    else:
                        logger.warning('No valid prediction data after removing NaN values')
                else:
                    logger.warning('No prediction data available in the specified date range')
                    
            except Exception as e:
                logger.error(f'Prediction error: {str(e)}', exc_info=True)
                return jsonify({
                    'status': 'error',
                    'message': f'预测失败: {str(e)}'
                }), 500
        else:
            logger.info('Step 6: No prediction period specified, skipping prediction')
        
        # ========== 步骤7: 保存模型到session（可选）==========
        model_id = str(uuid.uuid4())

        predictions = np.nan_to_num(predictions, nan=0.0)
        actual_values = np.nan_to_num(actual_values, nan=0.0)
        
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
        
        return jsonify({
            'status': 'success',
            'model_id': model_id,
            'model_type': model_type,
            'metrics': metrics,
            'predictions': predictions.tolist(),
            'actual': actual_values.tolist(),
            'timestamps': timestamps,
            'train_size': len(feature_matrix_train),
            'prediction_size': len(predictions),
            'capacity': station_capacity
        }), 200
        
    except ValueError as e:
        logger.error(f'ValueError in model training: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except RuntimeError as e:
        logger.error(f'RuntimeError in model training: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except FileNotFoundError as e:
        logger.error(f'FileNotFoundError in model training: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': f'数据文件不存在: {str(e)}'
        }), 404
    except Exception as e:
        logger.error(f'Exception in model training: {str(e)}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'模型训练失败: {str(e)}'
        }), 500


@api_bp.route('/model/feature_importance', methods=['POST'])
def get_feature_importance():
    """
    获取特征重要性
    
    请求体:
        {
            "model_id": "model_key",
            "top_n": 20
        }
    
    Returns:
        JSON响应，包含特征重要性
        {
            "status": "success",
            "importance": [
                {"feature": "DWD_WS", "importance": 0.25},
                ...
            ]
        }
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        model_id = data.get('model_id')
        top_n = data.get('top_n', 20)
        
        # 验证必需参数
        if not model_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: model_id'
            }), 400
        
        # 检查模型是否存在
        if model_id not in session_store:
            return jsonify({
                'status': 'error',
                'message': '模型不存在或已过期，请重新训练模型'
            }), 404
        
        # 获取模型数据
        model_data = session_store[model_id]
        trainer = model_data['model_wrapper']
        model_type = model_data['model_type']
        
        # 计算特征重要性
        logger.info(f'Calculating feature importance for model type: {model_type}')
        importance_df = trainer.get_feature_importance()
        
        logger.info(f'Feature importance calculated, total features: {len(importance_df)}')
        logger.debug(f'Top 5 features: {importance_df.head().to_dict("records")}')
        
        # 限制返回的特征数量
        if top_n and top_n > 0:
            importance_df = importance_df.head(top_n)
        
        importance = importance_df.to_dict('records')
        
        logger.info(f'Returning {len(importance)} features')
        
        return jsonify({
            'status': 'success',
            'importance': importance,
            'total_features': len(importance)
        }), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f'Error getting feature importance: {str(e)}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'获取特征重要性失败: {str(e)}'
        }), 500


# ============================================================================
# 数据导出相关API
# ============================================================================

@api_bp.route('/export/csv', methods=['POST'])
def export_csv():
    """
    导出CSV文件
    
    请求体:
        {
            "data": [...],  // 数据数组或对象
            "filename": "export.csv",
            "columns": ["col1", "col2"]  // 可选
        }
    
    Returns:
        CSV文件下载
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        export_data = data.get('data')
        filename = data.get('filename', 'export.csv')
        columns = data.get('columns')
        
        # 验证必需参数
        if not export_data:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: data'
            }), 400
        
        # 转换为DataFrame
        if isinstance(export_data, list):
            df = pd.DataFrame(export_data)
        elif isinstance(export_data, dict):
            df = pd.DataFrame(export_data)
        else:
            return jsonify({
                'status': 'error',
                'message': '数据格式错误，必须是数组或对象'
            }), 400
        
        # 如果指定了列，只导出这些列
        if columns:
            df = df[columns]
        
        # 创建CSV内存缓冲区
        output = io.StringIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')  # 使用utf-8-sig支持中文
        output.seek(0)
        
        # 创建字节流
        byte_output = io.BytesIO()
        byte_output.write(output.getvalue().encode('utf-8-sig'))
        byte_output.seek(0)
        
        # 返回文件
        return send_file(
            byte_output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'导出CSV失败: {str(e)}'
        }), 500


@api_bp.route('/export/chart', methods=['POST'])
def export_chart():
    """
    导出图表图片
    
    请求体:
        {
            "chart_data": "base64_encoded_image_data",
            "filename": "chart.png",
            "format": "png"  // 可选: "png", "svg", "jpeg"
        }
    
    Returns:
        图片文件下载
    """
    try:
        # 获取请求参数
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空'
            }), 400
        
        chart_data = data.get('chart_data')
        filename = data.get('filename', 'chart.png')
        file_format = data.get('format', 'png')
        
        # 验证必需参数
        if not chart_data:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: chart_data'
            }), 400
        
        # 解码base64数据
        import base64
        
        # 移除data URL前缀（如果存在）
        if ',' in chart_data:
            chart_data = chart_data.split(',')[1]
        
        image_data = base64.b64decode(chart_data)
        
        # 创建字节流
        byte_output = io.BytesIO(image_data)
        byte_output.seek(0)
        
        # 确定MIME类型
        mime_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'svg': 'image/svg+xml'
        }
        
        mimetype = mime_types.get(file_format.lower(), 'image/png')
        
        # 返回文件
        return send_file(
            byte_output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'导出图表失败: {str(e)}'
        }), 500
