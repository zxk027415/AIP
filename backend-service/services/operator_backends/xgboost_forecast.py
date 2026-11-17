# @AI_GENERATED
"""
xgboost_forecast operator backend — XGBoost time series forecasting.

Train mode (mode=train): Train XGBoost model, return predictions + model.
Predict mode (mode=predict): Load model_id, execute inference.
Params: n_estimators (default 200), auto_tune (default false), mode (train/predict), model_id.
Advanced params: separate_modeling, prefer_unit_len, default_retrain,
                 sample_weight_decay, task_type.
"""
import json
import uuid

import numpy as np
import pandas as pd
import xgboost as xgb
from loguru import logger

from services.operator_execution import model_registry
from services.operator_execution.router import OperatorExecutionError
from services.reference_rolling_backtest.config import ReferenceBacktestConfig
from services.reference_rolling_backtest.models import (
    ensemble_predict as parity_ensemble_predict,
    train_all_models as parity_train_all_models,
)

OPERATOR_ID = "xgboost_forecast"

def _sample_weights(n_samples: int, forecast_length: int, decay: float = 0.99) -> np.ndarray:
    """Generate sample weights — recent data weighted higher."""
    weights = []
    fl = max(forecast_length, 1)
    for i in range(n_samples):
        weights.append(pow(decay, i // fl))
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


def _train_xgboost(x_train: pd.DataFrame, y_train: np.ndarray,
                   n_estimators: int, forecast_length: int,
                   sample_weight_decay: float) -> xgb.Booster:
    """Train an XGBoost model with reasonable defaults."""
    # Sort feature columns for consistency
    feat_columns = sorted(x_train.columns)
    x_sorted = x_train[feat_columns]

    # Keep only numeric columns
    numeric_cols = x_sorted.select_dtypes(include=[np.number]).columns.tolist()
    x_numeric = x_sorted[numeric_cols]

    if x_numeric.empty:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "No numeric feature columns found for training"
        )

    y_arr = np.asarray(y_train, dtype=float)
    valid_mask = np.isfinite(y_arr)
    if valid_mask.sum() <= 1:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Train labels are invalid (all NaN/Inf or too few valid rows)"
        )
    if (~valid_mask).sum() > 0:
        logger.warning(f"[{OPERATOR_ID}] Dropped {(~valid_mask).sum()} rows due to NaN/Inf labels")
    x_numeric = x_numeric.loc[valid_mask].replace([np.inf, -np.inf], np.nan)
    y_arr = y_arr[valid_mask]

    weights = _sample_weights(len(x_numeric), forecast_length, sample_weight_decay)
    dtrain = xgb.DMatrix(x_numeric, label=y_arr, missing=0, weight=weights)

    xgb_params = {
        "objective": "reg:squarederror",
        "booster": "gbtree",
        "eval_metric": "rmse",
        "max_depth": 5,
        "min_child_weight": 3.0,
        "subsample": 0.8,
        "eta": 0.05,
        "lambda": 10.0,
        "seed": 100,
        "nthread": -1,
        "verbosity": 0,
    }

    model = xgb.train(
        xgb_params, dtrain, n_estimators,
        evals=[(dtrain, "train")],
        early_stopping_rounds=10, verbose_eval=0,
    )

    return model, numeric_cols


