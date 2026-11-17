# @AI_GENERATED
"""optics_cluster — OPTICS 密度聚类。"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.cluster import OPTICS

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "optics_cluster"
logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    try:
        min_samples = int(params.get("min_samples") or 5)
        xi = float(params.get("xi") if params.get("xi") is not None else 0.05)
        min_cluster_size = params.get("min_cluster_size")
        if min_cluster_size in (None, "", "None"):
            min_cluster_size = None
        else:
            min_cluster_size = float(min_cluster_size)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    numeric = data.select_dtypes(include=[np.number])
    if numeric.empty or len(numeric) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Need >=2 numeric rows")

    X = numeric.fillna(numeric.mean()).astype(float).values
    model = OPTICS(min_samples=max(min_samples, 2), xi=xi, min_cluster_size=min_cluster_size)
    labels = model.fit_predict(X)
    n_clusters = int(len(set(labels)) - (1 if -1 in labels else 0))
    logger.info(f"[{OPERATOR_ID}] n_clusters={n_clusters}")
    return {"labels": np.asarray(labels), "n_clusters_found": n_clusters}
# @AI_GENERATED: end
