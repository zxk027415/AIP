"""
数据处理器模块
负责时间对齐、插值、数据清洗
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime


class DataProcessor:
    """数据处理器类，用于处理和转换场站数据"""
    
    def __init__(self, nwp_data: pd.DataFrame, true_data: pd.DataFrame):
        """
        初始化数据处理器
        
        Args:
            nwp_data: NWP数值天气预报数据
            true_data: 真实风速数据
        """
        # 深拷贝数据，避免修改原始数据
        self.nwp_data = nwp_data.copy()
        self.true_data = true_data.copy()
        
        # 存储处理后的数据
        self.processed_nwp = None
        self.processed_true = None
        
        # 标识数据是否已处理
        self._is_processed = False
        
        # 存储被删除的列信息
        self.removed_columns = []
        
        # 清理完全缺失的列
        self._remove_completely_missing_columns()
    
    def _remove_completely_missing_columns(self):
        """
        删除完全缺失的列
        
        检测NWP数据中完全为NaN的列，并删除这些列。
        记录被删除的列信息，便于后续日志记录和调试。
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 检查NWP数据中完全缺失的列
        completely_missing = []
        nwp_cols = [x for x in self.nwp_data.columns if x not in ['forecast_time', 'timestamp']]
        
        for col in nwp_cols:
            # 检查该列是否完全为NaN
            if self.nwp_data[col].isna().all():
                completely_missing.append(col)
        
        # 删除完全缺失的列
        if completely_missing:
            logger.info(f'检测到 {len(completely_missing)} 个完全缺失的列，将被删除:')
            
            # 按气象源分组显示
            missing_by_source = {}
            for col in completely_missing:
                # 提取气象源名称和要素
                parts = col.split('_')
                if len(parts) >= 2:
                    source = '_'.join(parts[:-1])  # 气象源名称
                    feature = parts[-1]  # 要素名称
                    
                    if source not in missing_by_source:
                        missing_by_source[source] = []
                    missing_by_source[source].append(feature)
            
            # 记录详细信息
            for source, features in missing_by_source.items():
                logger.info(f'  - {source}: {", ".join(features)}')
                self.removed_columns.append({
                    'source': source,
                    'features': features,
                    'columns': [f'{source}_{f}' for f in features]
                })
            
            # 删除这些列
            self.nwp_data.drop(columns=completely_missing, inplace=True)
            logger.info(f'已删除 {len(completely_missing)} 个完全缺失的列')
            logger.info(f'剩余列数: {len(self.nwp_data.columns)}')
    
    def align_timestamps(self, resolution: str = "1H", timestamp_col: str = 'timestamp') -> None:
        """
        将所有数据对齐到指定时间分辨率
        
        Args:
            resolution: 时间分辨率，支持pandas时间频率字符串
                       如 "15T" (15分钟), "30T" (30分钟), "1H" (1小时), "3H" (3小时)
            timestamp_col: 需要时间对齐的列
        
        Raises:
            ValueError: 无效的时间分辨率
        """
        try:
            # 标准化分辨率格式 (将大写H转换为小写h以避免FutureWarning)
            resolution = resolution.replace('H', 'h')
            # 验证分辨率格式
            pd.Timedelta(resolution)
        except ValueError:
            raise ValueError(f"无效的时间分辨率: {resolution}")
        
        # 找到所有数据的时间范围
        nwp_data_copy = self.nwp_data.set_index(timestamp_col)
        true_data_copy = self.true_data.set_index(timestamp_col)
        start_time = max(
            nwp_data_copy.index.min(),
            true_data_copy.index.min(),
        )
        
        end_time = min(
            nwp_data_copy.index.max(),
            true_data_copy.index.max(),
        )
        
        # 创建统一的时间索引
        unified_index = pd.date_range(start=start_time, end=end_time, freq=resolution)
        
        # 对齐每个数据集到统一时间索引
        self.processed_nwp = nwp_data_copy.reindex(unified_index)
        self.processed_true = true_data_copy.reindex(unified_index)
        
        self._is_processed = True

    def interpolate_data(self, method: str = "linear") -> None:
        """
        对缺失值进行插值
        
        Args:
            method: 插值方法，默认为"linear"（线性插值）
                   支持pandas interpolate方法的所有选项
        
        Raises:
            RuntimeError: 数据未对齐时调用此方法
        """
        if not self._is_processed:
            raise RuntimeError("请先调用align_timestamps()方法对齐时间戳")
        
        # 对每个数据集进行插值
        self.processed_nwp = self.processed_nwp.interpolate(method=method, limit_direction='both')
        self.processed_true = self.processed_true.interpolate(method=method, limit_direction='both')
    
    def filter_by_date_range(self, start_date: str, end_date: str) -> None:
        """
        按日期范围过滤数据
        
        Args:
            start_date: 开始日期，格式如 "2024-06-01" 或 "2024-06-01 00:00:00"
            end_date: 结束日期，格式如 "2024-06-15" 或 "2024-06-15 23:59:59"
        
        Raises:
            RuntimeError: 数据未对齐时调用此方法
            ValueError: 日期格式错误或日期范围无效
        """
        if not self._is_processed:
            raise RuntimeError("请先调用align_timestamps()方法对齐时间戳")
        
        try:
            # 转换日期字符串为datetime
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
        except Exception as e:
            raise ValueError(f"日期格式错误: {str(e)}")
        
        # 验证日期范围
        if start > end:
            raise ValueError("开始日期不能晚于结束日期")
        
        # 过滤数据
        self.processed_nwp = self.processed_nwp.loc[start:end]
        self.processed_true = self.processed_true.loc[start:end]
    
    def get_meteorological_sources(self) -> List[str]:
        """
        提取所有气象源名称（从NWP列名中解析）
        
        气象源格式示例: DWD_WS, EC_10D_WS, GFS_WS 等
        提取规则: 列名中包含气象要素（WS, WD, TMP, PRES等）的前缀部分
        
        Returns:
            气象源名称列表，去重后按字母顺序排序
        """
        # 使用处理后的数据，如果未处理则使用原始数据
        data = self.processed_nwp if self._is_processed else self.nwp_data
        
        sources = set()
        
        # 定义常见的气象要素后缀
        meteorological_features = ['_WS', '_WD', '_TMP', '_PRES', '_RH', '_U', '_V']
        
        for col in data.columns:
            # 检查列名是否包含气象要素
            for feature in meteorological_features:
                if feature in col:
                    # 提取气象源名称（去除要素后缀）
                    source = col.replace(feature, '')
                    sources.add(source)
                    break
        
        return sorted(list(sources))
    
    def extract_feature_by_source(self, source: str, feature: str = "WS") -> pd.Series:
        """
        提取指定气象源的指定要素数据
        
        Args:
            source: 气象源名称，如 "DWD", "EC_10D", "GFS"
            feature: 气象要素名称，如 "WS" (风速), "WD" (风向), "TMP" (温度), "PRES" (气压)
        
        Returns:
            包含指定气象源和要素的时间序列数据
        
        Raises:
            ValueError: 指定的气象源或要素不存在
        """
        # 使用处理后的数据，如果未处理则使用原始数据
        data = self.processed_nwp if self._is_processed else self.nwp_data
        
        # 构建列名
        column_name = f"{source}_{feature}"
        
        # 检查列是否存在
        if column_name not in data.columns:
            raise ValueError(f"列 '{column_name}' 不存在于数据中")
        
        return data[column_name]
    
    def get_processed_data(self) -> Dict[str, pd.DataFrame]:
        """
        返回处理后的数据
        
        Returns:
            包含处理后数据的字典
            {"nwp": DataFrame, "true": DataFrame}
        
        Raises:
            RuntimeError: 数据未处理时调用此方法
        """
        if not self._is_processed:
            raise RuntimeError("数据尚未处理，请先调用align_timestamps()方法")
        
        return {
            "nwp": self.processed_nwp,
            "true": self.processed_true,
        }
    
    def get_removed_columns_info(self) -> List[Dict]:
        """
        获取被删除的列信息
        
        Returns:
            被删除列的信息列表，每个元素包含:
            {
                'source': 气象源名称,
                'features': 被删除的要素列表,
                'columns': 被删除的完整列名列表
            }
        """
        return self.removed_columns
