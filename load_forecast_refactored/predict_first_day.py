# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
要求：预测验证数据的第一天，数据先截取

思路：
  1. 加载威海数据
  2. 截取数据到预测日前一天（2026-03-31 23:45:00），彻底不包含预测日数据
  3. 用截取后的数据做特征工程（无需 mask，因为根本没有未来数据）
  4. 训练模型，预测 2026-04-01 的 96 个点
  5. 与真实值对比评估

这种"先截取"的方式比"合并后 mask"更直观、更安全，
因为从源头上就不存在未来数据，不可能穿越。

用法:
    python predict_first_day.py
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
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from bayes_opt import BayesianOptimization

warnings.filterwarnings(action="ignore")

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "predict_first_day")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PRED_DAY = "2026-04-01"          # 预测目标日
TRAIN_DAYS = 30                   # 训练窗口天数
DAILY_HORIZON = 96                # 15min × 96 = 24h


# ===========================================================================
# 1. 数据加载
# ===========================================================================

def load_weihai_data():
    """加载威海负荷数据"""
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
    logger.info(f"原始数据: {load_df['record_time'].min()} ~ {load_df['record_time'].max()}, "
                f"{len(load_df)} rows")
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
# 3. 特征工程（与 run_weihai_backtest.py 一致）
# ===========================================================================

def if_workday(date):
    try:
        from chinese_calendar import is_workday
        return is_workday(pd.to_datetime(date))
    except Exception:
        return pd.to_datetime(date).weekday() <= 4


def build_features(df, time_field="record_time", load_field="load"):
    """构建特征 — 与 run_weihai_backtest.py 完全一致"""
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

    # ---- Lag 特征 ----
    for lag in [1, 2, 3, 4, 5, 6, 7, 14, 21, 28]:
        feat[f"lag_{lag}d"] = feat[load_field].shift(lag * dh)
    feat["same_time_2w"] = (feat["lag_7d"] + feat["lag_14d"]) / 2
    feat["same_time_3w"] = (feat["lag_7d"] + feat["lag_14d"] + feat["lag_21d"]) / 3

    # ---- 差分特征 ----
    load_prev = feat[load_field].shift(1)
    feat["diff_1"]      = load_prev - load_prev.shift(1)
    feat["diff_96"]     = load_prev - load_prev.shift(dh)
    feat["diff_192"]    = load_prev - load_prev.shift(2 * dh)
    feat["diff_96_of_96"] = load_prev.shift(dh-1) - load_prev.shift(2*dh-1)

    # ---- 滚动统计 ----
    load_yd = feat[load_field].shift(dh)
    for w in [4, 8, 12, 24, 48, 96]:
        feat[f"roll_{w}_mean"] = load_yd.rolling(w, center=False, min_periods=1).mean().values
        feat[f"roll_{w}_std"]  = load_yd.rolling(w, center=False, min_periods=1).std().values
        feat[f"roll_{w}_max"]  = load_yd.rolling(w, center=False, min_periods=1).max().values
        feat[f"roll_{w}_min"]  = load_yd.rolling(w, center=False, min_periods=1).min().values

    # ---- 日统计特征 ----
    feat["date"] = feat[time_field].dt.strftime("%Y-%m-%d")
    ds = feat.groupby("date")[load_field].agg(["mean", "max", "min", "std"]).reset_index()
    ds.columns = ["date", "day_mean", "day_max", "day_min", "day_std"]
    ds["day_pv"]       = ds["day_max"] - ds["day_min"]
    ds["day_pv_rate"]  = ds["day_pv"] / ds["day_max"].replace(0, np.nan)
    ds["day_rate"]     = ds["day_mean"] / ds["day_max"].replace(0, np.nan)
    for c in ["day_mean", "day_max", "day_min", "day_std", "day_pv", "day_pv_rate", "day_rate"]:
        ds[c] = ds[c].shift(1)
    feat = feat.merge(ds, on="date", how="left")

    ds2 = feat.groupby("date")["lag_1d"].agg(["mean", "std"]).reset_index()
    ds2.columns = ["date", "lag1d_day_mean", "lag1d_day_std"]
    ds2["lag1d_day_mean"] = ds2["lag1d_day_mean"].shift(1)
    ds2["lag1d_day_std"]  = ds2["lag1d_day_std"].shift(1)
    feat = feat.merge(ds2, on="date", how="left")

    return feat


