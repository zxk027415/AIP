"""
统计分析器模块
负责计算相关性、误差指标、分布统计、缺失率
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from scipy import stats


class StatisticalAnalyzer:
    """统计分析器类，用于执行各类统计分析"""
    
    def __init__(self, processed_data: Dict[str, pd.DataFrame]):
        """
        初始化统计分析器
        
        Args:
            processed_data: 处理后的数据字典
                          {"nwp": DataFrame, "true": DataFrame, }
        
        Raises:
            ValueError: 输入数据格式错误
        """
        # 验证输入数据
        required_keys = ["nwp", "true"]
        for key in required_keys:
            if key not in processed_data:
                raise ValueError(f"缺少必需的数据: {key}")
        
        self.nwp_data = processed_data["nwp"]
        self.true_data = processed_data["true"]
        
        # 验证数据不为空
        if self.nwp_data.empty or self.true_data.empty:
            raise ValueError("输入数据不能为空")
    

    def calculate_correlation_matrix(self, sources: List[str]) -> pd.DataFrame:
        """
        计算气象源之间的相关性矩阵
        
        Args:
            sources: 气象源名称列表
        
        Returns:
            相关性矩阵DataFrame，行和列都是气象源名称
        
        Raises:
            ValueError: 气象源不存在或数据不足
        """
        # 提取所有气象源的风速数据
        df_ws = pd.merge(self.true_data['WS'], self.nwp_data[[f'{source}_WS' for source in sources]], left_index=True, right_index=True)
        # 计算相关性矩阵
        correlation_matrix = df_ws.corr()
        
        return correlation_matrix
    
    def calculate_rmse(self, predicted: pd.Series, actual: pd.Series) -> float:
        """
        计算均方根误差（RMSE）
        
        Args:
            predicted: 预测值序列
            actual: 实际值序列
        
        Returns:
            RMSE值
        
        Raises:
            ValueError: 输入数据长度不匹配或有效数据不足
        """
        if len(predicted) != len(actual):
            raise ValueError("预测值和实际值的长度必须相同")
        
        # 去除NaN值
        valid_mask = ~(predicted.isna() | actual.isna())
        
        if valid_mask.sum() < 1:
            raise ValueError("没有足够的有效数据点来计算RMSE")
        
        predicted_valid = predicted[valid_mask]
        actual_valid = actual[valid_mask]
        
        # 计算RMSE
        mse = np.mean((predicted_valid - actual_valid) ** 2)
        rmse = np.sqrt(mse)
        
        return rmse
    
    def calculate_mae(self, predicted: pd.Series, actual: pd.Series) -> float:
        """
        计算平均绝对误差（MAE）
        
        Args:
            predicted: 预测值序列
            actual: 实际值序列
        
        Returns:
            MAE值
        
        Raises:
            ValueError: 输入数据长度不匹配或有效数据不足
        """
        if len(predicted) != len(actual):
            raise ValueError("预测值和实际值的长度必须相同")
        
        # 去除NaN值
        valid_mask = ~(predicted.isna() | actual.isna())
        
        if valid_mask.sum() < 1:
            raise ValueError("没有足够的有效数据点来计算MAE")
        
        predicted_valid = predicted[valid_mask]
        actual_valid = actual[valid_mask]
        
        # 计算MAE
        mae = np.mean(np.abs(predicted_valid - actual_valid))
        
        return mae

    def calculate_error_metrics(self, sources: List[str]) -> pd.DataFrame:
        """
        批量计算所有源的误差指标
        
        Args:
            sources: 气象源名称列表
        
        Returns:
            DataFrame，包含列 [source, RMSE, MAE]
            按RMSE从低到高排序
        
        Raises:
            ValueError: 真实风速数据缺失
        """
        # 获取真实风速列
        true_ws_col = self._get_true_ws_column()
        
        if true_ws_col is None:
            raise ValueError("真实风速数据缺失")
        
        true_ws = self.true_data[true_ws_col]
        
        results = []
        
        # 计算每个气象源的误差指标
        for source in sources:
            ws_column = f"{source}_WS"
            
            if ws_column not in self.nwp_data.columns:
                # 跳过不存在的气象源
                continue
            
            source_ws = self.nwp_data[ws_column]
            
            try:
                rmse = self.calculate_rmse(source_ws, true_ws)
                mae = self.calculate_mae(source_ws, true_ws)
                
                results.append({
                    "source": source,
                    "RMSE": rmse,
                    "MAE": mae
                })
            except ValueError:
                # 数据不足，跳过该气象源
                continue
        
        # 创建DataFrame并按RMSE升序排序
        df_result = pd.DataFrame(results)
        if not df_result.empty:
            df_result = df_result.sort_values("RMSE", ascending=True)
            df_result = df_result.reset_index(drop=True)
        
        return df_result
    
    def calculate_distribution_stats(self, data: pd.Series) -> Dict:
        """
        计算基本统计量
        
        Args:
            data: 数据序列
        
        Returns:
            统计量字典，包含:
            {
                "mean": 均值,
                "median": 中位数,
                "std": 标准差,
                "min": 最小值,
                "max": 最大值,
                "q25": 25%分位数,
                "q75": 75%分位数,
                "count": 有效数据点数量
            }
        
        Raises:
            ValueError: 输入数据为空或全为NaN
        """
        # 去除NaN值
        valid_data = data.dropna()
        
        if len(valid_data) < 1:
            raise ValueError("没有足够的有效数据点来计算统计量")
        
        stats_dict = {
            "mean": float(valid_data.mean()),
            "median": float(valid_data.median()),
            "std": float(valid_data.std()),
            "min": float(valid_data.min()),
            "max": float(valid_data.max()),
            "q25": float(valid_data.quantile(0.25)),
            "q75": float(valid_data.quantile(0.75)),
            "count": int(len(valid_data))
        }
        
        return stats_dict

    def calculate_missing_rate(self, sources: List[str]) -> pd.DataFrame:
        """
        统计各数据源的缺失率
        
        Args:
            sources: 气象源名称列表
        
        Returns:
            DataFrame，包含列 [source, missing_rate, total_points, missing_points]
            按缺失率从低到高排序
        """
        results = []
        
        # 计算每个气象源的缺失率
        for source in sources:
            ws_column = f"{source}_WS"
            
            if ws_column not in self.nwp_data.columns:
                # 跳过不存在的气象源
                continue
            
            source_ws = self.nwp_data[ws_column]
            
            total_points = len(source_ws)
            missing_points = source_ws.isna().sum()
            missing_rate = missing_points / total_points if total_points > 0 else 0.0
            
            results.append({
                "source": source,
                "missing_rate": missing_rate,
                "total_points": total_points,
                "missing_points": missing_points
            })
        
        # 计算真实风速的缺失率
        true_ws_col = self._get_true_ws_column()
        if true_ws_col is not None:
            true_ws = self.true_data[true_ws_col]
            
            total_points = len(true_ws)
            missing_points = true_ws.isna().sum()
            missing_rate = missing_points / total_points if total_points > 0 else 0.0
            
            results.append({
                "source": "true",
                "missing_rate": missing_rate,
                "total_points": total_points,
                "missing_points": missing_points
            })
        
        # 创建DataFrame并按缺失率升序排序
        df_result = pd.DataFrame(results)
        if not df_result.empty:
            df_result = df_result.sort_values("missing_rate", ascending=True)
            df_result = df_result.reset_index(drop=True)
        
        return df_result
    
    def _get_true_ws_column(self) -> Optional[str]:
        """
        获取真实风速列名
        
        Returns:
            真实风速列名，如果不存在则返回None
        """
        # 查找包含 'WS' 的列
        for col in self.true_data.columns:
            if 'WS' in col.upper():
                return col
        
        # 如果只有一列数据（除了索引），假设它是风速
        if len(self.true_data.columns) == 1:
            return self.true_data.columns[0]
        
        return None

    def analyze_wind_speed_ranges(self, sources: List[str], 
                                   ranges: List[tuple] = None) -> Dict:
        """
        分析不同风速区间的预测表现
        
        Args:
            sources: 气象源名称列表
            ranges: 风速区间列表，格式为 [(min, max), ...]
                   默认为 [(0, 3), (3, 6), (6, 10), (10, 15), (15, 100)]
        
        Returns:
            字典，包含每个气象源在每个区间的误差指标
            {
                "DWD": {
                    "0-3": {"rmse": 1.2, "mae": 0.9, "count": 100},
                    "3-6": {"rmse": 1.5, "mae": 1.1, "count": 200},
                    ...
                },
                ...
            }
        """
        # 默认风速区间（类似风机的大中小风）
        if ranges is None:
            ranges = [
                (0, 3),      # 小风
                (3, 6),      # 中小风
                (6, 10),     # 中风
                (10, 15),    # 中大风
                (15, 100)    # 大风
            ]
        
        # 获取真实风速
        true_ws_col = self._get_true_ws_column()
        if true_ws_col is None:
            raise ValueError("真实风速数据缺失")
        
        true_ws = self.true_data[true_ws_col]
        
        # 结果字典
        result = {}
        
        for source in sources:
            ws_column = f"{source}_WS"
            
            if ws_column not in self.nwp_data.columns:
                continue
            
            source_ws = self.nwp_data[ws_column]
            source_result = {}
            
            # 对每个风速区间进行分析
            for min_ws, max_ws in ranges:
                # 创建区间掩码
                mask = (true_ws >= min_ws) & (true_ws < max_ws)
                
                # 过滤数据
                true_range = true_ws[mask]
                source_range = source_ws[mask]
                
                # 去除NaN
                valid_mask = ~(true_range.isna() | source_range.isna())
                true_valid = true_range[valid_mask]
                source_valid = source_range[valid_mask]
                
                # 计算误差指标
                if len(true_valid) > 0:
                    rmse = self.calculate_rmse(source_valid, true_valid)
                    mae = self.calculate_mae(source_valid, true_valid)
                    count = len(true_valid)
                else:
                    rmse = np.nan
                    mae = np.nan
                    count = 0
                
                # 区间标签
                range_label = f"{min_ws}-{max_ws if max_ws < 100 else '+'}"
                
                source_result[range_label] = {
                    "rmse": float(rmse) if not np.isnan(rmse) else None,
                    "mae": float(mae) if not np.isnan(mae) else None,
                    "count": int(count)
                }
            
            result[source] = source_result
        
        return result
    
    def analyze_seasonal_performance(self, sources: List[str]) -> Dict:
        """
        分析不同季节的预测表现
        
        Args:
            sources: 气象源名称列表
        
        Returns:
            字典，包含每个气象源在每个季节的误差指标
            {
                "DWD": {
                    "春季": {"rmse": 1.2, "mae": 0.9, "count": 100},
                    "夏季": {"rmse": 1.5, "mae": 1.1, "count": 200},
                    "秋季": {"rmse": 1.3, "mae": 1.0, "count": 150},
                    "冬季": {"rmse": 1.4, "mae": 1.0, "count": 180}
                },
                ...
            }
        """
        # 获取真实风速
        true_ws_col = self._get_true_ws_column()
        if true_ws_col is None:
            raise ValueError("真实风速数据缺失")
        
        true_ws = self.true_data[true_ws_col]
        
        # 获取月份
        months = true_ws.index.month
        
        # 定义季节映射
        season_map = {
            1: '冬季', 2: '冬季', 3: '春季',
            4: '春季', 5: '春季', 6: '夏季',
            7: '夏季', 8: '夏季', 9: '秋季',
            10: '秋季', 11: '秋季', 12: '冬季'
        }
        
        # 创建季节序列
        seasons = months.map(season_map)
        
        # 结果字典
        result = {}
        
        for source in sources:
            ws_column = f"{source}_WS"
            
            if ws_column not in self.nwp_data.columns:
                continue
            
            source_ws = self.nwp_data[ws_column]
            source_result = {}
            
            # 对每个季节进行分析
            for season_name in ['春季', '夏季', '秋季', '冬季']:
                # 创建季节掩码
                mask = (seasons == season_name)
                
                # 过滤数据
                true_season = true_ws[mask]
                source_season = source_ws[mask]
                
                # 去除NaN
                valid_mask = ~(true_season.isna() | source_season.isna())
                true_valid = true_season[valid_mask]
                source_valid = source_season[valid_mask]
                
                # 计算误差指标
                if len(true_valid) > 0:
                    rmse = self.calculate_rmse(source_valid, true_valid)
                    mae = self.calculate_mae(source_valid, true_valid)
                    count = len(true_valid)
                else:
                    rmse = np.nan
                    mae = np.nan
                    count = 0
                
                source_result[season_name] = {
                    "rmse": float(rmse) if not np.isnan(rmse) else None,
                    "mae": float(mae) if not np.isnan(mae) else None,
                    "count": int(count)
                }
            
            result[source] = source_result
        
        return result

    def analyze_bias_distribution(self, sources: List[str]) -> Dict:
        """
        分析不同气象源与真实风速的单点偏差分布
        
        Args:
            sources: 气象源名称列表
        
        Returns:
            字典，包含每个气象源的偏差统计信息
            {
                "DWD": {
                    "bias": [0.5, -0.3, 1.2, ...],  # 所有单点偏差值
                    "mean_bias": 0.2,  # 平均偏差
                    "std_bias": 1.1,   # 偏差标准差
                    "min_bias": -3.5,  # 最小偏差
                    "max_bias": 4.2,   # 最大偏差
                    "q25": -0.5,       # 25%分位数
                    "q50": 0.1,        # 中位数
                    "q75": 0.8,        # 75%分位数
                    "count": 1000      # 有效数据点数
                },
                ...
            }
        """
        # 获取真实风速
        true_ws_col = self._get_true_ws_column()
        if true_ws_col is None:
            raise ValueError("真实风速数据缺失")
        
        true_ws = self.true_data[true_ws_col]
        
        # 结果字典
        result = {}
        
        for source in sources:
            ws_column = f"{source}_WS"
            
            if ws_column not in self.nwp_data.columns:
                continue
            
            source_ws = self.nwp_data[ws_column]
            
            # 去除NaN值
            valid_mask = ~(true_ws.isna() | source_ws.isna())
            true_valid = true_ws[valid_mask]
            source_valid = source_ws[valid_mask]
            
            if len(true_valid) < 1:
                continue
            
            # 计算偏差（预测值 - 真实值）
            bias = source_valid - true_valid
            
            # 计算统计量
            result[source] = {
                "bias": bias.tolist(),
                "mean_bias": float(bias.mean()),
                "std_bias": float(bias.std()),
                "min_bias": float(bias.min()),
                "max_bias": float(bias.max()),
                "q25": float(bias.quantile(0.25)),
                "q50": float(bias.quantile(0.50)),
                "q75": float(bias.quantile(0.75)),
                "count": int(len(bias))
            }
        
        return result
