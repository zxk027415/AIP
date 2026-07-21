# @AI_GENERATED
"""pinball_loss — 分位数预测 Pinball / 分位损失。"""
from __future__ import annotations

import numpy as np
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "pinball_loss"


def execute(params: dict, inputs: dict) -> dict:
    """
    inputs: y_true, y_pred (array-like)
    params: quantile (默认 0.5)
    returns: score (越小越好)
    """
    y_true = inputs.get("y_true")
    y_pred = inputs.get("y_pred")
    if y_true is None or y_pred is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "y_true and y_pred are required")

    try:
        q = float(params.get("quantile") if params.get("quantile") is not None else 0.5)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid quantile: {e}")
    q = min(max(q, 0.01), 0.99)

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if len(y_true) != len(y_pred) or len(y_true) == 0:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "y_true/y_pred length invalid")

    err = y_true - y_pred
    loss = np.where(err >= 0, q * err, (q - 1.0) * err)
    score = float(np.mean(loss))
    logger.info(f"[{OPERATOR_ID}] q={q}, pinball={score:.6f}")
    return {"score": score, "quantile": q}
# @AI_GENERATED: end
