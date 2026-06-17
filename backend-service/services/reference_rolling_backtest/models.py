# -*- coding: utf-8 -*-
"""
多模型训练 + 逆 RMSE 自适应加权集成（与 run_weihai_backtest.py 一致）。
在缺少 lightgbm/catboost 时自动降级为 xgb+ridge，保证平台可装最小依赖集。
"""
# BLAS threading fix: prevent macOS libomp deadlock under ThreadPoolExecutor
import os as _osb
for _k, _v in [("OMP_NUM_THREADS","1"),("OPENBLAS_NUM_THREADS","1"),("MKL_NUM_THREADS","1"),("VECLIB_MAXIMUM_THREADS","1"),("NUMEXPR_NUM_THREADS","1")]:
    _osb.environ.setdefault(_k, _v)
del _osb, _k, _v

import gc
import os
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from bayes_opt import BayesianOptimization
from loguru import logger
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

from .config import ReferenceBacktestConfig

# 并发训练安全：BayesianOptimization 内部的 scipy GP 拟合在多线程并发时
# 可能因 BLAS 线程不安全导致死锁。当 batch_size > 1 时，用锁串行化 BO 的 GP 更新。
# batch_size=1 时此锁无竞争，零开销。
import threading as _threading

_BO_LOCK = _threading.Lock()


def _bo_maximize_safe(bo: BayesianOptimization, init_points: int, n_iter: int) -> None:
    """线程安全的 BO maximize。"""
    _acquired = _BO_LOCK.acquire(timeout=300)
    if not _acquired:
        logger.warning('_BO_LOCK timeout 300s - running unprotected')
    try:
        bo.maximize(init_points=init_points, n_iter=n_iter)
    finally:
        if _acquired:
            _BO_LOCK.release()

try:
    import lightgbm as lgb

    _HAS_LGB = True
except Exception:
    lgb = None
    _HAS_LGB = False

try:
    from catboost import CatBoostRegressor

    _HAS_CAT = True
except Exception:
    CatBoostRegressor = None
    _HAS_CAT = False


