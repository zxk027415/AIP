#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
威海负荷预测 — 加气象数据的滚动日回测（本地版）

基于 run_weihai_backtest.py，增加气象特征：
- 温度、风速、气压、风向、降雨
- 温度平方、风寒指数、风速分量
- 气象滚动统计（shift(4) 防穿越）

防穿越策略：
- 负荷 load: 测试日遮蔽为 NaN
- 气象数据: 不遮蔽（预报数据，业务可获得）
- 气象滚动统计: shift(4) 即 1h 前开始计算
- gap_days=1: 训练截止到 D-2

用法：
    python run_weihai_backtest_weather.py
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
from loguru import logger
from datetime import timedelta
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from bayes_opt import BayesianOptimization

warnings.filterwarnings(action="ignore")

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
WEATHER_PATH = os.path.join(BASE_DIR, "..", "backend-service", "datasets", "ens_avg_weihai.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "weihai_backtest_weather")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 回测参数
PRED_START = "2026-03-01"
PRED_END = "2026-03-09"
TRAIN_DAYS_LIST = [30, 45, 60, 90, 120]
DAILY_HORIZON = 96
GAP_DAYS = 1


def smape(y_true, y_pred):
    denominator = np.abs(y_true) + np.abs(y_pred)
    mask = denominator > 1e-8
    return np.round(2.0 * np.mean(np.abs(y_pred[mask] - y_true[mask]) / denominator[mask]) * 100, 4)


def load_weihai_data():
    xlsx_path = os.path.join(DATASETS_DIR, "load_true_weihai_260407.xlsx")
    df = pd.read_excel(xlsx_path)
    df["record_time"] = pd.to_datetime(df["record_time"])
    load_df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
    load_df.rename(columns={"value": "load"}, inplace=True)
    load_df = load_df.sort_values("record_time").reset_index(drop=True)
    load_df = load_df.drop_duplicates(subset="record_time", keep="first")
    load_df = load_df.set_index("record_time").resample("15min").mean()
    load_df = load_df.interpolate().fillna(method="bfill").fillna(method="ffill")
    load_df.reset_index(inplace=True)
    logger.info(f"负荷数据: {load_df['record_time'].min()} ~ {load_df['record_time'].max()}, {len(load_df)} rows")
    return load_df


def load_weather():
    wdf = pd.read_csv(WEATHER_PATH)
    wdf["timestamp"] = pd.to_datetime(wdf["timestamp"])
    wdf = wdf.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="first")
    weather_cols = ["wind_speed", "wind_direction", "temperature", "pressure", "rainfall"]
    wdf = wdf.set_index("timestamp")[weather_cols]
    full_idx = pd.date_range(wdf.index.min(), wdf.index.max(), freq="15min")
    wdf = wdf.reindex(full_idx).interpolate(method="linear").ffill().bfill()
    wdf = wdf.reset_index().rename(columns={"index": "record_time"})
    logger.info(f"气象数据: {len(wdf)} rows (插值到15min)")
    return wdf


def if_workday(date):
    try:
        from chinese_calendar import is_workday
        return is_workday(pd.to_datetime(date))
    except Exception:
        return pd.to_datetime(date).weekday() <= 4