def _execute_train(params: dict, inputs: dict, options: dict) -> dict:
    """Train mode: train XGBoost and return predictions + model."""
    train_features = inputs.get("train_features")
    train_target = inputs.get("train_target")
    test_features = inputs.get("test_features")
    test_target = inputs.get("test_target")

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
    strict_alignment_mode = _strict_alignment_enabled(params, options)
    global_cfg = params.get("_global_config") or {}
    backtest_mode = str(global_cfg.get("backtest_mode") or "").strip().lower()
    if backtest_mode == "inference_only":
        model_ref = (
            params.get("model_ref")
            or options.get("model_ref")
            or global_cfg.get("backtest_model_ref")
            or global_cfg.get("model_ref")
        )
        if not model_ref:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "ParameterError",
                "backtest_mode=inference_only requires model_ref/backtest_model_ref",
            )
        predict_params = dict(params)
        predict_params["mode"] = "predict"
        predict_params["model_ref"] = model_ref
        return _execute_predict(predict_params, inputs, options)

    n_estimators = int(params.get("n_estimators") or options.get("n_estimators") or 200)
    sample_weight_decay = float(
        params.get("sample_weight_decay") or options.get("sample_weight_decay") or 0.99
    )
    auto_tune = params.get("auto_tune") or options.get("auto_tune")
    if isinstance(auto_tune, str):
        auto_tune = auto_tune.lower() in ("true", "1", "yes")
    else:
        auto_tune = bool(auto_tune) if auto_tune is not None else False

    # Get forecast config from upstream multi_step_forecast
    forecast_config = inputs.get("forecast_config", {})
    forecast_steps = forecast_config.get("forecast_steps", len(test_target) if test_target is not None else 96)

    # @AI_GENERATED
    # Check if upstream auto_tune_xgboost already provided a tuned model
    upstream_model = inputs.get("model")
    upstream_best_params = inputs.get("best_params")
    local_parity_mode = params.get("local_parity_mode") or options.get("local_parity_mode")
    if isinstance(local_parity_mode, str):
        local_parity_mode = local_parity_mode.lower() in ("true", "1", "yes", "on")
    else:
        local_parity_mode = bool(local_parity_mode) if local_parity_mode is not None else False

    if local_parity_mode:
        # 与本地 run_weihai_backtest 对齐：在算子内按参数选择多模型集成（默认 xgb+lgb+catb+ridge）
        model_names = params.get("local_parity_models") or options.get("local_parity_models")
        if isinstance(model_names, str):
            model_names = [m.strip() for m in model_names.split(",") if m.strip()]
        if not model_names:
            model_names = ["xgb", "lgb", "catb", "ridge"]
        n_splits = int(params.get("local_parity_n_splits") or options.get("local_parity_n_splits") or 5)
        bo_init_points = int(
            params.get("local_parity_bo_init_points")
            or options.get("local_parity_bo_init_points")
            or 3
        )
        bo_n_iter = int(
            params.get("local_parity_bo_n_iter") or options.get("local_parity_bo_n_iter") or 12
        )
        use_bayes = params.get("local_parity_use_bayesian_tuning")
        if use_bayes is None:
            use_bayes = options.get("local_parity_use_bayesian_tuning", True)
        if isinstance(use_bayes, str):
            use_bayes = use_bayes.lower() in ("true", "1", "yes", "on")
        if strict_alignment_mode:
            n_splits = 5
            bo_init_points = 3
            bo_n_iter = 12
            use_bayes = True
        cfg = ReferenceBacktestConfig(
            daily_horizon=int(forecast_steps),
            n_splits=n_splits,
            bo_init_points=bo_init_points,
            bo_n_iter=bo_n_iter,
            n_estimators_final=n_estimators,
            use_bayesian_tuning=bool(use_bayes),
            models=tuple(model_names),
        )
        x_num = train_features.select_dtypes(include=[np.number]).copy()
        if x_num.empty:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError", "No numeric feature columns found for local parity mode"
            )
        x_num = x_num.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        y_arr = np.asarray(train_target, dtype=float)
        valid = np.isfinite(y_arr)
        if valid.sum() <= 1:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError", "Train labels are invalid for local parity mode"
            )
        x_num = x_num.loc[valid]
        y_arr = y_arr[valid]
        models, feature_list, weights = parity_train_all_models(
            x_num, pd.Series(y_arr), int(forecast_steps), cfg
        )
        model = {
            "kind": "local_parity_ensemble",
            "models": models,
            "feature_list": feature_list,
            "weights": weights,
        }
        numeric_cols = feature_list
        logger.info(
            f"[{OPERATOR_ID}] local_parity_mode enabled, models={list(weights.keys())}, weights={weights}"
        )
    elif upstream_model is not None and upstream_best_params is not None:
        # Use the pre-tuned model from upstream auto_tune_xgboost node
        model = upstream_model
        numeric_cols = sorted(
            train_features.select_dtypes(include=[np.number]).columns.tolist()
        )
        logger.info(f"[{OPERATOR_ID}] Using pre-tuned model from upstream auto_tune_xgboost, best_params={upstream_best_params}")
    elif auto_tune:
        # auto_tune enabled but no upstream model — run inline
        try:
            from services.operator_backends.auto_tune_xgboost import execute as auto_tune_execute
            tune_result = auto_tune_execute(params, {
                "train_features": train_features,
                "train_target": train_target,
            })
            model = tune_result["model"]
            numeric_cols = sorted(
                train_features.select_dtypes(include=[np.number]).columns.tolist()
            )
            logger.info(f"[{OPERATOR_ID}] Used inline auto-tuned model")
        except Exception as e:
            logger.warning(f"[{OPERATOR_ID}] Auto-tune failed, falling back to defaults: {e}")
            model, numeric_cols = _train_xgboost(
                train_features, train_target, n_estimators,
                forecast_steps, sample_weight_decay,
            )
    else:
        model, numeric_cols = _train_xgboost(
            train_features, train_target, n_estimators,
            forecast_steps, sample_weight_decay,
        )
    # @AI_GENERATED: end

    # @AI_GENERATED
    _log_fn = params.get("_log_fn")
    def _log(msg, t="info"):
        if _log_fn:
            _log_fn(msg, t)
    # @AI_GENERATED: end

    # Generate predictions on test set
    _log(f"模型训练完成，{len(numeric_cols)}个特征，开始生成测试集预测...")
    y_pred = np.array([])
    ensemble_details = {}
    forecast_timestamps = []
    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    if test_features is not None and isinstance(test_features, pd.DataFrame) and not test_features.empty:
        if time_field in test_features.columns:
            forecast_timestamps = pd.to_datetime(
                test_features[time_field], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
        test_numeric = test_features[
            [c for c in numeric_cols if c in test_features.columns]
        ].replace([np.inf, -np.inf], np.nan)
        if not test_numeric.empty:
            if isinstance(model, dict) and model.get("kind") == "local_parity_ensemble":
                test_numeric = test_numeric.fillna(0.0)
                ens, single_preds = parity_ensemble_predict(
                    model["models"], model["feature_list"], model["weights"], test_numeric
                )
                y_pred = np.asarray(ens, dtype=float).flatten()
                ensemble_details = {
                    "model_weights": model.get("weights", {}),
                    "single_model_predictions": {
                        k: (v.tolist() if hasattr(v, "tolist") else list(v))
                        for k, v in single_preds.items()
                    },
                }
            else:
                test_numeric = test_numeric.fillna(0.0)
                dtest = xgb.DMatrix(test_numeric, missing=0)
                y_pred = model.predict(dtest).flatten()

    # Store model for later predict mode
    model_id = f"xgb-{uuid.uuid4().hex[:12]}"
    model_registry.register_model(
        model_id,
        model,
        numeric_cols,
        metadata={"operator": OPERATOR_ID},
    )

    y_true = np.asarray(test_target, dtype=float) if test_target is not None else np.array([])

    _log(f"预测完成: model_id={model_id}, 预测{len(y_pred)}个点", "success")
    # Capture oof_rmse: from upstream auto_tune_xgboost or from inputs
    _oof_rmse = inputs.get("oof_rmse")
    output_prefix = str(params.get("output_prefix") or options.get("output_prefix") or "").strip()
    prefixed = {}
    if output_prefix:
        prefixed[f"y_pred_{output_prefix}"] = y_pred
        prefixed[f"forecast_values_{output_prefix}"] = (
            y_pred.tolist() if hasattr(y_pred, "tolist") else list(y_pred)
        )
        prefixed[f"model_id_{output_prefix}"] = model_id
        prefixed[f"model_ref_{output_prefix}"] = model_id
        if _oof_rmse is not None:
            prefixed[f"oof_rmse_{output_prefix}"] = float(_oof_rmse)
        if y_true.size > 0:
            prefixed[f"y_true_{output_prefix}"] = y_true

    result = {
        "predictions": y_pred,
        "model": model,
        "model_id": model_id,
        "model_ref": model_id,
        "y_true": y_true,
        "y_pred": y_pred,
        "forecast_timestamps": forecast_timestamps,
        "forecast_values": y_pred.tolist() if hasattr(y_pred, "tolist") else list(y_pred),
        **ensemble_details,
        **prefixed,
    }
    if _oof_rmse is not None:
        result["oof_rmse"] = float(_oof_rmse)
    return result


def _execute_predict(params: dict, inputs: dict, options: dict) -> dict:
    """Predict mode: load model and execute inference."""
    model_id = (
        params.get("model_ref")
        or options.get("model_ref")
        or params.get("model_id")
        or options.get("model_id")
    )
    if not model_id:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            "model_ref (or model_id) is required for predict mode"
        )

    stored = model_registry.get_model(model_id)
    if stored is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "ModelNotFoundError",
            f"Model '{model_id}' not found. Available: {model_registry.list_model_refs()}"
        )

    model = stored["model"]
    feature_list = stored["feature_list"]

    data = inputs.get("data")
    if data is None:
        data = inputs.get("test_features")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'data' or 'test_features' must be a pandas DataFrame"
        )

    # Get time field for timestamps
    time_field = params.get("time_field") or options.get("time_field") or "record_time"

    # Extract timestamps before selecting features
    forecast_timestamps = []
    if time_field in data.columns:
        forecast_timestamps = pd.to_datetime(
            data[time_field], errors="coerce"
        ).dt.strftime("%Y-%m-%d %H:%M:%S").tolist()

    # Select matching features
    available_features = [c for c in feature_list if c in data.columns]
    if not available_features:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"No matching features found. Model expects: {feature_list[:10]}..."
        )

    predict_data = data[available_features].replace([np.inf, -np.inf], np.nan)
    if isinstance(model, dict) and model.get("kind") == "local_parity_ensemble":
        predict_data = predict_data.fillna(0.0)
        ens, _ = parity_ensemble_predict(
            model["models"], model["feature_list"], model["weights"], predict_data
        )
        forecast_values = np.asarray(ens, dtype=float).flatten().tolist()
    else:
        predict_data = predict_data.fillna(0.0)
        dmatrix = xgb.DMatrix(predict_data, missing=0)
        forecast_values = model.predict(dmatrix).flatten().tolist()

    if not forecast_timestamps:
        forecast_timestamps = list(range(len(forecast_values)))

    logger.info(
        f"[{OPERATOR_ID}] Predict complete: {len(forecast_values)} values"
    )

    return {
        "forecast_timestamps": forecast_timestamps,
        "forecast_values": forecast_values,
    }


