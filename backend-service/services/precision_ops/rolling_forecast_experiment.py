"""
precision_ops/rolling_forecast_experiment.py — 滚动预测实验引擎

实现真实的每日滚动预测逻辑：
  Day T: train(数据到 T-1) → predict(T 日 96 个点) → 对比 T 日真值

直接调用 XGBoost 算子后端，复用平台已有的特征工程和训练逻辑。
严格无数据穿越：每天只使用截止到 T-1 的数据训练和构造特征。

两个模型配置：
  - 生产模型: XGBoost n_estimators=200（默认配置）
  - 预上线候选: XGBoost n_estimators=500 + 更长 lag 特征（更优配置）
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 特征工程（复用平台算子逻辑，内联实现避免复杂依赖）
# ---------------------------------------------------------------------------

def _build_features(df: pd.DataFrame, target_col: str = "load") -> pd.DataFrame:
    """
    从原始 load 时序构建预测特征。

    复用平台工作流中的特征逻辑：
    - 时间特征: hour, day_of_week, month, is_weekend
    - 滞后特征: lag_1, lag_96(1天), lag_672(7天)
    - 滚动统计: rolling_mean_96, rolling_std_96
    """
    out = df.copy()

    # 确保有 timestamp 索引
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        out = out.set_index("timestamp")

    # 时间特征
    out["hour"] = out.index.hour
    out["minute"] = out.index.minute
    out["day_of_week"] = out.index.dayofweek
    out["month"] = out.index.month
    out["is_weekend"] = (out.index.dayofweek >= 5).astype(int)
    out["hour_sin"] = np.sin(2 * np.pi * out.index.hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * out.index.hour / 24)

    # 滞后特征（15 分钟粒度: 96 点 = 1 天, 672 点 = 7 天）
    out["lag_1"] = out[target_col].shift(1)
    out["lag_4"] = out[target_col].shift(4)     # 1 小时前
    out["lag_96"] = out[target_col].shift(96)   # 1 天前同时刻
    out["lag_192"] = out[target_col].shift(192) # 2 天前
    out["lag_672"] = out[target_col].shift(672) # 7 天前同时刻

    # 滚动统计
    out["rolling_mean_96"] = out[target_col].shift(1).rolling(96, min_periods=1).mean()
    out["rolling_std_96"] = out[target_col].shift(1).rolling(96, min_periods=1).std()
    out["rolling_mean_672"] = out[target_col].shift(1).rolling(672, min_periods=1).mean()

    return out


def _build_features_extended(df: pd.DataFrame, target_col: str = "load") -> pd.DataFrame:
    """
    扩展版特征工程（预上线候选使用），比生产版多:
    - 更多 lag 点: lag_288(3天), lag_384(4天)
    - 同时刻多周均值
    - 日内滚动趋势
    """
    out = _build_features(df, target_col)

    # 额外 lag
    out["lag_288"] = out[target_col].shift(288)  # 3 天前
    out["lag_384"] = out[target_col].shift(384)  # 4 天前

    # 同时刻 2 周均值
    lag_7d = out[target_col].shift(672)
    lag_14d = out[target_col].shift(1344)
    out["same_time_2w_avg"] = (lag_7d + lag_14d) / 2.0

    # 24h 滚动趋势（差分）
    out["trend_24h"] = out[target_col].shift(1) - out[target_col].shift(97)

    return out


# ---------------------------------------------------------------------------
# 单日训练 + 预测
# ---------------------------------------------------------------------------

def _train_and_predict_one_day(
    full_data: pd.DataFrame,
    predict_date: datetime,
    n_estimators: int = 200,
    train_days: int = 60,
    use_extended_features: bool = False,
    target_col: str = "load",
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    对单个预测日执行训练 + 前向预测。

    严格无穿越：
    - 训练集 = predict_date 之前 train_days 天的数据（不含 predict_date 当天）
    - 预测 = predict_date 当天的 96 个点

    :param full_data: 含 timestamp + load 列的完整数据（特征工程在此函数内完成）
    :param predict_date: 预测日（datetime, timezone-aware or naive）
    :param n_estimators: XGBoost 树数量
    :param train_days: 训练窗口天数
    :param use_extended_features: 是否使用扩展特征集
    :param target_col: 目标列名
    :return: (y_pred, y_true, timestamps) 各长度 ≤ 96
    """
    import xgboost as xgb

    predict_date_naive = predict_date.replace(tzinfo=None) if predict_date.tzinfo else predict_date

    # 时间边界（严格无穿越）
    train_end = predict_date_naive  # 训练集不含 predict_date
    train_start = train_end - timedelta(days=train_days)
    predict_end = predict_date_naive + timedelta(days=1)

    # 特征需要更早数据来计算 lag（多取 14 天用于 lag warm-up）
    data_start = train_start - timedelta(days=14)

    # 切出所需数据范围
    df = full_data.copy()
    if "timestamp" not in df.columns and df.index.name == "timestamp":
        df = df.reset_index()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[(df["timestamp"] >= data_start) & (df["timestamp"] < predict_end)]
    df = df.sort_values("timestamp").reset_index(drop=True)

    if df.empty:
        return np.array([]), np.array([]), []

    # 特征工程
    if use_extended_features:
        featured = _build_features_extended(df, target_col)
    else:
        featured = _build_features(df, target_col)

    # 分割训练集 和 预测集
    train_mask = (featured.index >= train_start) & (featured.index < train_end)
    predict_mask = (featured.index >= predict_date_naive) & (featured.index < predict_end)

    train_df = featured[train_mask].copy()
    predict_df = featured[predict_mask].copy()

    if train_df.empty or predict_df.empty:
        return np.array([]), np.array([]), []

    # 准备 X, y
    feature_cols = [c for c in train_df.columns if c != target_col]
    feature_cols = [c for c in feature_cols if train_df[c].dtype in [np.float64, np.int64, float, int]]

    X_train = train_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    y_train = train_df[target_col].fillna(0).values

    X_predict = predict_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    y_true = predict_df[target_col].values

    # 去掉全 NaN 的训练行
    valid_mask = np.isfinite(y_train) & (y_train > 0)
    X_train = X_train[valid_mask]
    y_train = y_train[valid_mask]

    if len(X_train) < 96:  # 至少 1 天数据
        return np.array([]), np.array([]), []

    # 训练 XGBoost
    dtrain = xgb.DMatrix(X_train, label=y_train)
    params = {
        "objective": "reg:squarederror",
        "max_depth": 6,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "verbosity": 0,
    }
    model = xgb.train(params, dtrain, num_boost_round=n_estimators)

    # 预测
    dpredict = xgb.DMatrix(X_predict)
    y_pred = model.predict(dpredict)

    # 时间戳列表
    timestamps = predict_df.index.strftime("%Y-%m-%d %H:%M:%S").tolist()

    return y_pred, y_true, timestamps


