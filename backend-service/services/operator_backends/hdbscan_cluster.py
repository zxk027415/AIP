# @AI_GENERATED
"""hdbscan_cluster — sklearn HDBSCAN 密度层次聚类。"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "hdbscan_cluster"
logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    try:
        min_cluster_size = int(params.get("min_cluster_size") or 5)
        min_samples = params.get("min_samples")
        min_samples = int(min_samples) if min_samples not in (None, "", "None") else None
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    numeric = data.select_dtypes(include=[np.number])
    if numeric.empty or len(numeric) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Need >=2 numeric rows")

    X = numeric.fillna(numeric.mean()).astype(float).values
    model = HDBSCAN(min_cluster_size=max(min_cluster_size, 2), min_samples=min_samples)
    labels = model.fit_predict(X)
    n_clusters = int(len(set(labels)) - (1 if -1 in labels else 0))
    logger.info(f"[{OPERATOR_ID}] n_clusters={n_clusters}, noise={(labels == -1).sum()}")
    return {"labels": np.asarray(labels), "n_clusters_found": n_clusters}
# @AI_GENERATED: end
