# @AI_GENERATED
"""
polynomial_features operator backend — 多项式/交叉特征生成。

使用 sklearn PolynomialFeatures 生成二次/三次交叉项。
"""
import pandas as pd
from sklearn.preprocessing import PolynomialFeatures as SKPolynomialFeatures
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "polynomial_features"


def execute(params: dict, inputs: dict) -> dict:
    """
    多项式特征生成。

    params:
        - degree (int): 多项式阶数，默认 2
        - interaction_only (bool): 是否只生成交互项（不含 x^2），默认 False
        - include_bias (bool): 是否包含常数列 1，默认 False
        - columns (list[str] | None): 输入列，None 则全部数值列
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

    try:
        degree = int(params.get("degree") or 2)
    except (TypeError, ValueError):
        degree = 2
    interaction_only = str(params.get("interaction_only", "false")).lower() in ("true", "1", "yes")
    include_bias = str(params.get("include_bias", "false")).lower() in ("true", "1", "yes")

    columns = params.get("columns")
    if columns is None:
        columns = list(data.select_dtypes(include="number").columns)
    for col in columns:
        if col not in data.columns:
            raise OperatorExecutionError(OPERATOR_ID, "ColumnNotFoundError", f"Column '{col}' not found")

    if len(columns) == 0:
        return {"data": data.copy()}

    pf = SKPolynomialFeatures(degree=degree, interaction_only=interaction_only, include_bias=include_bias)
    X = data[columns].values
    X_poly = pf.fit_transform(X)
    feature_names = pf.get_feature_names_out(columns)

    result = pd.DataFrame(X_poly, columns=feature_names, index=data.index)
    # 保留非目标列
    other_cols = [c for c in data.columns if c not in columns]
    if other_cols:
        result = pd.concat([data[other_cols].reset_index(drop=True), result.reset_index(drop=True)], axis=1)

    logger.info(f"[{OPERATOR_ID}] degree={degree}, input_features={len(columns)}, output_features={X_poly.shape[1]}")
    return {"data": result}
# @AI_GENERATED: end
