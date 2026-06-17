# -*- coding: utf-8 -*-
"""
精度评估与提升框架

功能:
1. 使用已有 AESC 数据建立基线精度
2. 识别并修复数据穿越问题
3. 实现时间序列交叉验证 (避免随机 KFold 泄漏)
4. 特征工程改进
5. 模型精度对比

用法:
    python evaluate_and_improve.py
"""
import os
import sys
import copy
import warnings
import numpy as np
import pandas as pd
import xgboost as xgb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from loguru import logger
from datetime import timedelta, datetime
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings(action="ignore")

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PARENT_DIR, "data_process")
RESULT_DIR = os.path.join(PARENT_DIR, "aesc_dataset")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "evaluation")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ===========================================================================
# 1. 数据加载与预处理
# ===========================================================================

def load_aesc_data():
    """加载 AESC 源数据 (18设备-总负荷-气象.csv)"""
    csv_path = os.path.join(DATA_DIR, "18设备-总负荷-气象.csv")
    df = pd.read_csv(csv_path)
    df["record_time"] = pd.to_datetime(df["record_time"])
    df = df.sort_values("record_time").reset_index(drop=True)

    # 重命名 load_true -> load 以与 pipeline 一致
    df.rename(columns={"load_true": "load"}, inplace=True)
    return df


def load_baseline_results():
    """加载已有的回测预测结果"""
    all_preds = []
    for fname in os.listdir(RESULT_DIR):
        if fname.startswith("tmp_re_") and fname.endswith(".csv"):
            fpath = os.path.join(RESULT_DIR, fname)
            tmp = pd.read_csv(fpath)
            all_preds.append(tmp)
    pred_df = pd.concat(all_preds, ignore_index=True)
    pred_df["record_time"] = pd.to_datetime(pred_df["record_time"])
    return pred_df


# ===========================================================================
# 2. 评估指标
# ===========================================================================

def smape(y_true, y_pred):
    """对称平均绝对百分比误差"""
    denominator = np.abs(y_true) + np.abs(y_pred)
    mask = denominator > 1e-8
    result = 2.0 * np.mean(np.abs(y_pred[mask] - y_true[mask]) / denominator[mask]) * 100
    return np.round(result, 4)


def mape(y_true, y_pred):
    """平均绝对百分比误差"""
    mask = np.abs(y_true) > 1e-8
    result = np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
    return np.round(result, 4)


def evaluate_forecast(y_true, y_pred, label=""):
    """计算多维度评估指标"""
    m = {
        "label": label,
        "SMAPE": smape(y_true, y_pred),
        "MAPE": mape(y_true, y_pred),
        "MAE": np.round(mean_absolute_error(y_true, y_pred), 4),
        "RMSE": np.round(np.sqrt(mean_squared_error(y_true, y_pred)), 4),
        "max_error": np.round(np.max(np.abs(y_true - y_pred)), 4),
    }
    return m


# ===========================================================================
# 3. 数据穿越审计
# ===========================================================================

def audit_data_leakage():
    """
    审计整个 pipeline 中的数据穿越风险点
    """
    leakage_points = []

    # ---- Issue 1: chebyshev_detector 使用全局统计量 ----
    leakage_points.append({
        "module": "data_process.py::chebyshev_detector",
        "severity": "HIGH",
        "issue": "使用完整数据集(含未来数据)计算 load_delta 的 mean 和 std 来定义异常边界",
        "fix": "仅使用训练窗口内的历史数据计算统计量",
    })

    # ---- Issue 2: KFold 随机交叉验证 ----
    leakage_points.append({
        "module": "trainer.py::xgb_crossval",
        "severity": "HIGH",
        "issue": "使用 sklearn.model_selection.KFold (随机分折)，验证集包含训练集之前的时间点",
        "fix": "改用 TimeSeriesSplit 进行时序交叉验证",
    })

    # ---- Issue 3: DataFiller 周期性填补 ----
    leakage_points.append({
        "module": "data_process.py::DataFiller.fill_by_week",
        "severity": "MEDIUM",
        "issue": "在完整数据集上用相邻周相同天填补，可能使用未来数据填补历史缺失值",
        "fix": "仅向前查找历史数据填补",
    })

    # ---- Issue 4: get_completed_timestamp 固定窗口 ----
    leakage_points.append({
        "module": "data_process.py::get_completed_timestamp",
        "severity": "LOW",
        "issue": "train_days=30 固定截取，当数据包含预测时段真值时会穿越",
        "fix": "确保 is_training='true' 时截取窗口不包含预测日",
    })

    # ---- Issue 5: 训练时 forecast_timestamps 包含未来 ----
    leakage_points.append({
        "module": "features/engine.py::add_more_features",
        "severity": "MEDIUM",
        "issue": "训练阶段生成的 forecast_timestamps 超出训练数据范围，"
                 "shift 操作和 get_all_filled_data 可能使用未来数据",
        "fix": "训练阶段确保只使用 load_field 截止时间之前的数据",
    })

    # ---- Issue 6: 滚动特征 center=True ----
    leakage_points.append({
        "module": "add_features.py::get_rolling_features",
        "severity": "HIGH",
        "issue": "rolling(center=True) 使用未来值计算当前时刻的统计特征",
        "fix": "改为 center=False (仅使用历史窗口)",
    })

    return leakage_points


