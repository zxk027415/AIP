# @AI_GENERATED
"""
mse_rmse_mae operator backend — Computes MSE, RMSE, and MAE metrics.

Error if y_true and y_pred lengths don't match.
"""
import numpy as np
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "mse_rmse_mae"


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute MSE, RMSE, and MAE between true and predicted values.

    Args:
        params: Operator parameters (unused for this operator).
        inputs: {"y_true": array-like, "y_pred": array-like}

    Returns:
        {"mse": float, "rmse": float, "mae": float}
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

    errors = y_pred - y_true
    mse_val = float(np.mean(errors ** 2))
    rmse_val = float(np.sqrt(mse_val))
    mae_val = float(np.mean(np.abs(errors)))

    logger.info(
        f"[{OPERATOR_ID}] MSE={mse_val:.4f}, RMSE={rmse_val:.4f}, MAE={mae_val:.4f}"
    )

    return {"mse": mse_val, "rmse": rmse_val, "mae": mae_val}
# @AI_GENERATED: end