def execute(params: dict, inputs: dict) -> dict:
    """
    XGBoost time series forecasting — train or predict mode.

    Args:
        params: Operator parameters including:
            - mode (str, optional): "train" or "predict". Default "train".
            - n_estimators (int, optional): Number of boosting rounds. Default 200.
            - auto_tune (bool, optional): Enable Bayesian optimization. Default false.
            - model_id (str, optional): Model ID for predict mode.
            - sample_weight_decay (float, optional): Weight decay factor. Default 0.99.
            - separate_modeling (str, optional): Separate workday/holiday modeling.
            - prefer_unit_len (int, optional): Validation set length multiplier.
            - default_retrain (bool, optional): Retrain with full data.
            - task_type (str, optional): Forecast task type.
        inputs (train): {"forecast_config": dict, "train_features": DataFrame,
                         "train_target": ndarray, "test_features": DataFrame,
                         "test_target": ndarray}
        inputs (predict): {"data": DataFrame} or {"test_features": DataFrame}

    Returns (train):
        {"predictions": ndarray, "model": xgb.Booster, "model_id": str,
         "y_true": ndarray, "y_pred": ndarray}
    Returns (predict):
        {"forecast_timestamps": list, "forecast_values": list}
    """
    # Parse options
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    mode = str(params.get("mode") or options.get("mode") or "train").lower()

    if mode == "train":
        return _execute_train(params, inputs, options)
    elif mode == "predict":
        return _execute_predict(params, inputs, options)
    else:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"mode must be 'train' or 'predict', got '{mode}'"
        )
# @AI_GENERATED: end
