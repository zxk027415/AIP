# @AI_GENERATED
"""
电力负荷预测 - 数据准备和评估模块（只读）

此文件包含固定的数据加载、预处理和评估函数。
Agent 不应修改此文件。

支持六种预测场景：DI(日内)/D(日前)/WI(周内)/W(周前)/MI(月内)/M(月前)
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional, List

# ---------------------------------------------------------------------------
# 常量（固定，不可修改）
# ---------------------------------------------------------------------------

TIME_BUDGET = 600           # 训练时间预算（秒）
TEST_RATIO = 0.2            # 测试集比例
DEFAULT_TIME_GRANULARITY = "15min"
DEFAULT_TIME_FIELD = "record_time"
DEFAULT_LOAD_FIELD = "load"

# 场景配置
SCENARIO_CONFIGS = {
    "DI": {"name": "日内预测", "horizon_hours": 4, "min_history_days": 7},
    "D":  {"name": "日前预测", "horizon_hours": 24, "min_history_days": 30},
    "WI": {"name": "周内预测", "horizon_hours": 168, "min_history_days": 60},
    "W":  {"name": "周前预测", "horizon_hours": 168, "min_history_days": 90},
    "MI": {"name": "月内预测", "horizon_hours": 720, "min_history_days": 180},
    "M":  {"name": "月前预测", "horizon_hours": 720, "min_history_days": 365},
}

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_data(
    data_path: Optional[str] = None,
    time_field: str = DEFAULT_TIME_FIELD,
    load_field: str = DEFAULT_LOAD_FIELD,
) -> pd.DataFrame:
    """
    加载负荷数据。

    数据格式要求：
    - time_field: 时间戳列（15分钟间隔）
    - load_field: 负荷值列 (kW 或 MW)

    Returns:
        pd.DataFrame: 加载的数据
    """
    if data_path is None:
        possible_paths = [
            os.path.join(DATA_DIR, "load_data.csv"),
            os.path.join(DATA_DIR, "load_true.csv"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                data_path = path
                break

        if data_path is None:
            raise FileNotFoundError(
                f"找不到数据文件。请将负荷数据 CSV 放到 {DATA_DIR}/ 目录下"
            )

    df = pd.read_csv(data_path, parse_dates=[time_field])
    df = df.sort_values(time_field).reset_index(drop=True)

    print(f"数据加载完成: {len(df)} 条记录")
    print(f"时间范围: {df[time_field].min()} ~ {df[time_field].max()}")
    print(f"列: {list(df.columns)}")

    return df


# ---------------------------------------------------------------------------
# 数据预处理
# ---------------------------------------------------------------------------

def preprocess_data(
    df: pd.DataFrame,
    time_field: str = DEFAULT_TIME_FIELD,
    load_field: str = DEFAULT_LOAD_FIELD,
    time_granularity: str = DEFAULT_TIME_GRANULARITY,
) -> pd.DataFrame:
    """
    数据预处理：时间戳补全、异常检测、数据填补。

    简化版本，适用于 AutoResearch 实验环境。
    """
    df = df.copy()

    # 确保时间列为 datetime
    df[time_field] = pd.to_datetime(df[time_field])
    df = df.sort_values(time_field).reset_index(drop=True)

    # 时间戳补全
    freq_map = {"15min": "15T", "30min": "30T", "1h": "H", "1H": "H"}
    freq = freq_map.get(time_granularity, "15T")
    full_range = pd.date_range(
        start=df[time_field].min(),
        end=df[time_field].max(),
        freq=freq,
    )
    full_df = pd.DataFrame({time_field: full_range})
    df = full_df.merge(df, on=time_field, how="left")

    # 异常检测（Chebyshev 不等式简化版）
    mean_val = df[load_field].mean()
    std_val = df[load_field].std()
    if std_val > 0:
        k = 3  # 3-sigma
        lower = mean_val - k * std_val
        upper = mean_val + k * std_val
        anomaly_mask = (df[load_field] < lower) | (df[load_field] > upper)
        df.loc[anomaly_mask, load_field] = np.nan

    # 数据填补（线性插值 + 前向/后向填充）
    df[load_field] = df[load_field].interpolate(method="linear")
    df[load_field] = df[load_field].fillna(method="ffill").fillna(method="bfill")

    print(f"预处理完成: {len(df)} 条记录, 缺失值: {df[load_field].isna().sum()}")
    return df


# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------

def add_features(
    df: pd.DataFrame,
    time_field: str = DEFAULT_TIME_FIELD,
    load_field: str = DEFAULT_LOAD_FIELD,
) -> pd.DataFrame:
    """
    添加负荷预测特征（简化版 add_more_features）。

    包括时间特征、Lag 特征、滚动统计。
    """
    df = df.copy()

    # 时间特征
    df["hour"] = df[time_field].dt.hour
    df["day_of_week"] = df[time_field].dt.dayofweek
    df["month"] = df[time_field].dt.month
    df["day_of_year"] = df[time_field].dt.dayofyear
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # 周期性编码
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Lag 特征
    points_per_hour = 4  # 15分钟粒度
    df["lag_1h"] = df[load_field].shift(1 * points_per_hour)
    df["lag_2h"] = df[load_field].shift(2 * points_per_hour)
    df["lag_24h"] = df[load_field].shift(24 * points_per_hour)
    df["lag_168h"] = df[load_field].shift(168 * points_per_hour)  # 1周

    # 滚动统计
    df["rolling_mean_4h"] = df[load_field].rolling(4 * points_per_hour).mean()
    df["rolling_std_4h"] = df[load_field].rolling(4 * points_per_hour).std()
    df["rolling_mean_24h"] = df[load_field].rolling(24 * points_per_hour).mean()
    df["rolling_max_24h"] = df[load_field].rolling(24 * points_per_hour).max()
    df["rolling_min_24h"] = df[load_field].rolling(24 * points_per_hour).min()

    # 日统计（当日截至当前时刻）
    df["daily_cumsum"] = df.groupby(df[time_field].dt.date)[load_field].cumsum()

    # 删除 NaN 行（由 lag 和 rolling 产生）
    df = df.dropna().reset_index(drop=True)

    print(f"特征工程完成: {len(df)} 条记录, {len(df.columns)} 列")
    return df


# ---------------------------------------------------------------------------
# 数据划分
# ---------------------------------------------------------------------------

def train_test_split_temporal(
    df: pd.DataFrame,
    test_ratio: float = TEST_RATIO,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """时序数据划分（保持时间顺序）"""
    split_idx = int(len(df) * (1 - test_ratio))
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    print(f"训练集: {len(train_df)} 条记录")
    print(f"测试集: {len(test_df)} 条记录")

    return train_df, test_df


# ---------------------------------------------------------------------------
# 评估函数
# ---------------------------------------------------------------------------

def evaluate_smape(y_true: np.ndarray, y_pred: np.ndarray, eps: float = 1e-8) -> float:
    """
    计算 SMAPE（对称平均绝对百分比误差），单位为百分比。

    与 utils.py 中的 smape() 函数逻辑完全一致。

    SMAPE = mean(|y_pred - y_true| / max(eps, (|y_true| + |y_pred|) / 2)) * 100
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.maximum(eps, (np.abs(y_true) + np.abs(y_pred)) / 2.0)
    return float(np.mean(np.abs(y_pred - y_true) / denom) * 100.0)


def evaluate_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """计算 MAE（平均绝对误差）"""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def evaluate_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """计算 RMSE（均方根误差）"""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def evaluate_all(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """计算所有评估指标"""
    return {
        "smape": evaluate_smape(y_true, y_pred),
        "mae": evaluate_mae(y_true, y_pred),
        "rmse": evaluate_rmse(y_true, y_pred),
    }


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="电力负荷预测 - 数据准备")
    parser.add_argument("--data", type=str, default=None, help="数据文件路径")
    parser.add_argument("--time-field", type=str, default=DEFAULT_TIME_FIELD)
    parser.add_argument("--load-field", type=str, default=DEFAULT_LOAD_FIELD)
    args = parser.parse_args()

    try:
        df = load_data(args.data, args.time_field, args.load_field)
        df = preprocess_data(df, args.time_field, args.load_field)
        df = add_features(df, args.time_field, args.load_field)
        train_df, test_df = train_test_split_temporal(df)
        print("\n准备完成！")
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
# @AI_GENERATED: end
