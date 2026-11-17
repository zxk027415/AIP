# @AI_GENERATED
"""
smape_score operator backend — Computes Symmetric Mean Absolute Percentage Error.

Reuses utils.smape logic.
Error if y_true and y_pred lengths don't match.
"""
import numpy as np
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "smape_score"


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute SMAPE between true and predicted values.

    SMAPE = mean(|y_pred - y_true| / max(eps, (|y_true| + |y_pred|) / 2)) * 100

    Args:
        params: Operator parameters (unused for this operator).
        inputs: {"y_true": array-like, "y_pred": array-like}

    Returns:
        {"score": float} — SMAPE value in percent.
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

    # Reuse utils.smape logic
    eps = 1e-8
    denom = np.maximum(eps, (np.abs(y_true) + np.abs(y_pred)) / 2.0)
    score = float(np.mean(np.abs(y_pred - y_true) / denom) * 100.0)

    logger.info(f"[{OPERATOR_ID}] SMAPE = {score:.4f}%")

    return {"score": score}
# @AI_GENERATED: end
