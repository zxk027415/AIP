# @AI_GENERATED
"""
mape_score operator backend — Computes Mean Absolute Percentage Error (MAPE).

MAPE = mean(|y_true - y_pred| / |y_true|) * 100

Rows where y_true == 0 are excluded from calculation; their count is returned.
Error if all y_true values are zero, or if lengths don't match.
"""
import numpy as np
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "mape_score"


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute MAPE between true and predicted values, excluding zero y_true entries.

    Args:
        params: Operator parameters (unused for this operator).
        inputs: {"y_true": array-like, "y_pred": array-like}

    Returns:
        {"score": float, "excluded_zero_count": int}
        — score is MAPE in percent; excluded_zero_count is how many y_true==0 rows were dropped.
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

    # Identify and exclude rows where y_true == 0
    nonzero_mask = y_true != 0.0
    excluded_zero_count = int(np.sum(~nonzero_mask))

    if excluded_zero_count > 0:
        logger.warning(
            f"[{OPERATOR_ID}] Excluding {excluded_zero_count} row(s) where y_true == 0"
        )

    if not np.any(nonzero_mask):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "All y_true values are zero, cannot compute MAPE",
        )

    y_true_nz = y_true[nonzero_mask]
    y_pred_nz = y_pred[nonzero_mask]

    score = float(np.mean(np.abs(y_true_nz - y_pred_nz) / np.abs(y_true_nz)) * 100.0)

    logger.info(
        f"[{OPERATOR_ID}] MAPE = {score:.4f}%, excluded_zero_count = {excluded_zero_count}"
    )

    return {"score": score, "excluded_zero_count": excluded_zero_count}
# @AI_GENERATED: end
