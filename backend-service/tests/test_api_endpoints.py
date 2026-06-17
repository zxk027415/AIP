from fastapi.testclient import TestClient

import api.workflows_enhanced as workflows_enhanced


def _client():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(workflows_enhanced.router)
    return TestClient(app)


def test_knowledge_search_endpoint_accessible():
    response = _client().get("/api/workflows/enhanced/knowledge/search")

    assert response.status_code == 200
    assert "success" in response.json()


def test_dataset_register_list_and_missing_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(workflows_enhanced, "_DATASET_REGISTRY_PATH", str(tmp_path / "datasets.json"))
    client = _client()

    registered = client.post(
        "/api/workflows/enhanced/datasets/register",
        json={"dataset_id": "unit-dataset", "file_path": "/tmp/missing.csv"},
    )
    listed = client.get("/api/workflows/enhanced/datasets")
    profile = client.get("/api/workflows/enhanced/datasets/missing/profile")

    assert registered.status_code == 200
    assert registered.json()["success"] is True
    assert listed.status_code == 200
    assert profile.status_code == 200
    assert profile.json()["success"] is False


def test_research_questions_and_reflections_empty_for_unknown_run():
    client = _client()

    questions = client.get("/api/workflows/enhanced/auto-research/no-such-run/research-questions")
    reflections = client.get("/api/workflows/enhanced/auto-research/no-such-run/reflections")

    assert questions.status_code == 200
    assert questions.json() == {"success": True, "data": []}
    assert reflections.status_code == 200
    assert reflections.json() == {"success": True, "data": []}


def test_auto_research_run_row_compaction_drops_heavy_window_payload():
    row = workflows_enhanced._compact_autoresearch_run_row(
        {
            "run_id": "ares-test",
            "status": "success",
            "progress": {"iteration": 50, "total_iterations": 50},
            "current_iteration_live": {
                "live_summary": {"windows_done": 1, "windows_total": 1, "score_advantage": 0.1},
                "live_window_results": [{"y_true": [1, 2, 3], "y_pred": [1, 2, 3]}],
            },
            "batch_eval_status": {
                "iteration": 50,
                "running": False,
                "groups": [{"group_idx": 0, "status": "success", "override": {"train_days": 60}}],
            },
        }
    )

    assert row["run_id"] == "ares-test"
    assert row["current_iteration_live"]["live_summary"]["windows_done"] == 1
    assert "live_window_results" not in row["current_iteration_live"]
    assert "override" not in row["batch_eval_status"]["groups"][0]
