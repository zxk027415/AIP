"""G8 PVDAQ unlabeled benchmark profile and governance tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.benchmark_reuse import router as benchmark_reuse_router

from services.benchmark.governance import resolve_execution_purpose
from services.benchmark.g8_reuse_story import build_g8_reuse_story
from services.slot_datasets.annotation_candidates import register_annotation_candidate
from services.slot_governance.model_candidates import register_model_candidate
from services.slot_governance.provenance import ProvenanceError
from services.timeseries_point.replay_activity import create_session, replay_next_point
from services.timeseries_profiles.loader import load_dataset_from_profile
from services.timeseries_profiles.preflight import run_dataset_profile_preflight
from services.timeseries_profiles.store import TimeseriesProfileStore


SLOT = "benchmark_pvdaq_system683"
PROFILE_ID = "benchmark-pvdaq-system683-demo"


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(benchmark_reuse_router)
    return TestClient(app)


def test_reuse_story_api(api_client):
    response = api_client.get("/api/benchmark/reuse-story")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["story"]["reuse_conclusion"]["pvdaq_unlabeled_no_fake_metrics"] is True


def test_pvdaq_profile_unlabeled_preflight():
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile(PROFILE_ID)
    assert profile.slot == SLOT
    assert profile.clock_mode == "event_time"
    assert profile.label_column is None
    assert profile.label_semantics == "unlabeled"

    report = run_dataset_profile_preflight(profile, use_purpose="benchmark_reuse")
    assert report.ready is True
    assert report.row_count == 10
    assert report.entity_count == 1


def test_pvdaq_unlabeled_replay_no_ground_truth_metrics(tmp_path, monkeypatch):
    from services.timeseries_point import replay_activity as mod

    monkeypatch.setattr(mod, "_SESSION_ROOT", tmp_path)

    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile(PROFILE_ID)
    df = load_dataset_from_profile(profile)
    session = create_session(
        session_id="pvdaq-replay-1",
        profile=profile.model_dump(),
        source_df=df,
        slot=SLOT,
        execution_purpose="benchmark_reuse",
    )
    assert session.governance_eligible is False
    assert session.clock_mode == "event_time"

    step = replay_next_point("pvdaq-replay-1", context_length=4)
    assert step["status"] == "point_processed"
    assert "benchmark_ground_truth" not in str(step).lower()


def test_pvdaq_slot_purpose_invariant():
    ctx = resolve_execution_purpose(slot=SLOT, execution_purpose="benchmark_reuse")
    assert ctx["governance_eligible"] is False
    with pytest.raises(ValueError):
        resolve_execution_purpose(slot=SLOT, execution_purpose="product_workflow")


def test_pvdaq_blocks_product_governance_writes():
    with pytest.raises(ProvenanceError) as exc_model:
        register_model_candidate(
            slot=SLOT,
            source_workflow_id="workflow-pv-point-train-eval-v1",
            source_execution_id="exec-pvdaq",
            model_artifact_ref="data/models/demo/model.pt",
        )
    assert exc_model.value.code == "benchmark_governance_forbidden"

    with pytest.raises(ProvenanceError) as exc_ann:
        register_annotation_candidate(
            slot=SLOT,
            source_workflow_id="workflow-pv-point-predict-replay-v1",
            source_execution_id="exec-pvdaq",
            dataset_profile_ref=f"{PROFILE_ID}@v1",
            entity_key="683",
            boundary_start="2024-07-15T12:00:00Z",
            boundary_end="2024-07-15T12:05:00Z",
            suggested_label={"class": 0},
        )
    assert exc_ann.value.code == "benchmark_governance_forbidden"


def test_g8_reuse_story_includes_pvdaq():
    story = build_g8_reuse_story()
    assert story["story_id"].startswith("g8-story-")
    assert SLOT in story["benchmark_slots"]
    pvdaq = story["profiles"][SLOT]
    assert pvdaq["label_semantics"] == "unlabeled"
    assert pvdaq["preflight"]["ready"] is True
    assert story["reuse_conclusion"]["pvdaq_unlabeled_no_fake_metrics"] is True
    assert story["reuse_conclusion"]["product_governance_writes_blocked"] is True
