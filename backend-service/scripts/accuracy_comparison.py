# @AI_GENERATED
"""
精度对比验证：本地代码 vs 平台通用算子

两边使用相同的数据和参数，对比训练结果的 SMAPE/RMSE/MAE。
"""
import sys
import os
import time
import numpy as np
import pandas as pd

# Setup paths
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, PROJECT_ROOT)

CSV_PATH = os.path.join(PROJECT_ROOT, "datasets", "load_true_weihai_260415.csv")

print("=" * 70)
print("精度对比验证：本地代码 vs 平台通用算子")
print("=" * 70)
print(f"数据文件: {CSV_PATH}")
print(f"存在: {os.path.exists(CSV_PATH)}")
print()


# ============================================================
# Part 1: 平台通用算子流水线
# ============================================================
def run_platform_pipeline():
    """使用平台通用算子执行完整训练流水线"""
    print("=" * 50)
    print("【平台通用算子】开始执行...")
    print("=" * 50)

    from services.operator_execution import OperatorRouter
    BACKENDS_DIR = os.path.join(BACKEND_DIR, "services", "operator_backends")

    router = OperatorRouter()
    router.auto_discover(BACKENDS_DIR)

    t0 = time.time()

    # Step 1: load_csv
    r = router.execute("load_csv", {
        "file_path": CSV_PATH,
        "timestamp_column": "record_time",
        "delimiter": ",",
        "parent_field": "parent_id",
        "child_field": "child_id",
        "parent_id": "park_01",
        "child_id": "yARGkDuq",
    }, {})
    df = r["data"]
    print(f"  load_csv: {len(df)} rows, cols={list(df.columns)}")

    # Step 2: resample_timeseries
    r = router.execute("resample_timeseries", {
        "frequency": "15min", "method": "mean",
        "time_field": "record_time", "load_field": "value",
    }, {"data": df})
    df = r["data"]
    print(f"  resample: {len(df)} rows")

    # Step 3: detect_outliers
    r = router.execute("detect_outliers", {
        "method": "zscore", "threshold": 6.0,
        "load_field": "value", "window_size": 96,
    }, {"data": df})
    df = r["data"]
    print(f"  outliers: {len(r.get('outlier_indices', []))} detected")

    # Step 4: handle_missing
    r = router.execute("handle_missing", {
        "method": "linear",
        "time_field": "record_time", "load_field": "value",
    }, {"data": df})
    df = r["data"]
    print(f"  missing: NaN count={df.isna().sum().sum()}")

    # Step 5: extract_time_features
    r = router.execute("extract_time_features", {
        "features": ["hour", "dayofweek", "month", "day", "quarter"],
        "time_field": "record_time",
    }, {"data": df})
    df = r["data"]

    # Step 6: holiday_features
    r = router.execute("holiday_features", {"time_field": "record_time"}, {"data": df})
    df = r["data"]

    # Step 7: workday_features
    r = router.execute("workday_features", {"time_field": "record_time"}, {"data": df})
    df = r["data"]

    # Step 8: rolling_statistics
    r = router.execute("rolling_statistics", {
        "target_column": "value",
        "window_sizes": [24, 48, 96, 168],
        "statistics": ["mean", "std"],
    }, {"data": df})
    df = r["data"]

    # Step 9: create_lag_features
    r = router.execute("create_lag_features", {
        "lags": [1, 24, 168],
        "target_column": "value",
    }, {"data": df})
    df = r["data"]
    print(f"  features: {len(df)} rows, {len(df.columns)} cols")

    # Step 10: sliding_window
    r = router.execute("sliding_window", {
        "window_size": 96, "step": 1,
        "target_column": "value",
    }, {"data": df})
    df = r["data"]
    print(f"  sliding_window: {len(df)} rows")

    # Step 11: train_test_split_ts
    r = router.execute("train_test_split_ts", {
        "train_ratio": 0.8,
        "target_column": "value",
        "time_field": "record_time",
    }, {"data": df})
    print(f"  split: train={len(r['train_target'])}, test={len(r['test_target'])}")

    # Step 12: multi_step_forecast
    r = router.execute("multi_step_forecast", {
        "forecast_steps": 96,
        "strategy": "recursive",
        "step_size": 1,
    }, r)

    # Step 13: auto_tune_xgboost (贝叶斯优化，和本地一样的参数)
    print("  auto_tune_xgboost: 开始贝叶斯优化 (30轮, 5折CV)...")
    r_tune = router.execute("auto_tune_xgboost", {
        "n_trials": 30,
        "cv_folds": 5,
        "metric": "rmse",
    }, r)
    print(f"  auto_tune: best_params={r_tune.get('best_params', {})}")

    # Merge tune result back
    r.update(r_tune)

    # Step 14: xgboost_forecast (使用调优后的模型)
    r_xgb = router.execute("xgboost_forecast", {
        "n_estimators": 200,
        "mode": "train",
        "auto_tune": False,  # 已经有上游调优的模型
        "sample_weight_decay": 0.99,
    }, r)
    print(f"  xgboost: predictions={len(r_xgb.get('y_pred', []))}")

    # Step 15: smape_score
    r_smape = router.execute("smape_score", {}, {
        "y_true": r_xgb["y_true"],
        "y_pred": r_xgb["y_pred"],
    })

    # Step 16: mse_rmse_mae
    r_metrics = router.execute("mse_rmse_mae", {}, {
        "y_true": r_xgb["y_true"],
        "y_pred": r_xgb["y_pred"],
    })

    elapsed = time.time() - t0
    print(f"\n【平台通用算子】完成，耗时 {elapsed:.1f}s")
    print(f"  SMAPE: {r_smape['score']:.4f}%")
    print(f"  RMSE:  {r_metrics['rmse']:.4f}")
    print(f"  MAE:   {r_metrics['mae']:.4f}")
    print(f"  MSE:   {r_metrics['mse']:.4f}")

    return {
        "smape": r_smape["score"],
        "rmse": r_metrics["rmse"],
        "mae": r_metrics["mae"],
        "mse": r_metrics["mse"],
        "time": elapsed,
        "train_size": len(r["train_target"]),
        "test_size": len(r_xgb["y_true"]),
    }


