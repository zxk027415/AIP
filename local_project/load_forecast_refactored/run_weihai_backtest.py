# -*- coding: utf-8 -*-
"""
威海负荷预测 — 滚动日回测验证

- 数据: load_true_weihai_260407.xlsx (2025-07-02 ~ 2026-04-07, 15min)
- 预测目标: 2026-04-01 ~ 2026-04-07 (7天)
- 方式: 按日滚动训练 (用过去30天训练，预测下一天96个点)
- 无数据穿越: TimeSeriesSplit, rolling(center=False), 仅历史lag

用法:
    python run_weihai_backtest.py
"""
import os
import gc
import copy
import pickle
import warnings
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostRegressor, Pool
from sklearn.linear_model import Ridge
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from loguru import logger
from datetime import timedelta, datetime
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from bayes_opt import BayesianOptimization

warnings.filterwarnings(action="ignore")

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "weihai_backtest")
MODEL_DIR = os.path.join(OUTPUT_DIR, "models")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# 回测参数
PRED_START = "2026-03-01"
PRED_END   = "2026-03-09"   # exclusive（预测 3.1~3.8 共 8 天）
TRAIN_DAYS = 30
DAILY_HORIZON = 96          # 15min * 96 = 24h
# @AI_GENERATED
GAP_DAYS = 1  # 训练数据截止到 pred_day - 1 - GAP_DAYS（D-2）
# 业务含义：D 日执行预测时，D-1 日数据尚未采集完成，训练只能用到 D-2
# 设为 0 则退化为原始无 gap 逻辑
# @AI_GENERATED: end


# ===========================================================================
# 1. 数据加载
# ===========================================================================

