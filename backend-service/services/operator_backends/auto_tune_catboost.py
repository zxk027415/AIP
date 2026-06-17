# @AI_GENERATED
"""
auto_tune_catboost operator backend — CatBoost Bayesian hyperparameter optimization.

Reuses models_pkg/trainer.py xgb_model_trainer BayesianOptimization logic.
Params: n_trials (default 50), metric (default "rmse"), cv_folds (default 5).
Returns best_params dict and trained CatBoostRegressor model.
"""
import gc
import json
import inspect

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from loguru import logger
from sklearn.model_selection import KFold, TimeSeriesSplit
from sklearn.metrics import mean_squared_error as mse

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "auto_tune_catboost"


def _ensure_numpy_legacy_aliases() -> None:
    """
    Compatibility shim for third-party libs that still reference deprecated NumPy aliases
    (e.g. np.float) removed in NumPy 2.x.
    """
    if not hasattr(np, "float"):
        np.float = float  # type: ignore[attr-defined]


def _sample_weights(n_samples: int, forecast_length: int, decay: float = 0.99) -> np.ndarray:
    """Generate sample weights — recent data weighted higher."""
    weights = []
    for i in range(n_samples):
        weights.append(pow(decay, i // max(forecast_length, 1)))
    return np.array(list(reversed(weights)))


def _to_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "on")
    return bool(v)


def _strict_alignment_enabled(params: dict, options: dict) -> bool:
    v = params.get("strict_alignment_mode")
    if v is None:
        v = options.get("strict_alignment_mode")
    if v is None:
        gcfg = params.get("_global_config") or {}
        if isinstance(gcfg, dict):
            v = gcfg.get("strict_alignment_mode")
    return _to_bool(v, default=False)


def _cb_crossval(
    depth,
    learning_rate,
    l2_leaf_reg,
    border_count,
    random_strength,
    x_train,
    y_train,
    n_folds,
    cv_strategy: str,
    seed: int = 42,
    nthread: int = 4,
):
    """Cross-validation objective for Bayesian optimization."""
    if cv_strategy == "timeseries":
        folds = TimeSeriesSplit(n_splits=n_folds)
    else:
        folds = KFold(n_splits=n_folds, shuffle=True, random_state=10)
    oof = np.full(x_train.shape[0], np.nan)
    for fold_, (trn_idx, val_idx) in enumerate(folds.split(x_train, y_train)):
        model = CatBoostRegressor(
            depth=int(depth),
            learning_rate=float(learning_rate),
            l2_leaf_reg=float(l2_leaf_reg),
            border_count=int(border_count),
            random_strength=float(random_strength),
            iterations=100,
            thread_count=nthread,
            random_seed=seed,
            verbose=False,
            allow_writing_files=False,
        )
        model.fit(
            x_train.iloc[trn_idx], y_train[trn_idx],
            eval_set=(x_train.iloc[val_idx], y_train[val_idx]),
            verbose=False,
        )
        oof[val_idx] = model.predict(x_train.iloc[val_idx])
        del model
        gc.collect()
    mask = ~np.isnan(oof)
    return -(mse(y_train[mask], oof[mask]) ** 0.5)


def _sanitize_training_xy(x_train: pd.DataFrame, y_train: np.ndarray):
    """
    Drop invalid target rows (NaN/Inf) and align features.
    Also sanitize feature Inf values.
    """
    y = np.asarray(y_train, dtype=float)
    valid_mask = np.isfinite(y)
    x = x_train.loc[valid_mask].copy()
    y = y[valid_mask]
    # Keep feature NaN as-is for CatBoost missing handling, but remove Inf
    x = x.replace([np.inf, -np.inf], np.nan)
    return x, y, int((~valid_mask).sum())


def execute(params: dict, inputs: dict) -> dict:
    """
    Run Bayesian hyperparameter optimization for XGBoost.

    Args:
        params: Operator parameters including:
            - n_trials (int, optional): Number of optimization iterations. Default 50.
            - metric (str, optional): Optimization metric. Default "rmse".
            - cv_folds (int, optional): Cross-validation folds. Default 5.
        inputs: {"train_features": DataFrame, "train_target": ndarray}

    Returns:
        {"best_params": dict, "model": xgb.Booster}
    """
    train_features = inputs.get("train_features")
    train_target = inputs.get("train_target")
    _cancel_event = params.get("_cancel_event")

    if train_features is None or not isinstance(train_features, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'train_features' must be a pandas DataFrame"
        )
    if train_target is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'train_target' is required"
        )

    train_target = np.asarray(train_target, dtype=float)

    def _f(v, default: float) -> float:
        try:
            return float(v)
        except Exception:
            return default

    # Parse options
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    n_trials = int(params.get("n_trials") or options.get("n_trials") or 50)
    cv_folds = int(params.get("cv_folds") or options.get("cv_folds") or 5)
    cv_strategy_raw = (
        params.get("cv_strategy")
        or options.get("cv_strategy")
        or "auto"
    )
    cv_strategy_raw = str(cv_strategy_raw).strip().lower()
    strict_alignment_mode = _strict_alignment_enabled(params, options)
    if strict_alignment_mode:
        n_trials = 15
        cv_folds = 5
        cv_strategy_raw = "timeseries"

    # Sort feature columns for consistency
    feat_columns = sorted(train_features.columns)
    x_train = train_features[feat_columns].copy()

    # Drop non-numeric columns for XGBoost
    numeric_cols = x_train.select_dtypes(include=[np.number]).columns.tolist()
    x_train = x_train[numeric_cols]

    if x_train.empty:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "No numeric feature columns found"
        )

    raw_label_total = len(train_target)
    raw_label_finite = int(np.isfinite(train_target).sum())
    logger.info(
        f"[{OPERATOR_ID}] 训练输入统计: rows={len(x_train)}, label_finite={raw_label_finite}/{raw_label_total}"
    )

    # Sanitize invalid labels/features before optimization/training
    x_train, train_target, dropped = _sanitize_training_xy(x_train, train_target)
    if dropped > 0:
        logger.warning(f"[{OPERATOR_ID}] Dropped {dropped} rows due to NaN/Inf labels")

    sample_count = len(x_train)
    gcfg = params.get("_global_config") or {}
    is_backtest = (
        isinstance(gcfg, dict)
        and str(gcfg.get("operate_status", "")).lower() == "backtest"
    )
    if cv_strategy_raw == "auto":
        cv_strategy = "timeseries" if is_backtest else "kfold"
    elif cv_strategy_raw in {"timeseries", "kfold"}:
        cv_strategy = cv_strategy_raw
    else:
        logger.warning(
            f"[{OPERATOR_ID}] cv_strategy={cv_strategy_raw} 非法，已回退为 auto"
        )
        cv_strategy = "timeseries" if is_backtest else "kfold"

    if sample_count == 0:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "训练样本为 0。常见原因：1) 回测时间区间超出数据范围；"
            "2) 滚动训练窗口过短或筛选后无有效行；"
            "3) 训练标签 train_target 全为 NaN/Inf（例如预测窗掩码设置不当）。"
            "请检查回测起止日期、滚动训练天数、以及目标列有效值。"
        )
    if sample_count == 1:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "训练样本仅 1 条，无法进行交叉验证。请增大滚动训练天数或调整回测时间范围。"
        )
    if cv_folds < 2:
        logger.warning(f"[{OPERATOR_ID}] cv_folds={cv_folds} 非法，已自动调整为 2")
        cv_folds = 2
    max_allowed_folds = sample_count - 1 if cv_strategy == "timeseries" else sample_count
    if max_allowed_folds < 2:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "有效样本不足以进行交叉验证（至少需要 3 条样本用于时序切分）。"
            if cv_strategy == "timeseries"
            else "有效样本不足以进行交叉验证（至少需要 2 条样本）。",
        )
    if cv_folds > max_allowed_folds:
        logger.warning(
            f"[{OPERATOR_ID}] cv_folds({cv_folds}) 超过可用上限({max_allowed_folds})，"
            f"已自动降为 {max_allowed_folds} 折 (cv_strategy={cv_strategy})"
        )
        cv_folds = max_allowed_folds
    # @AI_GENERATED
    # Get log function for real-time training log output
    _log_fn = params.get("_log_fn")
    def _log(msg, t="info"):
        if _log_fn:
            _log_fn(msg, t)
        logger.info(f"[{OPERATOR_ID}] {msg}")
    # @AI_GENERATED: end

    _log(
        f"开始贝叶斯优化: {n_trials}轮, {cv_folds}折CV({cv_strategy}), "
        f"{len(numeric_cols)}个特征, {len(x_train)}个样本"
    )
    if _cancel_event is not None and _cancel_event.is_set():
        raise OperatorExecutionError(OPERATOR_ID, "Cancelled", "自动实验/比对已取消")

    default_best_params = {
        "depth": 6,
        "learning_rate": 0.05,
        "l2_leaf_reg": 3.0,
        "border_count": 128,
        "random_strength": 1.0,
    }

    gcfg = params.get("_global_config") or {}

    try:
        # Ensure bayes_opt works with NumPy>=2 where np.float alias was removed.
        _ensure_numpy_legacy_aliases()
        from bayes_opt import BayesianOptimization

        # @AI_GENERATED
        gcfg = params.get("_global_config") or {}
        _cv_seed = int(gcfg.get("xgb_seed") or 42)
        _cv_nthread = int(gcfg.get("xgb_nthread") or 4)
        _iteration_count = [0]
        def cb_cv(depth, learning_rate, l2_leaf_reg, border_count, random_strength):
            if _cancel_event is not None and _cancel_event.is_set():
                raise OperatorExecutionError(OPERATOR_ID, "Cancelled", "自动实验/比对已取消")
            _iteration_count[0] += 1
            result = _cb_crossval(
                depth, learning_rate, l2_leaf_reg, border_count, random_strength,
                x_train, train_target, cv_folds, cv_strategy,
                seed=_cv_seed, nthread=_cv_nthread,
            )
            _log(f"第{_iteration_count[0]}/{n_trials}轮: RMSE={-result:.2f}, depth={int(depth)}, lr={learning_rate:.4f}, l2_reg={l2_leaf_reg:.2f}")
            return result
        # @AI_GENERATED: end

        d_low = _f(gcfg.get("cb_depth_low"), 3.0)
        d_high = _f(gcfg.get("cb_depth_high"), 10.0)
        lr_low = _f(gcfg.get("cb_learning_rate_low"), 0.01)
        lr_high = _f(gcfg.get("cb_learning_rate_high"), 0.3)
        l2_low = _f(gcfg.get("cb_l2_leaf_reg_low"), 1.0)
        l2_high = _f(gcfg.get("cb_l2_leaf_reg_high"), 10.0)
        bc_low = _f(gcfg.get("cb_border_count_low"), 32.0)
        bc_high = _f(gcfg.get("cb_border_count_high"), 255.0)
        rs_low = _f(gcfg.get("cb_random_strength_low"), 0.0)
        rs_high = _f(gcfg.get("cb_random_strength_high"), 10.0)
        if d_high <= d_low:
            d_high = d_low + 1.0
        if lr_high <= lr_low:
            lr_high = lr_low + 1e-4
        if l2_high <= l2_low:
            l2_high = l2_low + 1.0
        if bc_high <= bc_low:
            bc_high = bc_low + 1.0
        if rs_high <= rs_low:
            rs_high = rs_low + 1.0
        _log(
            "贝叶斯搜索边界: "
            f"depth=({d_low:.1f},{d_high:.1f}), lr=({lr_low:.4f},{lr_high:.4f}), "
            f"l2_leaf_reg=({l2_low:.2f},{l2_high:.2f}), "
            f"border_count=({bc_low:.1f},{bc_high:.1f}), random_strength=({rs_low:.2f},{rs_high:.2f})"
        )
        crossval_params = {
            "depth": (d_low, d_high),
            "learning_rate": (lr_low, lr_high),
            "l2_leaf_reg": (l2_low, l2_high),
            "border_count": (bc_low, bc_high),
            "random_strength": (rs_low, rs_high),
        }

        optimizer = BayesianOptimization(cb_cv, crossval_params, random_state=42)
        # Some bayes_opt/sklearn/scipy combinations are sensitive to GP init params.
        # Use conservative GP params to maximize compatibility.
        optimizer.set_gp_params(alpha=1e-6, n_restarts_optimizer=0, normalize_y=True)

        init_points = min(5, max(1, n_trials // 5))
        n_iter = max(1, n_trials - init_points)
        try:
            maximize_params = inspect.signature(optimizer.maximize).parameters

            # bayes_opt versions differ:
            # - newer versions may support acquisition_function=UtilityFunction(...)
            # - older versions use acq/kappa/xi
            if "acquisition_function" in maximize_params:
                try:
                    from bayes_opt import UtilityFunction  # type: ignore
                    utility = UtilityFunction(kind="ei", kappa=2.5, xi=0.0)
                    optimizer.maximize(
                        init_points=init_points,
                        n_iter=n_iter,
                        acquisition_function=utility,
                    )
                except Exception:
                    optimizer.maximize(init_points=init_points, n_iter=n_iter)
            elif "acq" in maximize_params:
                optimizer.maximize(
                    init_points=init_points,
                    n_iter=n_iter,
                    acq="ei",
                    kappa=2.5,
                    xi=0.0,
                )
            else:
                optimizer.maximize(init_points=init_points, n_iter=n_iter)

            best_params = optimizer.max["params"]
            best_params["max_depth"] = int(best_params["max_depth"])
            oof_rmse = -optimizer.max["target"]  # BO maximizes -RMSE
            _log(f"优化完成! 最优参数: eta={best_params['eta']:.4f}, depth={best_params['max_depth']}, subsample={best_params['subsample']:.2f}, lambda={best_params.get('lambdas',10):.1f}", "success")
        except Exception as optimize_err:
            if _cancel_event is not None and _cancel_event.is_set():
                raise OperatorExecutionError(OPERATOR_ID, "Cancelled", "自动实验/比对已取消")
            logger.warning(
                f"[{OPERATOR_ID}] Bayesian optimization failed ({type(optimize_err).__name__}: {optimize_err}), falling back to default params"
            )
            _log("贝叶斯优化失败，已回退到默认参数继续训练", "warning")
            best_params = default_best_params.copy()
            oof_rmse = None

    except ImportError:
        logger.warning(
            f"[{OPERATOR_ID}] bayes_opt not available, using default params"
        )
        best_params = default_best_params.copy()
        oof_rmse = None
    except Exception as e:
        logger.warning(
            f"[{OPERATOR_ID}] Bayesian optimizer init failed ({type(e).__name__}: {e}), using default params"
        )
        _log("贝叶斯优化初始化失败，已回退到默认参数继续训练", "warning")
        best_params = default_best_params.copy()
        oof_rmse = None

    # Train final model with best params
    _log("使用最优参数训练最终模型 (200轮)...")
    _seed = int(gcfg.get("xgb_seed") or 100)
    _nthread = int(gcfg.get("xgb_nthread") or -1)

    model = CatBoostRegressor(
        depth=int(best_params["depth"]),
        learning_rate=float(best_params["learning_rate"]),
        l2_leaf_reg=float(best_params["l2_leaf_reg"]),
        border_count=int(best_params["border_count"]),
        random_strength=float(best_params.get("random_strength", 1.0)),
        iterations=200,
        thread_count=_nthread,
        random_seed=_seed,
        verbose=False,
        allow_writing_files=False,
    )

    if _cancel_event is not None and _cancel_event.is_set():
        raise OperatorExecutionError(OPERATOR_ID, "Cancelled", "自动实验/比对已取消")

    model.fit(x_train, train_target, verbose=False)

    logger.info(f"[{OPERATOR_ID}] Best params: {best_params}")

    # @AI_GENERATED
    # Passthrough upstream data so downstream xgboost_forecast can access it
    result = {
        "best_params": best_params,
        "model": model,
    }
    if oof_rmse is not None:
        result["oof_rmse"] = float(oof_rmse)
    # Pass through any upstream data keys (train_features, train_target, test_features, test_target, forecast_config)
    for key in ("train_features", "train_target", "test_features", "test_target", "forecast_config"):
        if key in inputs:
            result[key] = inputs[key]
    # @AI_GENERATED: end

    return result
# @AI_GENERATED: end
