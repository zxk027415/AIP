"""
Generic model artifact saver.

This operator standardizes model reference output for downstream predict/backtest
chains and is reusable across industries.
"""
from __future__ import annotations

import uuid

from services.operator_execution import model_registry
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "save_model_artifact"


def execute(params: dict, inputs: dict) -> dict:
    model = inputs.get("model")
    if model is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'model' is required")

    feature_list = inputs.get("feature_list") or inputs.get("model_feature_list") or []
    model_ref = (
        params.get("model_ref")
        or inputs.get("model_ref")
        or inputs.get("model_id")
        or f"model-{uuid.uuid4().hex[:12]}"
    )
    metadata = {
        "operator": OPERATOR_ID,
        "source_model_id": inputs.get("model_id"),
        "source_operator": params.get("source_operator"),
    }
    model_registry.register_model(model_ref, model, feature_list, metadata=metadata)
    return {
        "model_ref": model_ref,
        "model_id": model_ref,
        "feature_list": feature_list,
        "saved": True,
    }

