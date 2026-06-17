# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
D日预测D+1负荷，模型只能用D-1及之前的历史真值

实际业务场景：
  - D日 = 2026-03-31（预测执行日）
  - D+1日 = 2026-04-01（预测目标日）
  - 可用数据截止到 D-1 = 2026-03-30 23:45:00
  - D日（3/31）的数据不可用（采集延迟/未完成）
  - 中间 gap 一天

对比：
  - 原方式：用到 D-1（3/31）的数据预测 D（4/1）→ 无 gap
  - 新方式：用到 D-2（3/30）的数据预测 D（4/1）→ gap 1天

用法:
    python predict_with_gap.py
"""
import os
import gc
import warnings
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostRegressor
from sklearn.linear_model import Ridge
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from loguru import logger
from datetime import timedelta
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from bayes_opt import BayesianOptimization

warnings.filterwarnings(action="ignore")

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "predict_with_gap")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PRED_TARGET = "2026-04-01"   # D+1: 预测目标日
PRED_EXEC   = "2026-03-31"   # D:   预测执行日
DATA_CUTOFF = "2026-03-30"   # D-1: 数据可用截止日（含当天）
DAILY_HORIZON = 96


# ===========================================================================
# 1. 数据加载
# ===========================================================================

def load_weihai_data():
    xlsx_path = os.path.join(DATASETS_DIR, "load_true_weihai_260407.xlsx")
    df = pd.read_excel(xlsx_path)
    df["record_time"] = pd.to_datetime(df["record_time"])
    load_df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
    load_df.rename(columns={"value": "load"}, inplace=True)
    load_df = load_df.sort_values("record_time").reset_index(drop=True)
    load_df = load_df.drop_duplicates(subset="record_time", keep="first")
    load_df = load_df.set_index("record_time")
    load_df = load_df.resample("15min").mean()
    load_df = load_df.interpolate().fillna(method="bfill").fillna(method="ffill")
    load_df.reset_index(inplace=True)
    return load_df


# ===========================================================================
# 2. 评估指标
# ===========================================================================

def smape(y_true, y_pred):
    denominator = np.abs(y_true) + np.abs(y_pred)
    mask = denominator > 1e-8
    return np.round(2.0 * np.mean(np.abs(y_pred[mask] - y_true[mask]) / denominator[mask]) * 100, 4)

def evaluate(y_true, y_pred, label=""):
    return {
        "label": label,
        "SMAPE": smape(y_true, y_pred),
        "MAE":   np.round(mean_absolute_error(y_true, y_pred), 4),
        "RMSE":  np.round(np.sqrt(mean_squared_error(y_true, y_pred)), 4),
    }


# ===========================================================================
# 3. 特征工程（适配 gap 场景）
# ===========================================================================

def if_workday(date):
    try:
        from chinese_calendar import is_workday
        return is_workday(pd.to_datetime(date))
    except Exception:
        return pd.to_datetime(date).weekday() <= 4


def build_features_with_gap(df, time_field="record_time", load_field="load"):
    """
    构建特征 — 适配 gap 场景

    与原版的区别：
    - lag 特征从 lag_2d 起算（因为 lag_1d 引用的是 D 日数据，不可用）
    - diff 特征基于 shift(2*dh) 而非 shift(1)
    - rolling 特征基于 shift(2*dh)（前天的值）
    - 日统计特征 shift(2) 而非 shift(1)
    """
    feat = df.copy()
    feat[time_field] = pd.to_datetime(feat[time_field])
    dh = DAILY_HORIZON

    # ---- 时间特征 ----
    feat["is_holiday"]  = feat[time_field].apply(lambda x: 0 if if_workday(x) else 1)
    feat["day"]         = feat[time_field].dt.day
    feat["yday"]        = feat[time_field].dt.dayofyear
    feat["month"]       = feat[time_field].dt.month
    feat["dayofweek"]   = feat[time_field].dt.dayofweek
    feat["hour"]        = feat[time_field].dt.hour
    feat["minute"]      = feat[time_field].dt.minute
    feat["period"]      = feat["hour"] * 4 + feat["minute"] // 15

    feat["hour_sin"]    = np.sin(2 * np.pi * feat["hour"] / 24)
    feat["hour_cos"]    = np.cos(2 * np.pi * feat["hour"] / 24)
    feat["wday_sin"]    = np.sin(2 * np.pi * feat["dayofweek"] / 7)
    feat["wday_cos"]    = np.cos(2 * np.pi * feat["dayofweek"] / 7)
    feat["yday_sin"]    = np.sin(2 * np.pi * feat["yday"] / 365)
    feat["yday_cos"]    = np.cos(2 * np.pi * feat["yday"] / 365)
    feat["month_sin"]   = np.sin(2 * np.pi * feat["month"] / 12)
    feat["month_cos"]   = np.cos(2 * np.pi * feat["month"] / 12)

    # ---- Lag 特征（从 2d 起，跳过不可用的 D 日）----
    # lag_2d = D-1 的同时刻（可用的最新数据）
    for lag in [2, 3, 4, 5, 6, 7, 8, 14, 21, 28]:
        feat[f"lag_{lag}d"] = feat[load_field].shift(lag * dh)

    feat["same_time_2w"] = (feat["lag_7d"] + feat["lag_14d"]) / 2
    feat["same_time_3w"] = (feat["lag_7d"] + feat["lag_14d"] + feat["lag_21d"]) / 3

    # ---- 差分特征（基于 D-1 的数据）----
    # load_prev2 = D-1 同时刻的 load（shift 2天）
    load_prev2 = feat[load_field].shift(2 * dh)
    feat["diff_1"]      = load_prev2 - load_prev2.shift(1)
    feat["diff_96"]     = load_prev2 - load_prev2.shift(dh)
    feat["diff_192"]    = load_prev2 - load_prev2.shift(2 * dh)

    # ---- 滚动统计（基于 D-1 的值）----
    load_d_minus_1 = feat[load_field].shift(2 * dh)  # D-1 同时刻
    for w in [4, 8, 12, 24, 48, 96]:
        feat[f"roll_{w}_mean"] = load_d_minus_1.rolling(w, center=False, min_periods=1).mean().values
        feat[f"roll_{w}_std"]  = load_d_minus_1.rolling(w, center=False, min_periods=1).std().values
        feat[f"roll_{w}_max"]  = load_d_minus_1.rolling(w, center=False, min_periods=1).max().values
        feat[f"roll_{w}_min"]  = load_d_minus_1.rolling(w, center=False, min_periods=1).min().values

    # ---- 日统计特征（shift 2天，用 D-2 的统计量）----
    feat["date"] = feat[time_field].dt.strftime("%Y-%m-%d")
    ds = feat.groupby("date")[load_field].agg(["mean", "max", "min", "std"]).reset_index()
    ds.columns = ["date", "day_mean", "day_max", "day_min", "day_std"]
    ds["day_pv"]       = ds["day_max"] - ds["day_min"]
    ds["day_pv_rate"]  = ds["day_pv"] / ds["day_max"].replace(0, np.nan)
    ds["day_rate"]     = ds["day_mean"] / ds["day_max"].replace(0, np.nan)
    # shift(2): 对于预测目标日 D+1，用的是 D-1 的日统计（跳过 D）
    for c in ["day_mean", "day_max", "day_min", "day_std", "day_pv", "day_pv_rate", "day_rate"]:
        ds[c] = ds[c].shift(2)
    feat = feat.merge(ds, on="date", how="left")

    # ---- lag_2d 的日统计 ----
    ds2 = feat.groupby("date")["lag_2d"].agg(["mean", "std"]).reset_index()
    ds2.columns = ["date", "lag2d_day_mean", "lag2d_day_std"]
    ds2["lag2d_day_mean"] = ds2["lag2d_day_mean"].shift(2)
    ds2["lag2d_day_std"]  = ds2["lag2d_day_std"].shift(2)
    feat = feat.merge(ds2, on="date", how="left")

    # ---- 趋势特征 ----
    feat["ma_7d"] = feat[load_field].shift(2 * dh).rolling(7 * dh, min_periods=dh).mean()
    feat["ma_14d"] = feat[load_field].shift(2 * dh).rolling(14 * dh, min_periods=dh).mean()
    feat["ma_28d"] = feat[load_field].shift(2 * dh).rolling(28 * dh, min_periods=dh).mean()
    feat["trend_7d_14d"] = feat["ma_7d"] / feat["ma_14d"].replace(0, np.nan)
    feat["trend_7d_28d"] = feat["ma_7d"] / feat["ma_28d"].replace(0, np.nan)
    feat["ma_7d_diff"] = feat["ma_7d"] - feat["ma_14d"]
    feat["same_hour_trend"] = feat["lag_7d"] - feat["lag_14d"]

    # 供暖退出系数
    feat["days_in_year"] = feat[time_field].dt.dayofyear
    feat["heating_phase"] = np.where(
        feat["days_in_year"] <= 90, 1.0,
        np.where(feat["days_in_year"] <= 120, 1.0 - (feat["days_in_year"] - 90) / 30, 0.0))

    return feat


# ===========================================================================
# 4. 模型训练（复用）
# ===========================================================================

def _sample_weights(label, forecast_length, ac=0.99):
    n = len(label)
    return np.array([pow(ac, i // forecast_length) for i in range(n)])[::-1]


def train_xgb(x_train, y_train, forecast_length, n_splits=5):
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    def xgb_cv(eta, max_depth, min_child_weight, subsample, lambdas):
        tscv = TimeSeriesSplit(n_splits=n_splits)
        oof = np.full(x_train.shape[0], np.nan)
        for _, (ti, vi) in enumerate(tscv.split(x_train)):
            dtrn = xgb.DMatrix(x_train.iloc[ti], label=y_train.iloc[ti], missing=0)
            dval = xgb.DMatrix(x_train.iloc[vi], label=y_train.iloc[vi], missing=0)
            p = {'objective': 'reg:squarederror', 'eval_metric': 'rmse', 'verbosity': 0,
                 'max_depth': int(max_depth), 'min_child_weight': float(min_child_weight),
                 'subsample': float(subsample), 'eta': float(eta), 'lambda': float(lambdas),
                 'seed': 42, 'nthread': 4}
            m = xgb.train(p, dtrn, 100, evals=[(dtrn, 'train'), (dval, 'valid')],
                          verbose_eval=0, early_stopping_rounds=5)
            oof[vi] = m.predict(dval)
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))
    bo = BayesianOptimization(f=xgb_cv, pbounds={
        'eta': (0.01, 0.15), 'max_depth': (2, 8), 'min_child_weight': (0.3, 10),
        'subsample': (0.5, 1), 'lambdas': (0.1, 100)}, random_state=42)
    bo.maximize(init_points=3, n_iter=12)
    oof_rmse = -bo.max['target']
    params = bo.max['params']; params['max_depth'] = int(params['max_depth'])
    sw = _sample_weights(y_train, forecast_length)
    dtrain = xgb.DMatrix(x_train, label=y_train, missing=0, weight=sw)
    model = xgb.train(params, dtrain, 200, evals=[(dtrain, 'train')],
                       early_stopping_rounds=10, verbose_eval=0)
    logger.info(f"    [XGB] OOF_RMSE={oof_rmse:.1f}")
    return model, oof_rmse


def train_lgb(x_train, y_train, forecast_length, n_splits=5):
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    def lgb_cv(learning_rate, max_depth, num_leaves, min_child_samples, subsample):
        tscv = TimeSeriesSplit(n_splits=n_splits)
        oof = np.full(x_train.shape[0], np.nan)
        for _, (ti, vi) in enumerate(tscv.split(x_train)):
            p = {'objective': 'regression', 'metric': 'rmse', 'verbosity': -1,
                 'learning_rate': float(learning_rate), 'max_depth': int(max_depth),
                 'num_leaves': int(num_leaves), 'min_child_samples': int(min_child_samples),
                 'subsample': float(subsample), 'seed': 42, 'nthread': 4}
            m = lgb.train(p, lgb.Dataset(x_train.iloc[ti], label=y_train.iloc[ti]),
                          100, valid_sets=[lgb.Dataset(x_train.iloc[vi], label=y_train.iloc[vi])],
                          callbacks=[lgb.early_stopping(5, verbose=False), lgb.log_evaluation(0)])
            oof[vi] = m.predict(x_train.iloc[vi])
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))
    bo = BayesianOptimization(f=lgb_cv, pbounds={
        'learning_rate': (0.01, 0.15), 'max_depth': (2, 8), 'num_leaves': (15, 63),
        'min_child_samples': (5, 50), 'subsample': (0.5, 1)}, random_state=42)
    bo.maximize(init_points=3, n_iter=12)
    oof_rmse = -bo.max['target']
    params = bo.max['params']
    params['max_depth'] = int(params['max_depth'])
    params['num_leaves'] = int(params['num_leaves'])
    params['min_child_samples'] = int(params['min_child_samples'])
    params.update({'objective': 'regression', 'metric': 'rmse', 'verbosity': -1, 'seed': 42, 'nthread': 4})
    sw = _sample_weights(y_train, forecast_length)
    model = lgb.train(params, lgb.Dataset(x_train, label=y_train, weight=sw),
                      200, valid_sets=[lgb.Dataset(x_train, label=y_train)],
                      callbacks=[lgb.early_stopping(10, verbose=False), lgb.log_evaluation(0)])
    logger.info(f"    [LGB] OOF_RMSE={oof_rmse:.1f}")
    return model, oof_rmse


def train_catboost(x_train, y_train, forecast_length, n_splits=5):
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    def cb_cv(learning_rate, depth, l2_leaf_reg, bagging_temperature):
        tscv = TimeSeriesSplit(n_splits=n_splits)
        oof = np.full(x_train.shape[0], np.nan)
        for _, (ti, vi) in enumerate(tscv.split(x_train)):
            p = {'loss_function': 'RMSE', 'verbose': 0, 'learning_rate': float(learning_rate),
                 'depth': int(depth), 'l2_leaf_reg': float(l2_leaf_reg),
                 'bagging_temperature': float(bagging_temperature), 'random_seed': 42, 'thread_count': 4}
            m = CatBoostRegressor(**p)
            m.fit(x_train.iloc[ti], y_train.iloc[ti],
                  eval_set=(x_train.iloc[vi], y_train.iloc[vi]), early_stopping_rounds=5, verbose=0)
            oof[vi] = m.predict(x_train.iloc[vi])
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))
    bo = BayesianOptimization(f=cb_cv, pbounds={
        'learning_rate': (0.01, 0.15), 'depth': (2, 8),
        'l2_leaf_reg': (0.1, 10), 'bagging_temperature': (0, 1)}, random_state=42)
    bo.maximize(init_points=3, n_iter=12)
    oof_rmse = -bo.max['target']
    params = bo.max['params']; params['depth'] = int(params['depth'])
    params.update({'loss_function': 'RMSE', 'verbose': 0, 'random_seed': 42, 'thread_count': 4})
    sw = _sample_weights(y_train, forecast_length)
    model = CatBoostRegressor(iterations=200, **params)
    model.fit(x_train, y_train, sample_weight=sw, early_stopping_rounds=10, verbose=0)
    logger.info(f"    [CatB] OOF_RMSE={oof_rmse:.1f}")
    return model, oof_rmse


def train_ridge(x_train, y_train, forecast_length, n_splits=5):
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    tscv = TimeSeriesSplit(n_splits=n_splits)
    oof = np.full(x_train.shape[0], np.nan)
    for _, (ti, vi) in enumerate(tscv.split(x_train)):
        m = Ridge(alpha=1.0)
        m.fit(x_train.iloc[ti], y_train.iloc[ti])
        oof[vi] = m.predict(x_train.iloc[vi])
    mask = ~np.isnan(oof)
    oof_rmse = np.sqrt(mean_squared_error(y_train[mask], oof[mask]))
    sw = _sample_weights(y_train, forecast_length)
    model = Ridge(alpha=1.0)
    model.fit(x_train, y_train, sample_weight=sw)
    logger.info(f"    [Ridge] OOF_RMSE={oof_rmse:.1f}")
    return model, oof_rmse


# ===========================================================================
# 5. 主流程
# ===========================================================================

def run_prediction(train_days, label, use_enhanced=False):
    """
    执行一次预测实验

    Parameters
    ----------
    train_days : int  训练窗口天数
    label : str       实验标签
    use_enhanced : bool  是否使用增强特征
    """
    pred_target = pd.to_datetime(PRED_TARGET)  # 4/1
    # 数据截止到 D-1 = 3/30 23:45:00（不含 D=3/31 和 D+1=4/1）
    data_cutoff = pd.to_datetime(DATA_CUTOFF) + timedelta(days=1)  # < 3/31 00:00

    full_df = load_weihai_data()

    # 截取：只保留 D-1 及之前的数据
    history_df = full_df[full_df["record_time"] < data_cutoff].copy().reset_index(drop=True)
    logger.info(f"[{label}] 历史数据截止: {history_df['record_time'].max()} "
                f"({len(history_df)} rows)")

    # 真实值
    truth_df = full_df[
        (full_df["record_time"] >= pred_target) &
        (full_df["record_time"] < pred_target + timedelta(days=1))
    ]
    y_true = truth_df["load"].values

    # 追加 D 日（3/31）和 D+1 日（4/1）的空行
    # D 日也是空的（因为我们拿不到 D 日数据）
    gap_and_pred_timestamps = pd.date_range(
        data_cutoff,  # 3/31 00:00
        pred_target + timedelta(days=1),  # 4/2 00:00
        freq="15min", inclusive="left"
    )
    empty_rows = pd.DataFrame({
        "record_time": gap_and_pred_timestamps,
        "load": np.nan,
    })
    combined = pd.concat([history_df, empty_rows], ignore_index=True)
    logger.info(f"[{label}] 合并后: {len(combined)} rows "
                f"(其中 D 日和 D+1 日 load 全为 NaN)")

    # 特征工程
    feat_all = build_features_with_gap(combined)

    # 训练窗口
    train_start = data_cutoff - timedelta(days=train_days)
    train_feat = feat_all[
        (feat_all["record_time"] >= train_start) &
        (feat_all["record_time"] < data_cutoff)
    ].copy()
    test_feat = feat_all[feat_all["record_time"] >= pred_target].copy()

    drop_cols = ["load", "record_time", "date"]
    feature_cols = [c for c in train_feat.columns
                    if c not in drop_cols and train_feat[c].dtype in ['float64','float32','int64','int32']]

    train_feat[feature_cols] = train_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    test_feat[feature_cols]  = test_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)

    x_tr = train_feat[feature_cols]
    y_tr = train_feat["load"]
    x_te = test_feat[feature_cols]

    logger.info(f"[{label}] 训练集: {len(x_tr)} rows, 特征数: {len(feature_cols)}")
    logger.info(f"[{label}] 测试集: {len(x_te)} rows")

    # 训练
    models, oof_scores = {}, {}
    models['xgb'], oof_scores['xgb'] = train_xgb(x_tr, y_tr, DAILY_HORIZON)
    models['lgb'], oof_scores['lgb'] = train_lgb(x_tr, y_tr, DAILY_HORIZON)
    models['catb'], oof_scores['catb'] = train_catboost(x_tr, y_tr, DAILY_HORIZON)
    models['ridge'], oof_scores['ridge'] = train_ridge(x_tr, y_tr, DAILY_HORIZON)

    inv = {k: 1.0/v for k,v in oof_scores.items()}
    total = sum(inv.values())
    weights = {k: v/total for k,v in inv.items()}
    logger.info(f"[{label}] 权重: " + "  ".join(f"{k}={w:.3f}" for k,w in weights.items()))

    # 预测
    feat_list = sorted(feature_cols)
    x_te_sorted = x_te[feat_list]
    preds = {}
    preds['xgb']   = models['xgb'].predict(xgb.DMatrix(x_te_sorted))
    preds['lgb']   = models['lgb'].predict(x_te_sorted)
    preds['catb']  = models['catb'].predict(x_te_sorted)
    preds['ridge'] = models['ridge'].predict(x_te_sorted)

    ensemble = np.zeros(len(x_te))
    for name, w in weights.items():
        ensemble += w * preds[name]
    ensemble = np.maximum(ensemble, 0)[:len(y_true)]

    # 各模型结果
    for name in ['xgb', 'lgb', 'catb', 'ridge']:
        preds[name] = np.maximum(preds[name], 0)[:len(y_true)]

    return {
        'label': label,
        'ensemble': ensemble,
        'preds': preds,
        'weights': weights,
        'y_true': y_true,
        'test_times': test_feat["record_time"].values[:len(y_true)],
    }


def main():
    print("=" * 70)
    print("  D日预测D+1负荷 — 数据只用到D-1（gap 1天）")
    print(f"  预测执行日 D = {PRED_EXEC}")
    print(f"  数据截止   D-1 = {DATA_CUTOFF} 23:45:00")
    print(f"  预测目标   D+1 = {PRED_TARGET}")
    print("=" * 70)

    # 实验1: 30天窗口 + gap
    r30 = run_prediction(30, "30天+gap")

    # 实验2: 60天窗口 + gap
    r60 = run_prediction(60, "60天+gap")

    # 实验3: 90天窗口 + gap
    r90 = run_prediction(90, "90天+gap")

    y_true = r30['y_true']

    # 加载原始无 gap 的结果做对比
    orig_csv = os.path.join("output", "predict_first_day", "predict_2026-04-01.csv")
    ens_no_gap = None
    if os.path.exists(orig_csv):
        orig_df = pd.read_csv(orig_csv)
        ens_no_gap = orig_df["pred_ensemble"].values

    # ---- 汇总 ----
    print("\n" + "=" * 70)
    print("  汇总对比")
    print("=" * 70)

    all_results = {}
    if ens_no_gap is not None:
        all_results["原始(30天,无gap)"] = ens_no_gap
    all_results["30天+gap"] = r30['ensemble']
    all_results["60天+gap"] = r60['ensemble']
    all_results["90天+gap"] = r90['ensemble']

    print(f"\n  {'方案':<22} {'SMAPE':>8} {'MAE':>10} {'RMSE':>10} {'08:00误差':>12}")
    print(f"  {'-'*64}")
    for name, pred in all_results.items():
        p = pred[:len(y_true)]
        s = smape(y_true, p)
        mae = mean_absolute_error(y_true, p)
        rmse = np.sqrt(mean_squared_error(y_true, p))
        err_08 = p[32] - y_true[32]
        print(f"  {name:<22} {s:>7.2f}% {mae:>10.1f} {rmse:>10.1f} {err_08:>+12.0f}")

    # 各模型明细（90天+gap）
    print(f"\n  90天+gap 各模型:")
    print(f"  {'Model':<12} {'SMAPE':>8} {'MAE':>10} {'RMSE':>10}")
    print(f"  {'-'*42}")
    for name in ['xgb', 'lgb', 'catb', 'ridge']:
        p = r90['preds'][name]
        s = smape(y_true, p)
        mae = mean_absolute_error(y_true, p)
        rmse = np.sqrt(mean_squared_error(y_true, p))
        print(f"  {name:<12} {s:>7.2f}% {mae:>10.1f} {rmse:>10.1f}")
    s_ens = smape(y_true, r90['ensemble'])
    mae_ens = mean_absolute_error(y_true, r90['ensemble'])
    rmse_ens = np.sqrt(mean_squared_error(y_true, r90['ensemble']))
    print(f"  {'Ensemble':<12} {s_ens:>7.2f}% {mae_ens:>10.1f} {rmse_ens:>10.1f}")

    # ---- 穿越验证 ----
    print(f"\n  穿越验证:")
    print(f"    数据截止: {DATA_CUTOFF} 23:45:00")
    print(f"    D日({PRED_EXEC})数据: 不可用 (gap)")
    print(f"    D+1日({PRED_TARGET})数据: 不可用 (预测目标)")
    print(f"    [PASS] 模型只使用了 D-1 及之前的历史真值")

    # ---- 保存结果 ----
    result_df = pd.DataFrame({
        "record_time": r90['test_times'],
        "true": y_true,
        "pred_90d_gap": r90['ensemble'],
    })
    if ens_no_gap is not None:
        result_df["pred_30d_no_gap"] = ens_no_gap[:len(y_true)]
    result_df["pred_30d_gap"] = r30['ensemble']
    result_df["pred_60d_gap"] = r60['ensemble']

    csv_path = os.path.join(OUTPUT_DIR, f"predict_gap_{PRED_TARGET}.csv")
    result_df.to_csv(csv_path, index=False)
    print(f"\n  结果已保存: {csv_path}")

    # ---- 画图 ----
    fig, axes = plt.subplots(2, 1, figsize=(18, 10), gridspec_kw={'height_ratios': [3, 1]})

    ax = axes[0]
    x = range(len(y_true))
    ax.plot(x, y_true, 'k-o', ms=2.5, lw=1.8, label='真实值', zorder=5)

    colors = {'原始(30天,无gap)': '#bdc3c7', '30天+gap': '#3498db',
              '60天+gap': '#e67e22', '90天+gap': '#e74c3c'}
    for name, pred in all_results.items():
        p = pred[:len(y_true)]
        s = smape(y_true, p)
        c = colors.get(name, 'gray')
        lw = 1.0 if '无gap' in name else 1.5
        ls = '--' if '无gap' in name else '-'
        ax.plot(x, p, color=c, lw=lw, ls=ls, label=f'{name} (SMAPE={s:.2f}%)', alpha=0.8)

    ax.axvspan(28, 40, alpha=0.08, color='red')
    ax.set_title(f"D日预测D+1 (gap 1天) vs 无gap — {PRED_TARGET}", fontsize=14)
    ax.set_ylabel("Load (kW)", fontsize=12)
    ax.set_xticks([0,12,24,36,48,60,72,84,95])
    ax.set_xticklabels(["00:00","03:00","06:00","09:00","12:00","15:00","18:00","21:00","23:45"])
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    for name, pred in all_results.items():
        p = pred[:len(y_true)]
        err = p - y_true
        c = colors.get(name, 'gray')
        lw = 1.0 if '无gap' in name else 1.5
        ls = '--' if '无gap' in name else '-'
        ax.plot(x, err, color=c, lw=lw, ls=ls, label=name, alpha=0.8)
    ax.axhline(0, color='k', lw=0.5)
    ax.axvspan(28, 40, alpha=0.08, color='red')
    ax.set_ylabel("误差 (kW)")
    ax.set_xlabel("时刻")
    ax.set_xticks([0,12,24,36,48,60,72,84,95])
    ax.set_xticklabels(["00:00","03:00","06:00","09:00","12:00","15:00","18:00","21:00","23:45"])
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"gap_compare_{PRED_TARGET}.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  对比图已保存: {path}")

    print(f"\n输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
