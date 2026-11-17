# @AI_GENERATED
"""
silhouette_score operator backend — 聚类轮廓系数。

评估聚类质量：值越接近 1 越好，接近 0 表示交叠，负值表示分配错误。
"""
import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_score as sk_silhouette
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "silhouette_score"


def execute(params: dict, inputs: dict) -> dict:
    """
    聚类轮廓系数。

    inputs:
        - data (pd.DataFrame): 原始特征数据
        - labels (array-like): 聚类标签
    returns:
        {"score": float}
    """
    data = inputs.get("data")
    labels = inputs.get("labels")

    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")
    if labels is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'labels' is required")

    labels = np.asarray(labels)
    numeric_df = data.select_dtypes(include=[np.number])
    if numeric_df.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")
    if len(numeric_df) != len(labels):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", f"data rows ({len(numeric_df)}) != labels length ({len(labels)})")

    unique_labels = set(labels)
    unique_labels.discard(-1)  # 忽略噪声点
    if len(unique_labels) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Need at least 2 clusters for silhouette score")

    X = numeric_df.fillna(numeric_df.mean()).values
    score = float(sk_silhouette(X, labels))

    logger.info(f"[{OPERATOR_ID}] silhouette = {score:.4f}, n_clusters={len(unique_labels)}")
    return {"score": score}
# @AI_GENERATED: end
