# @AI_GENERATED
"""
precision_recall_f1 operator backend — 分类指标计算（accuracy / precision / recall / F1）。

输入 y_true / y_pred，支持 average 参数（macro / micro / weighted）。
y_true 与 y_pred 长度不一致时抛 ParameterError。
"""
import logging

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "precision_recall_f1"

logger = logging.getLogger(__name__)

_VALID_AVERAGES = {"macro", "micro", "weighted"}


def execute(params: dict, inputs: dict) -> dict:
    """
    计算分类评估指标。

    Args:
        params:
            - average (str): "macro" | "micro" | "weighted"，默认 "macro"
        inputs:
            - y_true (np.ndarray | list): 真实标签
            - y_pred (np.ndarray | list): 预测标签

    Returns:
        {
            "accuracy":  float,
            "precision": float,
            "recall":    float,
            "f1":        float,
        }

    Raises:
        OperatorExecutionError(ParameterError): y_true / y_pred 长度不一致
        OperatorExecutionError(InputError):     y_true / y_pred 缺失或为空
    """
    # ── 解析输入 ──────────────────────────────────────────────────────────────
    y_true = inputs.get("y_true")
    y_pred = inputs.get("y_pred") if inputs.get("y_pred") is not None else inputs.get("predictions")

    if y_true is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'y_true' is required"
        )
    if y_pred is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'y_pred' (or 'predictions') is required"
        )

    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    if len(y_true) == 0 or len(y_pred) == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "y_true and y_pred must not be empty"
        )

    # ── 长度校验 ──────────────────────────────────────────────────────────────
    if len(y_true) != len(y_pred):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"y_true length ({len(y_true)}) != y_pred length ({len(y_pred)})"
        )

    # ── 解析参数 ──────────────────────────────────────────────────────────────
    average = str(params.get("average") or "macro").strip().lower()
    if average not in _VALID_AVERAGES:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"Invalid average '{average}'. Must be one of {sorted(_VALID_AVERAGES)}"
        )

    # ── 计算指标 ──────────────────────────────────────────────────────────────
    accuracy  = float(accuracy_score(y_true, y_pred))
    precision = float(precision_score(y_true, y_pred, average=average, zero_division=0))
    recall    = float(recall_score(y_true, y_pred, average=average, zero_division=0))
    f1        = float(f1_score(y_true, y_pred, average=average, zero_division=0))

    logger.info(
        f"[{OPERATOR_ID}] average={average} | "
        f"accuracy={accuracy:.4f}, precision={precision:.4f}, "
        f"recall={recall:.4f}, f1={f1:.4f}"
    )

    return {
        "accuracy":  accuracy,
        "precision": precision,
        "recall":    recall,
        "f1":        f1,
    }
# @AI_GENERATED: end
