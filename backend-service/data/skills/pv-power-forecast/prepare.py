# @AI_GENERATED: Kiro v1.0
"""
光伏发电功率预测 - 数据准备和评估模块（只读）

日前预测场景：
- 预测时间点：每天 07:00
- 预测范围：次日 00:00 ~ 后天 23:45（48小时，192个点）
- 输入特征：历史实测数据 + 气象预报数据

此文件包含固定的数据加载、预处理和评估函数。
Agent 不应修改此文件。
"""

import os
import sys
import math
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional, List

# ---------------------------------------------------------------------------
# 常量（固定，不可修改）
# ---------------------------------------------------------------------------

TIME_BUDGET = 300           # 训练时间预算（秒）
PREDICTION_HOUR = 7         # 预测时间点：07:00
FORECAST_DAYS = 2           # 预测天数：2天（48小时）
FORECAST_HORIZON = 192      # 预测步长：48小时 = 192个15分钟
HISTORY_HOURS = 7           # 历史数据：当天00:00-07:00（7小时）
HISTORY_LENGTH = 28         # 历史序列长度：7小时 = 28个15分钟
TEST_RATIO = 0.2            # 测试集比例

# 特征分组
HISTORY_FEATURES = ['power_actual', 'irradiance_actual', 'temperature_actual', 'humidity_actual']
FORECAST_FEATURES = ['irradiance_forecast', 'temperature_forecast', 'wind_speed_forecast', 'cloud_cover_forecast']
TIME_FEATURES = ['hour_sin', 'hour_cos', 'month_sin', 'month_cos', 'is_daytime']

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "pv-forecast")

# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_pv_data(data_path: Optional[str] = None) -> pd.DataFrame:
    """
    加载光伏发电数据（日前预测版本）。
    
    数据格式要求：
    - timestamp: 时间戳列（15分钟间隔）
    - power_actual: 实际发电功率 (kW)
    - irradiance_actual: 实测辐照度 (W/m²)
    - irradiance_forecast: 预报辐照度 (W/m²)
    - temperature_actual: 实测温度 (°C)
    - temperature_forecast: 预报温度 (°C)
    - humidity_actual: 实测湿度 (%)
    - wind_speed_forecast: 预报风速 (m/s)
    - cloud_cover_forecast: 预报云量 (%)
    
    Returns:
        pd.DataFrame: 加载的数据
    """
    if data_path is None:
        possible_paths = [
            os.path.join(DATA_DIR, "pv_power_day_ahead.csv"),
            os.path.join(DATA_DIR, "pv_power_sample.csv"),
            os.path.join(CACHE_DIR, "pv_power_day_ahead.csv"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                data_path = path
                break
        
        if data_path is None:
            raise FileNotFoundError(
                f"找不到数据文件。请运行 'python prepare.py --download' 生成数据"
            )
    
    df = pd.read_csv(data_path, parse_dates=['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    print(f"数据加载完成: {len(df)} 条记录")
    print(f"时间范围: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    print(f"列: {list(df.columns)}")
    
    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """准备时间特征"""
    df = df.copy()
    
    # 时间特征
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['month'] = df['timestamp'].dt.month
    df['day_of_year'] = df['timestamp'].dt.dayofyear
    
    # 周期性编码
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
    
    # 是否白天（6:00-18:00）
    df['is_daytime'] = ((df['hour'] >= 6) & (df['hour'] <= 18)).astype(int)
    
    return df


# ---------------------------------------------------------------------------
# 日前预测序列创建
# ---------------------------------------------------------------------------

def create_day_ahead_sequences(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """
    创建日前预测序列
    
    场景：每天07:00预测未来48小时（次日00:00 ~ 后天23:45）
    
    输入特征:
    - 历史实测: 当天00:00-07:00的数据 (28个点 × 历史特征)
    - 气象预报: 未来48小时预报 (192个点 × 预报特征)
    
    输出目标:
    - 未来48小时功率 (192个点)
    
    Returns:
        X_history: (n_samples, 28, n_history_features) 历史实测
        X_forecast: (n_samples, 192, n_forecast_features) 气象预报
        y: (n_samples, 192) 目标功率
        dates: 预测日期列表
    """
    X_history = []
    X_forecast = []
    y = []
    dates = []
    
    # 确保有必要的列
    history_cols = [c for c in HISTORY_FEATURES if c in df.columns]
    forecast_cols = [c for c in FORECAST_FEATURES if c in df.columns]
    
    if not history_cols:
        history_cols = ['power_actual', 'irradiance', 'temperature', 'humidity']
        history_cols = [c for c in history_cols if c in df.columns]
    
    if not forecast_cols:
        # 如果没有预报列，用实测列模拟（加噪声）
        forecast_cols = history_cols
    
    print(f"历史特征: {history_cols}")
    print(f"预报特征: {forecast_cols}")
    
    # 按天遍历
    df['date'] = df['timestamp'].dt.date
    unique_dates = sorted(df['date'].unique())
    
    for i, pred_date in enumerate(unique_dates[:-2]):  # 留2天作为预测目标
        # 预测时间点：当天07:00
        pred_time = pd.Timestamp(pred_date) + pd.Timedelta(hours=PREDICTION_HOUR)
        
        # 历史数据：当天00:00-07:00（28个点）
        history_start = pd.Timestamp(pred_date)
        history_mask = (df['timestamp'] >= history_start) & (df['timestamp'] < pred_time)
        history_data = df.loc[history_mask, history_cols].values
        
        # 预测目标时间范围：次日00:00 ~ 后天23:45（192个点）
        target_start = pd.Timestamp(pred_date) + pd.Timedelta(days=1)
        target_end = target_start + pd.Timedelta(hours=48)
        target_mask = (df['timestamp'] >= target_start) & (df['timestamp'] < target_end)
        
        # 气象预报数据（与目标时间对齐）
        forecast_data = df.loc[target_mask, forecast_cols].values
        
        # 目标功率
        target_data = df.loc[target_mask, 'power_actual'].values
        
        # 检查数据完整性
        if len(history_data) >= HISTORY_LENGTH and len(forecast_data) >= FORECAST_HORIZON:
            # 截取固定长度
            X_history.append(history_data[:HISTORY_LENGTH])
            X_forecast.append(forecast_data[:FORECAST_HORIZON])
            y.append(target_data[:FORECAST_HORIZON])
            dates.append(str(pred_date))
    
    if len(X_history) == 0:
        raise ValueError("无法创建有效的训练序列，请检查数据完整性")
    
    print(f"创建序列: {len(X_history)} 个样本")
    print(f"历史形状: ({len(X_history)}, {HISTORY_LENGTH}, {len(history_cols)})")
    print(f"预报形状: ({len(X_forecast)}, {FORECAST_HORIZON}, {len(forecast_cols)})")
    
    return np.array(X_history), np.array(X_forecast), np.array(y), dates


def train_test_split_temporal(
    X_history: np.ndarray,
    X_forecast: np.ndarray,
    y: np.ndarray,
    test_ratio: float = TEST_RATIO
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """时序数据划分（保持时间顺序）"""
    split_idx = int(len(X_history) * (1 - test_ratio))
    
    X_hist_train = X_history[:split_idx]
    X_hist_test = X_history[split_idx:]
    X_fcst_train = X_forecast[:split_idx]
    X_fcst_test = X_forecast[split_idx:]
    y_train = y[:split_idx]
    y_test = y[split_idx:]
    
    print(f"训练集: {len(X_hist_train)} 样本")
    print(f"测试集: {len(X_hist_test)} 样本")
    
    return X_hist_train, X_hist_test, X_fcst_train, X_fcst_test, y_train, y_test


# ---------------------------------------------------------------------------
# 评估函数
# ---------------------------------------------------------------------------

def evaluate_mape(y_true: np.ndarray, y_pred: np.ndarray, ignore_zero: bool = True) -> float:
    """计算 MAPE（平均绝对百分比误差）"""
    y_true = np.array(y_true).flatten()
    y_pred = np.array(y_pred).flatten()
    
    if ignore_zero:
        mask = y_true > 0
        y_true = y_true[mask]
        y_pred = y_pred[mask]
    
    if len(y_true) == 0:
        return float('inf')
    
    return np.mean(np.abs((y_true - y_pred) / y_true)) * 100


def evaluate_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """计算 RMSE"""
    y_true = np.array(y_true).flatten()
    y_pred = np.array(y_pred).flatten()
    return np.sqrt(np.mean((y_true - y_pred) ** 2))


def evaluate_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """计算 R²"""
    y_true = np.array(y_true).flatten()
    y_pred = np.array(y_pred).flatten()
    
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    
    if ss_tot == 0:
        return 0.0
    return 1 - (ss_res / ss_tot)


def evaluate_day_ahead(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """
    日前预测评估 - 分时段
    
    Args:
        y_true: (n_samples, 192) 或 (192,)
        y_pred: (n_samples, 192) 或 (192,)
    """
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    
    # 展平处理
    if y_true.ndim == 1:
        y_true = y_true.reshape(1, -1)
        y_pred = y_pred.reshape(1, -1)
    
    results = {
        'overall_mape': evaluate_mape(y_true, y_pred),
        'overall_rmse': evaluate_rmse(y_true, y_pred),
        'overall_r2': evaluate_r2(y_true, y_pred),
    }
    
    # 分天评估
    if y_true.shape[1] >= 192:
        results['day1_mape'] = evaluate_mape(y_true[:, :96], y_pred[:, :96])
        results['day2_mape'] = evaluate_mape(y_true[:, 96:192], y_pred[:, 96:192])
        
        # 白天时段评估 (06:00-18:00 = 第24-72个点)
        day1_daytime = np.concatenate([y_true[:, 24:72], y_true[:, 120:168]], axis=1)
        day1_daytime_pred = np.concatenate([y_pred[:, 24:72], y_pred[:, 120:168]], axis=1)
        results['daytime_mape'] = evaluate_mape(day1_daytime, day1_daytime_pred)
    
    return results


def evaluate_all(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """计算所有评估指标"""
    return {
        'mape': evaluate_mape(y_true, y_pred),
        'rmse': evaluate_rmse(y_true, y_pred),
        'r2': evaluate_r2(y_true, y_pred),
    }


# ---------------------------------------------------------------------------
# 数据标准化
# ---------------------------------------------------------------------------

class MinMaxScaler:
    """Min-Max 标准化器"""
    
    def __init__(self):
        self.min_ = None
        self.max_ = None
        self.scale_ = None
    
    def fit(self, X: np.ndarray) -> 'MinMaxScaler':
        self.min_ = X.min(axis=0)
        self.max_ = X.max(axis=0)
        self.scale_ = self.max_ - self.min_
        self.scale_[self.scale_ == 0] = 1
        return self
    
    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.min_) / self.scale_
    
    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        self.fit(X)
        return self.transform(X)
    
    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        return X * self.scale_ + self.min_


# ---------------------------------------------------------------------------
# 日前预测数据生成
# ---------------------------------------------------------------------------

def generate_day_ahead_data(
    n_days: int = 180,
    interval_minutes: int = 15,
    output_path: Optional[str] = None,
    plant_capacity_kw: float = 5000,
    latitude: float = 38.5,  # 宁夏银川纬度
) -> pd.DataFrame:
    """
    生成日前预测数据集
    
    包含：
    - 实测数据：功率、辐照度、温度、湿度
    - 气象预报：辐照度、温度、风速、云量（带预报误差）
    
    Args:
        n_days: 生成天数（建议180天以上）
        interval_minutes: 时间间隔（15分钟）
        output_path: 输出路径
        plant_capacity_kw: 电站装机容量 (kW)
        latitude: 纬度（影响太阳高度角）
    """
    np.random.seed(42)
    
    start_date = datetime(2024, 1, 1)
    n_points = n_days * 24 * 60 // interval_minutes
    
    data = []
    
    for i in range(n_points):
        ts = start_date + timedelta(minutes=i * interval_minutes)
        hour = ts.hour + ts.minute / 60
        day_of_year = ts.timetuple().tm_yday
        
        # ========== 太阳位置计算 ==========
        # 太阳赤纬角（简化）
        declination = 23.45 * np.sin(2 * np.pi * (day_of_year - 81) / 365)
        
        # 时角
        hour_angle = 15 * (hour - 12)
        
        # 太阳高度角
        lat_rad = np.radians(latitude)
        dec_rad = np.radians(declination)
        ha_rad = np.radians(hour_angle)
        
        sin_elevation = (np.sin(lat_rad) * np.sin(dec_rad) + 
                        np.cos(lat_rad) * np.cos(dec_rad) * np.cos(ha_rad))
        solar_elevation = max(0, sin_elevation)
        
        # ========== 实测辐照度 ==========
        # 晴空辐照度
        clear_sky_irradiance = 1000 * solar_elevation  # W/m²
        
        # 云量影响（随机天气）
        # 使用自相关随机过程模拟天气持续性
        if i == 0:
            cloud_state = np.random.uniform(0, 0.5)
        else:
            cloud_state = 0.9 * cloud_state + 0.1 * np.random.uniform(0, 1)
        
        cloud_factor = 1 - cloud_state * 0.7  # 云量最多减少70%辐照
        
        # 实测辐照度
        irradiance_actual = clear_sky_irradiance * cloud_factor
        irradiance_actual = max(0, irradiance_actual + np.random.normal(0, 10))
        
        # ========== 实测温度 ==========
        # 基础温度（季节变化）
        base_temp = 15 + 15 * np.sin(2 * np.pi * (day_of_year - 100) / 365)
        # 日变化
        daily_temp = 8 * np.sin(np.pi * (hour - 6) / 12) if 6 <= hour <= 18 else -4
        temperature_actual = base_temp + daily_temp + np.random.normal(0, 2)
        
        # ========== 实测湿度 ==========
        humidity_actual = 50 - 20 * solar_elevation + 10 * cloud_state + np.random.normal(0, 5)
        humidity_actual = np.clip(humidity_actual, 20, 95)
        
        # ========== 实测功率 ==========
        # 温度效率系数
        temp_coeff = 1 - 0.004 * max(0, temperature_actual - 25)
        # 系统效率
        system_efficiency = 0.85
        # 功率计算
        power_actual = (irradiance_actual / 1000) * plant_capacity_kw * system_efficiency * temp_coeff
        power_actual = max(0, power_actual + np.random.normal(0, power_actual * 0.03))
        
        # ========== 气象预报（带误差）==========
        # 预报误差随预报时长增加
        # 假设这是"当前时刻"的预报，误差较小
        forecast_error_irr = np.random.normal(0, 0.10)  # 10% 辐照预报误差
        forecast_error_temp = np.random.normal(0, 2)     # 2°C 温度预报误差
        
        irradiance_forecast = irradiance_actual * (1 + forecast_error_irr)
        irradiance_forecast = max(0, irradiance_forecast)
        
        temperature_forecast = temperature_actual + forecast_error_temp
        
        # 风速预报
        wind_speed_base = 3 + 2 * np.sin(2 * np.pi * hour / 24)
        wind_speed_forecast = max(0, wind_speed_base + np.random.normal(0, 1))
        
        # 云量预报
        cloud_cover_forecast = cloud_state * 100 + np.random.normal(0, 10)
        cloud_cover_forecast = np.clip(cloud_cover_forecast, 0, 100)
        
        data.append({
            'timestamp': ts,
            'power_actual': round(power_actual, 2),
            'irradiance_actual': round(irradiance_actual, 2),
            'irradiance_forecast': round(irradiance_forecast, 2),
            'temperature_actual': round(temperature_actual, 2),
            'temperature_forecast': round(temperature_forecast, 2),
            'humidity_actual': round(humidity_actual, 2),
            'wind_speed_forecast': round(wind_speed_forecast, 2),
            'cloud_cover_forecast': round(cloud_cover_forecast, 2),
        })
    
    df = pd.DataFrame(data)
    
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"数据已保存到: {output_path}")
    
    # 统计信息
    print(f"\n数据统计:")
    print(f"  功率: min={df['power_actual'].min():.1f}, max={df['power_actual'].max():.1f}, mean={df['power_actual'].mean():.1f} kW")
    print(f"  辐照: min={df['irradiance_actual'].min():.1f}, max={df['irradiance_actual'].max():.1f} W/m²")
    print(f"  温度: min={df['temperature_actual'].min():.1f}, max={df['temperature_actual'].max():.1f} °C")
    
    return df


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="光伏发电功率预测 - 数据准备（日前预测版）")
    parser.add_argument("--download", action="store_true", help="生成日前预测数据集")
    parser.add_argument("--days", type=int, default=180, help="生成数据的天数")
    args = parser.parse_args()
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if args.download:
        print(f"生成 {args.days} 天的日前预测数据集...")
        output_path = os.path.join(DATA_DIR, "pv_power_day_ahead.csv")
        df = generate_day_ahead_data(n_days=args.days, output_path=output_path)
        print(f"\n数据生成完成: {len(df)} 条记录")
        print(f"可用于训练的天数: {args.days - 2} 天")
    else:
        try:
            df = load_pv_data()
            df = prepare_features(df)
            print("\n特征列:")
            print(df.columns.tolist())
        except FileNotFoundError as e:
            print(e)
            print("\n请运行 'python prepare.py --download' 生成数据")
            sys.exit(1)
    
    print("\n准备完成！")
# @AI_GENERATED: end
