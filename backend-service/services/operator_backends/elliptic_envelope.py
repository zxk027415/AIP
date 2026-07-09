# @AI_GENERATED
"""
elliptic_envelope operator backend — 椭圆包络异常检测。

假设数据服从多元高斯分布，用协方差矩阵估计椭圆包络，
包络外的点判定为异常。适合数据分布接近正态的场景。
"""
import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "elliptic_envelope"


def execute(params: dict, inputs: dict) -> dict:
    """
    椭圆包络异常检测。

    params:
        - contamination (float, default 0.1): 异常比例
        - support_fraction (float | None): 支持率
    inputs:
        - data (pd.DataFrame)
    returns:
        {"labels": np.ndarray (-1=异常, 1=正常), "scores": np.ndarray}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")
    if data.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' is empty")

    try:
        contamination = float(params.get("contamination") or 0.1)
    except (TypeError, ValueError):
        contamination = 0.1
    if not (0 < contamination <= 0.5):
        contamination = 0.1

    support_fraction = params.get("support_fraction")
    if support_fraction is not None:
        try:
            support_fraction = float(support_fraction)
        except (TypeError, ValueError):
            support_fraction = None

    numeric_df = data.select_dtypes(include=[np.number])
    if numeric_df.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")

    X = numeric_df.fillna(numeric_df.mean()).values
    if len(X) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Need at least 2 samples")

    try:
        clf = EllipticEnvelope(
            contamination=contamination,
            support_fraction=support_fraction,
            random_state=42,
        )
        labels = clf.fit_predict(X).astype(int)
        scores = clf.decision_function(X).astype(float)
    except Exception as e:
        raise OperatorExecutionError(OPERATOR_ID, "FitError", f"EllipticEnvelope fit failed: {e}")

    n_anomaly = int(np.sum(labels == -1))
    logger.info(f"[{OPERATOR_ID}] n_samples={len(X)}, contamination={contamination}, anomalies={n_anomaly}")
    return {"labels": labels, "scores": scores}
# @AI_GENERATED: end