def build_features(df, time_field="record_time", load_field="load"):
    """构建无穿越特征（负荷+气象）"""
    feat = df.copy()
    feat[time_field] = pd.to_datetime(feat[time_field])
    dh = DAILY_HORIZON

    # ---- 时间特征 ----
    feat["is_holiday"] = feat[time_field].apply(lambda x: 0 if if_workday(x) else 1)
    feat["day"] = feat[time_field].dt.day
    feat["yday"] = feat[time_field].dt.dayofyear
    feat["month"] = feat[time_field].dt.month
    feat["dayofweek"] = feat[time_field].dt.dayofweek
    feat["hour"] = feat[time_field].dt.hour
    feat["minute"] = feat[time_field].dt.minute
    feat["period"] = feat["hour"] * 4 + feat["minute"] // 15
    feat["hour_sin"] = np.sin(2 * np.pi * feat["hour"] / 24)
    feat["hour_cos"] = np.cos(2 * np.pi * feat["hour"] / 24)
    feat["wday_sin"] = np.sin(2 * np.pi * feat["dayofweek"] / 7)
    feat["wday_cos"] = np.cos(2 * np.pi * feat["dayofweek"] / 7)
    feat["yday_sin"] = np.sin(2 * np.pi * feat["yday"] / 365)
    feat["yday_cos"] = np.cos(2 * np.pi * feat["yday"] / 365)
    feat["month_sin"] = np.sin(2 * np.pi * feat["month"] / 12)
    feat["month_cos"] = np.cos(2 * np.pi * feat["month"] / 12)

    # ---- Lag 特征 ----
    for lag in [1, 2, 3, 4, 5, 6, 7, 14, 21, 28]:
        feat[f"lag_{lag}d"] = feat[load_field].shift(lag * dh)
    feat["same_time_2w"] = (feat["lag_7d"] + feat["lag_14d"]) / 2
    feat["same_time_3w"] = (feat["lag_7d"] + feat["lag_14d"] + feat["lag_21d"]) / 3

    # ---- 差分特征 ----
    load_prev = feat[load_field].shift(1)
    feat["diff_1"] = load_prev - load_prev.shift(1)
    feat["diff_96"] = load_prev - load_prev.shift(dh)
    feat["diff_192"] = load_prev - load_prev.shift(2 * dh)
    feat["diff_96_of_96"] = load_prev.shift(dh - 1) - load_prev.shift(2 * dh - 1)

    # ---- 滚动统计 ----
    load_yd = feat[load_field].shift(dh)
    for w in [4, 8, 12, 24, 48, 96]:
        feat[f"roll_{w}_mean"] = load_yd.rolling(w, center=False, min_periods=1).mean()
        feat[f"roll_{w}_std"] = load_yd.rolling(w, center=False, min_periods=1).std()
        feat[f"roll_{w}_max"] = load_yd.rolling(w, center=False, min_periods=1).max()
        feat[f"roll_{w}_min"] = load_yd.rolling(w, center=False, min_periods=1).min()

    # ---- 日统计特征 ----
    feat["date"] = feat[time_field].dt.strftime("%Y-%m-%d")
    ds = feat.groupby("date")[load_field].agg(["mean", "max", "min", "std"]).reset_index()
    ds.columns = ["date", "day_mean", "day_max", "day_min", "day_std"]
    ds["day_pv"] = ds["day_max"] - ds["day_min"]
    ds["day_pv_rate"] = ds["day_pv"] / ds["day_max"].replace(0, np.nan)
    ds["day_rate"] = ds["day_mean"] / ds["day_max"].replace(0, np.nan)
    for c in ["day_mean", "day_max", "day_min", "day_std", "day_pv", "day_pv_rate", "day_rate"]:
        ds[c] = ds[c].shift(1)
    feat = feat.merge(ds, on="date", how="left")

    ds2 = feat.groupby("date")["lag_1d"].agg(["mean", "std"]).reset_index()
    ds2.columns = ["date", "lag1d_day_mean", "lag1d_day_std"]
    ds2["lag1d_day_mean"] = ds2["lag1d_day_mean"].shift(1)
    ds2["lag1d_day_std"] = ds2["lag1d_day_std"].shift(1)
    feat = feat.merge(ds2, on="date", how="left")

    # ---- 气象衍生特征（不遮蔽，预报数据可用）----
    if "temperature" in feat.columns:
        feat["temp_sq"] = feat["temperature"] ** 2
        feat["wind_chill"] = (13.12 + 0.6215 * feat["temperature"]
                              - 11.37 * (feat["wind_speed"] * 3.6) ** 0.16
                              + 0.3965 * feat["temperature"] * (feat["wind_speed"] * 3.6) ** 0.16)
        wind_rad = np.radians(feat["wind_direction"])
        feat["wind_u"] = feat["wind_speed"] * np.sin(wind_rad)
        feat["wind_v"] = feat["wind_speed"] * np.cos(wind_rad)

        # 气象滚动统计（shift(4) = 1h 前）
        for col in ["temperature", "wind_speed", "pressure"]:
            shifted = feat[col].shift(4)
            for w in [4, 16, 96]:
                feat[f"{col}_roll_mean_{w}"] = shifted.rolling(w, min_periods=1).mean()
                feat[f"{col}_roll_std_{w}"] = shifted.rolling(w, min_periods=1).std()

        feat["temp_change_4h"] = feat["temperature"] - feat["temperature"].shift(16)
        feat["pressure_change_4h"] = feat["pressure"] - feat["pressure"].shift(16)

    return feat


