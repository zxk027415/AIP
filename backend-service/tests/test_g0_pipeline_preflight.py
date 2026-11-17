"""G0-S1: pipeline preflight — missing/unregistered operators must fail the run."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.workflows_enhanced import (
    EnhancedNodeData,
    EnhancedWorkflow,
    EnhancedWorkflowEdge,
    EnhancedWorkflowNode,
    NodeConfig,
    NodePort,
    _execute_pipeline_sync,
)


def _make_single_node_workflow(
    node_id: str,
    *,
    function_id: str | None = "load_csv",
    enabled: bool = True,
    extra_config: dict | None = None,
) -> EnhancedWorkflow:
    config_fields: dict = {}
    if function_id is not None:
        config_fields["functionId"] = function_id
    if not enabled:
        config_fields["enabled"] = False
    if extra_config:
        config_fields.update(extra_config)

    node = EnhancedWorkflowNode(
        id=node_id,
        position={"x": 0, "y": 0},
        data=EnhancedNodeData(
            label="test-node",
            type="function",
            inputs=[NodePort(id="in", name="in", type="input", dataType="any")],
            outputs=[NodePort(id="out", name="out", type="output", dataType="any")],
            config=NodeConfig(**config_fields),
        ),
    )
    return EnhancedWorkflow(
        id="wf-g0-preflight",
        name="g0-preflight",
        nodes=[node],
        edges=[],
        metadata={"global_config": {}},
    )


def _node_status(result: dict, node_id: str) -> str | None:
    node_result = (result.get("nodeResults") or {}).get(node_id) or {}
    return node_result.get("status")


def test_unregistered_operator_fails_pipeline():
    workflow = _make_single_node_workflow("n1", function_id="not_a_real_operator")
    result = _execute_pipeline_sync(workflow)

    assert result["success"] is False
    assert _node_status(result, "n1") == "failed"
    error_blob = " ".join(
        str(part)
        for part in (
            result.get("error"),
            (result.get("nodeResults") or {}).get("n1", {}).get("error"),
        )
        if part
    )
    assert "OperatorNotFound" in error_blob
    assert "not_a_real_operator" in error_blob


def test_missing_function_id_fails_pipeline():
    workflow = _make_single_node_workflow("n1", function_id=None)
    result = _execute_pipeline_sync(workflow)

    assert result["success"] is False
    assert _node_status(result, "n1") == "failed"
    error_blob = " ".join(
        str(part)
        for part in (
            result.get("error"),
            (result.get("nodeResults") or {}).get("n1", {}).get("error"),
        )
        if part
    )
    assert "functionId" in error_blob.lower() or "OperatorNotFound" in error_blob


def test_disabled_node_with_registered_operator_is_skipped():
    workflow = _make_single_node_workflow("n1", function_id="load_csv", enabled=False)
    result = _execute_pipeline_sync(workflow)

    assert _node_status(result, "n1") == "skipped"
    error_blob = str(result.get("error") or "")
    assert "OperatorNotFound" not in error_blob


def test_registered_operator_param_error_not_pseudo_success():
    workflow = _make_single_node_workflow("n1", function_id="load_csv")
    result = _execute_pipeline_sync(workflow)

    assert result["success"] is False
    assert _node_status(result, "n1") == "failed"
    error_blob = " ".join(
        str(part)
        for part in (
            result.get("error"),
            (result.get("nodeResults") or {}).get("n1", {}).get("error"),
        )
        if part
    )
    assert "OperatorNotFound" not in error_blob
    assert "file_path" in error_blob.lower() or "ParameterError" in error_blob
