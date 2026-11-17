"""G0-S3: execute-async slot validation and execution store wiring."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.workflows_enhanced import (
    EnhancedWorkflow,
    _execution_store,
    router as workflows_enhanced_router,
)


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr(
        "api.workflows_enhanced._run_async_execution",
        lambda execution_id, workflow, execution_data: None,
    )
    app = FastAPI()
    app.include_router(workflows_enhanced_router)
    return TestClient(app)


def _sample_workflow(metadata=None):
    return EnhancedWorkflow(
        id="workflow-g0-slot-test",
        name="slot-test",
        nodes=[],
        edges=[],
        metadata=metadata or {},
        version=3,
    )


def test_execute_async_missing_slot_returns_400(api_client, monkeypatch):
    monkeypatch.setattr(
        "api.workflows_enhanced.load_workflow_from_file",
        lambda workflow_id: _sample_workflow(),
    )
    response = api_client.post(
        "/api/workflows/enhanced/workflow-g0-slot-test/execute-async",
        json={"live_nodes": [], "global_config": {}},
    )
    assert response.status_code == 400
    assert "slot" in response.json()["detail"].lower()


def test_execute_async_scenario_key_in_body_returns_400(api_client, monkeypatch):
    monkeypatch.setattr(
        "api.workflows_enhanced.load_workflow_from_file",
        lambda _workflow_id: _sample_workflow({"slot": "pv_day"}),
    )
    response = api_client.post(
        "/api/workflows/enhanced/workflow-g0-slot-test/execute-async",
        json={
            "slot": "pv_day",
            "scenario_key": "pv_day",
            "live_nodes": [],
            "global_config": {},
        },
    )
    assert response.status_code == 400
    assert "scenario_key" in response.json()["detail"]


def test_execute_async_with_slot_stores_effective_global_config(api_client, monkeypatch):
    monkeypatch.setattr(
        "api.workflows_enhanced.load_workflow_from_file",
        lambda _workflow_id: _sample_workflow(
            {"slot": "pv_day", "global_config": {"template_key": "from_template"}}
        ),
    )
    response = api_client.post(
        "/api/workflows/enhanced/workflow-g0-slot-test/execute-async",
        json={
            "slot": "pv_day",
            "slot_config_ref": None,
            "live_nodes": [],
            "global_config": {"request_key": "from_request"},
        },
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]
    state = _execution_store[execution_id]
    assert state["slot"] == "pv_day"
    assert state["effective_global_config"] == {
        "template_key": "from_template",
        "request_key": "from_request",
    }
    assert state["effective_global_config_digest"]
    assert state["source_workflow_id"] == "workflow-g0-slot-test"
    assert state["source_workflow_version"] == 3
    assert state["graph_digest"]