# ===========================================================================
# 4. 模型训练（复用 run_weihai_backtest.py 的多模型逻辑）
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
            p = {
                'objective': 'reg:squarederror', 'eval_metric': 'rmse', 'verbosity': 0,
                'max_depth': int(max_depth), 'min_child_weight': float(min_child_weight),
                'subsample': float(subsample), 'eta': float(eta), 'lambda': float(lambdas),
                'seed': 42, 'nthread': 4,
            }
            m = xgb.train(p, dtrn, 100, evals=[(dtrn, 'train'), (dval, 'valid')],
                          verbose_eval=0, early_stopping_rounds=5)
            oof[vi] = m.predict(dval)
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))

    bo = BayesianOptimization(f=xgb_cv, pbounds={
        'eta': (0.01, 0.15), 'max_depth': (2, 8),
        'min_child_weight': (0.3, 10), 'subsample': (0.5, 1), 'lambdas': (0.1, 100),
    }, random_state=42)
    bo.maximize(init_points=3, n_iter=12)

    oof_rmse = -bo.max['target']
    params = bo.max['params']
    params['max_depth'] = int(params['max_depth'])

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
            p = {
                'objective': 'regression', 'metric': 'rmse', 'verbosity': -1,
                'learning_rate': float(learning_rate), 'max_depth': int(max_depth),
                'num_leaves': int(num_leaves), 'min_child_samples': int(min_child_samples),
                'subsample': float(subsample), 'seed': 42, 'nthread': 4,
            }
            m = lgb.train(p, lgb.Dataset(x_train.iloc[ti], label=y_train.iloc[ti]),
                          100, valid_sets=[lgb.Dataset(x_train.iloc[vi], label=y_train.iloc[vi])],
                          callbacks=[lgb.early_stopping(5, verbose=False), lgb.log_evaluation(0)])
            oof[vi] = m.predict(x_train.iloc[vi])
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))

    bo = BayesianOptimization(f=lgb_cv, pbounds={
        'learning_rate': (0.01, 0.15), 'max_depth': (2, 8),
        'num_leaves': (15, 63), 'min_child_samples': (5, 50), 'subsample': (0.5, 1),
    }, random_state=42)
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
            p = {
                'loss_function': 'RMSE', 'verbose': 0,
                'learning_rate': float(learning_rate), 'depth': int(depth),
                'l2_leaf_reg': float(l2_leaf_reg),
                'bagging_temperature': float(bagging_temperature),
                'random_seed': 42, 'thread_count': 4,
            }
            m = CatBoostRegressor(**p)
            m.fit(x_train.iloc[ti], y_train.iloc[ti],
                  eval_set=(x_train.iloc[vi], y_train.iloc[vi]),
                  early_stopping_rounds=5, verbose=0)
            oof[vi] = m.predict(x_train.iloc[vi])
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))

    bo = BayesianOptimization(f=cb_cv, pbounds={
        'learning_rate': (0.01, 0.15), 'depth': (2, 8),
        'l2_leaf_reg': (0.1, 10), 'bagging_temperature': (0, 1),
    }, random_state=42)
    bo.maximize(init_points=3, n_iter=12)

    oof_rmse = -bo.max['target']
    params = bo.max['params']
    params['depth'] = int(params['depth'])
    params.update({'loss_function': 'RMSE', 'verbose': 0, 'random_seed': 42, 'thread_count': 4})

    sw = _sample_weights(y_train, forecast_length)
    model = CatBoostRegressor(iterations=200, **params)
    model.fit(x_train, y_train, sample_weight=sw,
              early_stopping_rounds=10, verbose=0)
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
# 5. 核心逻辑：先截取数据，再预测第一天
# ===========================================================================

