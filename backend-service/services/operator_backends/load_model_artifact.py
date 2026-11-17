"""
Generic model artifact loader.

Provides a unified model_ref interface so predict/backtest flows do not need to
know operator-specific model stores.
"""
from __future__ import annotations

from services.operator_execution import model_registry
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "load_model_artifact"


def execute(params: dict, inputs: dict) -> dict:
    model_ref = (
        params.get("model_ref")
        or inputs.get("model_ref")
        or params.get("model_id")
        or inputs.get("model_id")
    )
    if not model_ref:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            "model_ref (or model_id) is required",
        )

    stored = model_registry.get_model(model_ref)
    if stored is None:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ModelNotFoundError",
            f"Model '{model_ref}' not found. Available: {model_registry.list_model_refs()}",
        )

    return {
        "model_ref": model_ref,
        "model_id": model_ref,
        "model": stored.get("model"),
        "feature_list": stored.get("feature_list", []),
        "metadata": stored.get("metadata", {}),
    }

