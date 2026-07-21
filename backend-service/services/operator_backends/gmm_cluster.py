# @AI_GENERATED
"""gmm_cluster — 高斯混合模型聚类。"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "gmm_cluster"
logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame")

    try:
        n_components = int(params.get("n_components") or params.get("n_clusters") or 3)
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
        covariance_type = str(params.get("covariance_type") or "full")
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    numeric = data.select_dtypes(include=[np.number])
    if numeric.empty or len(numeric) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Need >=2 numeric rows")

    X = numeric.fillna(numeric.mean()).astype(float).values
    n_components = max(1, min(n_components, len(X)))
    gmm = GaussianMixture(
        n_components=n_components,
        covariance_type=covariance_type,
        random_state=random_state,
    )
    labels = gmm.fit_predict(X)
    logger.info(f"[{OPERATOR_ID}] n_components={n_components}")
    return {
        "labels": np.asarray(labels),
        "n_clusters_found": int(len(np.unique(labels))),
        "means": np.asarray(gmm.means_),
        "weights": np.asarray(gmm.weights_),
    }
# @AI_GENERATED: end