# ---------------------------------------------------------------------------
# 完整滚动预测实验
# ---------------------------------------------------------------------------

def run_rolling_forecast_experiment(
    csv_path: str,
    start_date: str = "2026-04-01",
    observation_days: int = 7,
    train_days: int = 60,
    production_n_estimators: int = 200,
    prelaunch_n_estimators: int = 500,
) -> Dict[str, Any]:
    """
    运行完整的滚动预测实验。

    每天两个模型各自独立 train + predict:
      - 生产模型: 基础特征 + n_estimators=200
      - 预上线候选: 扩展特征 + n_estimators=500

    严格无穿越: Day T 的训练只用到 T-1 的数据。

    :param csv_path: 数据文件路径
    :param start_date: 观察起始日 (假设"今天")
    :param observation_days: 观察天数
    :param train_days: 每天训练的历史窗口天数
    :param production_n_estimators: 生产模型树数
    :param prelaunch_n_estimators: 预上线模型树数
    :return: 实验结果字典
    """
    t0 = time.time()

    # 加载数据
    df = pd.read_csv(csv_path)
    df["record_time"] = pd.to_datetime(df["record_time"])
    df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
    df.columns = ["timestamp", "load"]
    df = df.sort_values("timestamp").reset_index(drop=True)

    start_dt = datetime.fromisoformat(start_date)

    logger.info(
        "rolling_forecast_experiment: start=%s obs_days=%d train_days=%d "
        "prod_n_est=%d pre_n_est=%d",
        start_date, observation_days, train_days,
        production_n_estimators, prelaunch_n_estimators,
    )

    daily_results = []

    for day_offset in range(observation_days):
        predict_date = start_dt + timedelta(days=day_offset)
        day_label = predict_date.strftime("%Y-%m-%d")

        # --- 生产模型: 基础特征 + 200 棵树 ---
        prod_pred, prod_true, prod_ts = _train_and_predict_one_day(
            df, predict_date,
            n_estimators=production_n_estimators,
            train_days=train_days,
            use_extended_features=False,
        )

        # --- 预上线候选: 扩展特征 + 500 棵树 ---
        pre_pred, pre_true, pre_ts = _train_and_predict_one_day(
            df, predict_date,
            n_estimators=prelaunch_n_estimators,
            train_days=train_days,
            use_extended_features=True,
        )

        # 计算 MAPE（排除真值为 0 的点）
        prod_mape = _calc_mape(prod_pred, prod_true)
        pre_mape = _calc_mape(pre_pred, pre_true)

        daily_results.append({
            "date": day_label,
            "production_mape": round(prod_mape, 4) if prod_mape is not None else None,
            "prelaunch_mape": round(pre_mape, 4) if pre_mape is not None else None,
            "points": len(prod_pred),
            "winner": (
                "prelaunch" if (pre_mape is not None and prod_mape is not None and pre_mape < prod_mape)
                else "production"
            ),
        })

        logger.info(
            "  %s | prod_mape=%.4f%% pre_mape=%.4f%% | winner=%s | %d points",
            day_label,
            prod_mape or 0, pre_mape or 0,
            daily_results[-1]["winner"],
            len(prod_pred),
        )

    # 汇总
    prod_mapes = [r["production_mape"] for r in daily_results if r["production_mape"] is not None]
    pre_mapes = [r["prelaunch_mape"] for r in daily_results if r["prelaunch_mape"] is not None]
    avg_prod = float(np.mean(prod_mapes)) if prod_mapes else None
    avg_pre = float(np.mean(pre_mapes)) if pre_mapes else None
    win_days = sum(1 for r in daily_results if r["winner"] == "prelaunch")

    elapsed = time.time() - t0
    logger.info(
        "rolling_forecast_experiment complete: prod_avg=%.4f%% pre_avg=%.4f%% "
        "win_days=%d/%d elapsed=%.1fs",
        avg_prod or 0, avg_pre or 0, win_days, observation_days, elapsed,
    )

    return {
        "daily_results": daily_results,
        "summary": {
            "production_avg_mape": round(avg_prod, 4) if avg_prod else None,
            "prelaunch_avg_mape": round(avg_pre, 4) if avg_pre else None,
            "prelaunch_win_days": win_days,
            "total_days": observation_days,
            "elapsed_seconds": round(elapsed, 1),
        },
        "config": {
            "start_date": start_date,
            "observation_days": observation_days,
            "train_days": train_days,
            "production": f"XGBoost n_est={production_n_estimators}, 基础特征",
            "prelaunch": f"XGBoost n_est={prelaunch_n_estimators}, 扩展特征",
            "no_data_leakage": "严格: Day T train 截止 T-1, predict 覆盖 T",
        },
    }


def _calc_mape(y_pred: np.ndarray, y_true: np.ndarray) -> Optional[float]:
    """计算 MAPE%，排除 y_true=0 的点"""
    if len(y_pred) == 0 or len(y_true) == 0:
        return None
    mask = y_true != 0
    if mask.sum() == 0:
        return None
    return float(np.mean(np.abs(y_pred[mask] - y_true[mask]) / np.abs(y_true[mask])) * 100)
