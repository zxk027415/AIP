#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加气象数据的纯算子版回测 3.1~3.8（train_days=60, gap_days=1）

气象数据防穿越策略：
- 气象是预报数据（forecast），预测日当天的气象预报在 D 日执行时已可获得
- 训练集：用历史气象真实值（已发生）
- 测试集：用预测日当天的气象预报值（不遮蔽，因为业务上可获得）
- 气象滚动统计特征：基于 shift(1h) 避免当前时刻穿越
- 气象数据从 1h 插值到 15min 对齐负荷数据

用法：
    python test_operator_backtest_weather.py
"""
import os
import sys
import time
import gc
import numpy as np
import pandas as pd
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.operator_backends.resample_timeseries import execute as resample_execute
from services.operator_backends.detect_outliers import execute as outliers_execute
from services.operator_backends.handle_missing import execute as handle_missing_execute
from services.operator_backends.extract_time_features import execute as time_features_execute
from services.operator_backends.holiday_features import execute as holiday_execute
from services.operator_backends.workday_features import execute as workday_execute
from services.operator_backends.rolling_statistics import execute as rolling_execute
from services.operator_backends.create_lag_features import execute as lag_execute
from services.operator_backends.extract_statistical_features import execute as stat_features_execute
from services.operator_backends.diff_features import execute as diff_execute
from services.operator_backends.auto_tune_xgboost import execute as auto_tune_execute
from services.operator_backends.xgboost_forecast import execute as xgb_execute
from services.operator_backends.lightgbm_forecast import execute as lgb_execute
from services.operator_backends.catboost_forecast import execute as catb_execute
from services.operator_backends.ridge_forecast import execute as ridge_execute
from services.operator_backends.ensemble_forecast import execute as ensemble_execute

# ============================================================================
# 参数
# ============================================================================
PRED_START = "2026-03-01"
PRED_END = "2026-03-09"  # exclusive
TRAIN_DAYS_LIST = [30, 45, 60, 90, 120]
GAP_DAYS = 1
DAILY_HORIZON = 96

LOAD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasets", "load_true_weihai_260415.csv")
WEATHER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasets", "ens_avg_weihai.csv")

# 本地无气象结果（对比基准）
LOCAL_NO_WEATHER = {
    "2026-03-01": 4.10, "2026-03-02": 6.84, "2026-03-03": 7.98, "2026-03-04": 3.99,
    "2026-03-05": 4.11, "2026-03-06": 6.87, "2026-03-07": 4.92, "2026-03-08": 4.40,
}
# 同事结果（有气象）
COLLEAGUE = {
    "2026-03-01": 3.96, "2026-03-02": 6.62, "2026-03-03": 6.98, "2026-03-04": 5.67,
    "2026-03-05": 2.16, "2026-03-06": 3.67, "2026-03-07": 5.14, "2026-03-08": 2.64,
}


def smape(y_true, y_pred):
    denom = np.abs(y_true) + np.abs(y_pred)
    mask = denom > 1e-8
    return float(np.round(2.0 * np.mean(np.abs(y_pred[mask] - y_true[mask]) / denom[mask]) * 100, 4))


def load_data():
    """加载负荷数据"""
    df = pd.read_csv(LOAD_PATH)
    df["record_time"] = pd.to_datetime(df["record_time"])
    load_df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
    load_df = load_df.sort_values("record_time").reset_index(drop=True)
    print(f"负荷数据: {len(load_df)} rows, {load_df['record_time'].min()} ~ {load_df['record_time'].max()}")
    return load_df


def load_weather():
    """加载气象数据并插值到 15min"""
    wdf = pd.read_csv(WEATHER_PATH)
    wdf["timestamp"] = pd.to_datetime(wdf["timestamp"])
    wdf = wdf.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="first")

    weather_cols = ["wind_speed", "wind_direction", "temperature", "pressure", "rainfall"]

    # 插值到 15min
    wdf = wdf.set_index("timestamp")[weather_cols]
    full_idx = pd.date_range(wdf.index.min(), wdf.index.max(), freq="15min")
    wdf = wdf.reindex(full_idx).interpolate(method="linear").ffill().bfill()
    wdf = wdf.reset_index().rename(columns={"index": "record_time"})

    print(f"气象数据: {len(wdf)} rows (插值到15min), {wdf['record_time'].min()} ~ {wdf['record_time'].max()}")
    return wdf


def merge_load_weather(load_df, weather_df, train_start, pred_end):
    """合并负荷和气象数据（只取需要的时间范围）"""
    # 筛选时间范围
    mask_load = (load_df["record_time"] >= train_start) & (load_df["record_time"] < pred_end)
    mask_weather = (weather_df["record_time"] >= train_start) & (weather_df["record_time"] < pred_end)

    ld = load_df[mask_load].copy()
    wd = weather_df[mask_weather].copy()

    # merge on record_time
    merged = ld.merge(wd, on="record_time", how="left")
    # 填充气象缺失值（边界情况）
    weather_cols = ["wind_speed", "wind_direction", "temperature", "pressure", "rainfall"]
    for col in weather_cols:
        merged[col] = merged[col].interpolate().ffill().bfill()

    return merged


def build_weather_features(df):
    """构建气象衍生特征（无穿越）"""
    weather_cols = ["wind_speed", "wind_direction", "temperature", "pressure", "rainfall"]

    # 基础气象特征已在 df 中（wind_speed, temperature 等）

    # 温度相关衍生
    df["temp_sq"] = df["temperature"] ** 2  # 温度平方（非线性效应）
    df["wind_chill"] = 13.12 + 0.6215 * df["temperature"] - 11.37 * (df["wind_speed"] * 3.6) ** 0.16 + 0.3965 * df["temperature"] * (df["wind_speed"] * 3.6) ** 0.16
    # 风速分量
    wind_rad = np.radians(df["wind_direction"])
    df["wind_u"] = df["wind_speed"] * np.sin(wind_rad)  # 东西分量
    df["wind_v"] = df["wind_speed"] * np.cos(wind_rad)  # 南北分量

    # 气象滚动统计（基于 shift(4) 即 1 小时前，避免当前时刻穿越）
    for col in ["temperature", "wind_speed", "pressure"]:
        shifted = df[col].shift(4)  # shift 4 个 15min = 1 小时
        for w in [4, 16, 96]:  # 1h, 4h, 24h 窗口
            df[f"{col}_roll_mean_{w}"] = shifted.rolling(w, min_periods=1).mean()
            df[f"{col}_roll_std_{w}"] = shifted.rolling(w, min_periods=1).std()

    # 温度变化率（过去 4 小时）
    df["temp_change_4h"] = df["temperature"] - df["temperature"].shift(16)
    # 气压变化率（过去 4 小时）
    df["pressure_change_4h"] = df["pressure"] - df["pressure"].shift(16)

    return df


def run_feature_pipeline(df):
    """执行负荷特征工程流水线"""
    # 1. resample (负荷部分)
    result = resample_execute(
        {"frequency": "15min", "method": "mean", "time_field": "record_time", "load_field": "value"},
        {"data": df}
    )
    data = result["data"]

    # 2. skip outlier detection
    result = outliers_execute(
        {"method": "zscore", "threshold": 6, "load_field": "value", "window_size": 96,
         "skip_when_strict_alignment": True, "strict_alignment_mode": True},
        {"data": data}
    )
    data = result["data"]

    # 3. handle_missing
    result = handle_missing_execute(
        {"method": "linear", "time_field": "record_time", "load_field": "value"},
        {"data": data}
    )
    data = result["data"]

    # 4. time features
    result = time_features_execute(
        {"features": ["hour", "minute", "period", "dayofweek", "month", "day", "yday",
                      "hour_sin", "hour_cos", "wday_sin", "wday_cos",
                      "yday_sin", "yday_cos", "month_sin", "month_cos"],
         "time_field": "record_time"},
        {"data": data}
    )
    data = result["data"]

    # 5. holiday
    result = holiday_execute({"time_field": "record_time", "remove_spring_festival": False}, {"data": data})
    data = result["data"]

    # 6. workday
    result = workday_execute({"time_field": "record_time"}, {"data": data})
    data = result["data"]

    # 7. rolling statistics (负荷)
    result = rolling_execute(
        {"target_column": "value", "window_sizes": [4, 8, 12, 24, 48, 96],
         "statistics": ["mean", "std", "max", "min"], "base_shift": 96},
        {"data": data}
    )
    data = result["data"]

    # 8. lag features (负荷)
    result = lag_execute(
        {"lags": [1], "lag_days": [1, 2, 3, 4, 5, 6, 7, 14, 21, 28],
         "horizon_per_day": 96, "add_same_time_ensemble": True, "target_column": "value"},
        {"data": data}
    )
    data = result["data"]

    # 9. 日统计
    result = stat_features_execute(
        {"mode": "groupby", "target_column": "value", "source_column": "value",
         "group_by_from_time": "date", "group_shift": 1,
         "statistics": ["mean", "max", "min", "std"],
         "output_prefix": "day", "add_daily_derived": True, "time_field": "record_time"},
        {"data": data}
    )
    data = result["data"]

    # 10. lag1d 日统计
    lag_col = "value_lag_96"
    if lag_col in data.columns:
        result = stat_features_execute(
            {"mode": "groupby", "target_column": "value", "source_column": lag_col,
             "group_by_from_time": "date", "group_shift": 1,
             "statistics": ["mean", "std"],
             "output_prefix": "lag1d_day", "time_field": "record_time"},
            {"data": data}
        )
        data = result["data"]

    # 11. diff features
    result = diff_execute(
        {"target_column": "value", "diff_periods": [1], "seasonal_period": 24,
         "no_leak_mode": True, "horizon_per_day": 96, "include_cross_day_diff": True},
        {"data": data}
    )
    data = result["data"]

    return data


def run_single_day(load_df, weather_df, pred_day_str, train_days=60):
    """单天回测：合并气象 → 特征工程 → 训练 → 预测"""
    pred_day = pd.to_datetime(pred_day_str)
    train_end = pred_day - timedelta(days=1 + GAP_DAYS)
    train_start = train_end - timedelta(days=train_days)

    # 合并负荷+气象（包含训练期+测试日）
    merged = merge_load_weather(load_df, weather_df, train_start, pred_day + timedelta(days=1))

    if len(merged) < train_days * DAILY_HORIZON * 0.5:
        print(f"  {pred_day_str}: 数据不足 ({len(merged)} rows), 跳过")
        return None

    # 分离训练和测试的原始数据
    train_raw = merged[merged["record_time"] <= train_end].copy()
    test_raw = merged[(merged["record_time"] >= pred_day) & (merged["record_time"] < pred_day + timedelta(days=1))].copy()

    if len(test_raw) == 0:
        print(f"  {pred_day_str}: 无测试数据, 跳过")
        return None

    # 遮蔽测试日的负荷值（防穿越）
    # 注意：气象值不遮蔽（预报数据，业务上可获得）
    test_masked = test_raw.copy()
    test_masked["value"] = np.nan
    combined = pd.concat([train_raw, test_masked], ignore_index=True)

    # 负荷特征工程（在 combined 上做，测试日 value=NaN 确保 lag/rolling 不穿越）
    featured = run_feature_pipeline(combined)

    # 气象衍生特征（在 combined 上做，气象值未遮蔽）
    featured = build_weather_features(featured)

    # 切分
    train_feat = featured[featured["record_time"] <= train_end].copy()
    test_feat = featured[featured["record_time"] >= pred_day].copy()

    # 特征列
    drop_cols = ["value", "record_time", "date", "parent_id", "child_id", "feature_name",
                 "assetid", "forecast_time", "timestamp"]
    feature_cols = [c for c in train_feat.columns
                    if c not in drop_cols and train_feat[c].dtype in ['float64', 'float32', 'int64', 'int32']]

    x_train = train_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    y_train = train_feat["value"].values.astype(float)

    x_test = test_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)

    # 真实值从未遮蔽的 test_raw 取
    y_true = test_raw.sort_values("record_time")["value"].values.astype(float)
    n_te = min(len(x_test), len(y_true))
    x_test = x_test.iloc[:n_te]
    y_true = y_true[:n_te]

    if n_te == 0:
        print(f"  {pred_day_str}: 测试点数为 0, 跳过")
        return None

    print(f"    特征数: {len(feature_cols)} (含气象), 训练: {len(x_train)}, 测试: {n_te}")

    # global_config
    gcfg = {
        "operate_status": "backtest",
        "xgb_eta_high": 0.15,
        "xgb_max_depth_high": 8.0,
        "xgb_min_child_weight_high": 10.0,
        "xgb_seed": 42,
        "xgb_nthread": 4,
    }
    forecast_config = {"forecast_steps": DAILY_HORIZON}

    # XGB
    print(f"    训练 XGB...")
    tune_result = auto_tune_execute(
        {"n_trials": 15, "cv_folds": 5, "cv_strategy": "timeseries", "_global_config": gcfg},
        {"train_features": x_train, "train_target": y_train,
         "test_features": x_test, "test_target": y_true, "forecast_config": forecast_config}
    )
    xgb_result = xgb_execute(
        {"mode": "train", "n_estimators": 200, "sample_weight_decay": 0.99,
         "output_prefix": "xgb", "time_field": "record_time", "_global_config": gcfg},
        {"train_features": x_train, "train_target": y_train,
         "test_features": x_test, "test_target": y_true,
         "forecast_config": forecast_config,
         "model": tune_result.get("model"), "best_params": tune_result.get("best_params"),
         "oof_rmse": tune_result.get("oof_rmse")}
    )

    # LGB
    print(f"    训练 LGB...")
    lgb_result = lgb_execute(
        {"mode": "train", "n_estimators": 200, "sample_weight_decay": 0.99,
         "output_prefix": "lgb", "time_field": "record_time",
         "n_splits": 5, "bo_init_points": 3, "bo_n_iter": 12, "_global_config": gcfg},
        {"train_features": x_train, "train_target": y_train,
         "test_features": x_test, "test_target": y_true, "forecast_config": forecast_config}
    )

    # CatBoost
    print(f"    训练 CatBoost...")
    catb_result = catb_execute(
        {"mode": "train", "n_estimators": 200, "sample_weight_decay": 0.99,
         "output_prefix": "catb", "time_field": "record_time",
         "n_splits": 5, "bo_init_points": 3, "bo_n_iter": 12, "_global_config": gcfg},
        {"train_features": x_train, "train_target": y_train,
         "test_features": x_test, "test_target": y_true, "forecast_config": forecast_config}
    )

    # Ridge
    print(f"    训练 Ridge...")
    ridge_result = ridge_execute(
        {"mode": "train", "alpha": 1.0, "sample_weight_decay": 0.99,
         "output_prefix": "ridge", "time_field": "record_time",
         "n_splits": 5, "_global_config": gcfg},
        {"train_features": x_train, "train_target": y_train,
         "test_features": x_test, "test_target": y_true, "forecast_config": forecast_config}
    )

    # Ensemble (OOF RMSE 权重)
    ensemble_inputs = {
        "y_pred_xgb": xgb_result.get("y_pred_xgb", xgb_result.get("y_pred")),
        "y_pred_lgb": lgb_result.get("y_pred_lgb", lgb_result.get("y_pred")),
        "y_pred_catb": catb_result.get("y_pred_catb", catb_result.get("y_pred")),
        "y_pred_ridge": ridge_result.get("y_pred_ridge", ridge_result.get("y_pred")),
        "y_true": y_true,
        "oof_rmse_xgb": xgb_result.get("oof_rmse_xgb", xgb_result.get("oof_rmse")),
        "oof_rmse_lgb": lgb_result.get("oof_rmse_lgb", lgb_result.get("oof_rmse")),
        "oof_rmse_catb": catb_result.get("oof_rmse_catb", catb_result.get("oof_rmse")),
        "oof_rmse_ridge": ridge_result.get("oof_rmse_ridge", ridge_result.get("oof_rmse")),
    }

    ens_result = ensemble_execute(
        {"prediction_keys": "y_pred_xgb,y_pred_lgb,y_pred_catb,y_pred_ridge",
         "weight_mode": "upstream_oof_rmse"},
        ensemble_inputs
    )

    y_pred = np.asarray(ens_result["y_pred"], dtype=float)
    weights = ens_result.get("model_weights", {})
    day_smape = smape(y_true[:len(y_pred)], y_pred)

    prefix = "y_pred_"
    weight_str = ", ".join(f"{k[len(prefix):] if k.startswith(prefix) else k}={v:.3f}" for k, v in weights.items())
    print(f"    权重: {weight_str}")
    print(f"    SMAPE={day_smape:.2f}%")

    gc.collect()
    return {"date": pred_day_str, "smape": day_smape, "weights": weights, "n_points": len(y_pred)}


def main():
    print("=" * 70)
    print("  AIP 算子版回测 + 气象数据 — 多训练天数对比")
    print(f"  train_days={TRAIN_DAYS_LIST}, gap_days={GAP_DAYS}")
    print("=" * 70)

    t0 = time.time()
    load_df = load_data()
    weather_df = load_weather()

    all_days = pd.date_range(PRED_START, PRED_END, freq="D", inclusive="left")
    all_summary = []

    for td in TRAIN_DAYS_LIST:
        print(f"\n{'='*70}")
        print(f"  训练天数: {td}d")
        print(f"{'='*70}")
        results = []

        for pred_day in all_days:
            day_str = pred_day.strftime("%Y-%m-%d")
            print(f"\n  [{day_str}] td={td}")
            t_day = time.time()
            r = run_single_day(load_df, weather_df, day_str, train_days=td)
            if r:
                r["duration"] = round(time.time() - t_day, 1)
                results.append(r)

        if results:
            avg = np.mean([r["smape"] for r in results])
            all_summary.append({"train_days": td, "avg_smape": round(avg, 4)})
            print(f"\n  train_days={td} 平均 SMAPE: {avg:.2f}%")

    # 汇总
    print("\n" + "=" * 70)
    print("  AIP+气象 多训练天数汇总")
    print("=" * 70)
    for s in all_summary:
        print(f"  train_days={s['train_days']:>3d}  avg_smape={s['avg_smape']:.2f}%")
    print(f"\n总耗时: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
