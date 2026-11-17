# @AI_GENERATED
"""
knn_anomaly — 基于 K 近邻平均距离的异常检测。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.neighbors import NearestNeighbors

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "knn_anomaly"


def execute(params: dict, inputs: dict) -> dict:
    """
    params:
        - n_neighbors (int): 默认 5
        - contamination (float): 异常比例，默认 0.1；也可用 threshold 作为距离分位阈值覆盖
    inputs:
        - data (pd.DataFrame)
    returns:
        {"labels": ndarray, "scores": ndarray}  # score = 到 k 邻的平均距离
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")
    if data.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' is empty")

    try:
        n_neighbors = int(params.get("n_neighbors") or 5)
        contamination = float(params.get("contamination") if params.get("contamination") is not None else 0.1)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid numeric params: {e}")

    contamination = min(max(contamination, 0.01), 0.5)
    numeric = data.select_dtypes(include="number")
    if numeric.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")

    X = numeric.fillna(numeric.mean()).astype(float).values
    n = len(X)
    if n < 3:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", f"Need >=3 rows, got {n}")

    k = min(max(n_neighbors, 1), n - 1)
    nn = NearestNeighbors(n_neighbors=k + 1)  # +1 含自身
    nn.fit(X)
    dists, _ = nn.kneighbors(X)
    # 去掉自身距离 0
    scores = dists[:, 1:].mean(axis=1)
    # 全点重合 / 距离全相等：无法区分异常，全部标正常
    if float(np.nanmax(scores) - np.nanmin(scores)) < 1e-15:
        labels = np.ones(n, dtype=int)
    else:
        cut = float(np.quantile(scores, 1.0 - contamination))
        labels = np.where(scores >= cut, -1, 1).astype(int)

    logger.info(f"[{OPERATOR_ID}] k={k}, contamination={contamination}, anomalies={int(np.sum(labels == -1))}")
    return {"labels": labels, "scores": scores.astype(float)}
# @AI_GENERATED: end
