# @AI_GENERATED
"""
ridge_forecast operator backend — Ridge regression forecasting.
接口与 xgboost/lightgbm/catboost forecast 算子对齐。
"""
import json
import uuid

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from services.operator_execution import model_registry
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "ridge_forecast"


def _sample_weights(n_samples: int, forecast_length: int, decay: float = 0.99) -> np.ndarray:
    weights = []
    fl = max(forecast_length, 1)
    for i in range(n_samples):
        weights.append(pow(decay, i // fl))
    return np.array(list(reversed(weights)))


def _to_bool(v, default: bool = True) -> bool:
    if v is None:
        return default
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "on")
    return bool(v)


def _clamp_ts_cv_splits(n_splits: int, n_samples: int) -> int:
    if n_samples <= 2:
        return 2
    cap = n_samples - 1
    want = max(2, int(n_splits))
    return max(2, min(want, cap))


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
                    "warning": f"ridge skipped in inference_only mode: model_ref '{model_ref}' not available for ridge",
                }
        y_true = np.asarray(test_target, dtype=float) if test_target is not None else np.array([])
        return {
            "predictions": np.array([]),
            "y_true": y_true,
            "y_pred": np.array([]),
            "forecast_timestamps": [],
            "forecast_values": [],
            "warning": "ridge skipped in inference_only mode without model_ref",
        }

    x = train_features.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    x = x.reindex(sorted(x.columns), axis=1)
    y = np.asarray(train_target, dtype=float)
    valid = np.isfinite(y)
    if valid.sum() <= 1:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Train labels are invalid (all NaN/Inf or too few valid rows)")
    x = x.loc[valid]
    y = y[valid]

    alpha = float(params.get("alpha") or options.get("alpha") or 1.0)
    forecast_steps = int((inputs.get("forecast_config") or {}).get("forecast_steps") or (len(test_target) if test_target is not None else 96))
    sample_weight_decay = float(params.get("sample_weight_decay") or options.get("sample_weight_decay") or 0.99)
    sw = _sample_weights(len(x), forecast_steps, sample_weight_decay)

    # OOF RMSE via TimeSeriesSplit (aligned with local run_weihai_backtest.py)
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import mean_squared_error
    n_splits = _clamp_ts_cv_splits(
        int(params.get("n_splits") or options.get("n_splits") or 5),
        len(x),
    )
    tscv = TimeSeriesSplit(n_splits=n_splits)
    oof = np.full(len(x), np.nan)
    for _, (ti, vi) in enumerate(tscv.split(x)):
        m_cv = Ridge(alpha=alpha)
        m_cv.fit(x.iloc[ti], y[ti])
        oof[vi] = m_cv.predict(x.iloc[vi])
    mask = ~np.isnan(oof)
    oof_rmse = float(np.sqrt(mean_squared_error(y[mask], oof[mask]))) if mask.any() else 9999.0

    model = Ridge(alpha=alpha)
    model.fit(x, y, sample_weight=sw)

    numeric_cols = sorted(x.columns.tolist())
    y_pred = np.array([])
    forecast_timestamps = []
    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    if test_features is not None and isinstance(test_features, pd.DataFrame) and not test_features.empty:
        if time_field in test_features.columns:
            forecast_timestamps = pd.to_datetime(test_features[time_field], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
        xt = test_features[[c for c in numeric_cols if c in test_features.columns]].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        if not xt.empty:
            y_pred = np.asarray(model.predict(xt), dtype=float).reshape(-1)

    model_id = f"ridge-{uuid.uuid4().hex[:12]}"
    model_registry.register_model(
        model_id,
        model,
        numeric_cols,
        metadata={"operator": OPERATOR_ID},
    )
    y_true = np.asarray(test_target, dtype=float) if test_target is not None else np.array([])
    output_prefix = str(params.get("output_prefix") or options.get("output_prefix") or "").strip()
    prefixed = {}
    if output_prefix:
        prefixed[f"y_pred_{output_prefix}"] = y_pred
        prefixed[f"forecast_values_{output_prefix}"] = y_pred.tolist() if hasattr(y_pred, "tolist") else list(y_pred)
        prefixed[f"model_id_{output_prefix}"] = model_id
        prefixed[f"model_ref_{output_prefix}"] = model_id
        prefixed[f"oof_rmse_{output_prefix}"] = float(oof_rmse)
        if y_true.size > 0:
            prefixed[f"y_true_{output_prefix}"] = y_true
    return {
        "predictions": y_pred,
        "model": model,
        "model_id": model_id,
        "model_ref": model_id,
        "y_true": y_true,
        "y_pred": y_pred,
        "oof_rmse": float(oof_rmse),
        "forecast_timestamps": forecast_timestamps,
        "forecast_values": y_pred.tolist() if hasattr(y_pred, "tolist") else list(y_pred),
        **prefixed,
    }


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
