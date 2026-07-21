# @AI_GENERATED
"""单变量滞后特征时序预测共享工具（文件名 _ 开头，不被 auto_discover 注册）。"""
from __future__ import annotations

from typing import Callable, List, Tuple

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError


def parse_univariate_series(
    operator_id: str,
    params: dict,
    inputs: dict,
    *,
    min_points: int = 20,
) -> Tuple[pd.Series, pd.DatetimeIndex, object]:
    """解析 timestamp/value 列，返回 (series, timestamps, inferred_freq_offset)。"""
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(operator_id, "InputError", "Input 'data' must be a pandas DataFrame")

    ts_col = params.get("timestamp_column", "timestamp")
    val_col = params.get("value_column", "value")
    if ts_col not in data.columns:
        raise OperatorExecutionError(operator_id, "InputError", f"timestamp_column '{ts_col}' not found")
    if val_col not in data.columns:
        raise OperatorExecutionError(operator_id, "InputError", f"value_column '{val_col}' not found")

    df = data[[ts_col, val_col]].copy()
    if not pd.api.types.is_datetime64_any_dtype(df[ts_col]):
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col, val_col]).sort_values(ts_col).reset_index(drop=True)
    if len(df) < min_points:
        raise OperatorExecutionError(
            operator_id, "InputError", f"Need >= {min_points} points, got {len(df)}"
        )

    timestamps = pd.DatetimeIndex(df[ts_col])
    diffs = timestamps.to_series().diff().dropna()
    median_diff = diffs.median() if len(diffs) else pd.Timedelta(hours=1)
    try:
        freq = pd.tseries.frequencies.to_offset(median_diff)
    except Exception:
        freq = pd.tseries.frequencies.to_offset("h")

    series = df[val_col].astype(float)
    return series, timestamps, freq


def build_lag_xy(values: np.ndarray, n_lags: int) -> Tuple[np.ndarray, np.ndarray]:
    """用滞后 1..n_lags 预测下一步。"""
    X, y = [], []
    for i in range(n_lags, len(values)):
        X.append(values[i - n_lags : i])
        y.append(values[i])
    return np.asarray(X, dtype=float), np.asarray(y, dtype=float)


def recursive_forecast(
    model,
    history: np.ndarray,
    n_lags: int,
    horizon: int,
) -> List[float]:
    """滚动多步：每次用最近 n_lags 预测下一步并追加。"""
    hist = list(history.astype(float))
    out: List[float] = []
    for _ in range(horizon):
        x = np.asarray(hist[-n_lags:], dtype=float).reshape(1, -1)
        pred = float(np.asarray(model.predict(x)).ravel()[0])
        out.append(pred)
        hist.append(pred)
    return out


def forecast_dates_from(last_ts, freq, horizon: int) -> List[str]:
    idx = pd.date_range(start=last_ts + freq, periods=horizon, freq=freq)
    return [ts.isoformat() for ts in idx]


def run_lag_sklearn_forecast(
    operator_id: str,
    params: dict,
    inputs: dict,
    model_factory: Callable[[], object],
    *,
    default_lags: int = 12,
    min_points: int = 30,
) -> dict:
    """通用：建滞后 → fit sklearn 回归器 → 递归预测。"""
    series, timestamps, freq = parse_univariate_series(
        operator_id, params, inputs, min_points=min_points,
    )
    try:
        horizon = int(params.get("forecast_horizon") or 24)
        n_lags = int(params.get("n_lags") or default_lags)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(operator_id, "ParameterError", f"Invalid numeric params: {e}")

    horizon = max(horizon, 1)
    n_lags = max(n_lags, 1)
    values = series.to_numpy(dtype=float)
    if len(values) <= n_lags + 2:
        raise OperatorExecutionError(
            operator_id, "InputError",
            f"Need > n_lags+2 points (n_lags={n_lags}), got {len(values)}",
        )

    X, y = build_lag_xy(values, n_lags)
    model = model_factory()
    try:
        model.fit(X, y)
    except Exception as e:
        raise OperatorExecutionError(operator_id, "ModelFitError", f"Model fitting failed: {e}")

    forecast = recursive_forecast(model, values, n_lags, horizon)
    dates = forecast_dates_from(timestamps[-1], freq, horizon)
    return {"forecast": forecast, "forecast_dates": dates}
# @AI_GENERATED: end
