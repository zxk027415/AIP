# @AI_GENERATED
"""
agglomerative_clustering operator backend — 层次聚类 (凝聚式)。

使用 sklearn.cluster.AgglomerativeClustering。
"""
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "agglomerative_clustering"


def execute(params: dict, inputs: dict) -> dict:
    """
    层次聚类。

    params:
        - n_clusters (int, default 3)
        - linkage (str: ward/complete/average/single, default "ward")
    inputs:
        - data (pd.DataFrame)
    returns:
        {"labels": np.ndarray, "n_clusters": int}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    try:
        n_clusters = int(params.get("n_clusters") or 3)
    except (TypeError, ValueError):
        n_clusters = 3

    linkage = str(params.get("linkage") or "ward").strip().lower()
    if linkage not in ("ward", "complete", "average", "single"):
        linkage = "ward"

    numeric_df = data.select_dtypes(include=[np.number])
    if numeric_df.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric columns found")
    if len(numeric_df) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Need at least 2 samples")

    X = numeric_df.fillna(numeric_df.mean()).values
    model = AgglomerativeClustering(n_clusters=n_clusters, linkage=linkage)
    labels = model.fit_predict(X).astype(int)

    logger.info(f"[{OPERATOR_ID}] n_clusters={n_clusters}, linkage={linkage}, n_samples={len(X)}")
    return {"labels": labels, "n_clusters": n_clusters}
# @AI_GENERATED: end