def load_weihai_data():
    """加载威海负荷数据 (long format → wide)"""
    xlsx_path = os.path.join(DATASETS_DIR, "load_true_weihai_260407.xlsx")
    df = pd.read_excel(xlsx_path)
    df["record_time"] = pd.to_datetime(df["record_time"])

    # 只取 load 行
    load_df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
    load_df.rename(columns={"value": "load"}, inplace=True)
    load_df = load_df.sort_values("record_time").reset_index(drop=True)

    # 去重、重采样补齐到 15min
    load_df = load_df.drop_duplicates(subset="record_time", keep="first")
    load_df = load_df.set_index("record_time")
    load_df = load_df.resample("15min").mean()
    load_df = load_df.interpolate().fillna(method="bfill").fillna(method="ffill")
    load_df.reset_index(inplace=True)

    logger.info(f"数据加载完成: {load_df['record_time'].min()} ~ {load_df['record_time'].max()}, "
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
# 3. 无穿越特征工程 (纯负荷，无气象)
# ===========================================================================

def if_workday(date):
    try:
        from chinese_calendar import is_workday
        return is_workday(pd.to_datetime(date))
    except Exception:
        return pd.to_datetime(date).weekday() <= 4


def build_features(df, time_field="record_time", load_field="load"):
    """构建无穿越特征 (仅使用历史数据)"""
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

    # 周期编码
    feat["hour_sin"]    = np.sin(2 * np.pi * feat["hour"] / 24)
    feat["hour_cos"]    = np.cos(2 * np.pi * feat["hour"] / 24)
    feat["wday_sin"]    = np.sin(2 * np.pi * feat["dayofweek"] / 7)
    feat["wday_cos"]    = np.cos(2 * np.pi * feat["dayofweek"] / 7)
    feat["yday_sin"]    = np.sin(2 * np.pi * feat["yday"] / 365)
    feat["yday_cos"]    = np.cos(2 * np.pi * feat["yday"] / 365)
    feat["month_sin"]   = np.sin(2 * np.pi * feat["month"] / 12)
    feat["month_cos"]   = np.cos(2 * np.pi * feat["month"] / 12)

    # ---- Lag 特征 (仅历史) ----
    for lag in [1, 2, 3, 4, 5, 6, 7, 14, 21, 28]:
        feat[f"lag_{lag}d"] = feat[load_field].shift(lag * dh)

    # 同时刻多周加权平均
    feat["same_time_2w"] = (feat["lag_7d"] + feat["lag_14d"]) / 2
    feat["same_time_3w"] = (feat["lag_7d"] + feat["lag_14d"] + feat["lag_21d"]) / 3

    # ---- 差分特征 (基于 shift 历史, 无穿越) ----
    # 不能用 feat[load].diff(), 因为对测试集会用到未来 load
    # 所有 diff 都基于 shift(1) 后的 load_prev, 即 load[t-1]
    load_prev = feat[load_field].shift(1)       # t-1 时刻的 load (可知)
    feat["diff_1"]      = load_prev - load_prev.shift(1)            # load[t-1]-load[t-2]
    feat["diff_96"]     = load_prev - load_prev.shift(dh)           # load[t-1]-load[t-97]
    feat["diff_192"]    = load_prev - load_prev.shift(2 * dh)       # load[t-1]-load[t-193]
    feat["diff_96_of_96"] = load_prev.shift(dh-1) - load_prev.shift(2*dh-1)  # load[t-96]-load[t-192]

    # ---- 滚动统计 (center=False) ----
    load_yd = feat[load_field].shift(dh)   # 前一天同时刻值
    for w in [4, 8, 12, 24, 48, 96]:
        feat[f"roll_{w}_mean"] = load_yd.rolling(w, center=False, min_periods=1).mean().values
        feat[f"roll_{w}_std"]  = load_yd.rolling(w, center=False, min_periods=1).std().values
        feat[f"roll_{w}_max"]  = load_yd.rolling(w, center=False, min_periods=1).max().values
        feat[f"roll_{w}_min"]  = load_yd.rolling(w, center=False, min_periods=1).min().values

    # ---- 日统计特征 (基于前1天, shift 1行) ----
    feat["date"] = feat[time_field].dt.strftime("%Y-%m-%d")
    ds = feat.groupby("date")[load_field].agg(["mean", "max", "min", "std"]).reset_index()
    ds.columns = ["date", "day_mean", "day_max", "day_min", "day_std"]
    ds["day_pv"]       = ds["day_max"] - ds["day_min"]
    ds["day_pv_rate"]  = ds["day_pv"] / ds["day_max"].replace(0, np.nan)
    ds["day_rate"]     = ds["day_mean"] / ds["day_max"].replace(0, np.nan)
    # 前移1天
    for c in ["day_mean", "day_max", "day_min", "day_std", "day_pv", "day_pv_rate", "day_rate"]:
        ds[c] = ds[c].shift(1)
    feat = feat.merge(ds, on="date", how="left")

    # ---- 前1天的 lag_1d 的统计量 (日级别) ----
    ds2 = feat.groupby("date")["lag_1d"].agg(["mean", "std"]).reset_index()
    ds2.columns = ["date", "lag1d_day_mean", "lag1d_day_std"]
    ds2["lag1d_day_mean"] = ds2["lag1d_day_mean"].shift(1)
    ds2["lag1d_day_std"]  = ds2["lag1d_day_std"].shift(1)
    feat = feat.merge(ds2, on="date", how="left")

    return feat


# ===========================================================================
# 4. 多模型训练 (XGBoost / LightGBM / CatBoost / Ridge)
# ===========================================================================

def _sample_weights(label, forecast_length, ac=0.99):
    n = len(label)
    return np.array([pow(ac, i // forecast_length) for i in range(n)])[::-1]


def train_xgb(x_train, y_train, forecast_length, n_splits=5):
    """XGBoost: TimeSeriesSplit + 贝叶斯优化, 返回 (model, oof_rmse)"""
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

    oof_rmse = -bo.max['target']  # 负号: BO 最大化 -RMSE
    params = bo.max['params']
    params['max_depth'] = int(params['max_depth'])

    sw = _sample_weights(y_train, forecast_length)
    dtrain = xgb.DMatrix(x_train, label=y_train, missing=0, weight=sw)
    model = xgb.train(params, dtrain, 200, evals=[(dtrain, 'train')],
                       early_stopping_rounds=10, verbose_eval=0)

    imp = sorted(model.get_score(importance_type='gain').items(), key=lambda k: k[1], reverse=True)
    logger.info(f"    [XGB] OOF_RMSE={oof_rmse:.1f}  Top-5: {[f[0] for f in imp[:5]]}")
    return model, oof_rmse


def train_lgb(x_train, y_train, forecast_length, n_splits=5):
    """LightGBM: TimeSeriesSplit + 贝叶斯优化, 返回 (model, oof_rmse)"""
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

    imp = sorted(model.feature_importance('gain'), reverse=True)
    feat_names = model.feature_name()
    top_idx = np.argsort(imp)[::-1][:5]
    logger.info(f"    [LGB] OOF_RMSE={oof_rmse:.1f}  Top-5: {[feat_names[i] for i in top_idx]}")
    return model, oof_rmse


def train_catboost(x_train, y_train, forecast_length, n_splits=5):
    """CatBoost: TimeSeriesSplit + 贝叶斯优化, 返回 (model, oof_rmse)"""
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

    imp = model.get_feature_importance()
    top_idx = np.argsort(imp)[::-1][:5]
    logger.info(f"    [CatB] OOF_RMSE={oof_rmse:.1f}  Top-5: {[feat_columns[i] for i in top_idx]}")
    return model, oof_rmse


def train_ridge(x_train, y_train, forecast_length, n_splits=5):
    """Ridge 回归 + TimeSeriesSplit OOF 评估"""
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]

    # OOF 评估
    tscv = TimeSeriesSplit(n_splits=n_splits)
    oof = np.full(x_train.shape[0], np.nan)
    for _, (ti, vi) in enumerate(tscv.split(x_train)):
        m = Ridge(alpha=1.0)
        m.fit(x_train.iloc[ti], y_train.iloc[ti])
        oof[vi] = m.predict(x_train.iloc[vi])
    mask = ~np.isnan(oof)
    oof_rmse = np.sqrt(mean_squared_error(y_train[mask], oof[mask]))

    # 全量训练
    sw = _sample_weights(y_train, forecast_length)
    model = Ridge(alpha=1.0)
    model.fit(x_train, y_train, sample_weight=sw)
    logger.info(f"    [Ridge] OOF_RMSE={oof_rmse:.1f}  coef_norm={np.linalg.norm(model.coef_):.2f}")
    return model, oof_rmse


def _compute_adaptive_weights(oof_scores):
    """
    根据 OOF RMSE 计算自适应权重 (逆误差加权 + 归一化)

    Parameters
    ----------
    oof_scores : dict  {'xgb': rmse, 'lgb': rmse, ...}

    Returns
    -------
    weights : dict  {'xgb': w, 'lgb': w, ...}  sum=1.0
    """
    # 逆 RMSE 加权: w_i = (1/rmse_i) / sum(1/rmse_j)
    inv_scores = {k: 1.0 / v for k, v in oof_scores.items()}
    total = sum(inv_scores.values())
    weights = {k: v / total for k, v in inv_scores.items()}
    return weights


def train_all_models(x_train, y_train, forecast_length):
    """训练全部 4 个模型，返回模型字典和自适应权重"""
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    feature_list = list(feat_columns)

    models = {}
    oof_scores = {}

    logger.info("  训练 XGBoost...")
    models['xgb'], oof_scores['xgb'] = train_xgb(x_train, y_train, forecast_length)
    logger.info("  训练 LightGBM...")
    models['lgb'], oof_scores['lgb'] = train_lgb(x_train, y_train, forecast_length)
    logger.info("  训练 CatBoost...")
    models['catb'], oof_scores['catb'] = train_catboost(x_train, y_train, forecast_length)
    logger.info("  训练 Ridge...")
    models['ridge'], oof_scores['ridge'] = train_ridge(x_train, y_train, forecast_length)

    # 计算自适应权重
    weights = _compute_adaptive_weights(oof_scores)
    logger.info(f"  自适应权重: " + "  ".join(f"{k}={w:.3f}" for k, w in weights.items()))

    return models, feature_list, weights


def ensemble_predict(models, feature_list, weights, x_test):
    """
    自适应加权集成预测

    Parameters
    ----------
    models : dict
    feature_list : list
    weights : dict  {'xgb': 0.35, 'lgb': 0.10, ...}
    x_test : DataFrame
    """
    x_test = x_test[feature_list]
    preds = {}

    preds['xgb'] = models['xgb'].predict(xgb.DMatrix(x_test))
    preds['lgb'] = models['lgb'].predict(x_test)
    preds['catb'] = models['catb'].predict(x_test)
    preds['ridge'] = models['ridge'].predict(x_test)

    ensemble = np.zeros(len(x_test))
    for name, w in weights.items():
        ensemble += w * preds[name]

    # 负值 -> 0
    ensemble = np.maximum(ensemble, 0)
    for k in preds:
        preds[k] = np.maximum(preds[k], 0)

    return ensemble, preds


# ===========================================================================
# 5. 滚动回测
# ===========================================================================

def rolling_backtest(df):
    """
    按日滚动: 用前 TRAIN_DAYS 天训练 → 预测下一天 96 点
    预测期间: PRED_START ~ PRED_END
    """
    all_days = pd.date_range(PRED_START, PRED_END, freq='D', inclusive='left')
    results = []

    for pred_day in all_days:
        day_str = pred_day.strftime('%Y-%m-%d')
        # @AI_GENERATED
        # gap_days: 训练截止到 pred_day - 1 - GAP_DAYS（默认 D-2）
        train_end   = pred_day - timedelta(days=1 + GAP_DAYS)
        # @AI_GENERATED: end
        train_start = train_end - timedelta(days=TRAIN_DAYS)

        # 划分
        mask_tr = (df["record_time"] >= train_start) & (df["record_time"] <= train_end)
        mask_te = (df["record_time"] >= pred_day) & (df["record_time"] < pred_day + timedelta(days=1))
        train_raw = df[mask_tr].copy().reset_index(drop=True)
        test_raw  = df[mask_te].copy().reset_index(drop=True)

        if len(train_raw) < TRAIN_DAYS * DAILY_HORIZON * 0.7:
            logger.warning(f"{day_str}: 训练数据不足 ({len(train_raw)} 行), 跳过")
            continue
        if len(test_raw) == 0:
            logger.warning(f"{day_str}: 无测试数据, 跳过")
            continue

        # 合并后做特征工程 (lag/rolling 等会自然使用历史)
        # 关键：将测试集的 load 置为 NaN，防止 shift(1)/diff 等特征引用预测日真实值
        # @AI_GENERATED
        test_raw_masked = test_raw.copy()
        test_raw_masked["load"] = np.nan
        combined = pd.concat([train_raw, test_raw_masked], ignore_index=True)
        # @AI_GENERATED: end
        feat_all = build_features(combined)

        # 切分
        train_feat = feat_all[feat_all["record_time"] <= train_end].copy()
        test_feat  = feat_all[feat_all["record_time"] >= pred_day].copy()

        drop_cols = ["load", "record_time", "date"]
        feature_cols = [c for c in train_feat.columns
                        if c not in drop_cols and train_feat[c].dtype in ['float64','float32','int64','int32']]

        train_feat[feature_cols] = train_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
        test_feat[feature_cols]  = test_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)

        x_tr = train_feat[feature_cols]
        y_tr = train_feat["load"]
        # 真实值从原始 test_raw 取（test_feat["load"] 是 NaN，因为做了遮蔽防穿越）
        tr_ord = test_raw.sort_values("record_time").reset_index(drop=True)
        te_ord = test_feat.sort_values("record_time").reset_index(drop=True)
        n_te = min(len(tr_ord), len(te_ord))
        x_te = te_ord[feature_cols].iloc[:n_te]
        y_te = tr_ord["load"].to_numpy(dtype=float)[:n_te]

        logger.info(f"训练 {day_str}: train={len(x_tr)}, test={len(x_te)}")

        # 训练全部模型 (含自适应权重)
        models, flist, weights = train_all_models(x_tr, y_tr, forecast_length=DAILY_HORIZON)

        # 自适应加权集成预测
        y_pred, single_preds = ensemble_predict(models, flist, weights, x_te)

        day_res = pd.DataFrame({
            "record_time": te_ord["record_time"].values[:n_te],
            "true": y_te,
            "pred": y_pred,
            "pred_xgb": single_preds['xgb'],
            "pred_lgb": single_preds['lgb'],
            "pred_catb": single_preds['catb'],
            "pred_ridge": single_preds['ridge'],
            "pred_day": day_str,
        })
        results.append(day_res)

        m = evaluate(y_te, y_pred, label=day_str)
        m_xgb = evaluate(y_te, single_preds['xgb'], label="xgb")
        m_lgb = evaluate(y_te, single_preds['lgb'], label="lgb")
        m_catb = evaluate(y_te, single_preds['catb'], label="catb")
        m_ridge = evaluate(y_te, single_preds['ridge'], label="ridge")
        logger.info(f"  {day_str} Ensemble: SMAPE={m['SMAPE']:.2f}%  MAE={m['MAE']:.1f}  RMSE={m['RMSE']:.1f}")
        logger.info(f"    XGB={m_xgb['SMAPE']:.2f}%  LGB={m_lgb['SMAPE']:.2f}%  "
                     f"CatB={m_catb['SMAPE']:.2f}%  Ridge={m_ridge['SMAPE']:.2f}%")

        # 保存模型
        model_path = os.path.join(MODEL_DIR, f"ensemble_model_{day_str}.pkl")
        with open(model_path, "wb") as f:
            pickle.dump({"models": models, "feature_list": flist, "weights": weights}, f)
        logger.info(f"  模型已保存: {model_path}")

        del models
        gc.collect()

    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)


# ===========================================================================
# 6. 可视化
# ===========================================================================

def plot_results(results, output_dir):
    """生成所有对比图"""
    if results.empty:
        return

    # ---- 图1: 全局对比 (含多模型曲线) ----
    fig, axes = plt.subplots(2, 1, figsize=(20, 10), sharex=True)
    ax = axes[0]
    ax.plot(results["record_time"], results["true"], "k-", lw=1.2, label="True")
    ax.plot(results["record_time"], results["pred"], "#2ecc71", lw=1.0, alpha=0.85, label="Ensemble")
    ax.plot(results["record_time"], results["pred_xgb"], "#3498db", lw=0.6, alpha=0.5, label="XGBoost")
    ax.plot(results["record_time"], results["pred_lgb"], "#e67e22", lw=0.6, alpha=0.5, label="LightGBM")
    ax.plot(results["record_time"], results["pred_catb"], "#9b59b6", lw=0.6, alpha=0.5, label="CatBoost")
    ax.plot(results["record_time"], results["pred_ridge"], "#e74c3c", lw=0.6, alpha=0.4, label="Ridge")
    ax.set_ylabel("Load (kW)")
    ax.set_title("Weihai Load Forecast — Multi-Model Ensemble Backtest", fontsize=14)
    ax.legend(loc="upper right", ncol=3)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    err = results["pred"] - results["true"]
    ax.fill_between(results["record_time"], 0, err.values, where=err >= 0,
                     color="#2ecc71", alpha=0.5, label="Over-predict")
    ax.fill_between(results["record_time"], 0, err.values, where=err < 0,
                     color="#e74c3c", alpha=0.5, label="Under-predict")
    ax.axhline(0, color="k", lw=0.5)
    ax.set_ylabel("Error (Pred - True)")
    ax.set_xlabel("Time")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    plt.xticks(rotation=30)
    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "forecast_vs_true.png"), dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info("已保存 forecast_vs_true.png")

    # ---- 图2: 逐天对比 ----
    days = sorted(results["pred_day"].unique())
    n = len(days)
    ncols = 3
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 4 * nrows))
    axes = axes.flatten() if n > 1 else [axes]

    for idx, d in enumerate(days):
        ax = axes[idx]
        grp = results[results["pred_day"] == d]
        x = range(len(grp))
        ax.plot(x, grp["true"].values, "k-o", ms=1.5, lw=1.5, label="True")
        ax.plot(x, grp["pred"].values, color="#2ecc71", lw=1.2, label="Ensemble")
        ax.plot(x, grp["pred_xgb"].values, color="#3498db", lw=0.7, alpha=0.6, label="XGB")
        ax.plot(x, grp["pred_lgb"].values, color="#e67e22", lw=0.7, alpha=0.6, label="LGB")
        s = smape(grp["true"].values, grp["pred"].values)
        wd = pd.to_datetime(d).strftime('%a')
        ax.set_title(f"{d} ({wd})  SMAPE={s:.2f}%", fontsize=10)
        ax.set_xticks([0, 24, 48, 72, 95])
        ax.set_xticklabels(["00:00","06:00","12:00","18:00","23:45"], fontsize=7)
        ax.legend(fontsize=6, loc="upper right", ncol=2)
        ax.grid(True, alpha=0.3)

    for i in range(n, len(axes)):
        axes[i].set_visible(False)
    plt.suptitle("Daily Forecast Details", fontsize=16, y=1.01)
    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "daily_details.png"), dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info("已保存 daily_details.png")

    # ---- 图3: 每日 SMAPE 柱状图 ----
    fig, ax = plt.subplots(figsize=(10, 5))
    daily_metrics = []
    for d in days:
        grp = results[results["pred_day"] == d]
        daily_metrics.append(evaluate(grp["true"].values, grp["pred"].values, label=d))
    dm = pd.DataFrame(daily_metrics)
    colors = ['#e74c3c' if s > 5 else '#f39c12' if s > 3 else '#2ecc71' for s in dm["SMAPE"]]
    ax.bar(dm["label"], dm["SMAPE"], color=colors, alpha=0.85)
    ax.axhline(dm["SMAPE"].mean(), color="blue", ls="--", lw=1, label=f'Avg={dm["SMAPE"].mean():.2f}%')
    ax.set_ylabel("SMAPE (%)")
    ax.set_title("Daily SMAPE Distribution", fontsize=13)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    plt.xticks(rotation=30)
    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "daily_smape_bar.png"), dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info("已保存 daily_smape_bar.png")

    # ---- 图4: 散点图 ----
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(results["true"], results["pred"], alpha=0.3, s=8, color="#2ecc71", edgecolors='none')
    lo = min(results["true"].min(), results["pred"].min()) * 0.95
    hi = max(results["true"].max(), results["pred"].max()) * 1.05
    ax.plot([lo, hi], [lo, hi], "k--", lw=1)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("True Load")
    ax.set_ylabel("Predicted Load")
    ax.set_title("True vs Predicted", fontsize=14)
    r2 = 1 - np.sum((results["true"] - results["pred"])**2) / np.sum((results["true"] - results["true"].mean())**2)
    ax.text(0.05, 0.92, f"R² = {r2:.4f}\nSMAPE = {smape(results['true'].values, results['pred'].values):.2f}%\n"
             f"MAE = {mean_absolute_error(results['true'], results['pred']):.1f}\n"
             f"RMSE = {np.sqrt(mean_squared_error(results['true'], results['pred'])):.1f}",
            transform=ax.transAxes, fontsize=11, va='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "scatter.png"), dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info("已保存 scatter.png")


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 60)
    print("  威海负荷预测 — 滚动日回测验证（含 gap 逻辑）")
    print(f"  预测期间: {PRED_START} ~ {PRED_END}")
    print(f"  Gap 天数: {GAP_DAYS}（训练截止到预测日前 {1 + GAP_DAYS} 天）")
    print(f"  日粒度: 15min ({DAILY_HORIZON}点/天)")
    print("=" * 60)

    # @AI_GENERATED
    # 多训练天数对比实验
    train_days_list = [30, 45, 60, 90]
    all_summary = []

    for td in train_days_list:
        global TRAIN_DAYS
        TRAIN_DAYS = td
        print(f"\n{'='*60}")
        print(f"  训练天数: {td}d")
        print(f"{'='*60}")

        # 1. 加载数据
        df = load_weihai_data()

        # 2. 滚动回测
        results = rolling_backtest(df)

        if results.empty:
            logger.error(f"train_days={td}: 回测结果为空, 跳过")
            continue

        # 3. 保存预测结果（按训练天数分子目录）
        sub_dir = os.path.join(OUTPUT_DIR, f"train_days_{td}")
        os.makedirs(sub_dir, exist_ok=True)
        results.to_csv(os.path.join(sub_dir, "weihai_predictions.csv"), index=False)

        # 4. 总体评估
        overall = evaluate(results["true"].values, results["pred"].values, label=f"Ensemble_td{td}")
        logger.info(f"\ntrain_days={td} 总体: SMAPE={overall['SMAPE']:.2f}%  MAE={overall['MAE']:.1f}  RMSE={overall['RMSE']:.1f}")

        # 5. 按天评估
        daily = []
        for d, grp in results.groupby("pred_day"):
            daily.append(evaluate(grp["true"].values, grp["pred"].values, label=d))
        dm = pd.DataFrame(daily)
        dm.to_csv(os.path.join(sub_dir, "weihai_daily_metrics.csv"), index=False)

        # 6. 绘图
        plot_results(results, sub_dir)

        # 汇总
        all_summary.append({
            "train_days": td,
            "avg_smape": overall["SMAPE"],
            "avg_mae": overall["MAE"],
            "avg_rmse": overall["RMSE"],
        })

        print(f"\n  train_days={td} 完成，输出目录: {sub_dir}")

    # 汇总对比表
    if all_summary:
        summary_df = pd.DataFrame(all_summary)
        summary_path = os.path.join(OUTPUT_DIR, "multi_train_days_summary.csv")
        summary_df.to_csv(summary_path, index=False)
        print(f"\n{'='*60}")
        print("  多训练天数对比汇总")
        print(f"{'='*60}")
        print(summary_df.to_string(index=False))
        print(f"\n汇总已保存: {summary_path}")
    # @AI_GENERATED: end


if __name__ == "__main__":
    main()