def predict_first_day():
    """
    要求的流程：数据先截取，再预测验证数据的第一天

    与原 rolling_backtest 的关键区别：
    ┌─────────────────────────────────────────────────────────────────┐
    │  原方式 (mask):                                                 │
    │    combined = concat(train, test_masked)  # test load → NaN    │
    │    特征工程在 combined 上做                                      │
    │    → 安全，但 combined 中仍包含测试集的时间戳行                    │
    │                                                                 │
    │  新方式 (截取):                                                  │
    │    data = full_data[: pred_day前一天]  # 直接截断，无未来数据      │
    │    特征工程只在历史数据上做                                        │
    │    → 更安全，从源头杜绝穿越可能                                   │
    │    → 测试集的特征行需要单独构造（追加空行再做特征）                  │
    └─────────────────────────────────────────────────────────────────┘
    """
    pred_day = pd.to_datetime(PRED_DAY)
    train_end = pred_day - timedelta(minutes=15)  # 2026-03-31 23:45:00
    train_start = pred_day - timedelta(days=1) - timedelta(days=TRAIN_DAYS)

    print("=" * 70)
    print("  先截取数据，再预测验证数据的第一天")
    print(f"  预测日: {PRED_DAY}")
    print(f"  训练窗口: {train_start.strftime('%Y-%m-%d')} ~ {train_end.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # ---- Step 1: 加载全量数据 ----
    full_df = load_weihai_data()

    # ---- Step 2: 截取！只保留预测日之前的数据 ----
    # 这是领导要求的核心：数据先截取一下
    cutoff = pred_day  # 严格 < pred_day
    history_df = full_df[full_df["record_time"] < cutoff].copy().reset_index(drop=True)
    logger.info(f"截取后数据: {history_df['record_time'].min()} ~ {history_df['record_time'].max()}, "
                f"{len(history_df)} rows")
    logger.info(f"截取点: < {cutoff} (预测日 {PRED_DAY} 的数据完全不包含)")

    # 保留真实值用于评估
    truth_df = full_df[
        (full_df["record_time"] >= pred_day) &
        (full_df["record_time"] < pred_day + timedelta(days=1))
    ].copy().reset_index(drop=True)
    logger.info(f"真实值: {len(truth_df)} rows ({truth_df['record_time'].min()} ~ {truth_df['record_time'].max()})")

    # ---- Step 3: 构造特征工程的输入 ----
    # 追加预测日的 96 个空行（load=NaN），这样 lag/rolling 特征可以自然计算
    pred_timestamps = pd.date_range(pred_day, pred_day + timedelta(days=1),
                                     freq="15min", inclusive="left")
    pred_rows = pd.DataFrame({
        "record_time": pred_timestamps,
        "load": np.nan,  # 关键：预测日的 load 全部是 NaN
    })
    combined = pd.concat([history_df, pred_rows], ignore_index=True)
    logger.info(f"合并后（历史 + 空预测行）: {len(combined)} rows")
    logger.info(f"  其中预测日 load 全部为 NaN: {combined[combined['record_time'] >= pred_day]['load'].isna().all()}")

    # ---- Step 4: 特征工程 ----
    feat_all = build_features(combined)

    # 取训练窗口
    train_start_actual = pred_day - timedelta(days=1) - timedelta(days=TRAIN_DAYS)
    train_feat = feat_all[
        (feat_all["record_time"] >= train_start_actual) &
        (feat_all["record_time"] < cutoff)
    ].copy()
    test_feat = feat_all[feat_all["record_time"] >= pred_day].copy()

    drop_cols = ["load", "record_time", "date"]
    feature_cols = [c for c in train_feat.columns
                    if c not in drop_cols and train_feat[c].dtype in ['float64','float32','int64','int32']]

    train_feat[feature_cols] = train_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    test_feat[feature_cols]  = test_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)

    x_tr = train_feat[feature_cols]
    y_tr = train_feat["load"]
    x_te = test_feat[feature_cols]

    logger.info(f"训练集: {len(x_tr)} rows, 特征数: {len(feature_cols)}")
    logger.info(f"测试集: {len(x_te)} rows")

    # ---- Step 5: 训练 4 个模型 ----
    print("\n" + "-" * 70)
    print("  训练模型...")
    print("-" * 70)

    models = {}
    oof_scores = {}

    logger.info("  训练 XGBoost...")
    models['xgb'], oof_scores['xgb'] = train_xgb(x_tr, y_tr, DAILY_HORIZON)
    logger.info("  训练 LightGBM...")
    models['lgb'], oof_scores['lgb'] = train_lgb(x_tr, y_tr, DAILY_HORIZON)
    logger.info("  训练 CatBoost...")
    models['catb'], oof_scores['catb'] = train_catboost(x_tr, y_tr, DAILY_HORIZON)
    logger.info("  训练 Ridge...")
    models['ridge'], oof_scores['ridge'] = train_ridge(x_tr, y_tr, DAILY_HORIZON)

    # 自适应权重
    inv_scores = {k: 1.0 / v for k, v in oof_scores.items()}
    total = sum(inv_scores.values())
    weights = {k: v / total for k, v in inv_scores.items()}
    logger.info(f"  自适应权重: " + "  ".join(f"{k}={w:.3f}" for k, w in weights.items()))

    # ---- Step 6: 预测 ----
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
    ensemble = np.maximum(ensemble, 0)

    # ---- Step 7: 评估 ----
    y_true = truth_df["load"].values
    if len(y_true) != len(ensemble):
        logger.warning(f"真实值 {len(y_true)} 行 vs 预测值 {len(ensemble)} 行，取最小长度")
        min_len = min(len(y_true), len(ensemble))
        y_true = y_true[:min_len]
        ensemble = ensemble[:min_len]

    print("\n" + "=" * 70)
    print(f"  预测结果: {PRED_DAY}")
    print("=" * 70)

    m_ens = evaluate(y_true, ensemble, "Ensemble")
    m_xgb = evaluate(y_true, np.maximum(preds['xgb'], 0)[:len(y_true)], "XGBoost")
    m_lgb = evaluate(y_true, np.maximum(preds['lgb'], 0)[:len(y_true)], "LightGBM")
    m_catb = evaluate(y_true, np.maximum(preds['catb'], 0)[:len(y_true)], "CatBoost")
    m_ridge = evaluate(y_true, np.maximum(preds['ridge'], 0)[:len(y_true)], "Ridge")

    print(f"\n  {'Model':<12} {'SMAPE':>8} {'MAE':>10} {'RMSE':>10}")
    print(f"  {'-'*42}")
    for m in [m_xgb, m_lgb, m_catb, m_ridge, m_ens]:
        print(f"  {m['label']:<12} {m['SMAPE']:>7.2f}% {m['MAE']:>10.1f} {m['RMSE']:>10.1f}")

    # ---- Step 8: 保存结果 ----
    result_df = pd.DataFrame({
        "record_time": test_feat["record_time"].values[:len(y_true)],
        "true": y_true,
        "pred_ensemble": ensemble,
        "pred_xgb": np.maximum(preds['xgb'], 0)[:len(y_true)],
        "pred_lgb": np.maximum(preds['lgb'], 0)[:len(y_true)],
        "pred_catb": np.maximum(preds['catb'], 0)[:len(y_true)],
        "pred_ridge": np.maximum(preds['ridge'], 0)[:len(y_true)],
    })
    csv_path = os.path.join(OUTPUT_DIR, f"predict_{PRED_DAY}.csv")
    result_df.to_csv(csv_path, index=False)
    logger.info(f"预测结果已保存: {csv_path}")

    # ---- Step 9: 绘图 ----
    plot_prediction(result_df, OUTPUT_DIR)

    # ---- Step 10: 穿越验证 ----
    verify_no_leakage_simple(history_df, pred_day)

    print(f"\n输出目录: {OUTPUT_DIR}")
    return result_df