def _sample_weights(label, forecast_length: int, ac: float = 0.99):
    n = len(label)
    return np.array([pow(ac, i // forecast_length) for i in range(n)])[::-1]


def _train_thread_count() -> int:
    try:
        return max(1, int(os.getenv("REFERENCE_BACKTEST_MODEL_THREADS", "1") or 1))
    except (TypeError, ValueError):
        return 1


def _clamp_ts_cv_splits(n_splits: int, n_samples: int) -> int:
    """
    TimeSeriesSplit 要求 n_splits <= n_samples - 1（gap=0）。
    预检 max_rows 较小时训练行数极少，不钳制会触发 CatBoost/LGB/XGB CV 报错。
    """
    if n_samples <= 2:
        return 2
    cap = n_samples - 1
    want = max(2, int(n_splits))
    return max(2, min(want, cap))



def _mape_percent(y_true, y_pred) -> float:
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    mask = np.abs(yt) > 1e-8
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((yt[mask] - yp[mask]) / yt[mask])) * 100.0)


def compute_cv_fold_metrics(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    n_splits: int = 5,
) -> List[Dict[str, float]]:
    """
    Compute lightweight TimeSeriesSplit diagnostics for Dataset_Profiler.

    Loss values are RMSE. The production ensemble still trains through
    train_all_models; this helper only exposes stable per-fold diagnostics.
    """
    if x_train is None or y_train is None:
        return []
    if len(x_train) < 3 or len(y_train) < 3:
        return []

    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    y_train = pd.Series(y_train).reset_index(drop=True)
    max_splits = max(0, min(int(n_splits), len(x_train) - 1))
    if max_splits < 2:
        return []

    metrics: List[Dict[str, float]] = []
    tscv = TimeSeriesSplit(n_splits=max_splits)
    for fold_idx, (ti, vi) in enumerate(tscv.split(x_train), start=1):
        model = Ridge(alpha=1.0)
        model.fit(x_train.iloc[ti], y_train.iloc[ti])
        train_pred = model.predict(x_train.iloc[ti])
        val_pred = model.predict(x_train.iloc[vi])
        train_loss = float(np.sqrt(mean_squared_error(y_train.iloc[ti], train_pred)))
        val_loss = float(np.sqrt(mean_squared_error(y_train.iloc[vi], val_pred)))
        val_mape = _mape_percent(y_train.iloc[vi], val_pred)
        metrics.append(
            {
                "fold_id": int(fold_idx),
                "train_loss": round(train_loss, 6),
                "val_loss": round(val_loss, 6),
                "val_mape": round(val_mape, 6),
            }
        )
    return metrics

def train_xgb(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    forecast_length: int,
    cfg: ReferenceBacktestConfig,
) -> Tuple[Any, float]:
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    n_splits = _clamp_ts_cv_splits(cfg.n_splits, len(x_train))
    n_bo = cfg.bo_n_iter
    init = cfg.bo_init_points

    def xgb_cv(eta, max_depth, min_child_weight, subsample, lambdas):
        tscv = TimeSeriesSplit(n_splits=n_splits)
        oof = np.full(x_train.shape[0], np.nan)
        for _, (ti, vi) in enumerate(tscv.split(x_train)):
            dtrn = xgb.DMatrix(x_train.iloc[ti], label=y_train.iloc[ti], missing=0)
            dval = xgb.DMatrix(x_train.iloc[vi], label=y_train.iloc[vi], missing=0)
            p = {
                "objective": "reg:squarederror",
                "eval_metric": "rmse",
                "verbosity": 0,
                "max_depth": int(max_depth),
                "min_child_weight": float(min_child_weight),
                "subsample": float(subsample),
                "eta": float(eta),
                "lambda": float(lambdas),
                "seed": 42,
                "nthread": _train_thread_count(),
            }
            m = xgb.train(p, dtrn, 100, evals=[(dtrn, "train"), (dval, "valid")])
            oof[vi] = m.predict(dval)
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))

    if not cfg.use_bayesian_tuning:
        tscv = TimeSeriesSplit(n_splits=n_splits)
        oof = np.full(x_train.shape[0], np.nan)
        for _, (ti, vi) in enumerate(tscv.split(x_train)):
            dtrn = xgb.DMatrix(x_train.iloc[ti], label=y_train.iloc[ti], missing=0)
            dval = xgb.DMatrix(x_train.iloc[vi], label=y_train.iloc[vi], missing=0)
            p = {
                "objective": "reg:squarederror",
                "eval_metric": "rmse",
                "verbosity": 0,
                "max_depth": 5,
                "min_child_weight": 3.0,
                "subsample": 0.8,
                "eta": 0.05,
                "lambda": 10.0,
                "seed": 42,
                "nthread": _train_thread_count(),
            }
            m = xgb.train(p, dtrn, 100, evals=[(dtrn, "train"), (dval, "valid")])
            oof[vi] = m.predict(dval)
        mask = ~np.isnan(oof)
        oof_rmse = float(np.sqrt(mean_squared_error(y_train[mask], oof[mask])))
    else:
        bo = BayesianOptimization(
            f=xgb_cv,
            pbounds={
                "eta": (0.01, 0.15),
                "max_depth": (2, 8),
                "min_child_weight": (0.3, 10),
                "subsample": (0.5, 1),
                "lambdas": (0.1, 100),
            },
            random_state=42,
        )
        _bo_maximize_safe(bo, init_points=init, n_iter=n_bo)
        oof_rmse = -bo.max["target"]
        rawp = bo.max["params"]
        p_train = {
            "objective": "reg:squarederror",
            "eval_metric": "rmse",
            "verbosity": 0,
            "max_depth": int(rawp["max_depth"]),
            "min_child_weight": float(rawp["min_child_weight"]),
            "subsample": float(rawp["subsample"]),
            "eta": float(rawp["eta"]),
            "lambda": float(rawp["lambdas"]),
            "seed": 42,
            "nthread": _train_thread_count(),
        }
        sw = _sample_weights(y_train, forecast_length)
        dtrain = xgb.DMatrix(x_train, label=y_train, missing=0, weight=sw)
        model = xgb.train(
            p_train, dtrain, cfg.n_estimators_final, evals=[(dtrain, "train")]
        )
        imp = sorted(model.get_score(importance_type="gain").items(), key=lambda k: k[1], reverse=True)
        logger.info(f"    [XGB] OOF_RMSE={oof_rmse:.1f}  Top-5: {[f[0] for f in imp[:5]]}")
        return model, oof_rmse

    sw = _sample_weights(y_train, forecast_length)
    dtrain = xgb.DMatrix(x_train, label=y_train, missing=0, weight=sw)
    params = {
        "objective": "reg:squarederror",
        "eval_metric": "rmse",
        "verbosity": 0,
        "max_depth": 5,
        "min_child_weight": 3.0,
        "subsample": 0.8,
        "eta": 0.05,
        "lambda": 10.0,
        "seed": 42,
        "nthread": _train_thread_count(),
    }
    model = xgb.train(
        params, dtrain, cfg.n_estimators_final, evals=[(dtrain, "train")]
    )
    return model, oof_rmse


