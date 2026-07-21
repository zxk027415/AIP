# @AI_GENERATED
"""adaboost_classifier — AdaBoost 分类器 train/predict。"""
from __future__ import annotations

from sklearn.ensemble import AdaBoostClassifier

from services.operator_backends._sklearn_classifier_utils import run_sklearn_classifier
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "adaboost_classifier"


def execute(params: dict, inputs: dict) -> dict:
    try:
        n_estimators = int(params.get("n_estimators") or 50)
        learning_rate = float(params.get("learning_rate") or 1.0)
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    def factory():
        return AdaBoostClassifier(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            random_state=random_state,
        )

    return run_sklearn_classifier(
        OPERATOR_ID, params, inputs, factory, model_prefix="adaboost",
    )
# @AI_GENERATED: end