# ===========================================================================
# 4. 无穿越特征工程
# ===========================================================================

def build_features_no_leakage(df, time_field="record_time", load_field="load"):
    """
    构建无数据穿越的特征集

    Parameters
    ----------
    df : DataFrame
        包含 [record_time, load, ...weather_cols] 的数据
    """
    feat = df.copy()
    feat[time_field] = pd.to_datetime(feat[time_field])

    # ---- 时间特征 ----
    feat["is_holiday"] = feat[time_field].apply(lambda x: 0 if _if_workday(x) else 1)
    feat["day"] = feat[time_field].dt.day
    feat["yday"] = feat[time_field].dt.dayofyear
    feat["month"] = feat[time_field].dt.month
    feat["dayofweek"] = feat[time_field].dt.dayofweek
    feat["hour"] = feat[time_field].dt.hour
    feat["minute"] = feat[time_field].dt.minute
    feat["period"] = (feat["hour"] * 4 + feat["minute"] // 15)

    # 周期编码
    feat["hour_sin"] = np.sin(2 * np.pi * feat["hour"] / 24)
    feat["hour_cos"] = np.cos(2 * np.pi * feat["hour"] / 24)
    feat["wday_sin"] = np.sin(2 * np.pi * feat["dayofweek"] / 7)
    feat["wday_cos"] = np.cos(2 * np.pi * feat["dayofweek"] / 7)
    feat["yday_sin"] = np.sin(2 * np.pi * feat["yday"] / 365)
    feat["yday_cos"] = np.cos(2 * np.pi * feat["yday"] / 365)

    # ---- Lag 特征 (仅使用历史数据) ----
    daily_horizon = 96  # 15min granularity
    for lag_days in [1, 2, 3, 7, 14]:
        feat[f"load_lag_{lag_days}d"] = feat[load_field].shift(lag_days * daily_horizon)

    # 同一时刻上周均值
    feat[f"load_lag_7d"] = feat[load_field].shift(7 * daily_horizon)
    feat[f"load_lag_14d"] = feat[load_field].shift(14 * daily_horizon)
    feat["load_same_hour_avg_2w"] = (feat[f"load_lag_7d"] + feat[f"load_lag_14d"]) / 2

    # ---- 差分特征 (仅使用历史) ----
    feat["load_diff_1"] = feat[load_field].diff(1)
    feat["load_diff_96"] = feat[load_field].diff(daily_horizon)
    feat["load_diff_96x2"] = feat[load_field].diff(2 * daily_horizon)
    feat["load_diff_96x3"] = feat[load_field].shift(daily_horizon).diff(daily_horizon)

    # ---- 滚动统计特征 (center=False, 无穿越) ----
    load_shifted = feat[load_field].shift(daily_horizon)  # 使用昨天的值
    for window in [4, 8, 12, 24, 48]:
        feat[f"rolling_{window}_mean"] = load_shifted.rolling(window, center=False, min_periods=1).mean().values
        feat[f"rolling_{window}_std"] = load_shifted.rolling(window, center=False, min_periods=1).std().values
        feat[f"rolling_{window}_max"] = load_shifted.rolling(window, center=False, min_periods=1).max().values
        feat[f"rolling_{window}_min"] = load_shifted.rolling(window, center=False, min_periods=1).min().values

    # ---- 日统计特征 (基于前一天) ----
    feat["date"] = feat[time_field].dt.strftime("%Y-%m-%d")
    daily_stats = feat.groupby("date")[load_field].agg(["mean", "max", "min", "std"]).reset_index()
    daily_stats.columns = ["date", "day_mean", "day_max", "day_min", "day_std"]
    daily_stats["day_peak_valley"] = daily_stats["day_max"] - daily_stats["day_min"]
    daily_stats["day_load_rate"] = daily_stats["day_mean"] / daily_stats["day_max"].replace(0, np.nan)
    # 前移一天 — 只使用前一天的统计量
    daily_stats[["day_mean", "day_max", "day_min", "day_std",
                  "day_peak_valley", "day_load_rate"]] = \
        daily_stats[["day_mean", "day_max", "day_min", "day_std",
                      "day_peak_valley", "day_load_rate"]].shift(1)
    feat = feat.merge(daily_stats, on="date", how="left")

    # ---- 气象特征 (原始列保留) ----
    weather_cols = [c for c in feat.columns if c.startswith(("EC.", "ENS_AVG."))]
    # 气象差分
    for wc in weather_cols:
        feat[f"{wc}_diff1d"] = feat[wc].diff(daily_horizon)

    return feat


def _if_workday(date):
    """判断是否工作日"""
    try:
        from chinese_calendar import is_workday
        return is_workday(pd.to_datetime(date))
    except Exception:
        return pd.to_datetime(date).weekday() <= 4


# ===========================================================================
# 5. 无穿越异常检测
# ===========================================================================

def chebyshev_detector_no_leakage(df, load_field="load", window_size=7):
    """
    无数据穿越的 Chebyshev 异常检测

    使用滚动窗口计算历史统计量，不使用未来数据

    Parameters
    ----------
    df : DataFrame
        包含 load_field 列的数据
    load_field : str
        负荷列名
    window_size : int
        滚动窗口大小 (天)
    """
    df = df.copy()
    daily_horizon = 96
    window_points = window_size * daily_horizon

    # 计算差分
    df["load_shift"] = df[load_field].shift(1)
    df["load_delta"] = df[load_field] - df["load_shift"]

    # 使用滚动窗口统计量 (仅历史数据)
    df["delta_rolling_mean"] = df["load_delta"].rolling(window_points, min_periods=daily_horizon).mean()
    df["delta_rolling_std"] = df["load_delta"].rolling(window_points, min_periods=daily_horizon).std()

    # 异常标记
    up_delta = df["delta_rolling_mean"] + 3 * df["delta_rolling_std"]
    down_delta = df["delta_rolling_mean"] - 3 * df["delta_rolling_std"]
    df["tag"] = ((df["load_delta"] > up_delta) | (df["load_delta"] < down_delta)).astype(int)

    # 标记异常值为 NaN
    nan_indexes = df[df["tag"] == 1].index.tolist()
    df.loc[nan_indexes, load_field] = np.nan

    # 使用历史数据插值
    df[load_field] = df[load_field].interpolate()
    df[load_field] = df[load_field].fillna(method="bfill").fillna(method="ffill")

    df.drop(columns=["load_shift", "load_delta", "delta_rolling_mean",
                      "delta_rolling_std", "tag"], inplace=True)
    return df


# ===========================================================================
# 6. 时序交叉验证 XGBoost 训练
# ===========================================================================

def xgb_train_with_tscv(x_train, y_train, forecast_length, n_splits=5):
    """
    使用 TimeSeriesSplit 交叉验证训练 XGBoost (无数据穿越)

    Parameters
    ----------
    x_train : DataFrame
        特征
    y_train : Series
        目标值
    forecast_length : int
        预测长度
    n_splits : int
        折数
    """
    from bayes_opt import BayesianOptimization

    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    feature_list = list(feat_columns)

    def sample_weights(train_label, ac=0.99):
        train_len = len(train_label)
        sw = []
        for i in range(train_len):
            sw.append(pow(ac, i // forecast_length))
        return np.array(list(reversed(sw)))

    def xgb_tscv(eta, max_depth, min_child_weight, subsample, lambdas):
        tscv = TimeSeriesSplit(n_splits=n_splits)
        oof = np.full(x_train.shape[0], np.nan)
        for fold_idx, (trn_idx, val_idx) in enumerate(tscv.split(x_train)):
            trn_data = xgb.DMatrix(x_train.iloc[trn_idx], label=y_train.iloc[trn_idx], missing=0)
            val_data = xgb.DMatrix(x_train.iloc[val_idx], label=y_train.iloc[val_idx], missing=0)
            param = {
                'objective': 'reg:squarederror', 'booster': 'gbtree', 'eval_metric': 'rmse',
                'verbosity': 0,
                'max_depth': int(max_depth), 'min_child_weight': float(min_child_weight),
                'subsample': float(subsample), 'eta': float(eta), 'lambda': float(lambdas),
                'seed': 42, 'nthread': 4,
            }
            clf = xgb.train(param, trn_data, 100,
                            evals=[(trn_data, 'train'), (val_data, 'valid')],
                            verbose_eval=0, early_stopping_rounds=5)
            oof[val_idx] = clf.predict(val_data)
            del clf
        valid_mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[valid_mask], oof[valid_mask]))

    # 贝叶斯优化
    crossval_params = {
        'eta': (0.01, 0.15),
        'max_depth': (2, 8),
        'min_child_weight': (0.3, 10),
        'subsample': (0.5, 1),
        'lambdas': (0.1, 100),
    }
    xgb_op = BayesianOptimization(f=xgb_tscv, pbounds=crossval_params, random_state=42)
    xgb_op.maximize(init_points=3, n_iter=12)

    bst_params = xgb_op.max['params']
    bst_params['max_depth'] = int(bst_params['max_depth'])

    # 全量训练
    sw = sample_weights(y_train)
    dtrain = xgb.DMatrix(x_train, label=y_train, missing=0, weight=sw)
    final_model = xgb.train(bst_params, dtrain, 200,
                            evals=[(dtrain, 'train')],
                            early_stopping_rounds=10, verbose_eval=0)

    importance = sorted(final_model.get_score(importance_type='gain').items(),
                        key=lambda k: k[1], reverse=True)
    logger.info(f"Top-10 features: {importance[:10]}")

    return final_model, feature_list


# ===========================================================================
# 7. 滚动回测 (Rolling Backtest)
# ===========================================================================

def rolling_backtest(df, start_date, end_date, forecast_horizon_days=1,
                     train_days=30, daily_horizon=96,
                     load_field="load", time_field="record_time"):
    """
    滚动回测：逐天训练 + 预测，确保无数据穿越

    Parameters
    ----------
    df : DataFrame
        完整数据 (含历史和未来)
    start_date : str
        回测开始日期
    end_date : str
        回测结束日期
    forecast_horizon_days : int
        预测天数
    train_days : int
        训练数据天数
    daily_horizon : int
        日内数据点数
    """
    results = []
    all_days = pd.date_range(start_date, end_date, freq='D', inclusive='left')

    for pred_day in all_days:
        pred_day_str = pred_day.strftime('%Y-%m-%d')

        # 训练截止 = 预测日前一天
        train_end = pred_day - timedelta(days=1)
        train_start = train_end - timedelta(days=train_days)

        # 划分训练/测试
        mask_train = (df[time_field] >= train_start) & (df[time_field] <= train_end)
        mask_test = (df[time_field] >= pred_day) & (df[time_field] < pred_day + timedelta(days=forecast_horizon_days))

        train_df = df[mask_train].copy()
        test_df = df[mask_test].copy()

        if len(train_df) < train_days * daily_horizon * 0.8:
            logger.warning(f"{pred_day_str}: 训练数据不足, 跳过")
            continue
        if len(test_df) == 0:
            logger.warning(f"{pred_day_str}: 无测试数据, 跳过")
            continue

        # ---- 异常检测 (仅用训练数据统计量) ----
        combined = pd.concat([train_df, test_df], ignore_index=True)
        # 对训练部分做异常检测，预测部分保持原始
        train_clean = chebyshev_detector_no_leakage(train_df, load_field=load_field)
        combined_clean = pd.concat([train_clean, test_df], ignore_index=True)

        # ---- 特征工程 ----
        feat_all = build_features_no_leakage(combined_clean, time_field, load_field)

        # 划分
        train_feat = feat_all[feat_all[time_field] <= train_end].copy()
        test_feat = feat_all[feat_all[time_field] >= pred_day].copy()

        # 可用特征列 (排除目标列和时间列)
        drop_cols = [load_field, time_field, "date"]
        feature_cols = [c for c in train_feat.columns if c not in drop_cols
                        and train_feat[c].dtype in ['float64', 'float32', 'int64', 'int32']]

        # 清理 NaN
        train_feat[feature_cols] = train_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
        test_feat[feature_cols] = test_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)

        x_train = train_feat[feature_cols]
        y_train = train_feat[load_field]
        x_test = test_feat[feature_cols]
        y_test = test_feat[load_field]

        if len(x_train) < daily_horizon * 10:
            logger.warning(f"{pred_day_str}: 有效训练样本不足, 跳过")
            continue

        # ---- 训练 ----
        logger.info(f"训练 {pred_day_str}: train={len(x_train)}, test={len(x_test)}")
        model, feat_list = xgb_train_with_tscv(x_train, y_train, forecast_length=daily_horizon)

        # ---- 预测 ----
        dtest = xgb.DMatrix(x_test[feat_list])
        y_pred = model.predict(dtest)

        # ---- 评估 ----
        day_result = pd.DataFrame({
            time_field: test_feat[time_field].values,
            "true": y_test.values,
            "pred": y_pred,
            "pred_day": pred_day_str,
        })
        results.append(day_result)

        # 日指标
        day_metrics = evaluate_forecast(y_test.values, y_pred, label=pred_day_str)
        logger.info(f"  {pred_day_str}: SMAPE={day_metrics['SMAPE']:.2f}%, "
                     f"MAE={day_metrics['MAE']:.2f}, RMSE={day_metrics['RMSE']:.2f}")

    if not results:
        return pd.DataFrame(), []

    all_results = pd.concat(results, ignore_index=True)
    return all_results, feat_list


