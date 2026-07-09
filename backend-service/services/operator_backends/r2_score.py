# @AI_GENERATED
"""
r2_score operator backend — Computes R² (coefficient of determination) score.

Error if y_true and y_pred lengths don't match or either is None.
"""
import numpy as np
from loguru import logger
from sklearn.metrics import r2_score as sklearn_r2_score

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "r2_score"


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute R² score between true and predicted values.

    Args:
        params: Operator parameters (unused for this operator).
        inputs: {"y_true": array-like, "y_pred": array-like}

    Returns:
        {"score": float} — R² value (can be negative for poor models).
    """
    y_true = inputs.get("y_true")
    y_pred = inputs.get("y_pred")

    if y_true is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'y_true' is required"
        )
    if y_pred is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'y_pred' is required"
        )

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    if len(y_true) != len(y_pred):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"y_true length ({len(y_true)}) != y_pred length ({len(y_pred)})",
        )

    if len(y_true) == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "y_true and y_pred are empty"
        )

    score = float(sklearn_r2_score(y_true, y_pred))

    logger.info(f"[{OPERATOR_ID}] R² = {score:.4f}")

    return {"score": score}
# @AI_GENERATED: end