# ============================================================
# Part 2: 本地代码流水线
# ============================================================
def run_local_pipeline():
    """使用本地代码的简化版本执行训练（避免 pandas 版本兼容性问题）"""
    print("\n" + "=" * 50)
    print("【本地代码（简化版）】开始执行...")
    print("=" * 50)

    from models_pkg.trainer import xgb_model_trainer
    from forecast_utils import smape
    import xgboost as xgb

    t0 = time.time()

    # 直接读取 CSV 并做和平台一样的预处理
    df = pd.read_csv(CSV_PATH)
    df = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")]
    df = df[["record_time", "value"]].copy()
    df["record_time"] = pd.to_datetime(df["record_time"])
    df = df.sort_values("record_time").drop_duplicates(subset=["record_time"], keep="first").reset_index(drop=True)
    print(f"  data: {len(df)} rows")

    # 重采样到 15min
    df.set_index("record_time", inplace=True)
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="15min")
    df = df.reindex(full_idx)
    df.index.name = "record_time"
    df.reset_index(inplace=True)
    print(f"  resample: {len(df)} rows")

    # 异常检测（rolling MAD，和平台一样）
    x = pd.to_numeric(df["value"], errors="coerce")
    med = x.rolling(window=96, min_periods=10).median().shift(1)
    mad = (x - med).abs().rolling(window=96, min_periods=10).median().shift(1)
    scale = 1.4826 * mad
    denom = scale.replace(0, np.nan)
    score = (x - med).abs() / denom
    mask = score > 6.0
    n_outliers = int(mask.sum(skipna=True))
    df.loc[mask, "value"] = np.nan
    print(f"  outliers: {n_outliers}")

    # 缺失值填充（线性插值，和平台一样）
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df.set_index("record_time", inplace=True)
    df["value"] = df["value"].interpolate(method="time", limit_direction="forward")
    df["value"] = df["value"].ffill().bfill()
    df.reset_index(inplace=True)
    print(f"  fill: NaN={df['value'].isna().sum()}")

    # 特征工程（和平台一样）
    df["hour"] = df["record_time"].dt.hour
    df["dayofweek"] = df["record_time"].dt.dayofweek
    df["month"] = df["record_time"].dt.month
    df["day"] = df["record_time"].dt.day
    df["quarter"] = df["record_time"].dt.quarter

    try:
        from chinese_calendar import is_workday as cc_is_workday
        df["is_holiday"] = df["record_time"].apply(lambda x: 0 if cc_is_workday(x.date()) else 1)
        df["is_workday"] = df["record_time"].apply(lambda x: 1 if cc_is_workday(x.date()) else 0)
    except ImportError:
        df["is_holiday"] = (df["record_time"].dt.dayofweek >= 5).astype(int)
        df["is_workday"] = (df["record_time"].dt.dayofweek < 5).astype(int)

    # 滚动统计
    shifted = df["value"].shift(1)
    for w in [24, 48, 96, 168]:
        rolling = shifted.rolling(window=w, min_periods=1)
        df[f"value_rolling_mean_{w}"] = rolling.mean()
        df[f"value_rolling_std_{w}"] = rolling.std()

    # 滞后特征
    for lag in [1, 24, 168]:
        df[f"value_lag_{lag}"] = df["value"].shift(lag)

    print(f"  features: {len(df)} rows, {len(df.columns)} cols")

    # 滑动窗口
    df = df.iloc[95:].reset_index(drop=True)  # 去掉前 95 行不完整窗口
    print(f"  window: {len(df)} rows")

    # 切分
    split_idx = int(len(df) * 0.8)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    target_col = "value"
    feature_cols = [c for c in df.columns if c not in ["record_time", target_col]]

    x_train = train_df[feature_cols]
    y_train = train_df[target_col]
    x_test = test_df[feature_cols]
    y_test = test_df[target_col].values

    print(f"  split: train={len(x_train)}, test={len(x_test)}")

    # 使用本地的 xgb_model_trainer（贝叶斯优化）
    print("  xgb_model_trainer: 开始贝叶斯优化 (5折CV)...")
    forecast_length = len(y_test)
    trained_model, feature_list = xgb_model_trainer(x_train, y_train, forecast_length, nfolds=5, set_weight_ac=0.99)

    # 预测
    dtest = xgb.DMatrix(x_test[feature_list], missing=0)
    y_pred = trained_model.predict(dtest).flatten()

    # 评估
    smape_val = smape(y_test, y_pred)
    mse_val = float(np.mean((y_test - y_pred) ** 2))
    rmse_val = float(np.sqrt(mse_val))
    mae_val = float(np.mean(np.abs(y_test - y_pred)))

    elapsed = time.time() - t0
    print(f"\n【本地代码（简化版）】完成，耗时 {elapsed:.1f}s")
    print(f"  SMAPE: {smape_val:.4f}%")
    print(f"  RMSE:  {rmse_val:.4f}")
    print(f"  MAE:   {mae_val:.4f}")
    print(f"  MSE:   {mse_val:.4f}")

    return {
        "smape": smape_val,
        "rmse": rmse_val,
        "mae": mae_val,
        "mse": mse_val,
        "time": elapsed,
        "train_size": len(x_train),
        "test_size": len(y_test),
    }


