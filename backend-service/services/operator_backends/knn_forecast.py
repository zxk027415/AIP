# @AI_GENERATED
"""knn_forecast — 滞后特征 + KNeighborsRegressor 单变量多步预测。"""
from __future__ import annotations

from sklearn.neighbors import KNeighborsRegressor

from services.operator_backends._lag_forecast_utils import run_lag_sklearn_forecast
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "knn_forecast"


def execute(params: dict, inputs: dict) -> dict:
    try:
        n_neighbors = int(params.get("n_neighbors") or 5)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    def factory():
        return KNeighborsRegressor(n_neighbors=max(n_neighbors, 1))

    return run_lag_sklearn_forecast(OPERATOR_ID, params, inputs, factory, default_lags=12)
# @AI_GENERATED: end
