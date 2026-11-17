"""G6.3 FHC Twin-Plant benchmark profile placeholder tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.timeseries_point.replay_activity import create_session, replay_next_point
from services.timeseries_profiles.loader import load_dataset_from_profile
from services.timeseries_profiles.preflight import run_dataset_profile_preflight
from services.timeseries_profiles.store import TimeseriesProfileStore


def test_fhc_profile_loads_and_preflight():
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile("benchmark-fhc-twin-plant-demo")
    assert profile.slot == "benchmark_fhc_twin_plant"
    assert profile.clock_mode == "event_time"
    assert profile.sampling_interval == "PT30S"
    assert profile.label_semantics == "benchmark_ground_truth"

    report = run_dataset_profile_preflight(profile, use_purpose="benchmark_reuse")
    assert report.ready is True
    assert report.row_count == 8
    assert report.entity_count == 1


def test_fhc_event_time_replay(tmp_path, monkeypatch):
    from services.timeseries_point import replay_activity as mod

    monkeypatch.setattr(mod, "_SESSION_ROOT", tmp_path)

    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile("benchmark-fhc-twin-plant-demo")
    df = load_dataset_from_profile(profile)
    session = create_session(
        session_id="fhc-replay-1",
        profile=profile.model_dump(),
        source_df=df,
        slot="benchmark_fhc_twin_plant",
        execution_purpose="benchmark_reuse",
    )
    assert session.governance_eligible is False
    assert session.clock_mode == "event_time"

    step = replay_next_point("fhc-replay-1", context_length=4)
    assert step["status"] == "point_processed"


def test_fhc_blocks_product_governance_write():
    from services.slot_governance.model_candidates import register_model_candidate
    from services.slot_governance.provenance import ProvenanceError

    with pytest.raises(ProvenanceError) as exc:
        register_model_candidate(
            slot="benchmark_fhc_twin_plant",
            source_workflow_id="workflow-pv-point-train-eval-v1",
            source_execution_id="exec-1",
            model_artifact_ref="data/models/demo/model.pt",
        )
    assert exc.value.code == "benchmark_governance_forbidden"