# ============================================================
# Part 3: 对比
# ============================================================
if __name__ == "__main__":
    print("\n>>> 运行平台通用算子流水线...")
    platform_result = run_platform_pipeline()

    print("\n>>> 运行本地代码流水线...")
    local_result = run_local_pipeline()

    if platform_result and local_result:
        print("\n" + "=" * 70)
        print("精度对比结果")
        print("=" * 70)
        print(f"{'指标':<10} {'平台算子':>15} {'本地代码':>15} {'差异':>15}")
        print("-" * 55)
        for key in ["smape", "rmse", "mae", "mse"]:
            p = platform_result[key]
            l = local_result[key]
            diff = p - l
            pct = (diff / l * 100) if l != 0 else 0
            print(f"{key.upper():<10} {p:>15.4f} {l:>15.4f} {diff:>+15.4f} ({pct:+.1f}%)")
        print("-" * 55)
        print(f"{'训练集':>10} {platform_result['train_size']:>15} {local_result['train_size']:>15}")
        print(f"{'测试集':>10} {platform_result['test_size']:>15} {local_result['test_size']:>15}")
        print(f"{'耗时(s)':>10} {platform_result['time']:>15.1f} {local_result['time']:>15.1f}")
        print()
        print("注意：由于贝叶斯优化的随机性，两边的结果会有小幅差异，这是正常的。")
        print("关键是量级一致（SMAPE 在同一个百分比范围内，RMSE/MAE 在同一个数量级）。")
    else:
        print("\n某一方执行失败，无法对比。")
# @AI_GENERATED: end