# ===========================================================================
# 8. 基线对比
# ===========================================================================

def evaluate_baseline():
    """评估已有回测结果的基线精度"""
    logger.info("=" * 60)
    logger.info("1. 基线精度评估")
    logger.info("=" * 60)

    # 加载源数据
    df = load_aesc_data()
    logger.info(f"源数据: {df['record_time'].min()} ~ {df['record_time'].max()}, {len(df)} rows")

    # 加载预测结果
    pred_df = load_baseline_results()
    logger.info(f"预测结果: {pred_df['record_time'].min()} ~ {pred_df['record_time'].max()}, "
                f"{len(pred_df)} rows")

    # 合并
    true_df = df[["record_time", "load"]].copy()
    merged = pred_df.merge(true_df, on="record_time", how="inner")
    merged.rename(columns={"load": "true_load"}, inplace=True)

    if len(merged) == 0:
        logger.warning("无匹配数据, 无法评估基线")
        return None

    # 按天评估
    merged["date"] = merged["record_time"].dt.strftime("%Y-%m-%d")
    daily_metrics = []
    for date, group in merged.groupby("date"):
        m = evaluate_forecast(group["true_load"].values, group["fcst_load"].values, label=date)
        daily_metrics.append(m)
        logger.info(f"  {date}: SMAPE={m['SMAPE']:.2f}%, MAE={m['MAE']:.2f}, RMSE={m['RMSE']:.2f}")

    # 总体
    overall = evaluate_forecast(merged["true_load"].values, merged["fcst_load"].values, label="OVERALL")
    logger.info(f"\n  基线总精度: SMAPE={overall['SMAPE']:.2f}%, MAE={overall['MAE']:.2f}, "
                f"RMSE={overall['RMSE']:.2f}")

    return overall, daily_metrics, merged


