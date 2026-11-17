# @AI_GENERATED
"""
catboost_forecast operator backend — CatBoost time series forecasting.
接口与 xgboost_forecast 对齐，便于在流程图中互换。
"""
import json
import uuid

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution import model_registry
from services.operator_execution.router import OperatorExecutionError
from services.reference_rolling_backtest.config import ReferenceBacktestConfig
from services.reference_rolling_backtest.models import train_catboost

OPERATOR_ID = "catboost_forecast"


def _to_bool(v, default: bool = True) -> bool:
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


def _execute_train(params: dict, inputs: dict, options: dict) -> dict:
    train_features = inputs.get("train_features")
    train_target = inputs.get("train_target")
    test_features = inputs.get("test_features")
    test_target = inputs.get("test_target")
    if train_features is None or not isinstance(train_features, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'train_features' must be a pandas DataFrame")
    if train_target is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'train_target' is required")
    global_cfg = params.get("_global_config") or {}
    backtest_mode = str(global_cfg.get("backtest_mode") or "").strip().lower()
    if backtest_mode == "inference_only":
        model_ref = (
            params.get("model_ref")
            or options.get("model_ref")
            or global_cfg.get("backtest_model_ref")
            or global_cfg.get("model_ref")
        )
        if model_ref:
            predict_params = dict(params)
            predict_params["mode"] = "predict"
            predict_params["model_ref"] = model_ref
            try:
                return _execute_predict(predict_params, inputs, options)
            except OperatorExecutionError:
                # inference_only may provide model_ref for another model family (e.g., xgb)
                y_true = np.asarray(test_target, dtype=float) if test_target is not None else np.array([])
                return {
                    "predictions": np.array([]),
                    "y_true": y_true,
                    "y_pred": np.array([]),
                    "forecast_timestamps": [],
                    "forecast_values": [],
                    "warning": f"catboost skipped in inference_only mode: model_ref '{model_ref}' not available for catboost",
                }
        y_true = np.asarray(test_target, dtype=float) if test_target is not None else np.array([])
        return {
            "predictions": np.array([]),
            "y_true": y_true,
            "y_pred": np.array([]),
            "forecast_timestamps": [],
            "forecast_values": [],
            "warning": "catboost skipped in inference_only mode without model_ref",
        }

    x = train_features.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = np.asarray(train_target, dtype=float)
    valid = np.isfinite(y)
    if valid.sum() <= 1:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Train labels are invalid (all NaN/Inf or too few valid rows)")
    x = x.loc[valid]
    y = y[valid]

    numeric_cols = sorted(x.columns.tolist())
    upstream_model = inputs.get("model")
    upstream_best_params = inputs.get("best_params")
    if upstream_model is not None and upstream_best_params is not None:
        model = upstream_model
        oof_rmse = inputs.get("oof_rmse")
        logger.info(f"[{OPERATOR_ID}] Using pre-tuned model from upstream auto_tune_catboost, best_params={upstream_best_params}")
    else:
        forecast_steps = int((inputs.get("forecast_config") or {}).get("forecast_steps") or (len(test_target) if test_target is not None else 96))
        strict_alignment_mode = _strict_alignment_enabled(params, options)
        n_splits = int(params.get("n_splits") or options.get("n_splits") or 5)
        bo_init_points = int(params.get("bo_init_points") or options.get("bo_init_points") or 3)
        bo_n_iter = int(params.get("bo_n_iter") or options.get("bo_n_iter") or 12)
        use_bayes = _to_bool(
            params.get("use_bayesian_tuning")
            if params.get("use_bayesian_tuning") is not None
            else options.get("use_bayesian_tuning"),
            default=True,
        )
        if strict_alignment_mode:
            n_splits = 5
            bo_init_points = 3
            bo_n_iter = 12
            use_bayes = True
        cfg = ReferenceBacktestConfig(
            daily_horizon=forecast_steps,
            n_splits=n_splits,
            bo_init_points=bo_init_points,
            bo_n_iter=bo_n_iter,
            n_estimators_final=int(params.get("n_estimators") or options.get("n_estimators") or 200),
            use_bayesian_tuning=use_bayes,
        )

        allow_missing_dependency = _to_bool(params.get("allow_missing_dependency") if params.get("allow_missing_dependency") is not None else options.get("allow_missing_dependency"), default=True)
        _cancel_event = params.get("_cancel_event")
        if _cancel_event is not None and _cancel_event.is_set():
            raise OperatorExecutionError(OPERATOR_ID, "Cancelled", "已取消")
        try:
            model, oof_rmse = train_catboost(x, pd.Series(y), forecast_steps, cfg)
        except RuntimeError as e:
            if allow_missing_dependency:
                y_true = np.asarray(test_target, dtype=float) if test_target is not None else np.array([])
                return {
                    "predictions": np.array([]),
                    "y_true": y_true,
                    "y_pred": np.array([]),
                    "forecast_timestamps": [],
                    "forecast_values": [],
                    "warning": f"{OPERATOR_ID} skipped: {e}",
                }
            raise OperatorExecutionError(OPERATOR_ID, "DependencyError", str(e))

    y_pred = np.array([])
    forecast_timestamps = []
    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    if test_features is not None and isinstance(test_features, pd.DataFrame) and not test_features.empty:
        if time_field in test_features.columns:
            forecast_timestamps = pd.to_datetime(test_features[time_field], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
        xt = test_features[[c for c in numeric_cols if c in test_features.columns]].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        if not xt.empty:
            y_pred = np.asarray(model.predict(xt), dtype=float).reshape(-1)

    model_id = f"catb-{uuid.uuid4().hex[:12]}"
    model_registry.register_model(
        model_id,
        model,
        numeric_cols,
        metadata={"operator": OPERATOR_ID},
    )
    y_true = np.asarray(test_target, dtype=float) if test_target is not None else np.array([])
    logger.info(f"[{OPERATOR_ID}] Train complete: model_id={model_id}, pred_points={len(y_pred)}")
    output_prefix = str(params.get("output_prefix") or options.get("output_prefix") or "").strip()
    prefixed = {}
    if output_prefix:
        prefixed[f"y_pred_{output_prefix}"] = y_pred
        prefixed[f"forecast_values_{output_prefix}"] = y_pred.tolist() if hasattr(y_pred, "tolist") else list(y_pred)
        prefixed[f"model_id_{output_prefix}"] = model_id
        prefixed[f"model_ref_{output_prefix}"] = model_id
        if oof_rmse is not None:
            prefixed[f"oof_rmse_{output_prefix}"] = float(oof_rmse)
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
        **prefixed,
    }
    if oof_rmse is not None:
        result["oof_rmse"] = float(oof_rmse)
    return result


def _execute_predict(params: dict, inputs: dict, options: dict) -> dict:
    model_id = (
        params.get("model_ref")
        or options.get("model_ref")
        or params.get("model_id")
        or options.get("model_id")
    )
    if not model_id:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "model_ref (or model_id) is required for predict mode")
    stored = model_registry.get_model(model_id)
    if stored is None:
        raise OperatorExecutionError(OPERATOR_ID, "ModelNotFoundError", f"Model '{model_id}' not found")
    model = stored["model"]
    feature_list = stored["feature_list"]
    data = inputs.get("data") or inputs.get("test_features")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' or 'test_features' must be a pandas DataFrame")
    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    forecast_timestamps = pd.to_datetime(data[time_field], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S").tolist() if time_field in data.columns else []
    xt = data[[c for c in feature_list if c in data.columns]].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if xt.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No matching features found")
    forecast_values = np.asarray(model.predict(xt), dtype=float).reshape(-1).tolist()
    if not forecast_timestamps:
        forecast_timestamps = list(range(len(forecast_values)))
    return {"forecast_timestamps": forecast_timestamps, "forecast_values": forecast_values}


def execute(params: dict, inputs: dict) -> dict:
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
    if mode == "predict":
        return _execute_predict(params, inputs, options)
    raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"mode must be 'train' or 'predict', got '{mode}'")
# @AI_GENERATED: end