def train_lgb(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    forecast_length: int,
    cfg: ReferenceBacktestConfig,
) -> Tuple[Any, float]:
    if not _HAS_LGB:
        raise RuntimeError("lightgbm not available")
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    n_splits = _clamp_ts_cv_splits(cfg.n_splits, len(x_train))
    n_bo = cfg.bo_n_iter
    init = cfg.bo_init_points

    def lgb_cv(learning_rate, max_depth, num_leaves, min_child_samples, subsample):
        tscv = TimeSeriesSplit(n_splits=n_splits)
        oof = np.full(x_train.shape[0], np.nan)
        for _, (ti, vi) in enumerate(tscv.split(x_train)):
            p = {
                "objective": "regression",
                "metric": "rmse",
                "verbosity": -1,
                "learning_rate": float(learning_rate),
                "max_depth": int(max_depth),
                "num_leaves": int(num_leaves),
                "min_child_samples": int(min_child_samples),
                "subsample": float(subsample),
                "seed": 42,
                "nthread": _train_thread_count(),
            }
            m = lgb.train(
                p,
                lgb.Dataset(x_train.iloc[ti], label=y_train.iloc[ti]),
                100,
                valid_sets=[lgb.Dataset(x_train.iloc[vi], label=y_train.iloc[vi])],
                callbacks=[lgb.early_stopping(5, verbose=False), lgb.log_evaluation(0)],
            )
            oof[vi] = m.predict(x_train.iloc[vi])
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))

    if not cfg.use_bayesian_tuning:
        raise ValueError("lgb with use_bayesian_tuning False not implemented; enable tuning")
    bo = BayesianOptimization(
        f=lgb_cv,
        pbounds={
            "learning_rate": (0.01, 0.15),
            "max_depth": (2, 8),
            "num_leaves": (15, 63),
            "min_child_samples": (5, 50),
            "subsample": (0.5, 1),
        },
        random_state=42,
    )
    _bo_maximize_safe(bo, init_points=init, n_iter=n_bo)
    oof_rmse = -bo.max["target"]
    params = bo.max["params"]
    params["max_depth"] = int(params["max_depth"])
    params["num_leaves"] = int(params["num_leaves"])
    params["min_child_samples"] = int(params["min_child_samples"])
    params.update(
        {
            "objective": "regression",
            "metric": "rmse",
            "verbosity": -1,
            "seed": 42,
            "nthread": _train_thread_count(),
        }
    )
    sw = _sample_weights(y_train, forecast_length)
    model = lgb.train(
        params,
        lgb.Dataset(x_train, label=y_train, weight=sw),
        cfg.n_estimators_final,
        valid_sets=[lgb.Dataset(x_train, label=y_train)],
        callbacks=[lgb.early_stopping(10, verbose=False), lgb.log_evaluation(0)],
    )
    return model, oof_rmse


def train_catboost(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    forecast_length: int,
    cfg: ReferenceBacktestConfig,
) -> Tuple[Any, float]:
    if not _HAS_CAT:
        raise RuntimeError("catboost not available")
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    n_splits = _clamp_ts_cv_splits(cfg.n_splits, len(x_train))
    n_bo = cfg.bo_n_iter
    init = cfg.bo_init_points

    def cb_cv(learning_rate, depth, l2_leaf_reg, bagging_temperature):
        tscv = TimeSeriesSplit(n_splits=n_splits)
        oof = np.full(x_train.shape[0], np.nan)
        for _, (ti, vi) in enumerate(tscv.split(x_train)):
            p = {
                "loss_function": "RMSE",
                "verbose": False,
                "learning_rate": float(learning_rate),
                "depth": int(depth),
                "l2_leaf_reg": float(l2_leaf_reg),
                "bagging_temperature": float(bagging_temperature),
                "random_seed": 42,
                "thread_count": _train_thread_count(),
            }
            m = CatBoostRegressor(**p, iterations=100)
            m.fit(
                x_train.iloc[ti],
                y_train.iloc[ti],
                eval_set=(x_train.iloc[vi], y_train.iloc[vi]),
                early_stopping_rounds=5,
                verbose=0,
            )
            oof[vi] = m.predict(x_train.iloc[vi])
            del m
        mask = ~np.isnan(oof)
        return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))

    if not cfg.use_bayesian_tuning:
        raise ValueError("catb with use_bayesian_tuning False not implemented")
    bo = BayesianOptimization(
        f=cb_cv,
        pbounds={
            "learning_rate": (0.01, 0.15),
            "depth": (2, 8),
            "l2_leaf_reg": (0.1, 10),
            "bagging_temperature": (0, 1),
        },
        random_state=42,
    )
    _bo_maximize_safe(bo, init_points=init, n_iter=n_bo)
    oof_rmse = -bo.max["target"]
    params = bo.max["params"]
    params["depth"] = int(params["depth"])
    params.update(
        {
            "loss_function": "RMSE",
            "verbose": False,
            "random_seed": 42,
            "thread_count": _train_thread_count(),
        }
    )
    sw = _sample_weights(y_train, forecast_length)
    model = CatBoostRegressor(iterations=cfg.n_estimators_final, **params)
    model.fit(x_train, y_train, sample_weight=sw, early_stopping_rounds=10, verbose=0)
    return model, oof_rmse


