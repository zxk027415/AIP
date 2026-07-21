# @AI_GENERATED
"""stratified_sample — 按标签分层抽样。"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "stratified_sample"
logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    inputs: features (DataFrame), target (array)
    params: sample_ratio (0-1, 默认 0.5), random_state
    returns: features, target, sample_indices
    """
    features = inputs.get("features")
    if features is None:
        features = inputs.get("data")
    target = inputs.get("target")
    if features is None or not isinstance(features, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "features/data must be a DataFrame")
    if target is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "target is required for stratification")

    try:
        sample_ratio = float(params.get("sample_ratio") if params.get("sample_ratio") is not None else 0.5)
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    sample_ratio = min(max(sample_ratio, 0.01), 0.99)
    y = np.asarray(target)
    if len(y) != len(features):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "features/target length mismatch")
    if len(np.unique(y)) < 2:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "target must have >= 2 classes")

    idx = np.arange(len(features))
    try:
        idx_sample, _ = train_test_split(
            idx, train_size=sample_ratio, stratify=y, random_state=random_state,
        )
    except ValueError as e:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", f"Stratified split failed: {e}")

    idx_sample = np.sort(idx_sample)
    logger.info(f"[{OPERATOR_ID}] ratio={sample_ratio}, n={len(idx_sample)}")
    return {
        "features": features.iloc[idx_sample].reset_index(drop=True),
        "target": y[idx_sample],
        "sample_indices": idx_sample,
        "n_rows": int(len(idx_sample)),
    }
# @AI_GENERATED: end