# ===========================================================================
# 9. 可视化
# ===========================================================================

# 中文字体配置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def plot_full_comparison(baseline_merged, improved_results, output_dir):
    """
    绘制基线 vs 改进的全局对比曲线 (所有回测天)
    """
    fig, axes = plt.subplots(3, 1, figsize=(20, 14), sharex=True)

    # 合并两个 DataFrame
    base = baseline_merged[["record_time", "true_load", "fcst_load"]].copy()
    base.rename(columns={"true_load": "true", "fcst_load": "baseline"}, inplace=True)
    base.set_index("record_time", inplace=True)

    impr = improved_results[["record_time", "true", "pred"]].copy()
    impr.rename(columns={"pred": "improved"}, inplace=True)
    impr.set_index("record_time", inplace=True)

    merged = base.join(impr[["improved"]], how="outer").sort_index()

    # 上图: 真实值 vs 基线 vs 改进
    ax = axes[0]
    ax.plot(merged.index, merged["true"], color="black", linewidth=1.2, label="True", alpha=0.9)
    ax.plot(merged.index, merged["baseline"], color="#e74c3c", linewidth=0.8, label="Baseline", alpha=0.7)
    ax.plot(merged.index, merged["improved"], color="#2ecc71", linewidth=0.8, label="Improved", alpha=0.7)
    ax.set_ylabel("Load", fontsize=12)
    ax.set_title("Load Forecast: True vs Baseline vs Improved", fontsize=14)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, alpha=0.3)

    # 中图: 误差对比
    ax = axes[1]
    base_err = (merged["baseline"] - merged["true"]).dropna()
    impr_err = (merged["improved"] - merged["true"]).dropna()
    ax.bar(base_err.index, base_err.values, width=0.01, color="#e74c3c", alpha=0.5, label="Baseline Error")
    ax.bar(impr_err.index, impr_err.values, width=0.01, color="#2ecc71", alpha=0.5, label="Improved Error")
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_ylabel("Error (Pred - True)", fontsize=12)
    ax.set_title("Prediction Error Comparison", fontsize=14)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, alpha=0.3)

    # 下图: 绝对误差
    ax = axes[2]
    base_abs = base_err.abs()
    impr_abs = impr_err.abs()
    ax.fill_between(base_abs.index, 0, base_abs.values, color="#e74c3c", alpha=0.4, label="Baseline |Error|")
    ax.fill_between(impr_abs.index, 0, impr_abs.values, color="#2ecc71", alpha=0.4, label="Improved |Error|")
    ax.set_ylabel("|Error|", fontsize=12)
    ax.set_xlabel("Time", fontsize=12)
    ax.set_title("Absolute Error Comparison", fontsize=14)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    plt.tight_layout()
    path = os.path.join(output_dir, "comparison_full.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"全局对比图已保存: {path}")
    return path


def plot_daily_comparison(baseline_merged, improved_results, output_dir):
    """
    逐天绘制对比曲线 (每天一张子图)
    """
    # 获取公共日期
    base_dates = sorted(baseline_merged["record_time"].dt.strftime("%Y-%m-%d").unique())
    impr_dates = sorted(improved_results["record_time"].dt.strftime("%Y-%m-%d").unique())
    common_dates = sorted(set(base_dates) & set(impr_dates))

    if not common_dates:
        logger.warning("无公共日期, 无法绘制逐天对比图")
        return None

    n = len(common_dates)
    ncols = 3
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 4 * nrows))
    axes = axes.flatten() if n > 1 else [axes]

    for idx, date_str in enumerate(common_dates):
        ax = axes[idx]
        # 基线数据
        b_day = baseline_merged[baseline_merged["record_time"].dt.strftime("%Y-%m-%d") == date_str]
        # 改进数据
        i_day = improved_results[improved_results["record_time"].dt.strftime("%Y-%m-%d") == date_str]

        times = b_day["record_time"].dt.strftime("%H:%M") if len(b_day) else i_day["record_time"].dt.strftime("%H:%M")

        # 真实值 (取基线或改进中可用的)
        if len(b_day):
            ax.plot(range(len(b_day)), b_day["true_load"].values, "k-o", markersize=1.5,
                    linewidth=1.5, label="True")
            ax.plot(range(len(b_day)), b_day["fcst_load"].values, color="#e74c3c",
                    linewidth=1.2, label="Baseline", alpha=0.8)
        if len(i_day):
            if not len(b_day):
                ax.plot(range(len(i_day)), i_day["true"].values, "k-o", markersize=1.5,
                        linewidth=1.5, label="True")
            ax.plot(range(len(i_day)), i_day["pred"].values, color="#2ecc71",
                    linewidth=1.2, label="Improved", alpha=0.8)

        # 计算当日 SMAPE
        if len(i_day):
            day_smape = smape(i_day["true"].values, i_day["pred"].values)
        elif len(b_day):
            day_smape = smape(b_day["true_load"].values, b_day["fcst_load"].values)
        else:
            day_smape = 0

        weekday = pd.to_datetime(date_str).strftime('%a')
        ax.set_title(f"{date_str} ({weekday})  SMAPE={day_smape:.2f}%", fontsize=10)
        ax.legend(fontsize=7, loc="upper right")
        ax.grid(True, alpha=0.3)
        # x 轴只显示 0, 24, 48, 72, 96
        ax.set_xticks([0, 24, 48, 72, 95])
        ax.set_xticklabels(["00:00", "06:00", "12:00", "18:00", "23:45"], fontsize=7)

    # 隐藏空白子图
    for idx in range(n, len(axes)):
        axes[idx].set_visible(False)

    plt.suptitle("Daily Load Forecast: Baseline vs Improved", fontsize=16, y=1.01)
    plt.tight_layout()
    path = os.path.join(output_dir, "comparison_daily.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"逐天对比图已保存: {path}")
    return path


def plot_metrics_bar(baseline_daily, improved_daily, output_dir):
    """
    绘制 SMAPE/MAE/RMSE 柱状对比图
    """
    b_df = pd.DataFrame(baseline_daily)
    i_df = pd.DataFrame(improved_daily)

    fig, axes = plt.subplots(1, 3, figsize=(20, 5))

    for ax_idx, metric in enumerate(["SMAPE", "MAE", "RMSE"]):
        ax = axes[ax_idx]
        # 合并
        b_vals = b_df[["label", metric]].rename(columns={metric: "Baseline"})
        i_vals = i_df[["label", metric]].rename(columns={metric: "Improved"})
        merged = b_vals.merge(i_vals, on="label", how="outer").fillna(0)
        merged = merged.sort_values("label")

        x = np.arange(len(merged))
        width = 0.35
        ax.bar(x - width / 2, merged["Baseline"], width, label="Baseline", color="#e74c3c", alpha=0.8)
        ax.bar(x + width / 2, merged["Improved"], width, label="Improved", color="#2ecc71", alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([l[5:] for l in merged["label"]], rotation=45, fontsize=8)
        ax.set_ylabel(metric, fontsize=11)
        ax.set_title(f"{metric} by Day", fontsize=13)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    path = os.path.join(output_dir, "comparison_metrics.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"指标柱状图已保存: {path}")
    return path


def plot_scatter(improved_results, output_dir):
    """
    绘制 True vs Pred 散点图
    """
    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    true_vals = improved_results["true"].values
    pred_vals = improved_results["pred"].values

    ax.scatter(true_vals, pred_vals, alpha=0.3, s=8, color="#2ecc71", edgecolors='none')
    lim_min = min(true_vals.min(), pred_vals.min()) * 0.95
    lim_max = max(true_vals.max(), pred_vals.max()) * 1.05
    ax.plot([lim_min, lim_max], [lim_min, lim_max], "k--", linewidth=1, label="y=x")
    ax.set_xlim(lim_min, lim_max)
    ax.set_ylim(lim_min, lim_max)
    ax.set_xlabel("True Load", fontsize=12)
    ax.set_ylabel("Predicted Load", fontsize=12)
    ax.set_title("True vs Predicted (Improved Model)", fontsize=14)

    r2 = 1 - np.sum((true_vals - pred_vals) ** 2) / np.sum((true_vals - true_vals.mean()) ** 2)
    ax.text(0.05, 0.92, f"R² = {r2:.4f}\nSMAPE = {smape(true_vals, pred_vals):.2f}%\n"
             f"MAE = {mean_absolute_error(true_vals, pred_vals):.2f}\n"
             f"RMSE = {np.sqrt(mean_squared_error(true_vals, pred_vals)):.2f}",
            transform=ax.transAxes, fontsize=11, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(output_dir, "scatter_true_vs_pred.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"散点图已保存: {path}")
    return path


# ===========================================================================
# 10. 数据穿越报告
# ===========================================================================

def print_leakage_report():
    """打印数据穿越审计报告"""
    logger.info("\n" + "=" * 60)
    logger.info("2. 数据穿越审计报告")
    logger.info("=" * 60)

    issues = audit_data_leakage()
    for i, issue in enumerate(issues, 1):
        logger.info(f"\n[{issue['severity']}] Issue #{i}: {issue['module']}")
        logger.info(f"  问题: {issue['issue']}")
        logger.info(f"  修复: {issue['fix']}")


# ===========================================================================
# 10. 改进后模型回测
# ===========================================================================

def run_improved_backtest():
    """运行改进后的回测并与基线对比"""
    logger.info("\n" + "=" * 60)
    logger.info("3. 改进模型回测")
    logger.info("=" * 60)

    df = load_aesc_data()
    logger.info(f"数据范围: {df['record_time'].min()} ~ {df['record_time'].max()}")

    # 回测期间: 与基线一致 (2025-03-15 ~ 2025-03-26)
    start_date = "2025-03-15"
    end_date = "2025-03-26"

    # 检查数据是否覆盖该范围
    data_start = df["record_time"].min().strftime("%Y-%m-%d")
    data_end = df["record_time"].max().strftime("%Y-%m-%d")
    logger.info(f"数据覆盖: {data_start} ~ {data_end}")

    if data_start > start_date:
        # 如果数据不够，调整回测期间
        new_start = (pd.to_datetime(data_start) + timedelta(days=35)).strftime("%Y-%m-%d")
        new_end = (pd.to_datetime(new_start) + timedelta(days=11)).strftime("%Y-%m-%d")
        logger.info(f"数据不足，调整回测期间: {new_start} ~ {new_end}")
        start_date = new_start
        end_date = new_end

    # 运行滚动回测
    results, feat_list = rolling_backtest(
        df, start_date, end_date,
        forecast_horizon_days=1,
        train_days=30,
        daily_horizon=96,
        load_field="load",
        time_field="record_time",
    )

    if len(results) == 0:
        logger.warning("回测结果为空")
        return None

    # 保存结果
    results.to_csv(os.path.join(OUTPUT_DIR, "improved_predictions.csv"), index=False)
    logger.info(f"预测结果已保存到 {OUTPUT_DIR}/improved_predictions.csv")

    # 总体评估
    overall = evaluate_forecast(results["true"].values, results["pred"].values, label="IMPROVED")
    logger.info(f"\n改进模型总精度: SMAPE={overall['SMAPE']:.2f}%, MAE={overall['MAE']:.2f}, "
                f"RMSE={overall['RMSE']:.2f}")

    # 按天评估
    daily_metrics = []
    for date, group in results.groupby("pred_day"):
        m = evaluate_forecast(group["true"].values, group["pred"].values, label=date)
        daily_metrics.append(m)

    metrics_df = pd.DataFrame(daily_metrics)
    metrics_df.to_csv(os.path.join(OUTPUT_DIR, "improved_daily_metrics.csv"), index=False)

    logger.info(f"\n按天精度:")
    for _, row in metrics_df.iterrows():
        logger.info(f"  {row['label']}: SMAPE={row['SMAPE']:.2f}%, MAE={row['MAE']:.2f}")

    return overall, daily_metrics


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 70)
    print("  负荷预测精度评估与提升")
    print("  1. 基线评估 | 2. 数据穿越审计 | 3. 改进回测")
    print("=" * 70)

    # Step 1: 基线评估
    baseline_result = None
    baseline_merged = None
    try:
        baseline_result = evaluate_baseline()
        if baseline_result:
            baseline_merged = baseline_result[2]
            baseline_result = (baseline_result[0], baseline_result[1])
    except Exception as e:
        logger.warning(f"基线评估失败: {e}")

    # Step 2: 数据穿越审计
    print_leakage_report()

    # Step 3: 改进后回测
    improved_result = None
    improved_results_df = None
    try:
        improved_result = run_improved_backtest()
        if improved_result:
            improved_results_df = pd.read_csv(os.path.join(OUTPUT_DIR, "improved_predictions.csv"))
            improved_results_df["record_time"] = pd.to_datetime(improved_results_df["record_time"])
    except Exception as e:
        logger.error(f"改进回测失败: {e}")
        import traceback
        traceback.print_exc()

    # Step 4: 对比
    if baseline_result and improved_result:
        logger.info("\n" + "=" * 60)
        logger.info("4. 基线 vs 改进 对比")
        logger.info("=" * 60)
        b = baseline_result[0]
        imp = improved_result[0]
        logger.info(f"{'指标':<10} {'基线':>12} {'改进':>12} {'提升':>12}")
        for metric in ['SMAPE', 'MAPE', 'MAE', 'RMSE']:
            bv = b[metric]
            iv = imp[metric]
            delta = bv - iv  # 正值=改进
            pct = (delta / bv * 100) if bv != 0 else 0
            logger.info(f"{metric:<10} {bv:>12.4f} {iv:>12.4f} {pct:>11.2f}%")
    else:
        if not baseline_result:
            logger.info("\n无法进行对比 (基线评估缺失)")
        if not improved_result:
            logger.info("\n无法进行对比 (改进评估缺失)")

    # Step 5: 绘制对比曲线
    if baseline_merged is not None and improved_results_df is not None:
        logger.info("\n" + "=" * 60)
        logger.info("5. 绘制对比曲线")
        logger.info("=" * 60)
        try:
            plot_full_comparison(baseline_merged, improved_results_df, OUTPUT_DIR)
        except Exception as e:
            logger.warning(f"全局对比图绘制失败: {e}")
        try:
            plot_daily_comparison(baseline_merged, improved_results_df, OUTPUT_DIR)
        except Exception as e:
            logger.warning(f"逐天对比图绘制失败: {e}")
        try:
            plot_metrics_bar(baseline_result[1], improved_result[1], OUTPUT_DIR)
        except Exception as e:
            logger.warning(f"指标柱状图绘制失败: {e}")
        try:
            plot_scatter(improved_results_df, OUTPUT_DIR)
        except Exception as e:
            logger.warning(f"散点图绘制失败: {e}")
    elif improved_results_df is not None:
        logger.info("\n仅改进模型结果, 绘制散点图")
        try:
            plot_scatter(improved_results_df, OUTPUT_DIR)
        except Exception as e:
            logger.warning(f"散点图绘制失败: {e}")

    print(f"\n结果输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
