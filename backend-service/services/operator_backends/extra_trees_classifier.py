# @AI_GENERATED
"""extra_trees_classifier — ExtraTrees 分类器 train/predict。"""
from __future__ import annotations

from sklearn.ensemble import ExtraTreesClassifier

from services.operator_backends._sklearn_classifier_utils import run_sklearn_classifier
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "extra_trees_classifier"


def execute(params: dict, inputs: dict) -> dict:
    try:
        n_estimators = int(params.get("n_estimators") or 50)
        max_depth = params.get("max_depth")
        max_depth = int(max_depth) if max_depth not in (None, "", "None") else None
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    def factory():
        return ExtraTreesClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            n_jobs=1,
        )

    return run_sklearn_classifier(
        OPERATOR_ID, params, inputs, factory, model_prefix="etrees",
    )
# @AI_GENERATED: end
