# @AI_GENERATED
"""balanced_accuracy — 平衡准确率评估。"""
from __future__ import annotations

import numpy as np
from loguru import logger
from sklearn.metrics import balanced_accuracy_score

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "balanced_accuracy"


def execute(params: dict, inputs: dict) -> dict:
    y_true = inputs.get("y_true")
    y_pred = inputs.get("y_pred")
    if y_true is None or y_pred is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "y_true and y_pred are required")

    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    if len(y_true) != len(y_pred) or len(y_true) == 0:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "y_true/y_pred length invalid")

    score = float(balanced_accuracy_score(y_true, y_pred))
    logger.info(f"[{OPERATOR_ID}] balanced_accuracy={score:.4f}")
    return {"score": score}
# @AI_GENERATED: end
