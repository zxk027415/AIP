# @AI_GENERATED
"""
roc_auc operator backend — Computes ROC-AUC score.

Supports binary and multiclass classification.
Multiclass uses One-vs-Rest (ovr) or One-vs-One (ovo) strategy.
Error if y_true and y_score lengths differ, or if only one unique class is present.
"""
import numpy as np
from loguru import logger
from sklearn.metrics import roc_auc_score

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "roc_auc"


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute ROC-AUC score between true labels and predicted scores.

    Args:
        params: {
            "multi_class": "ovr" | "ovo"  (default "ovr"),
            "average": "macro" | "micro" | "weighted"  (default "macro"),
        }
        inputs: {
            "y_true": array-like of true class labels,
            "y_score": array-like (binary) or 2D array (multiclass probability matrix),
        }

    Returns:
        {"score": float} — ROC-AUC value in [0, 1].
    """
    y_true = inputs.get("y_true")
    y_score = inputs.get("y_score")

    if y_true is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'y_true' is required"
        )
    if y_score is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'y_score' is required"
        )

    multi_class = params.get("multi_class", "ovr")
    average = params.get("average", "macro")

    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)

    if len(y_true) != len(y_score):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"y_true length ({len(y_true)}) != y_score length ({len(y_score)})",
        )

    if len(y_true) == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "y_true and y_score are empty"
        )

    unique_classes = np.unique(y_true)
    if len(unique_classes) < 2:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"y_true must contain at least 2 unique classes; found: {unique_classes.tolist()}",
        )

    is_multiclass = len(unique_classes) > 2

    try:
        if is_multiclass:
            score = float(
                roc_auc_score(
                    y_true,
                    y_score,
                    multi_class=multi_class,
                    average=average,
                )
            )
        else:
            # For binary classification, y_score should be 1D (positive class probabilities)
            y_score_bin = y_score if y_score.ndim == 1 else y_score[:, 1]
            score = float(roc_auc_score(y_true, y_score_bin))
    except ValueError as exc:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", str(exc)
        ) from exc

    logger.info(
        f"[{OPERATOR_ID}] ROC-AUC = {score:.4f} "
        f"(multi_class={multi_class}, average={average}, classes={len(unique_classes)})"
    )

    return {"score": score}
# @AI_GENERATED: end
