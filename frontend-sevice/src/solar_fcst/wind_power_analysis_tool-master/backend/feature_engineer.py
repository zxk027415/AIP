"""
特征工程器模块
负责构建特征、特征分组、特征选择
"""
import copy
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import polars as pl


class FeatureEngineer:
    """特征工程器类，用于构建和管理机器学习特征"""
    
    def __init__(self, processed_data: Dict[str, pd.DataFrame]):
        """
        初始化特征工程器
        
        Args:
            processed_data: 处理后的数据字典
                          {"nwp": DataFrame, "true": DataFrame}
        
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
        self.nwps = [x.split('_WS')[0] for x in self.nwp_data if x.endswith('_WS')]
        
        # 验证数据不为空
        if self.nwp_data.empty or self.true_data.empty:
            raise ValueError("输入数据不能为空")
        
        # 存储生成的特征
        self._time_features = None
        self._statistical_features = None
        self._difference_features = None
        self._interaction_features = None
        self._business_features = None
        
        # 特征分组字典
        self._feature_groups = {}
    
    def create_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        创建时间特征
        
        生成的特征包括:
        - hour: 小时 (0-23)
        - day_of_week: 星期几 (0=周一, 6=周日)
        - month: 月份 (1-12)
        - season: 季节 (1=春, 2=夏, 3=秋, 4=冬)
        - is_weekend: 是否周末 (0或1)
        - hour_sin: 小时的正弦编码
        - hour_cos: 小时的余弦编码
        
        Returns:
            包含时间特征的DataFrame
        """
        # 基本时间特征
        df['hour'] = df.index.hour
        df['day_of_week'] = df.index.dayofweek
        df['month'] = df.index.month
        
        # 季节特征 (3-5月春, 6-8月夏, 9-11月秋, 12-2月冬)
        df['season'] = df.index.month.map(
            lambda m: 1 if m in [3, 4, 5] else 
                     2 if m in [6, 7, 8] else 
                     3 if m in [9, 10, 11] else 4
        )
        
        # 是否周末
        df['is_weekend'] = (df.index.dayofweek >= 5).astype(int)
        
        # 小时的周期性编码（正弦和余弦）
        df['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)
        
        # 月份的周期性编码
        df['month_sin'] = np.sin(2 * np.pi * df.index.month / 12)
        df['month_cos'] = np.cos(2 * np.pi * df.index.month / 12)
        time_feature_cols = ['hour', 'day_of_week', 'month', 'season', 'is_weekend', 'hour_sin', 'hour_cos', 'month_sin', 'month_cos']
        self._time_features = time_feature_cols
        return df

    def create_business_features(self, tmp_business):
        business_feature_cols = []
        for nwp in self.nwps:
            for window in range(1, 4):
                tmp_business[f'{nwp}_WS_p{window}'] = tmp_business[f'{nwp}_WS'].shift(window).ffill().bfill()
                tmp_business[f'{nwp}_WS_n{window}'] = tmp_business[f'{nwp}_WS'].shift(-window).ffill().bfill()
                business_feature_cols.extend([f'{nwp}_WS_p{window}', f'{nwp}_WS_n{window}'])
            tmp_business[f'{nwp}_WD_p1'] = tmp_business[f'{nwp}_WD'].shift(1).ffill().bfill()
            tmp_business[f'{nwp}_WD_n1'] = tmp_business[f'{nwp}_WD'].shift(-1).ffill().bfill()
            tmp_business[f'{nwp}_DENSITY'] = tmp_business[f'{nwp}_PRES'] * 1e2 / (287.05 + (tmp_business[f'{nwp}_TMP'] + 273.15))
            tmp_business[f'{nwp}_u'] = tmp_business[f'{nwp}_WS'] * np.sin((270 - tmp_business[f'{nwp}_WD']) / 180 * np.pi)
            tmp_business[f'{nwp}_v'] = tmp_business[f'{nwp}_WS'] * np.cos((270 - tmp_business[f'{nwp}_WD']) / 180 * np.pi)
            tmp_business[f'{nwp}_u_p1'] = tmp_business[f'{nwp}_WS_p1'] * np.sin((270 - tmp_business[f'{nwp}_WD_p1']) / 180 * np.pi)
            tmp_business[f'{nwp}_v_p1'] = tmp_business[f'{nwp}_WS_p1'] * np.cos((270 - tmp_business[f'{nwp}_WD_p1']) / 180 * np.pi)
            tmp_business[f'{nwp}_u_n1'] = tmp_business[f'{nwp}_WS_n1'] * np.sin((270 - tmp_business[f'{nwp}_WD_n1']) / 180 * np.pi)
            tmp_business[f'{nwp}_v_n1'] = tmp_business[f'{nwp}_WS_n1'] * np.cos((270 - tmp_business[f'{nwp}_WD_n1']) / 180 * np.pi)

            tmp_business[f'{nwp}_trend_n1'] = tmp_business[f'{nwp}_WS'] - tmp_business[f'{nwp}_WS_n1']
            tmp_business[f'{nwp}_trend_p1'] = tmp_business[f'{nwp}_WS'] - tmp_business[f'{nwp}_WS_p1']
            tmp_business[f'{nwp}_trend_13'] = tmp_business[[f'{nwp}_WS_p{window}' for window in range(1, 4)]].mean(axis=1) - tmp_business[[f'{nwp}_WS_n{window}' for window in range(1, 4)]].mean(axis=1)
        self._business_features = business_feature_cols
        return tmp_business

    def create_statistical_features(self, statistical_features,  window_sizes: List[int] = [3, 6, 12]) -> pd.DataFrame:
        """
        创建滚动统计特征
        
        为每个气象源的风速生成滚动窗口统计特征:
        - rolling_mean: 滚动平均值
        - rolling_std: 滚动标准差
        - rolling_min: 滚动最小值
        - rolling_max: 滚动最大值
        
        Args:
            window_sizes: 滚动窗口大小列表，默认为[3, 6, 12]
        
        Returns:
            包含统计特征的DataFrame
        """
        statistical_feature_cols = []

        ws_columns = [col for col in self.nwp_data.columns if '_WS' in col]
        
        for col in ws_columns:
            # 提取气象源名称
            source_name = col.replace('_WS', '')
            
            for window in window_sizes:
                # 滚动平均
                statistical_features[f'{source_name}_rolling_mean_{window}'] = \
                    self.nwp_data[col].rolling(window=window, min_periods=1).mean()
                
                # 滚动标准差
                statistical_features[f'{source_name}_rolling_std_{window}'] = \
                    self.nwp_data[col].rolling(window=window, min_periods=1).std()
                
                # 滚动最小值
                statistical_features[f'{source_name}_rolling_min_{window}'] = \
                    self.nwp_data[col].rolling(window=window, min_periods=1).min()
                
                # 滚动最大值
                statistical_features[f'{source_name}_rolling_max_{window}'] = \
                    self.nwp_data[col].rolling(window=window, min_periods=1).max()
                statistical_feature_cols.extend([
                    f'{source_name}_rolling_mean_{window}',
                    f'{source_name}_rolling_std_{window}',
                    f'{source_name}_rolling_min_{window}',
                    f'{source_name}_rolling_max_{window}'
                ])
        
        self._statistical_features = statistical_feature_cols
        return statistical_features

    def create_difference_features(self, difference_features) -> pd.DataFrame:
        """
        创建气象源间差值特征
        
        计算不同气象源风速预测之间的差值，以及与历史预测的差值
        
        Returns:
            包含差值特征的DataFrame
        """
        difference_feature_cols = []

        ws_columns = [col for col in self.nwp_data.columns if '_WS' in col]
        sources = [col.replace('_WS', '') for col in ws_columns]
        
        # 计算气象源之间的两两差值
        for i, source1 in enumerate(sources):
            for source2 in sources[i+1:]:
                col1 = f'{source1}_WS'
                col2 = f'{source2}_WS'
                
                if col1 in self.nwp_data.columns and col2 in self.nwp_data.columns:
                    difference_features[f'{source1}_minus_{source2}'] = \
                        self.nwp_data[col1] - self.nwp_data[col2]
                    difference_feature_cols.append(f'{source1}_minus_{source2}')

        self._difference_features = difference_feature_cols
        return difference_features
    
    def create_interaction_features(self, interaction_features) -> pd.DataFrame:
        """
        创建交互特征
        
        生成不同气象要素之间的交互特征:
        - WS * WD: 风速与风向的交互
        - WS * TMP: 风速与温度的交互
        - WS * PRES: 风速与气压的交互
        - WS^2: 风速的平方
        
        只为存在的列创建交互特征，自动跳过缺失的列。
        
        Returns:
            包含交互特征的DataFrame
        """
        interaction_feature_cols = []

        ws_columns = [col for col in self.nwp_data.columns if '_WS' in col]
        sources = [col.replace('_WS', '') for col in ws_columns]
        
        for source in sources:
            ws_col = f'{source}_WS'
            wd_col = f'{source}_WD'
            tmp_col = f'{source}_TMP'
            pres_col = f'{source}_PRES'
            
            # 风速平方（只要有风速就创建）
            if ws_col in self.nwp_data.columns:
                interaction_features[f'{source}_WS_squared'] = \
                    self.nwp_data[ws_col] ** 2
                interaction_feature_cols.append(f'{source}_WS_squared')
            
            # 风速 * 风向（只有两者都存在时才创建）
            if ws_col in self.nwp_data.columns and wd_col in self.nwp_data.columns:
                interaction_features[f'{source}_WS_x_WD'] = \
                    self.nwp_data[ws_col] * self.nwp_data[wd_col]
                interaction_feature_cols.append(f'{source}_WS_x_WD')
            
            # 风速 * 温度（只有两者都存在时才创建）
            if ws_col in self.nwp_data.columns and tmp_col in self.nwp_data.columns:
                interaction_features[f'{source}_WS_x_TMP'] = \
                    self.nwp_data[ws_col] * self.nwp_data[tmp_col]
                interaction_feature_cols.append(f'{source}_WS_x_TMP')
            
            # 风速 * 气压（只有两者都存在时才创建）
            if ws_col in self.nwp_data.columns and pres_col in self.nwp_data.columns:
                interaction_features[f'{source}_WS_x_PRES'] = \
                    self.nwp_data[ws_col] * self.nwp_data[pres_col]
                interaction_feature_cols.append(f'{source}_WS_x_PRES')
            
            # 风向的正弦和余弦分量（只有风向存在时才创建）
            if wd_col in self.nwp_data.columns:
                interaction_features[f'{source}_WD_sin'] = \
                    np.sin(np.deg2rad(self.nwp_data[wd_col]))
                interaction_features[f'{source}_WD_cos'] = \
                    np.cos(np.deg2rad(self.nwp_data[wd_col]))
                interaction_feature_cols.extend([f'{source}_WD_sin', f'{source}_WD_cos'])
        
        self._interaction_features = interaction_feature_cols
        return interaction_features

    def get_feature_groups(self) -> Dict[str, List[str]]:
        """
        返回特征分组
        
        将所有特征按类型分组，便于用户选择和管理
        
        Returns:
            特征分组字典，格式为:
            {
                "raw_meteorological": [...],  # 原始气象要素
                "time_features": [...],        # 时间特征
                "statistical_features": [...], # 统计特征
                "difference_features": [...],  # 差值特征
                "interaction_features": [...]  # 交互特征
            }
        """
        feature_groups = {}

        # 原始气象要素特征（排除 timestamp）
        raw_features = [col for col in self.nwp_data.columns if col not in ['timestamp', 'forecast_time']]
        feature_groups['raw_meteorological'] = raw_features

        # 时间特征
        if self._time_features is not None:
            feature_groups['time_features'] = copy.deepcopy(self._time_features)
        else:
            feature_groups['time_features'] = []

        if self._business_features is not None:
            feature_groups['business_features'] = copy.deepcopy(self._business_features)
        else:
            feature_groups['business_features'] = []

        # 统计特征
        if self._statistical_features is not None:
            feature_groups['statistical_features'] = copy.deepcopy(self._statistical_features)
        else:
            feature_groups['statistical_features'] = []

        # 差值特征
        if self._difference_features is not None:
            feature_groups['difference_features'] = copy.deepcopy(self._difference_features)
        else:
            feature_groups['difference_features'] = []

        # 交互特征
        if self._interaction_features is not None:
            feature_groups['interaction_features'] = copy.deepcopy(self._interaction_features)
        else:
            feature_groups['interaction_features'] = []

        self._feature_groups = feature_groups
        return feature_groups
    
    def build_feature_matrix(self, selected_groups: List[str]) -> pd.DataFrame:
        """
        根据选定的特征组构建特征矩阵
        
        Args:
            selected_groups: 选定的特征组名称列表
                           可选值: ["raw_meteorological", "time_features", 
                                   "statistical_features", "difference_features", 
                                   "interaction_features"]
        
        Returns:
            包含所有选定特征的DataFrame
        
        Raises:
            ValueError: 特征组不存在或特征未生成
        """
        # 验证特征组名称
        valid_groups = ["raw_meteorological", "time_features", "business_features", "statistical_features",
                       "difference_features", "interaction_features"]

        for group in selected_groups:
            if group not in valid_groups:
                raise ValueError(f"无效的特征组名称: {group}")

        nwp_df = copy.deepcopy(self.nwp_data)
        min_date = nwp_df['forecast_time'].min()
        nwp_df['i.set'] = (nwp_df['forecast_time'] - min_date).dt.days
        raw_features = [x for x in nwp_df.columns if x not in ['timestamp', 'forecast_time']]
        selected_features = []
        
        # 添加选定的特征组
        for group in selected_groups:
            if group == "raw_meteorological":
                # 添加原始气象要素
                selected_features.extend(raw_features)

            elif group == "time_features":
                nwp_df = self.create_time_features(nwp_df)
                selected_features.extend(self._time_features)

                if self._time_features is None:
                    raise ValueError("时间特征未生成，请先调用create_time_features()")

            elif group == "business_features":
                nwp_df = self.create_business_features(nwp_df)
                selected_features.extend(self._business_features)

                if self._business_features is None:
                    raise ValueError("业务特征未生成, 请先调用create_business_features()")

            elif group == "statistical_features":
                nwp_df = self.create_statistical_features(nwp_df)
                selected_features.extend(self._statistical_features)

                if self._statistical_features is None:
                    raise ValueError("统计特征未生成，请先调用create_statistical_features()")

            elif group == "difference_features":
                nwp_df = self.create_difference_features(nwp_df)
                selected_features.extend(self._difference_features)

                if self._difference_features is None:
                    raise ValueError("差值特征未生成，请先调用create_difference_features()")


            elif group == "interaction_features":
                nwp_df = self.create_interaction_features(nwp_df)
                selected_features.extend(self._interaction_features)

                if self._interaction_features is None:
                    raise ValueError("交互特征未生成，请先调用create_interaction_features()")

        return nwp_df[['forecast_time', 'i.set'] + selected_features]


class PolarsFeatureEngineer:
    """
    基于 Polars 的特征工程器类，支持高效的按日期分组特征计算

    相比 Pandas 版本，Polars 在处理大规模数据和分组操作时性能更优
    """

    def __init__(self, processed_data: Dict[str, pd.DataFrame]):
        """
        初始化 Polars 特征工程器

        Args:
            processed_data: 处理后的数据字典
                          {"nwp": DataFrame, "true": DataFrame}

        Raises:
            ImportError: Polars 未安装
            ValueError: 输入数据格式错误
        """

        # 验证输入数据
        required_keys = ["nwp", "true"]
        for key in required_keys:
            if key not in processed_data:
                raise ValueError(f"缺少必需的数据: {key}")

        # 转换为 Polars DataFrame
        self.nwp_data = processed_data["nwp"]
        self.true_data = processed_data["true"]
        self.nwps = [x.split('_WS')[0] for x in self.nwp_data if x.endswith('_WS')]

        # 验证数据不为空
        if self.nwp_data.empty or self.true_data.empty:
            raise ValueError("输入数据不能为空")

        # 存储生成的特征列表
        self._time_features = None
        self._statistical_features = None
        self._difference_features = None
        self._interaction_features = None
        self._business_features = None

        # 特征分组字典
        self._feature_groups = {}

    def create_time_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        创建时间特征（使用 Polars）

        生成的特征包括:
        - hour: 小时 (0-23)
        - day_of_week: 星期几 (0=周一, 6=周日)
        - month: 月份 (1-12)
        - season: 季节 (1=春, 2=夏, 3=秋, 4=冬)
        - is_weekend: 是否周末 (0或1)
        - hour_sin: 小时的正弦编码
        - hour_cos: 小时的余弦编码

        Returns:
            包含时间特征的 Polars DataFrame（只包含新特征，不包含原始数据）
        """
        df = df.with_columns([
            pl.col('timestamp').dt.hour().alias('hour'),
            pl.col('timestamp').dt.weekday().alias('day_of_week'),
            pl.col('timestamp').dt.month().alias('month'),

            # 季节特征
            pl.when(pl.col('timestamp').dt.month().is_in([3, 4, 5]))
            .then(1)
            .when(pl.col('timestamp').dt.month().is_in([6, 7, 8]))
            .then(2)
            .when(pl.col('timestamp').dt.month().is_in([9, 10, 11]))
            .then(3)
            .otherwise(4)
            .alias('season'),

            # 是否周末
            (pl.col('timestamp').dt.weekday() >= 5).cast(pl.Int32).alias('is_weekend'),

            # 小时的周期性编码
            (2 * np.pi * pl.col('timestamp').dt.hour() / 24).sin().alias('hour_sin'),
            (2 * np.pi * pl.col('timestamp').dt.hour() / 24).cos().alias('hour_cos'),

            # 月份的周期性编码
            (2 * np.pi * pl.col('timestamp').dt.month() / 12).sin().alias('month_sin'),
            (2 * np.pi * pl.col('timestamp').dt.month() / 12).cos().alias('month_cos'),
        ])

        self._time_features = ['hour', 'day_of_week', 'month', 'season', 'is_weekend', 'hour_sin', 'hour_cos',
                               'month_sin', 'month_cos']
        return df

    def create_business_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        创建业务特征（使用 Polars）

        包括滞后特征、超前特征、空气密度、风速分量等

        Returns:
            包含业务特征的 Polars DataFrame（只包含新特征，不包含原始数据）
        """
        # 从 nwp_data 开始构建特征
        business_feature_cols = []

        for nwp in self.nwps:
            # 滞后和超前特征
            for window in range(1, 4):
                df = df.with_columns([
                    pl.col(f'{nwp}_WS').shift(window).over('forecast_time').forward_fill().backward_fill().alias(
                        f'{nwp}_WS_p{window}'),
                    pl.col(f'{nwp}_WS').shift(-window).over('forecast_time').forward_fill().backward_fill().alias(
                        f'{nwp}_WS_n{window}'),
                ])
                business_feature_cols.extend([f'{nwp}_WS_p{window}', f'{nwp}_WS_n{window}'])

            # 风向滞后和超前
            df = df.with_columns([
                pl.col(f'{nwp}_WD').shift(1).over('forecast_time').forward_fill().backward_fill().alias(f'{nwp}_WD_p1'),
                pl.col(f'{nwp}_WD').shift(-1).over('forecast_time').forward_fill().backward_fill().alias(
                    f'{nwp}_WD_n1'),
            ])
            business_feature_cols.extend([f'{nwp}_WD_p1', f'{nwp}_WD_n1'])

            # 空气密度
            df = df.with_columns([
                (pl.col(f'{nwp}_PRES') * 1e2 / (287.05 * (pl.col(f'{nwp}_TMP') + 273.15))).alias(f'{nwp}_DENSITY')
            ])
            business_feature_cols.append(f'{nwp}_DENSITY')

            # 风速分量 (u, v)
            df = df.with_columns([
                (pl.col(f'{nwp}_WS') * ((270 - pl.col(f'{nwp}_WD')) / 180 * np.pi).sin()).alias(f'{nwp}_u'),
                (pl.col(f'{nwp}_WS') * ((270 - pl.col(f'{nwp}_WD')) / 180 * np.pi).cos()).alias(f'{nwp}_v'),
                (pl.col(f'{nwp}_WS_p1') * ((270 - pl.col(f'{nwp}_WD_p1')) / 180 * np.pi).sin()).alias(f'{nwp}_u_p1'),
                (pl.col(f'{nwp}_WS_p1') * ((270 - pl.col(f'{nwp}_WD_p1')) / 180 * np.pi).cos()).alias(f'{nwp}_v_p1'),
                (pl.col(f'{nwp}_WS_n1') * ((270 - pl.col(f'{nwp}_WD_n1')) / 180 * np.pi).sin()).alias(f'{nwp}_u_n1'),
                (pl.col(f'{nwp}_WS_n1') * ((270 - pl.col(f'{nwp}_WD_n1')) / 180 * np.pi).cos()).alias(f'{nwp}_v_n1'),
            ])
            business_feature_cols.extend(
                [f'{nwp}_u', f'{nwp}_v', f'{nwp}_u_p1', f'{nwp}_v_p1', f'{nwp}_u_n1', f'{nwp}_v_n1'])

            # 趋势特征
            df = df.with_columns([
                (pl.col(f'{nwp}_WS') - pl.col(f'{nwp}_WS_n1')).alias(f'{nwp}_trend_n1'),
                (pl.col(f'{nwp}_WS') - pl.col(f'{nwp}_WS_p1')).alias(f'{nwp}_trend_p1'),
            ])

            df = df.with_columns([
                (pl.mean_horizontal([f'{nwp}_WS_p{w}' for w in range(1, 4)]).over('forecast_time') -
                 pl.mean_horizontal([f'{nwp}_WS_n{w}' for w in range(1, 4)]).over('forecast_time')).forward_fill().backward_fill().alias(
                    f'{nwp}_trend_13'),
            ])

            business_feature_cols.extend([f'{nwp}_trend_n1', f'{nwp}_trend_p1', f'{nwp}_trend_13'])

            df = df.with_columns([
                (pl.col(f'{nwp}_WS').rolling_max(window_size=6, min_periods=1).over('forecast_time').forward_fill().backward_fill().alias(f'{nwp}_WS_max')),
                (pl.col(f'{nwp}_WS').rolling_min(window_size=6, min_periods=1).over('forecast_time').forward_fill().backward_fill().alias(f'{nwp}_WS_min'))
            ])
            business_feature_cols.extend([f'{nwp}_WS_max', f'{nwp}_WS_min'])

        self._business_features = business_feature_cols
        return df

    def create_statistical_features(self, df: pl.DataFrame, window_sizes: List[int] = [3, 6, 12]) -> pl.DataFrame:
        """
        创建滚动统计特征（使用 Polars）

        为每个气象源的风速生成滚动窗口统计特征

        Args:
            df: 待构建特征的pl。DataFrame
            window_sizes: 滚动窗口大小列表，默认为[3, 6, 12]

        Returns:
            包含统计特征的 Polars DataFrame（只包含新特征，不包含原始数据）
        """
        statistical_feature_cols = []

        ws_columns = [col for col in self.nwp_data.columns if '_WS' in col]

        for col in ws_columns:
            source_name = col.replace('_WS', '')

            for window in window_sizes:
                df = df.with_columns([
                    pl.col(col).rolling_mean(window_size=window, min_periods=1).over('forecast_time').forward_fill().backward_fill()
                    .alias(f'{source_name}_rolling_mean_{window}'),
                    pl.col(col).rolling_std(window_size=window, min_periods=1).over('forecast_time').forward_fill().backward_fill()
                    .alias(f'{source_name}_rolling_std_{window}'),
                    pl.col(col).rolling_min(window_size=window, min_periods=1).over('forecast_time').forward_fill().backward_fill()
                    .alias(f'{source_name}_rolling_min_{window}'),
                    pl.col(col).rolling_max(window_size=window, min_periods=1).over('forecast_time').forward_fill().backward_fill()
                    .alias(f'{source_name}_rolling_max_{window}'),
                ])
                statistical_feature_cols.extend([
                    f'{source_name}_rolling_mean_{window}',
                    f'{source_name}_rolling_std_{window}',
                    f'{source_name}_rolling_min_{window}',
                    f'{source_name}_rolling_max_{window}'
                ])

        # 只保留新构建的特征列
        self._statistical_features = statistical_feature_cols
        return df

    def create_difference_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        创建气象源间差值特征（使用 Polars）

        Returns:
            包含差值特征的 Polars DataFrame（只包含新特征，不包含原始数据）
        """
        difference_feature_cols = []

        ws_columns = [col for col in self.nwp_data.columns if '_WS' in col]
        sources = [col.replace('_WS', '') for col in ws_columns]

        # 计算气象源之间的两两差值
        for i, source1 in enumerate(sources):
            for source2 in sources[i + 1:]:
                col1 = f'{source1}_WS'
                col2 = f'{source2}_WS'

                if col1 in self.nwp_data.columns and col2 in self.nwp_data.columns:
                    df = df.with_columns([
                        (pl.col(col1) - pl.col(col2)).alias(f'{source1}_minus_{source2}')
                    ])
                    difference_feature_cols.append(f'{source1}_minus_{source2}')

        # 只保留新构建的特征列
        self._difference_features = difference_feature_cols
        return df

    def create_interaction_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        创建交互特征（使用 Polars）

        Returns:
            包含交互特征的 Polars DataFrame（只包含新特征，不包含原始数据）
        """
        interaction_feature_cols = []

        ws_columns = [col for col in self.nwp_data.columns if '_WS' in col]
        sources = [col.replace('_WS', '') for col in ws_columns]

        for source in sources:
            ws_col = f'{source}_WS'
            wd_col = f'{source}_WD'
            tmp_col = f'{source}_TMP'
            pres_col = f'{source}_PRES'

            # 风速平方
            if ws_col in self.nwp_data.columns:
                df = df.with_columns([
                    (pl.col(ws_col) ** 2).alias(f'{source}_WS_squared')
                ])
                interaction_feature_cols.append(f'{source}_WS_squared')

            # 风速 * 风向
            if ws_col in self.nwp_data.columns and wd_col in self.nwp_data.columns:
                df = df.with_columns([
                    (pl.col(ws_col) * pl.col(wd_col)).alias(f'{source}_WS_x_WD')
                ])
                interaction_feature_cols.append(f'{source}_WS_x_WD')

            # 风速 * 温度
            if ws_col in self.nwp_data.columns and tmp_col in self.nwp_data.columns:
                df = df.with_columns([
                    (pl.col(ws_col) * pl.col(tmp_col)).alias(f'{source}_WS_x_TMP')
                ])
                interaction_feature_cols.append(f'{source}_WS_x_TMP')

            # 风速 * 气压
            if ws_col in self.nwp_data.columns and pres_col in self.nwp_data.columns:
                df = df.with_columns([
                    (pl.col(ws_col) * pl.col(pres_col)).alias(f'{source}_WS_x_PRES')
                ])
                interaction_feature_cols.append(f'{source}_WS_x_PRES')

            # 风向的正弦和余弦分量
            if wd_col in self.nwp_data.columns:
                df = df.with_columns([
                    (pl.col(wd_col) * np.pi / 180).sin().alias(f'{source}_WD_sin'),
                    (pl.col(wd_col) * np.pi / 180).cos().alias(f'{source}_WD_cos'),
                ])
                interaction_feature_cols.extend([f'{source}_WD_sin', f'{source}_WD_cos'])

        # 只保留新构建的特征列
        self._interaction_features = interaction_feature_cols
        return df

    def get_feature_groups(self) -> Dict[str, List[str]]:
        """
        返回特征分组

        Returns:
            特征分组字典
        """
        feature_groups = {}

        # 原始气象要素特征（排除 timestamp）
        raw_features = [col for col in self.nwp_data.columns if col not in ['timestamp', 'forecast_time']]
        feature_groups['raw_meteorological'] = raw_features

        # 时间特征
        if self._time_features is not None:
            feature_groups['time_features'] = copy.deepcopy(self._time_features)
        else:
            feature_groups['time_features'] = []

        if self._business_features is not None:
            feature_groups['business_features'] = copy.deepcopy(self._business_features)
        else:
            feature_groups['business_features'] = []

        # 统计特征
        if self._statistical_features is not None:
            feature_groups['statistical_features'] = copy.deepcopy(self._statistical_features)
        else:
            feature_groups['statistical_features'] = []

        # 差值特征
        if self._difference_features is not None:
            feature_groups['difference_features'] = copy.deepcopy(self._difference_features)
        else:
            feature_groups['difference_features'] = []

        # 交互特征
        if self._interaction_features is not None:
            feature_groups['interaction_features'] = copy.deepcopy(self._interaction_features)
        else:
            feature_groups['interaction_features'] = []

        self._feature_groups = feature_groups
        return feature_groups

    def build_feature_matrix(self, selected_groups: List[str]) -> pl.DataFrame:
        """
        根据选定的特征组构建特征矩阵（返回 Polars DataFrame）

        Args:
            selected_groups: 选定的特征组名称列表

        Returns:
            包含所有选定特征的 Polars DataFrame（包含 timestamp 列）

        Raises:
            ValueError: 特征组不存在或特征未生成
        """
        # 验证特征组名称
        valid_groups = ["raw_meteorological", "time_features", "business_features", "statistical_features",
                        "difference_features", "interaction_features"]

        for group in selected_groups:
            if group not in valid_groups:
                raise ValueError(f"无效的特征组名称: {group}")

        # 初始化特征矩阵
        feature_matrix = pd.DataFrame(index=self.nwp_data.index)
        nwp_df = copy.deepcopy(self.nwp_data)
        min_date = nwp_df['forecast_time'].min()
        nwp_df['i.set'] = (nwp_df['forecast_time'] - min_date).dt.days
        nwp_df = pl.from_pandas(nwp_df)
        raw_features = [x for x in nwp_df.columns if x not in ['timestamp', 'forecast_time']]
        selected_features = []

        # 添加选定的特征组
        for group in selected_groups:
            if group == "raw_meteorological":
                # 添加原始气象要素
                selected_features.extend(raw_features)

            elif group == "time_features":
                nwp_df = self.create_time_features(nwp_df)
                selected_features.extend(self._time_features)

                if self._time_features is None:
                    raise ValueError("时间特征未生成，请先调用create_time_features()")

            elif group == "business_features":
                nwp_df = self.create_business_features(nwp_df)
                selected_features.extend(self._business_features)

                if self._business_features is None:
                    raise ValueError("业务特征未生成, 请先调用create_business_features()")

            elif group == "statistical_features":
                nwp_df = self.create_statistical_features(nwp_df)
                selected_features.extend(self._statistical_features)

                if self._statistical_features is None:
                    raise ValueError("统计特征未生成，请先调用create_statistical_features()")

            elif group == "difference_features":
                nwp_df = self.create_difference_features(nwp_df)
                selected_features.extend(self._difference_features)

                if self._difference_features is None:
                    raise ValueError("差值特征未生成，请先调用create_difference_features()")

            elif group == "interaction_features":
                nwp_df = self.create_interaction_features(nwp_df)
                selected_features.extend(self._interaction_features)

                if self._interaction_features is None:
                    raise ValueError("交互特征未生成，请先调用create_interaction_features()")

        nwp_df = nwp_df.to_pandas()
        return nwp_df[['timestamp', 'forecast_time'] + selected_features]
