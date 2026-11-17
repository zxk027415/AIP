# @AI_GENERATED
"""
classification_report operator backend — 分类完整报告。

返回每类的 precision/recall/f1/support 以及 macro/weighted 平均。
"""
import numpy as np
from sklearn.metrics import classification_report as sk_report, precision_score, recall_score, f1_score, accuracy_score
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "classification_report"


def execute(params: dict, inputs: dict) -> dict:
    """
    分类报告。

    inputs: y_true, y_pred (array-like)
    returns:
        {
            "report_text": str,        # sklearn 文本报告
            "report_dict": dict,       # 结构化报告
            "accuracy": float,
            "macro_precision": float,
            "macro_recall": float,
            "macro_f1": float,
        }
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
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"y_true len ({len(y_true)}) != y_pred len ({len(y_pred)})"
        )
    if len(y_true) == 0:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "inputs are empty")

    report_text = sk_report(y_true, y_pred, zero_division=0)
    report_dict = sk_report(y_true, y_pred, output_dict=True, zero_division=0)

    result = {
        "report_text": report_text,
        "report_dict": report_dict,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_precision": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
    }
    logger.info(f"[{OPERATOR_ID}] accuracy={result['accuracy']:.4f}, macro_f1={result['macro_f1']:.4f}")
    return result
# @AI_GENERATED: end
