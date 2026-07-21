# @AI_GENERATED
"""calibrated_classifier — CalibratedClassifierCV(LogisticRegression) 概率校准分类。"""
from __future__ import annotations

from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression

from services.operator_backends._sklearn_classifier_utils import run_sklearn_classifier
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "calibrated_classifier"


def execute(params: dict, inputs: dict) -> dict:
    try:
        method = str(params.get("method") or "sigmoid")
        if method not in ("sigmoid", "isotonic"):
            method = "sigmoid"
        cv = int(params.get("cv") or 3)
        max_iter = int(params.get("max_iter") or 500)
        C = float(params.get("C") or 1.0)
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    def factory():
        base = LogisticRegression(C=C, max_iter=max_iter, random_state=random_state)
        return CalibratedClassifierCV(estimator=base, method=method, cv=cv)

    return run_sklearn_classifier(
        OPERATOR_ID, params, inputs, factory,
        model_prefix="calclf",
        importance_attr=None,
    )
# @AI_GENERATED: end
