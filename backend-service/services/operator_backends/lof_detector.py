# @AI_GENERATED
"""
lof_detector operator backend — 局部离群因子（Local Outlier Factor）。

基于密度的异常检测，标记每个样本的局部异常程度。
"""
import numpy as np
import pandas as pd
from sklearn.neighbors import LocalOutlierFactor
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "lof_detector"


def execute(params: dict, inputs: dict) -> dict:
    """
    LOF 异常检测。

    params:
        - n_neighbors (int, default 20): 邻居数
        - contamination (float | "auto", default "auto"): 异常比例
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
        n_neighbors = int(params.get("n_neighbors") or 20)
    except (TypeError, ValueError):
        n_neighbors = 20

    contam_raw = params.get("contamination", "auto")
    if isinstance(contam_raw, str) and contam_raw.lower() == "auto":
        contamination = "auto"
    else:
        try:
            contamination = float(contam_raw)
        except (TypeError, ValueError):
            contamination = "auto"

    numeric_df = data.select_dtypes(include=[np.number])
    if numeric_df.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")

    X = numeric_df.fillna(numeric_df.mean()).values
    # n_neighbors 不能 >= 样本数
    n_neighbors = min(n_neighbors, max(2, len(X) - 1))

    clf = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    labels = clf.fit_predict(X).astype(int)
    # negative_outlier_factor_ 越小越异常，取反使值大代表更异常
    scores = -clf.negative_outlier_factor_

    n_anomaly = int(np.sum(labels == -1))
    logger.info(f"[{OPERATOR_ID}] n_samples={len(X)}, n_neighbors={n_neighbors}, anomalies={n_anomaly}")
    return {"labels": labels, "scores": scores}
# @AI_GENERATED: end