# ===========================================================================
# 6. 可视化
# ===========================================================================

def plot_prediction(result_df, output_dir):
    """绘制预测 vs 真实对比图"""
    fig, axes = plt.subplots(2, 1, figsize=(16, 8), sharex=True)

    x = range(len(result_df))
    times = pd.to_datetime(result_df["record_time"])

    # 上图：曲线对比
    ax = axes[0]
    ax.plot(x, result_df["true"], "k-o", ms=2, lw=1.5, label="True")
    ax.plot(x, result_df["pred_ensemble"], color="#2ecc71", lw=1.2, label="Ensemble")
    ax.plot(x, result_df["pred_xgb"], color="#3498db", lw=0.7, alpha=0.5, label="XGB")
    ax.plot(x, result_df["pred_lgb"], color="#e67e22", lw=0.7, alpha=0.5, label="LGB")
    ax.plot(x, result_df["pred_catb"], color="#9b59b6", lw=0.7, alpha=0.5, label="CatB")

    s = smape(result_df["true"].values, result_df["pred_ensemble"].values)
    weekday = times.iloc[0].strftime('%A')
    ax.set_title(f"{PRED_DAY} ({weekday}) — 先截取数据再预测  SMAPE={s:.2f}%", fontsize=14)
    ax.set_ylabel("Load (kW)")
    ax.legend(loc="upper right", ncol=3)
    ax.grid(True, alpha=0.3)

    # 下图：误差
    ax = axes[1]
    err = result_df["pred_ensemble"].values - result_df["true"].values
    ax.fill_between(x, 0, err, where=err >= 0, color="#2ecc71", alpha=0.5, label="Over")
    ax.fill_between(x, 0, err, where=err < 0, color="#e74c3c", alpha=0.5, label="Under")
    ax.axhline(0, color="k", lw=0.5)
    ax.set_ylabel("Error")
    ax.set_xlabel("Time (15min intervals)")
    ax.set_xticks([0, 24, 48, 72, 95])
    ax.set_xticklabels(["00:00", "06:00", "12:00", "18:00", "23:45"])
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(output_dir, f"predict_{PRED_DAY}.png")
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"图表已保存: {path}")


# ===========================================================================
# 7. 简单穿越验证
# ===========================================================================

def verify_no_leakage_simple(history_df, pred_day):
    """
    简单验证：截取方式下不可能穿越

    因为 history_df 中根本不包含 pred_day 及之后的数据，
    所以任何基于 history_df 的特征计算都不可能引用未来数据。
    """
    print("\n" + "-" * 70)
    print("  穿越验证（截取方式）")
    print("-" * 70)

    max_time = history_df["record_time"].max()
    has_future = (history_df["record_time"] >= pred_day).any()

    print(f"  历史数据最大时间: {max_time}")
    print(f"  预测日: {pred_day}")
    print(f"  历史数据中是否包含预测日数据: {has_future}")

    if not has_future:
        print(f"  [PASS] 数据已在 {max_time} 处截断，不包含任何预测日数据")
        print(f"         从源头杜绝了数据穿越的可能性")
    else:
        print(f"  [FAIL] 历史数据中包含了预测日的数据！请检查截取逻辑")


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    predict_first_day()
# @AI_GENERATED: end
