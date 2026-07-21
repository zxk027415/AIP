# @AI_GENERATED
"""quantile_regression_forecast — 滞后特征 + QuantileRegressor 分位预测。"""
from __future__ import annotations

from sklearn.linear_model import QuantileRegressor

from services.operator_backends._lag_forecast_utils import run_lag_sklearn_forecast
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "quantile_regression_forecast"


def execute(params: dict, inputs: dict) -> dict:
    try:
        quantile = float(params.get("quantile") if params.get("quantile") is not None else 0.5)
        alpha = float(params.get("alpha") if params.get("alpha") is not None else 0.0)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    quantile = min(max(quantile, 0.01), 0.99)

    def factory():
        return QuantileRegressor(quantile=quantile, alpha=alpha, solver="highs")

    return run_lag_sklearn_forecast(
        OPERATOR_ID, params, inputs, factory, default_lags=8, min_points=40,
    )
# @AI_GENERATED: end
