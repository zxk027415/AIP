import math

import pytest

from services.autoresearch_run_store import AutoResearchRunStore
from services.autoresearch_persister import AutoResearchPersister
from api import workflows_enhanced as wf


def test_run_store_save_load_and_list(tmp_path):
    store = AutoResearchRunStore(root_dir=str(tmp_path))
    state = {
        "run_id": "ares-test-1",
        "status": "running",
        "progress": {"iteration": 2, "total_iterations": 5},
        "best_candidate": {"mape": math.nan},
    }

    path = store.save("ares-test-1", state)
    loaded = store.load("ares-test-1")
    rows = store.list(limit=10)

    assert path.endswith("ares-test-1/snapshot.json")
    assert loaded["run_id"] == "ares-test-1"
    assert loaded["status"] == "running"
    assert loaded["best_candidate"]["mape"] is None
    assert rows[0]["run_id"] == "ares-test-1"


def test_run_store_marks_running_snapshot_interrupted(tmp_path):
    store = AutoResearchRunStore(root_dir=str(tmp_path))
    store.save("ares-test-2", {"run_id": "ares-test-2", "status": "waiting_review"})

    loaded = store.load_for_status("ares-test-2", active_in_memory=False)
    reloaded = store.load("ares-test-2")

    assert loaded["status"] == "interrupted"
    assert loaded["previous_status"] == "waiting_review"
    assert loaded["recoverable"] is True
    assert reloaded["status"] == "interrupted"


def test_run_store_keeps_terminal_snapshot_status(tmp_path):
    store = AutoResearchRunStore(root_dir=str(tmp_path))
    store.save("ares-test-3", {"run_id": "ares-test-3", "status": "success"})

    loaded = store.load_for_status("ares-test-3", active_in_memory=False)

    assert loaded["status"] == "success"
    assert "previous_status" not in loaded


@pytest.mark.asyncio
async def test_status_endpoint_falls_back_to_interrupted_snapshot(tmp_path, monkeypatch):
    store = AutoResearchRunStore(root_dir=str(tmp_path))
    store.save(
        "ares-test-4",
        {
            "run_id": "ares-test-4",
            "status": "running",
            "progress": {"iteration": 1, "total_iterations": 3},
            "compare_config": {},
            "logs": [],
        },
    )
    monkeypatch.setattr(wf, "_auto_research_persister", AutoResearchPersister(run_store=store))
    wf._auto_research_store.pop("ares-test-4", None)

    result = await wf.get_auto_research_status("ares-test-4")

    assert result["run_id"] == "ares-test-4"
    assert result["status"] == "interrupted"
    assert result["previous_status"] == "running"
    assert result["recoverable"] is True
    assert result["snapshot_source"] == "disk"


@pytest.mark.asyncio
async def test_status_endpoint_prefers_disk_snapshot_when_job_exists(tmp_path, monkeypatch):
    store = AutoResearchRunStore(root_dir=str(tmp_path))
    store.save(
        "ares-test-worker",
        {
            "run_id": "ares-test-worker",
            "status": "running",
            "progress": {"iteration": 2, "total_iterations": 5},
            "compare_config": {},
            "logs": [],
        },
    )
    monkeypatch.setattr(wf, "_auto_research_persister", AutoResearchPersister(run_store=store))
    monkeypatch.setattr(
        wf._jq,
        "get_job",
        lambda run_id: {"run_id": run_id, "status": "running", "payload": "{}"},
    )
    wf._auto_research_store["ares-test-worker"] = {
        "run_id": "ares-test-worker",
        "status": "pending",
        "progress": {"iteration": 0, "total_iterations": 5},
        "compare_config": {},
        "logs": [],
    }

    result = await wf.get_auto_research_status("ares-test-worker")

    assert result["status"] == "running"
    assert result["progress"]["iteration"] == 2
    assert result["snapshot_source"] == "disk+job"
    assert result["job_status"] == "running"

    wf._auto_research_store.pop("ares-test-worker", None)


@pytest.mark.asyncio
async def test_list_runs_merges_job_queue_rows(tmp_path, monkeypatch):
    store = AutoResearchRunStore(root_dir=str(tmp_path))
    store.save(
        "ares-test-job-list",
        {
            "run_id": "ares-test-job-list",
            "status": "running",
            "progress": {"iteration": 3, "total_iterations": 8},
            "baseline_workflow_id": "wf-1",
        },
    )
    monkeypatch.setattr(wf, "_auto_research_persister", AutoResearchPersister(run_store=store))
    monkeypatch.setattr(
        wf._jq,
        "list_jobs",
        lambda limit=50: [{
            "run_id": "ares-test-job-list",
            "status": "running",
            "created_at": "2026-05-22T10:00:00",
            "started_at": "2026-05-22T10:01:00",
            "heartbeat_at": "2026-05-22T10:02:00",
            "payload": "{}",
        }],
    )

    result = await wf.list_auto_research_runs(limit=10)
    row = result["runs"][0]

    assert row["run_id"] == "ares-test-job-list"
    assert row["job_status"] == "running"
    assert row["progress"]["iteration"] == 3
    assert row["snapshot_source"] == "disk+job"
