# @AI_GENERATED
"""
quantile_transform — 分位数变换（均匀/正态映射）。
"""
from __future__ import annotations

import pandas as pd
from loguru import logger
from sklearn.preprocessing import QuantileTransformer

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "quantile_transform"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - columns (list[str] | None): 目标列，默认全部数值列
        - output_distribution (str): "uniform" | "normal"，默认 uniform
        - n_quantiles (int): 分位数数量，默认 min(1000, n_samples)
        - random_state (int): 默认 42
    inputs:
        - data (pd.DataFrame)
    returns:
        {"data": pd.DataFrame}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")
    if data.empty:
        return {"data": data}

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)
    if not columns:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns to transform")
    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    dist = str(params.get("output_distribution") or "uniform").strip().lower()
    if dist not in ("uniform", "normal"):
        dist = "uniform"
    try:
        n_quantiles = int(params.get("n_quantiles") or min(1000, max(10, len(data))))
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid numeric params: {e}")

    n_quantiles = max(10, min(n_quantiles, len(data)))
    result = data.copy()
    X = result[columns].astype(float)
    transformer = QuantileTransformer(
        n_quantiles=n_quantiles,
        output_distribution=dist,
        random_state=random_state,
    )
    try:
        transformed = transformer.fit_transform(X)
    except Exception as e:
        raise OperatorExecutionError(OPERATOR_ID, "TransformError", f"QuantileTransformer failed: {e}")

    result[columns] = transformed
    logger.info(f"[{OPERATOR_ID}] columns={columns}, dist={dist}, n_quantiles={n_quantiles}")
    return {"data": result}
# @AI_GENERATED: end
