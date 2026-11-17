# @AI_GENERATED
"""class_imbalance_check — 类别不平衡诊断。"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "class_imbalance_check"
logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    inputs: target (array) 或 data+label_column
    params: imbalance_threshold (多数/少数比，默认 3.0)
    returns: class_counts, imbalance_ratio, is_imbalanced, minority_class, majority_class
    """
    target = inputs.get("target")
    if target is None:
        data = inputs.get("data")
        label_col = params.get("label_column") or params.get("column")
        if isinstance(data, pd.DataFrame) and label_col and label_col in data.columns:
            target = data[label_col].values
        else:
            raise OperatorExecutionError(
                OPERATOR_ID, "InputError",
                "Provide target array or data + label_column",
            )

    try:
        threshold = float(params.get("imbalance_threshold") if params.get("imbalance_threshold") is not None else 3.0)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    y = np.asarray(target)
    if len(y) == 0:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "target is empty")

    classes, counts = np.unique(y, return_counts=True)
    class_counts = {str(c): int(n) for c, n in zip(classes, counts)}
    maj_i = int(np.argmax(counts))
    min_i = int(np.argmin(counts))
    ratio = float(counts[maj_i] / max(counts[min_i], 1))
    is_imbalanced = bool(ratio >= threshold)
    logger.info(f"[{OPERATOR_ID}] ratio={ratio:.3f}, imbalanced={is_imbalanced}")
    return {
        "class_counts": class_counts,
        "imbalance_ratio": ratio,
        "is_imbalanced": is_imbalanced,
        "majority_class": classes[maj_i].item() if hasattr(classes[maj_i], "item") else classes[maj_i],
        "minority_class": classes[min_i].item() if hasattr(classes[min_i], "item") else classes[min_i],
        "n_classes": int(len(classes)),
    }
# @AI_GENERATED: end
