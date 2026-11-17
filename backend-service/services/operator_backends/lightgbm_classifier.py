# @AI_GENERATED
"""lightgbm_classifier — LightGBM 分类器 train/predict。"""
from __future__ import annotations

from services.operator_backends._sklearn_classifier_utils import run_sklearn_classifier
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "lightgbm_classifier"


def execute(params: dict, inputs: dict) -> dict:
    try:
        from lightgbm import LGBMClassifier
    except ImportError as e:
        raise OperatorExecutionError(OPERATOR_ID, "DependencyError", f"lightgbm not installed: {e}")

    try:
        n_estimators = int(params.get("n_estimators") or 50)
        max_depth = int(params.get("max_depth") or -1)
        learning_rate = float(params.get("learning_rate") or 0.1)
        num_leaves = int(params.get("num_leaves") or 31)
        random_state = int(params.get("random_state") if params.get("random_state") is not None else 42)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid params: {e}")

    def factory():
        return LGBMClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            num_leaves=num_leaves,
            random_state=random_state,
            verbosity=-1,
            n_jobs=1,
        )

    return run_sklearn_classifier(
        OPERATOR_ID, params, inputs, factory, model_prefix="lgbmc",
    )
# @AI_GENERATED: end
