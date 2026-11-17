# @AI_GENERATED
"""random_forest_forecast — 滞后特征 + RandomForest 单变量多步预测。"""
from __future__ import annotations

from sklearn.ensemble import RandomForestRegressor

from services.operator_backends._lag_forecast_utils import run_lag_sklearn_forecast
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "random_forest_forecast"


def execute(params: dict, inputs: dict) -> dict:
    """
    params: timestamp_column, value_column, forecast_horizon, n_lags, n_estimators, max_depth, random_state
    inputs: data (DataFrame)
    returns: forecast, forecast_dates
    """
    try:
        n_estimators = int(params.get("n_estimators") or 50)
        max_depth = params.get("max_depth")
        max_depth = int(max_depth) if max_depth not in (None, "", "None") else None
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    def factory():
        return RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            n_jobs=1,
        )

    return run_lag_sklearn_forecast(OPERATOR_ID, params, inputs, factory, default_lags=12)
# @AI_GENERATED: end
