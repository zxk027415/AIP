"""Execute a frozen predict_replay workflow once per pending point."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

import pandas as pd

from services.operator_execution.router import OperatorRouter


PV_POINT_CONTRACT = {
    "entity_keys": ["site_id", "device_id", "branch_id"],
    "time_column": "time",
    "feature_columns": ["value", "i_cal"],
    "label_column": "label",
    "context_length": 8,
}

_OPERATOR_BACKENDS_DIR = "services/operator_backends"


def _topological_order(workflow) -> list[str]:
    from api.workflows_enhanced import _topological_sort_nodes

    return _topological_sort_nodes(workflow.nodes, workflow.edges)


def _collect_inputs(node_id: str, edges, node_outputs: dict[str, Any]) -> dict[str, Any]:
    from api.workflows_enhanced import _collect_upstream_inputs

    return _collect_upstream_inputs(node_id, edges, node_outputs)


def run_frozen_replay_graph(
    workflow_id: str,
    *,
    replay_df: pd.DataFrame,
    pending_row_index: int,
    model_ref: Optional[str] = None,
    profile_contract: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run one predict_replay graph invocation for a single pending point."""
    from api.workflows_enhanced import load_workflow_from_file
    from services.operator_execution.global_config_injector import GlobalConfigInjector

    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        raise ValueError(f"workflow not found: {workflow_id}")

    contract = profile_contract or PV_POINT_CONTRACT
    metadata = workflow.metadata or {}
    global_config = metadata.get("global_config") or {}
    config_injector = GlobalConfigInjector(global_config)
    op_router = OperatorRouter()
    op_router.auto_discover(_OPERATOR_BACKENDS_DIR)

    node_outputs: dict[str, Any] = {}
    point_outcome: Optional[dict[str, Any]] = None

    for node_id in _topological_order(workflow):
        node = next(item for item in workflow.nodes if item.id == node_id)
        config = node.data.config.dict() if hasattr(node.data.config, "dict") else dict(node.data.config)
        function_id = config.get("functionId")
        if not function_id:
            continue

        params = {k: v for k, v in config.items() if k not in ("functionId", "operation", "chartType")}
        params = config_injector.inject(params)
        if function_id == "load_csv":
            node_outputs[node_id] = {"data": replay_df.copy()}
            continue

        inputs = _collect_inputs(node_id, workflow.edges, node_outputs)
        if function_id.startswith("ts_point_") and "contract" not in params:
            params["contract"] = deepcopy(contract)
        if function_id == "ts_point_causal_window":
            params["pending_row_index"] = pending_row_index
            params.setdefault("context_length", contract.get("context_length", 8))
        if function_id == "ts_point_predict" and model_ref:
            params["model_ref"] = model_ref
            inputs["model_ref"] = model_ref

        try:
            output = op_router.execute(function_id, params, inputs)
        except Exception as exc:
            if function_id == "ts_point_predict":
                point_outcome = {
                    "kind": "no_decision",
                    "reason": "predict_operator_failed",
                    "evidence": {"error": str(exc)},
                }
                node_outputs[node_id] = {"point_outcome": point_outcome}
                continue
            raise
        node_outputs[node_id] = output
        if function_id == "ts_point_predict":
            point_outcome = output.get("point_outcome")

    if point_outcome is None:
        raise RuntimeError("frozen replay graph did not produce point_outcome")
    return {
        "point_outcome": point_outcome,
        "node_outputs": {key: _summarize(value) for key, value in node_outputs.items()},
        "workflow_id": workflow_id,
    }


def _summarize(value: Any) -> Any:
    if isinstance(value, dict):
        summary = {}
        for key, item in value.items():
            if key == "window_tensor":
                summary[key] = "ndarray"
            elif isinstance(item, pd.DataFrame):
                summary[key] = f"DataFrame[{len(item)}]"
            elif isinstance(item, (str, int, float, bool)) or item is None:
                summary[key] = item
            elif isinstance(item, dict):
                summary[key] = _summarize(item)
            else:
                summary[key] = type(item).__name__
        return summary
    return value