def train_ridge(
    x_train: pd.DataFrame, y_train: pd.Series, forecast_length: int, cfg: ReferenceBacktestConfig
) -> Tuple[Any, float]:
    feat_columns = sorted(x_train.columns)
    x_train = x_train[feat_columns]
    n_splits = _clamp_ts_cv_splits(cfg.n_splits, len(x_train))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    oof = np.full(x_train.shape[0], np.nan)
    for _, (ti, vi) in enumerate(tscv.split(x_train)):
        m = Ridge(alpha=1.0)
        m.fit(x_train.iloc[ti], y_train.iloc[ti])
        oof[vi] = m.predict(x_train.iloc[vi])
    mask = ~np.isnan(oof)
    oof_rmse = float(np.sqrt(mean_squared_error(y_train[mask], oof[mask])))
    sw = _sample_weights(y_train, forecast_length)
    model = Ridge(alpha=1.0)
    model.fit(x_train, y_train, sample_weight=sw)
    return model, oof_rmse


def _compute_adaptive_weights(oof_scores: Dict[str, float]) -> Dict[str, float]:
    inv_scores = {k: 1.0 / v for k, v in oof_scores.items() if v and v > 0}
    total = sum(inv_scores.values())
    if total <= 0:
        n = len(inv_scores) or 1
        return {k: 1.0 / n for k in oof_scores}
    return {k: inv_scores[k] / total for k in inv_scores}


def train_all_models(
    x_tr: pd.DataFrame, y_tr: pd.Series, forecast_length: int, cfg: ReferenceBacktestConfig
) -> Tuple[Dict[str, Any], List[str], Dict[str, float]]:
    feat_columns = sorted(x_tr.columns)
    x_tr = x_tr[feat_columns]
    feature_list = list(feat_columns)
    models: Dict[str, Any] = {}
    oof_scores: Dict[str, float] = {}
    want = [m for m in cfg.models if m in ("xgb", "lgb", "catb", "ridge")]
    if "xgb" in want:
        logger.info("  训练 XGBoost...")
        models["xgb"], oof_scores["xgb"] = train_xgb(x_tr, y_tr, forecast_length, cfg)
    if "lgb" in want and _HAS_LGB:
        logger.info("  训练 LightGBM...")
        models["lgb"], oof_scores["lgb"] = train_lgb(x_tr, y_tr, forecast_length, cfg)
    elif "lgb" in want:
        logger.warning("  LightGBM 未安装，跳过")
    if "catb" in want and _HAS_CAT:
        logger.info("  训练 CatBoost...")
        models["catb"], oof_scores["catb"] = train_catboost(x_tr, y_tr, forecast_length, cfg)
    elif "catb" in want:
        logger.warning("  CatBoost 未安装，跳过")
    if "ridge" in want:
        logger.info("  训练 Ridge...")
        models["ridge"], oof_scores["ridge"] = train_ridge(x_tr, y_tr, forecast_length, cfg)
    weights = _compute_adaptive_weights(oof_scores)
    logger.info("  自适应权重: " + "  ".join(f"{k}={w:.3f}" for k, w in weights.items()))
    return models, feature_list, weights


def ensemble_predict(
    models: Dict[str, Any], feature_list: List[str], weights: Dict[str, float], x_test: pd.DataFrame
):
    x_test = x_test[feature_list]
    preds: Dict[str, np.ndarray] = {}
    if "xgb" in models:
        preds["xgb"] = models["xgb"].predict(xgb.DMatrix(x_test, missing=0))
    if "lgb" in models:
        preds["lgb"] = models["lgb"].predict(x_test)
    if "catb" in models:
        preds["catb"] = models["catb"].predict(x_test)
    if "ridge" in models:
        preds["ridge"] = models["ridge"].predict(x_test)
    ensemble = np.zeros(len(x_test))
    for name, w in weights.items():
        if name in preds:
            ensemble = ensemble + w * preds[name]
    ensemble = np.maximum(ensemble, 0)
    for k in preds:
        preds[k] = np.maximum(preds[k], 0)
    return ensemble, preds


def release_models(models: Dict[str, Any]) -> None:
    del models
    gc.collect()