def _sample_weights(label, forecast_length, ac=0.99):
    n = len(label)
    return np.array([pow(ac, i // forecast_length) for i in range(n)])[::-1]


def train_all_models(x_train, y_train, forecast_length):
    """训练 4 个模型 + OOF 权重"""
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    models = {}
    oof_scores = {}

    # XGB
    def xgb_cv(eta, max_depth, min_child_weight, subsample, lambdas):
        tscv = TimeSeriesSplit(n_splits=5)
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
        'eta': (0.01, 0.15), 'max_depth': (2, 8),
        'min_child_weight': (0.3, 10), 'subsample': (0.5, 1), 'lambdas': (0.1, 100),
    }, random_state=42, verbose=0)
    bo.maximize(init_points=3, n_iter=12)
    oof_scores['xgb'] = -bo.max['target']
    params = bo.max['params']
    params['max_depth'] = int(params['max_depth'])
    sw = _sample_weights(y_train, forecast_length)
    dtrain = xgb.DMatrix(x_train, label=y_train, missing=0, weight=sw)
    models['xgb'] = xgb.train(params, dtrain, 200, evals=[(dtrain, 'train')],
                               early_stopping_rounds=10, verbose_eval=0)

    # LGB
    def lgb_cv(learning_rate, max_depth, num_leaves, min_child_samples, subsample):
        tscv = TimeSeriesSplit(n_splits=5)
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
        'learning_rate': (0.01, 0.15), 'max_depth': (2, 8),
        'num_leaves': (15, 63), 'min_child_samples': (5, 50), 'subsample': (0.5, 1),
    }, random_state=42, verbose=0)
    bo.maximize(init_points=3, n_iter=12)
    oof_scores['lgb'] = -bo.max['target']
    params = bo.max['params']
    params['max_depth'] = int(params['max_depth'])
    params['num_leaves'] = int(params['num_leaves'])
    params['min_child_samples'] = int(params['min_child_samples'])
    params.update({'objective': 'regression', 'metric': 'rmse', 'verbosity': -1, 'seed': 42, 'nthread': 4})
    models['lgb'] = lgb.train(params, lgb.Dataset(x_train, label=y_train, weight=sw),
                              200, valid_sets=[lgb.Dataset(x_train, label=y_train)],
                              callbacks=[lgb.early_stopping(10, verbose=False), lgb.log_evaluation(0)])

    # CatBoost
    def cb_cv(learning_rate, depth, l2_leaf_reg, bagging_temperature):
        tscv = TimeSeriesSplit(n_splits=5)
        oof = np.full(x_train.shape[0], np.nan)
        for _, (ti, vi) in enumerate(tscv.split(x_train)):
            p = {'loss_function': 'RMSE', 'verbose': 0,
                 'learning_rate': float(learning_rate), 'depth': int(depth),
                 'l2_leaf_reg': float(l2_leaf_reg),
                 'bagging_temperature': float(bagging_temperature),
                 'random_seed': 42, 'thread_count': 4}
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
    }, random_state=42, verbose=0)
    bo.maximize(init_points=3, n_iter=12)
    oof_scores['catb'] = -bo.max['target']
    params = bo.max['params']
    params['depth'] = int(params['depth'])
    params.update({'loss_function': 'RMSE', 'verbose': 0, 'random_seed': 42, 'thread_count': 4})
    models['catb'] = CatBoostRegressor(iterations=200, **params)
    models['catb'].fit(x_train, y_train, sample_weight=sw, early_stopping_rounds=10, verbose=0)

    # Ridge
    tscv = TimeSeriesSplit(n_splits=5)
    oof = np.full(x_train.shape[0], np.nan)
    for _, (ti, vi) in enumerate(tscv.split(x_train)):
        m = Ridge(alpha=1.0)
        m.fit(x_train.iloc[ti], y_train.iloc[ti])
        oof[vi] = m.predict(x_train.iloc[vi])
    mask = ~np.isnan(oof)
    oof_scores['ridge'] = np.sqrt(mean_squared_error(y_train[mask], oof[mask]))
    models['ridge'] = Ridge(alpha=1.0)
    models['ridge'].fit(x_train, y_train, sample_weight=sw)

    # 权重
    inv_scores = {k: 1.0 / v for k, v in oof_scores.items()}
    total = sum(inv_scores.values())
    weights = {k: v / total for k, v in inv_scores.items()}
    logger.info(f"  权重: " + "  ".join(f"{k}={w:.3f}" for k, w in weights.items()))

    return models, list(feat_columns), weights


def ensemble_predict(models, feature_list, weights, x_test):
    x_test = x_test[feature_list]
    preds = {}
    preds['xgb'] = models['xgb'].predict(xgb.DMatrix(x_test))
    preds['lgb'] = models['lgb'].predict(x_test)
    preds['catb'] = models['catb'].predict(x_test)
    preds['ridge'] = models['ridge'].predict(x_test)
    ensemble = np.zeros(len(x_test))
    for name, w in weights.items():
        ensemble += w * preds[name]
    return np.maximum(ensemble, 0), preds


