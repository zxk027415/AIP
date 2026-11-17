# @AI_GENERATED
"""adasyn_oversample — 自适应合成过采样（纯 sklearn 实现，无需 imblearn）。"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "adasyn_oversample"
logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    inputs: features (DataFrame), target (array)
    params: sampling_strategy (minority 目标比例，默认 1.0=与多数类持平), n_neighbors, random_state
    returns: features, target, n_synthetic
    """
    features = inputs.get("features")
    target = inputs.get("target")
    if features is None or not isinstance(features, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "features must be a DataFrame")
    if target is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "target is required")

    try:
        sampling_strategy = float(params.get("sampling_strategy") if params.get("sampling_strategy") is not None else 1.0)
        n_neighbors = int(params.get("n_neighbors") or 5)
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    X = features.select_dtypes(include=[np.number]).fillna(0.0).astype(float)
    if X.empty:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "No numeric feature columns")
    y = np.asarray(target)
    if len(y) != len(X):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "features/target length mismatch")

    classes, counts = np.unique(y, return_counts=True)
    if len(classes) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "target must have >= 2 classes")

    majority = classes[np.argmax(counts)]
    minority = classes[np.argmin(counts)]
    n_maj = int(counts.max())
    n_min = int(counts.min())
    target_min = int(round(n_maj * sampling_strategy))
    n_syn = max(target_min - n_min, 0)
    if n_syn == 0:
        return {"features": X.copy(), "target": y.copy(), "n_synthetic": 0}

    X_min = X.loc[y == minority].values
    k = min(max(n_neighbors, 1), len(X_min) - 1) if len(X_min) > 1 else 1
    if len(X_min) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Need >=2 minority samples for ADASYN")

    # 用全体样本估计每个少数点周围多数类比例作为难度权重
    nn_all = NearestNeighbors(n_neighbors=min(k + 1, len(X)))
    nn_all.fit(X.values)
    _, idx_all = nn_all.kneighbors(X_min)
    ratios = []
    for neigh in idx_all:
        neigh_labels = y[neigh[1:]]  # 去掉自身
        ratios.append(float(np.mean(neigh_labels == majority)) if len(neigh_labels) else 0.0)
    ratios = np.asarray(ratios, dtype=float)
    if ratios.sum() <= 0:
        ratios = np.ones(len(X_min), dtype=float)
    weights = ratios / ratios.sum()
    rng = np.random.RandomState(random_state)

    nn_min = NearestNeighbors(n_neighbors=k + 1)
    nn_min.fit(X_min)
    syn_rows = []
    for _ in range(n_syn):
        i = int(rng.choice(len(X_min), p=weights))
        dists, idxs = nn_min.kneighbors(X_min[i].reshape(1, -1))
        j = int(rng.choice(idxs[0][1:]))
        gap = rng.rand()
        syn_rows.append(X_min[i] + gap * (X_min[j] - X_min[i]))

    X_syn = pd.DataFrame(np.asarray(syn_rows), columns=X.columns)
    y_syn = np.full(n_syn, minority)
    X_out = pd.concat([X.reset_index(drop=True), X_syn], ignore_index=True)
    y_out = np.concatenate([y, y_syn])
    logger.info(f"[{OPERATOR_ID}] minority={minority}, n_synthetic={n_syn}, out={len(X_out)}")
    return {"features": X_out, "target": y_out, "n_synthetic": n_syn}
# @AI_GENERATED: end
