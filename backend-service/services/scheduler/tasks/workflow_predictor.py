# -*- coding: utf-8 -*-
"""
services/scheduler/tasks/workflow_predictor.py — 工作流预测执行器

封装“给定 workflow_id + 输入数据 → 跑完整 pipeline → 返回预测值”的逻辑。
供 prediction_task 调用，用于生产模型和影子模型的在线定时预测。

复用现有 _execute_pipeline_sync 引擎和 operator_backends 算子。
"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Resolve paths
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
_OPERATOR_BACKENDS_DIR = os.path.join(_BACKEND_DIR, "services", "operator_backends")
_WORKFLOWS_DIR = os.path.join(_BACKEND_DIR, "data", "workflows_enhanced")

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def load_workflow_json(workflow_id: str) -> Optional[Dict[str, Any]]:
    """Load a workflow JSON by ID from data/workflows_enhanced/."""
    import json

    path = os.path.join(_WORKFLOWS_DIR, f"{workflow_id}.json")
    if not os.path.exists(path):
        logger.warning("workflow_predictor: workflow file not found: %s", path)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# @AI_GENERATED: strict-gap-online-workflow-execution
_ONLINE_SCORE_FUNCTION_IDS = frozenset({"smape_score", "mse_rmse_mae", "mape_score", "accuracy_score"})


def run_prediction(
    workflow_id: str,
    input_data: pd.DataFrame,
    slot: str = "default",
    operator_param_overrides: Optional[Dict[str, Any]] = None,
    online_mode: bool = False,
    experiment_patch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute one workflow and return its prediction values.

    ``online_mode`` preserves the same algorithm graph used by AutoResearch,
    while changing only the execution contract: the caller supplies a causally
    constructed forecast horizon, ``train_test_split_ts`` separates it from
    historical labels, and score-only leaves are skipped because truth is not
    available until the later accuracy-backfill task.

    ``experiment_patch``：来自部署 ModelVersion 的 AutoResearch 实验补丁
    （structure / parameter / node_param / challenger_override），在执行前
    真实打进工作流 JSON，避免影子/预上线只靠 version_tag 区分。
    """
    from services.operator_execution import GlobalConfigInjector, OperatorRouter

    start_time = time.time()
    wf_data = load_workflow_json(workflow_id)
    if wf_data is None:
        return _failure_result(start_time, f"Workflow not found: {workflow_id}", 0)

    if experiment_patch:
        try:
            from services.deployment.experiment_patch import apply_experiment_patch_to_workflow_dict

            wf_data = apply_experiment_patch_to_workflow_dict(wf_data, experiment_patch)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "run_prediction: apply experiment_patch failed wf=%s: %s",
                workflow_id,
                exc,
            )

    nodes_raw = wf_data.get("nodes", [])
    edges_raw = wf_data.get("edges", [])
    metadata = wf_data.get("metadata") or {}
    global_config = dict(metadata.get("global_config") or {})
    if online_mode:
        global_config.update({"operate_status": "online", "run_mode": "online"})

    if not nodes_raw:
        return _failure_result(start_time, "Workflow has no nodes", 0)

    config_injector = GlobalConfigInjector(global_config)
    op_router = OperatorRouter()
    op_router.auto_discover(_OPERATOR_BACKENDS_DIR)

    try:
        execution_order = _topological_sort(nodes_raw, edges_raw)
    except ValueError as exc:
        return _failure_result(start_time, f"Topology error: {exc}", len(nodes_raw))

    nodes_by_id = {node.get("id"): node for node in nodes_raw if node.get("id")}
    node_outputs: Dict[str, Any] = {}

    for node_id in execution_order:
        node = nodes_by_id.get(node_id)
        if not node:
            continue

        config = (node.get("data") or {}).get("config") or {}
        function_id = config.get("functionId")
        inputs = _collect_upstream(node_id, edges_raw, node_outputs)

        if not config.get("enabled", True):
            node_outputs[node_id] = _passthrough(inputs)
            continue
        if not function_id:
            continue

        # The online prediction contract delegates accuracy to later truth
        # backfill. These terminal score nodes require y_true and must never
        # consume synthetic future labels.
        if online_mode and function_id in _ONLINE_SCORE_FUNCTION_IDS:
            node_outputs[node_id] = {"status": "skipped_online_score"}
            continue

        if function_id == "load_csv" and input_data is not None and not input_data.empty:
            node_outputs[node_id] = input_data
            continue

        params = {
            key: value
            for key, value in config.items()
            if key not in ("functionId", "operation", "chartType", "enabled")
        }
        params = config_injector.inject(params)
        if operator_param_overrides and function_id in operator_param_overrides:
            params.update(operator_param_overrides[function_id])
        params["_log_fn"] = lambda _message, _type="info": None
        params["_cancel_event"] = None

        try:
            # Keep the same params/inputs ordering and edge-port flattening as
            # api.workflows_enhanced._execute_pipeline_sync.
            node_outputs[node_id] = op_router.execute(function_id, params, inputs)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "workflow_predictor: node %s (%s) failed: %s",
                node_id,
                function_id,
                exc,
            )
            return _failure_result(
                start_time,
                f"Node {function_id} failed: {exc}",
                len(nodes_raw),
            )

    prediction_values: list[float] = []
    for node_id in reversed(execution_order):
        values = _extract_prediction_values(node_outputs.get(node_id))
        if values:
            prediction_values = values
            break

    if not prediction_values:
        return _failure_result(
            start_time,
            "Could not extract prediction values from pipeline output",
            len(nodes_raw),
        )

    return {
        "success": True,
        "predicted_value": prediction_values[0],
        "predicted_values": prediction_values,
        "execution_time": time.time() - start_time,
        "error": None,
        "node_count": len(nodes_raw),
    }


