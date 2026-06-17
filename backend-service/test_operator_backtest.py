#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试纯算子版流水线回测 3.1~3.8，参数与本地 run_weihai_backtest.py 对齐。
对比本地结果（train_days=60, gap_days=1）。

用法：
    python test_operator_backtest.py
"""
import os
import sys
import time
import numpy as np
import pandas as pd
from datetime import timedelta

# 确保能 import backend-service 下的模块
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
from services.operator_backends.train_test_split_ts import execute as split_execute
from services.operator_backends.auto_tune_xgboost import execute as auto_tune_execute
from services.operator_backends.xgboost_forecast import execute as xgb_execute
from services.operator_backends.lightgbm_forecast import execute as lgb_execute
from services.operator_backends.catboost_forecast import execute as catb_execute
from services.operator_backends.ridge_forecast import execute as ridge_execute
from services.operator_backends.ensemble_forecast import execute as ensemble_execute

# ============================================================================
# 参数（与本地 run_weihai_backtest.py 对齐）
# ============================================================================
PRED_START = "2026-03-01"
PRED_END = "2026-03-09"  # exclusive
TRAIN_DAYS = 60
GAP_DAYS = 1
DAILY_HORIZON = 96

# 数据路径
DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "datasets", "load_true_weihai_260415.csv"
)

# 本地结果（train_days=60）
LOCAL_RESULTS = {
    "2026-03-01": 4.10,
    "2026-03-02": 6.84,
    "2026-03-03": 7.98,
    "2026-03-04": 3.99,
    "2026-03-05": 4.11,
    "2026-03-06": 6.87,
    "2026-03-07": 4.92,
    "2026-03-08": 4.40,
}
LOCAL_AVG_SMAPE = 5.40


def smape(y_true, y_pred):
    denom = np.abs(y_true) + np.abs(y_pred)
    mask = denom > 1e-8
    return float(np.round(2.0 * np.mean(np.abs(y_pred[mask] - y_true[mask]) / denom[mask]) * 100, 4))


def load_data():
    """加载数据（CSV 格式，和流水线 load_csv 算子一致）"""
    if not os.path.exists(DATA_PATH):
        # 尝试从 xlsx 加载
        xlsx_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "load_forecast_refactored", "datasets", "load_true_weihai_260407.xlsx"
        )
        if os.path.exists(xlsx_path):
            df = pd.read_excel(xlsx_path)
            df["record_time"] = pd.to_datetime(df["record_time"])
            load_df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
            load_df = load_df.sort_values("record_time").reset_index(drop=True)
            print(f"从 xlsx 加载: {len(load_df)} rows")
            return load_df
        raise FileNotFoundError(f"找不到数据文件: {DATA_PATH} 或 {xlsx_path}")

    df = pd.read_csv(DATA_PATH)
    df["record_time"] = pd.to_datetime(df["record_time"])
    # 筛选 load 数据
    if "feature_name" in df.columns:
        df = df[df["feature_name"] == "load"]
    if "value" not in df.columns and "load" in df.columns:
        df["value"] = df["load"]
    load_df = df[["record_time", "value"]].copy()
    load_df = load_df.sort_values("record_time").reset_index(drop=True)
    print(f"从 CSV 加载: {len(load_df)} rows, {load_df['record_time'].min()} ~ {load_df['record_time'].max()}")
    return load_df


def run_feature_pipeline(df):
    """执行特征工程流水线（算子串联）"""
    # 1. resample
    result = resample_execute(
        {"frequency": "15min", "method": "mean", "time_field": "record_time", "load_field": "value"},
        {"data": df}
    )
    data = result["data"]

    # 2. detect_outliers (skip — 本地代码没有)
    # 设 skip_when_strict_alignment=true + strict_alignment_mode=true 来跳过
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

    # 4. extract_time_features
    result = time_features_execute(
        {"features": ["hour", "minute", "period", "dayofweek", "month", "day", "yday",
                      "hour_sin", "hour_cos", "wday_sin", "wday_cos",
                      "yday_sin", "yday_cos", "month_sin", "month_cos"],
         "time_field": "record_time"},
        {"data": data}
    )
    data = result["data"]

    # 5. holiday_features
    result = holiday_execute(
        {"time_field": "record_time", "remove_spring_festival": False},
        {"data": data}
    )
    data = result["data"]

    # 6. workday_features
    result = workday_execute(
        {"time_field": "record_time"},
        {"data": data}
    )
    data = result["data"]

    # 7. rolling_statistics
    result = rolling_execute(
        {"target_column": "value", "window_sizes": [4, 8, 12, 24, 48, 96],
         "statistics": ["mean", "std", "max", "min"], "base_shift": 96},
        {"data": data}
    )
    data = result["data"]

    # 8. create_lag_features
    result = lag_execute(
        {"lags": [1], "lag_days": [1, 2, 3, 4, 5, 6, 7, 14, 21, 28],
         "horizon_per_day": 96, "add_same_time_ensemble": True, "target_column": "value"},
        {"data": data}
    )
    data = result["data"]

    # 9. extract_statistical_features (日统计)
    result = stat_features_execute(
        {"mode": "groupby", "target_column": "value", "source_column": "value",
         "group_by_from_time": "date", "group_shift": 1,
         "statistics": ["mean", "max", "min", "std"],
         "output_prefix": "day", "add_daily_derived": True, "time_field": "record_time"},
        {"data": data}
    )
    data = result["data"]

    # 10. extract_statistical_features (lag1d 日统计)
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

    # 11. diff_features
    result = diff_execute(
        {"target_column": "value", "diff_periods": [1], "seasonal_period": 24,
         "no_leak_mode": True, "horizon_per_day": 96, "include_cross_day_diff": True},
        {"data": data}
    )
    data = result["data"]

    return data


def run_single_day(raw_data, pred_day_str):
    """对单天执行特征工程+训练+预测（和本地代码一致：遮蔽测试日 load 后做特征）"""
    pred_day = pd.to_datetime(pred_day_str)
    train_end = pred_day - timedelta(days=1 + GAP_DAYS)
    train_start = train_end - timedelta(days=TRAIN_DAYS)

    # 切分原始数据
    mask_tr = (raw_data["record_time"] >= train_start) & (raw_data["record_time"] <= train_end)
    mask_te = (raw_data["record_time"] >= pred_day) & (raw_data["record_time"] < pred_day + timedelta(days=1))

    train_raw = raw_data[mask_tr].copy().reset_index(drop=True)
    test_raw = raw_data[mask_te].copy().reset_index(drop=True)

    if len(train_raw) < TRAIN_DAYS * DAILY_HORIZON * 0.5:
        print(f"  {pred_day_str}: 训练数据不足 ({len(train_raw)} rows), 跳过")
        return None
    if len(test_raw) == 0:
        print(f"  {pred_day_str}: 无测试数据, 跳过")
        return None

    # 关键：遮蔽测试日的 value（防止 lag/rolling 穿越）
    test_masked = test_raw.copy()
    test_masked["value"] = np.nan
    combined = pd.concat([train_raw, test_masked], ignore_index=True)

    # 在 combined 上做特征工程
    featured = run_feature_pipeline(combined)

    # 切分特征后的训练/测试
    train_feat = featured[featured["record_time"] <= train_end].copy()
    test_feat = featured[featured["record_time"] >= pred_day].copy()

    # 特征列
    drop_cols = ["value", "record_time", "date", "parent_id", "child_id", "feature_name"]
    feature_cols = [c for c in train_feat.columns
                    if c not in drop_cols and train_feat[c].dtype in ['float64', 'float32', 'int64', 'int32']]

    x_train = train_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    y_train = train_feat["value"].values.astype(float)

    x_test = test_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)

    # 真实值从原始 test_raw 取
    y_true = test_raw.sort_values("record_time")["value"].values.astype(float)
    n_te = min(len(x_test), len(y_true))
    x_test = x_test.iloc[:n_te]
    y_true = y_true[:n_te]

    # global_config 注入
    gcfg = {
        "operate_status": "backtest",
        "xgb_eta_high": 0.15,
        "xgb_max_depth_high": 8.0,
        "xgb_min_child_weight_high": 10.0,
        "xgb_seed": 42,
        "xgb_nthread": 4,
    }

    # 训练 4 个模型
    forecast_config = {"forecast_steps": DAILY_HORIZON}

    # XGB (with auto_tune)
    print(f"    训练 XGB (BO 15轮)...")
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
         "n_splits": 5, "bo_init_points": 3, "bo_n_iter": 12,
         "_global_config": gcfg},
        {"train_features": x_train, "train_target": y_train,
         "test_features": x_test, "test_target": y_true, "forecast_config": forecast_config}
    )

    # CatBoost
    print(f"    训练 CatBoost...")
    catb_result = catb_execute(
        {"mode": "train", "n_estimators": 200, "sample_weight_decay": 0.99,
         "output_prefix": "catb", "time_field": "record_time",
         "n_splits": 5, "bo_init_points": 3, "bo_n_iter": 12,
         "_global_config": gcfg},
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

    # Ensemble (upstream_oof_rmse mode)
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

    print(f"    权重: {', '.join(f'{k}={v:.3f}' for k, v in weights.items())}")
    print(f"    SMAPE={day_smape:.2f}%")

    return {
        "date": pred_day_str,
        "smape": day_smape,
        "weights": weights,
        "n_points": len(y_pred),
    }


def main():
    print("=" * 70)
    print("  纯算子版流水线回测测试 (3.1~3.8, train_days=60, gap_days=1)")
    print("=" * 70)

    t0 = time.time()

    # 加载数据
    raw_data = load_data()

    # 逐日回测（每天单独做特征工程，遮蔽测试日 value 防穿越）
    print(f"\n▶ 开始逐日回测 ({PRED_START} ~ {PRED_END})...")
    all_days = pd.date_range(PRED_START, PRED_END, freq="D", inclusive="left")
    results = []

    for pred_day in all_days:
        day_str = pred_day.strftime("%Y-%m-%d")
        print(f"\n  [{day_str}]")
        t_day = time.time()
        r = run_single_day(raw_data, day_str)
        if r:
            r["duration"] = round(time.time() - t_day, 1)
            results.append(r)

    # 汇总
    if not results:
        print("\n❌ 无有效结果")
        return

    print("\n" + "=" * 70)
    print("  结果对比")
    print("=" * 70)
    print(f"\n{'日期':<12} {'算子版 SMAPE':<15} {'本地 SMAPE':<15} {'差异':<10} {'耗时'}")
    print("-" * 65)
    total_smape = 0
    for r in results:
        d = r["date"]
        op_smape = r["smape"]
        local_smape = LOCAL_RESULTS.get(d, 0)
        diff = op_smape - local_smape
        total_smape += op_smape
        print(f"{d:<12} {op_smape:<15.2f} {local_smape:<15.2f} {diff:+.2f}%     {r['duration']}s")

    avg_smape = total_smape / len(results)
    print("-" * 65)
    print(f"{'平均':<12} {avg_smape:<15.2f} {LOCAL_AVG_SMAPE:<15.2f} {avg_smape - LOCAL_AVG_SMAPE:+.2f}%")
    print(f"\n总耗时: {time.time() - t0:.0f}s")

    # 判定
    diff_abs = abs(avg_smape - LOCAL_AVG_SMAPE)
    if diff_abs < 1.0:
        print(f"\n✅ 对齐成功！差异 {diff_abs:.2f}% < 1.0%")
    elif diff_abs < 2.0:
        print(f"\n⚠️ 基本对齐，差异 {diff_abs:.2f}%（在可接受范围内，主要来自 BO 随机性）")
    else:
        print(f"\n❌ 差异较大 {diff_abs:.2f}%，需要排查")


if __name__ == "__main__":
    main()
