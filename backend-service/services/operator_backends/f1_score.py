# @AI_GENERATED
"""
f1_score operator backend — F1 分数。

支持 binary / macro / micro / weighted 模式。
"""
import numpy as np
from sklearn.metrics import f1_score as sk_f1
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "f1_score"


def execute(params: dict, inputs: dict) -> dict:
    """
    计算 F1 分数。

    params:
        - average (str): binary / macro / micro / weighted，默认 macro
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

    average = str(params.get("average") or "macro").strip().lower()
    if average not in ("binary", "macro", "micro", "weighted"):
        average = "macro"

    score = float(sk_f1(y_true, y_pred, average=average, zero_division=0))
    logger.info(f"[{OPERATOR_ID}] F1({average}) = {score:.4f}")
    return {"score": score}
# @AI_GENERATED: end