def _failure_result(start_time: float, error: str, node_count: int) -> Dict[str, Any]:
    """Build one stable failure result for the scheduler task boundary."""
    return {
        "success": False,
        "predicted_value": None,
        "predicted_values": [],
        "execution_time": time.time() - start_time,
        "error": error,
        "node_count": node_count,
    }


def _extract_prediction_values(output: Any) -> list[float]:
    """Extract a finite ordered forecast sequence from a node output."""
    if output is None:
        return []

    value = output
    if isinstance(output, dict):
        for key in (
            "forecast_values",
            "y_pred",
            "predictions",
            "prediction",
            "predicted_value",
            "forecast",
            "predicted",
        ):
            if key in output:
                value = output[key]
                break
        else:
            return []

    if isinstance(value, pd.DataFrame):
        for column in ("prediction", "predicted_value", "y_pred", "forecast"):
            if column in value.columns:
                value = value[column]
                break
        else:
            return []

    if isinstance(value, pd.Series):
        raw_values = value.tolist()
    elif hasattr(value, "tolist"):
        raw_values = value.tolist()
    elif isinstance(value, (list, tuple)):
        raw_values = list(value)
    else:
        raw_values = [value]

    if not isinstance(raw_values, list):
        raw_values = [raw_values]

    numeric = pd.to_numeric(pd.Series(raw_values), errors="coerce")
    return [float(item) for item in numeric if pd.notna(item)]


def _passthrough(inputs: Dict[str, Any]) -> Any:
    """Retain the existing disabled-node pass-through behavior."""
    if len(inputs) == 1:
        return next(iter(inputs.values()))
    return inputs


def _topological_sort(nodes: list, edges: list) -> list:
    """Simple topological sort of node IDs based on edges."""
    from collections import deque

    node_ids = [node.get("id") for node in nodes if node.get("id")]
    in_degree = {node_id: 0 for node_id in node_ids}
    adjacency = {node_id: [] for node_id in node_ids}

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in adjacency and target in in_degree:
            adjacency[source].append(target)
            in_degree[target] += 1

    queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
    order: list[str] = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for neighbor in adjacency.get(node_id, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(node_ids):
        raise ValueError("Workflow graph has cycles")
    return order


def _collect_upstream(node_id: str, edges: list, node_outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten upstream outputs using the platform's existing port convention."""
    incoming = [edge for edge in edges if edge.get("target") == node_id]
    key_counts: Dict[str, int] = {}
    for edge in incoming:
        source_output = node_outputs.get(edge.get("source"))
        if source_output is None:
            continue
        if isinstance(source_output, dict):
            for key in source_output:
                key_counts[key] = key_counts.get(key, 0) + 1
        else:
            key_counts["data"] = key_counts.get("data", 0) + 1

    inputs: Dict[str, Any] = {}
    for edge in incoming:
        source_output = node_outputs.get(edge.get("source"))
        if source_output is None:
            continue

        target_handle = edge.get("targetHandle") or ""
        alias = target_handle if target_handle and "-" not in target_handle else None
        if isinstance(source_output, dict):
            for key, value in source_output.items():
                destination = alias if key_counts.get(key, 0) > 1 and alias else key
                if destination not in inputs:
                    inputs[destination] = value
        else:
            destination = alias or (
                target_handle.split("-")[-1] if "-" in target_handle else "data"
            )
            if destination not in inputs:
                inputs[destination] = source_output
    return inputs
# @AI_GENERATED: end
