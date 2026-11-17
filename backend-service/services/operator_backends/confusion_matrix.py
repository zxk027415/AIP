# @AI_GENERATED
"""
confusion_matrix operator backend — 混淆矩阵 + classification_report。

输入 y_true / y_pred，返回：
  - matrix : pd.DataFrame（行=真实类别，列=预测类别）
  - report : str（sklearn classification_report 文本）

y_true 与 y_pred 长度不一致时抛 ParameterError。
"""
import logging

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.metrics import confusion_matrix as sk_confusion_matrix

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "confusion_matrix"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    生成混淆矩阵和分类报告。

    Args:
        params: 无必填参数（保留扩展）
        inputs:
            - y_true (np.ndarray | list): 真实标签
            - y_pred (np.ndarray | list): 预测标签

    Returns:
        {
            "matrix": pd.DataFrame,  # 行=真实类别，列=预测类别
            "report": str,           # sklearn classification_report 文本
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

    # ── 计算混淆矩阵 ───────────────────────────────────────────────────────────
    labels = sorted(np.unique(np.concatenate([y_true, y_pred])))
    cm = sk_confusion_matrix(y_true, y_pred, labels=labels)
    matrix_df = pd.DataFrame(cm, index=labels, columns=labels)
    matrix_df.index.name = "true"
    matrix_df.columns.name = "predicted"

    # ── 生成 classification_report ────────────────────────────────────────────
    report = classification_report(y_true, y_pred, labels=labels, zero_division=0)

    logger.info(
        f"[{OPERATOR_ID}] n_classes={len(labels)}, n_samples={len(y_true)}"
    )

    return {
        "matrix": matrix_df,
        "report": report,
    }
# @AI_GENERATED: end
