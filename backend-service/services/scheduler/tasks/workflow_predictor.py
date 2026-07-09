# -*- coding: utf-8 -*-
"""
services/scheduler/tasks/workflow_predictor.py — 工作流预测执行器

封装"给定 workflow_id + 输入数据 → 跑完整 pipeline → 返回预测值"的逻辑。
供 prediction_task 调用，用于生产模型和影子模型的在线定时预测。

复用现有 _execute_pipeline_sync 引擎和 operator_backends 算子。
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
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


def run_prediction(
    workflow_id: str,
    input_data: pd.DataFrame,
    slot: str = "default",
    operator_param_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a workflow pipeline for online prediction.

    Args:
        workflow_id:              The workflow template ID to load and execute.
        input_data:               DataFrame with station data to feed into the pipeline
                                  (injected as the output of the first load_csv node).
        slot:                     Slot identifier for context.
        operator_param_overrides: 按 functionId 覆盖节点参数，例如：
                                  {"train_test_split_ts": {"mode": "all_train"}}
                                  匹配 functionId 的节点其 params 会被 merge（override 优先）。
                                  用于生产 cron 强制 mode="all_train" 不切测试集。

    Returns:
        {
            "success": bool,
            "predicted_value": float | None,
            "execution_time": float,
            "error": str | None,
            "node_count": int,
        }
    """
    from services.operator_execution import (
        OperatorRouter,
        GlobalConfigInjector,
    )

    start_time = time.time()

    # 1. Load workflow
    wf_data = load_workflow_json(workflow_id)
    if wf_data is None:
        return {
            "success": False,
            "predicted_value": None,
            "execution_time": time.time() - start_time,
            "error": f"Workflow not found: {workflow_id}",
            "node_count": 0,
        }

    nodes_raw = wf_data.get("nodes", [])
    edges_raw = wf_data.get("edges", [])
    metadata = wf_data.get("metadata") or {}
    global_config = metadata.get("global_config", {})

    if not nodes_raw:
        return {
            "success": False,
            "predicted_value": None,
            "execution_time": time.time() - start_time,
            "error": "Workflow has no nodes",
            "node_count": 0,
        }

    # 2. Initialize execution framework
    config_injector = GlobalConfigInjector(global_config)
    op_router = OperatorRouter()
    op_router.auto_discover(_OPERATOR_BACKENDS_DIR)

    # 3. Topological sort
    try:
        execution_order = _topological_sort(nodes_raw, edges_raw)
    except ValueError as e:
        return {
            "success": False,
            "predicted_value": None,
            "execution_time": time.time() - start_time,
            "error": f"Topology error: {e}",
            "node_count": len(nodes_raw),
        }

    # 4. Execute nodes in order
    node_outputs: Dict[str, Any] = {}
    last_output = None

    for node_id in execution_order:
        node = next((n for n in nodes_raw if n.get("id") == node_id), None)
        if not node:
            continue

        data_block = node.get("data", {})
        config = data_block.get("config", {})
        function_id = config.get("functionId")

        # Skip disabled nodes
        if not config.get("enabled", True):
            # Pass through upstream data
            inputs = _collect_upstream(node_id, edges_raw, node_outputs)
            passthrough = next(iter(inputs.values())) if len(inputs) == 1 else inputs
            node_outputs[node_id] = passthrough
            continue

        if not function_id:
            continue

        # Collect upstream inputs
        inputs = _collect_upstream(node_id, edges_raw, node_outputs)

        # For the first data-loading node (load_csv), inject our input_data
        if function_id == "load_csv" and input_data is not None and not input_data.empty:
            node_outputs[node_id] = input_data
            continue

        # Build params
        params = {k: v for k, v in config.items() if k not in ("functionId", "operation", "chartType", "enabled")}
        params = config_injector.inject(params)
        # @AI_GENERATED: 合并 operator_param_overrides（生产 cron 传 mode="all_train" 等）
        if operator_param_overrides and function_id in operator_param_overrides:
            params.update(operator_param_overrides[function_id])
        # @AI_GENERATED: end
        params["_log_fn"] = lambda msg, t="info": None  # suppress logs in batch
        params["_cancel_event"] = None

        # Determine input to pass
        if isinstance(inputs, dict) and len(inputs) == 1:
            execute_input = next(iter(inputs.values()))
        elif isinstance(inputs, dict) and len(inputs) > 1:
            execute_input = inputs
        else:
            execute_input = None

        try:
            result = op_router.execute(function_id, execute_input, params)
            node_outputs[node_id] = result
            last_output = result
        except Exception as exc:
            logger.warning(
                "workflow_predictor: node %s (%s) failed: %s",
                node_id, function_id, exc,
            )
            return {
                "success": False,
                "predicted_value": None,
                "execution_time": time.time() - start_time,
                "error": f"Node {function_id} failed: {exc}",
                "node_count": len(nodes_raw),
            }

    # 5. Extract predicted value from last output
    predicted_value = _extract_prediction(last_output)

    return {
        "success": predicted_value is not None,
        "predicted_value": predicted_value,
        "execution_time": time.time() - start_time,
        "error": None if predicted_value is not None else "Could not extract prediction from pipeline output",
        "node_count": len(nodes_raw),
    }


def _extract_prediction(output: Any) -> Optional[float]:
    """
    Extract a single predicted value from pipeline output.

    Supports:
    - dict with 'prediction' or 'predicted_value' or 'y_pred' key
    - DataFrame with a prediction column → last row value
    - scalar number
    """
    if output is None:
        return None

    if isinstance(output, (int, float)):
        return float(output)

    if isinstance(output, dict):
        for key in ("prediction", "predicted_value", "y_pred", "forecast", "predicted"):
            if key in output:
                val = output[key]
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, pd.Series):
                    return float(val.iloc[-1]) if len(val) > 0 else None
                if isinstance(val, pd.DataFrame):
                    return float(val.iloc[-1, 0]) if len(val) > 0 else None
        # Try 'metrics' sub-dict
        if "metrics" in output and isinstance(output["metrics"], dict):
            for key in ("mape", "rmse"):
                if key in output["metrics"]:
                    pass  # metrics are not predictions
        return None

    if isinstance(output, pd.DataFrame):
        # Look for prediction-like columns
        for col in ("prediction", "predicted_value", "y_pred", "forecast"):
            if col in output.columns:
                return float(output[col].iloc[-1]) if len(output) > 0 else None
        # Fallback: last column, last row
        if len(output) > 0 and len(output.columns) > 0:
            return float(output.iloc[-1, -1])
        return None

    if isinstance(output, pd.Series):
        return float(output.iloc[-1]) if len(output) > 0 else None

    return None


def _topological_sort(nodes: list, edges: list) -> list:
    """Simple topological sort of node IDs based on edges."""
    from collections import deque

    node_ids = [n.get("id") for n in nodes if n.get("id")]
    in_degree = {nid: 0 for nid in node_ids}
    adj = {nid: [] for nid in node_ids}

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    order = []

    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(node_ids):
        raise ValueError("Workflow graph has cycles")

    return order


def _collect_upstream(node_id: str, edges: list, node_outputs: dict) -> dict:
    """Collect outputs from upstream nodes connected to this node."""
    inputs = {}
    for edge in edges:
        if edge.get("target") == node_id:
            src = edge.get("source")
            if src in node_outputs:
                src_handle = edge.get("sourceHandle") or src
                inputs[src_handle] = node_outputs[src]
    return inputs
