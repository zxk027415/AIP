# @AI_GENERATED
"""
accuracy_score operator backend — 分类准确率。
"""
import numpy as np
from sklearn.metrics import accuracy_score as sk_accuracy
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "accuracy_score"


def execute(params: dict, inputs: dict) -> dict:
    """
    计算分类准确率。

    inputs: y_true, y_pred (array-like)
    returns: {"score": float}
    """
    y_true = inputs.get("y_true")
    y_pred = inputs.get("y_pred")

    if y_true is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'y_true' is required")
    if y_pred is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'y_pred' is required")

    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    if len(y_true) != len(y_pred):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", f"y_true len ({len(y_true)}) != y_pred len ({len(y_pred)})")
    if len(y_true) == 0:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "inputs are empty")

    score = float(sk_accuracy(y_true, y_pred))
    logger.info(f"[{OPERATOR_ID}] accuracy = {score:.4f}")
    return {"score": score}
# @AI_GENERATED: end
