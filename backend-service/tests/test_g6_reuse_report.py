"""G6.5 benchmark graph reuse evidence report tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.benchmark_reuse import router as benchmark_reuse_router
from services.benchmark.reuse_report import build_g6_reuse_report
from services.operator_execution.slot_workflows import resolve_replay_workflow_id, resolve_train_workflow_id
from services.slot_governance.model_candidates import register_model_candidate
from services.slot_governance.provenance import ProvenanceError


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(benchmark_reuse_router)
    return TestClient(app)


def test_benchmark_slots_use_pv_point_workflows():
    nasa_train = resolve_train_workflow_id("benchmark_nasa_smap_msl")
    fhc_train = resolve_train_workflow_id("benchmark_fhc_twin_plant")
    assert nasa_train == fhc_train == "workflow-pv-point-train-eval-v1"
    assert resolve_replay_workflow_id("benchmark_nasa_smap_msl") == "workflow-pv-point-predict-replay-v1"


def test_g6_reuse_report_graph_match():
    report = build_g6_reuse_report()
    assert report["reuse_conclusion"]["same_visible_operator_graph"] is True
    assert report["reuse_conclusion"]["subgraph_used"] is False

    train_role = report["workflow_comparison"]["roles"]["train_eval"]
    assert train_role["graph_signature_match"] is True
    nasa_ops = set(train_role["operator_ids"]["benchmark_nasa_smap_msl"])
    fhc_ops = set(train_role["operator_ids"]["benchmark_fhc_twin_plant"])
    assert nasa_ops == fhc_ops
    assert "ts_point_profile_map" in nasa_ops
    assert "load_csv" in nasa_ops

    nasa_profile = report["profiles"]["benchmark_nasa_smap_msl"]
    fhc_profile = report["profiles"]["benchmark_fhc_twin_plant"]
    assert nasa_profile["preflight"]["ready"] is True
    assert fhc_profile["preflight"]["ready"] is True
    assert nasa_profile["clock_mode"] == "index"
    assert fhc_profile["clock_mode"] == "event_time"


def test_governance_evidence_in_report():
    report = build_g6_reuse_report()
    gov = report["governance_evidence"]
    assert gov["execution_purpose"] == "benchmark_reuse"
    assert gov["governance_eligible"] is False
    for slot in ("benchmark_nasa_smap_msl", "benchmark_fhc_twin_plant"):
        assert gov["per_slot_governance_eligible"][slot] is False

    with pytest.raises(ProvenanceError) as exc:
        register_model_candidate(
            slot="benchmark_fhc_twin_plant",
            source_workflow_id="workflow-pv-point-train-eval-v1",
            source_execution_id="exec-demo",
            model_artifact_ref="data/models/demo/model.pt",
        )
    assert exc.value.code == "benchmark_governance_forbidden"


def test_reuse_report_api(api_client):
    response = api_client.get("/api/benchmark/reuse-report")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["report"]["reuse_conclusion"]["same_visible_operator_graph"] is True


def test_reuse_report_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.benchmark.reuse_report._REPORT_DIR",
        tmp_path,
    )
    report = build_g6_reuse_report(persist=True)
    assert "persisted_path" in report
    saved = tmp_path / f"{report['report_id']}.json"
    assert saved.is_file()
