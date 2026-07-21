# @AI_GENERATED
"""exponential_smoothing — Holt-Winters / 指数平滑单变量多步预测。"""
from __future__ import annotations

import logging

from services.operator_backends._lag_forecast_utils import (
    forecast_dates_from,
    parse_univariate_series,
)
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "exponential_smoothing"
logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
      timestamp_column, value_column, forecast_horizon,
      trend ('add'|'mul'|None), seasonal ('add'|'mul'|None), seasonal_periods
    returns: forecast, forecast_dates
    """
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    series, timestamps, freq = parse_univariate_series(
        OPERATOR_ID, params, inputs, min_points=20,
    )
    try:
        horizon = int(params.get("forecast_horizon") or 24)
    except (TypeError, ValueError):
        horizon = 24
    horizon = max(horizon, 1)

    trend = params.get("trend", "add")
    if trend in ("", "none", "None", None):
        trend = None
    seasonal = params.get("seasonal")
    if seasonal in ("", "none", "None", None):
        seasonal = None
    try:
        seasonal_periods = int(params.get("seasonal_periods") or 0) or None
    except (TypeError, ValueError):
        seasonal_periods = None

    # 数据不够长时关闭季节项，避免 fit 失败
    if seasonal and (seasonal_periods is None or len(series) < 2 * int(seasonal_periods)):
        seasonal = None
        seasonal_periods = None

    try:
        model = ExponentialSmoothing(
            series.astype(float),
            trend=trend,
            seasonal=seasonal,
            seasonal_periods=seasonal_periods,
            initialization_method="estimated",
        )
        fitted = model.fit(optimized=True)
        forecast_values = fitted.forecast(horizon)
    except Exception as e:
        raise OperatorExecutionError(OPERATOR_ID, "ModelFitError", f"ExponentialSmoothing failed: {e}")

    forecast = [float(v) for v in forecast_values]
    dates = forecast_dates_from(timestamps[-1], freq, horizon)
    logger.info(f"[{OPERATOR_ID}] horizon={horizon}, trend={trend}, seasonal={seasonal}")
    return {"forecast": forecast, "forecast_dates": dates}
# @AI_GENERATED: end