def main():
    print("=" * 60)
    print("  威海负荷预测 — 加气象数据多训练天数对比（本地版）")
    print(f"  train_days={TRAIN_DAYS_LIST}, gap_days={GAP_DAYS}")
    print("=" * 60)

    load_df = load_weihai_data()
    weather_df = load_weather()

    # 合并
    merged = load_df.merge(weather_df, on="record_time", how="left")
    for col in ["wind_speed", "wind_direction", "temperature", "pressure", "rainfall"]:
        merged[col] = merged[col].interpolate().ffill().bfill()
    logger.info(f"合并后: {len(merged)} rows")

    all_days = pd.date_range(PRED_START, PRED_END, freq='D', inclusive='left')
    all_summary = []

    for TRAIN_DAYS in TRAIN_DAYS_LIST:
        print(f"\n{'='*60}")
        print(f"  训练天数: {TRAIN_DAYS}d")
        print(f"{'='*60}")
        results = []

        for pred_day in all_days:
            day_str = pred_day.strftime('%Y-%m-%d')
            train_end = pred_day - timedelta(days=1 + GAP_DAYS)
            train_start = train_end - timedelta(days=TRAIN_DAYS)

            mask_tr = (merged["record_time"] >= train_start) & (merged["record_time"] <= train_end)
            mask_te = (merged["record_time"] >= pred_day) & (merged["record_time"] < pred_day + timedelta(days=1))
            train_raw = merged[mask_tr].copy().reset_index(drop=True)
            test_raw = merged[mask_te].copy().reset_index(drop=True)

            if len(train_raw) < TRAIN_DAYS * DAILY_HORIZON * 0.5 or len(test_raw) == 0:
                logger.warning(f"{day_str}: 数据不足, 跳过")
                continue

            test_masked = test_raw.copy()
            test_masked["load"] = np.nan
            combined = pd.concat([train_raw, test_masked], ignore_index=True)

            feat_all = build_features(combined)
            train_feat = feat_all[feat_all["record_time"] <= train_end].copy()
            test_feat = feat_all[feat_all["record_time"] >= pred_day].copy()

            drop_cols = ["load", "record_time", "date"]
            feature_cols = [c for c in train_feat.columns
                            if c not in drop_cols and train_feat[c].dtype in ['float64', 'float32', 'int64', 'int32']]

            train_feat[feature_cols] = train_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
            test_feat[feature_cols] = test_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)

            x_tr = train_feat[feature_cols]
            y_tr = train_feat["load"]
            y_true = test_raw.sort_values("record_time")["load"].to_numpy(dtype=float)
            te_ord = test_feat.sort_values("record_time").reset_index(drop=True)
            n_te = min(len(te_ord), len(y_true))
            x_te = te_ord[feature_cols].iloc[:n_te]
            y_true = y_true[:n_te]

            logger.info(f"[td={TRAIN_DAYS}] {day_str}: train={len(x_tr)}, test={n_te}")
            models, flist, weights = train_all_models(x_tr, y_tr, DAILY_HORIZON)
            y_pred, _ = ensemble_predict(models, flist, weights, x_te)

            s = smape(y_true, y_pred)
            results.append({"date": day_str, "smape": s})
            logger.info(f"  {day_str} SMAPE={s:.2f}%")
            del models
            gc.collect()

        if results:
            avg = np.mean([r['smape'] for r in results])
            all_summary.append({"train_days": TRAIN_DAYS, "avg_smape": round(avg, 4)})
            print(f"\n  train_days={TRAIN_DAYS} 平均 SMAPE: {avg:.2f}%")
            sub_dir = os.path.join(OUTPUT_DIR, f"train_days_{TRAIN_DAYS}")
            os.makedirs(sub_dir, exist_ok=True)
            pd.DataFrame(results).to_csv(os.path.join(sub_dir, "daily_metrics.csv"), index=False)

    # 汇总
    print("\n" + "=" * 60)
    print("  多训练天数对比汇总（本地+气象）")
    print("=" * 60)
    summary_df = pd.DataFrame(all_summary)
    print(summary_df.to_string(index=False))
    summary_df.to_csv(os.path.join(OUTPUT_DIR, "multi_train_days_summary.csv"), index=False)
    print(f"\n汇总已保存: {OUTPUT_DIR}/multi_train_days_summary.csv")


if __name__ == "__main__":
    main()
