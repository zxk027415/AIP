"""G6.1 replay activity: pause/resume/cancel + benchmark index-clock."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.timeseries_point.replay_activity import (
    cancel_session,
    create_session,
    load_session,
    pause_session,
    replay_next_point,
    resume_session,
)


def _patch_session_root(tmp_path, monkeypatch):
    from services.timeseries_point import replay_activity as mod

    monkeypatch.setattr(mod, "_SESSION_ROOT", tmp_path)


def test_replay_pause_resume_cancel(tmp_path, monkeypatch):
    _patch_session_root(tmp_path, monkeypatch)
    rows = []
    t = pd.Timestamp("2024-01-01T08:00:00Z")
    for i in range(4):
        rows.append(
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
                "time": (t + pd.Timedelta(minutes=i * 5)).isoformat(),
                "value": float(i + 1),
                "i_cal": float(i),
            }
        )
    profile = {
        "entity_keys": ["site_id", "device_id", "branch_id"],
        "time_column": "time",
        "feature_columns": ["value", "i_cal"],
        "clock_mode": "event_time",
    }
    create_session(session_id="sess-ctl", profile=profile, source_df=pd.DataFrame(rows))
    pause_session("sess-ctl")
    paused = replay_next_point("sess-ctl")
    assert paused["status"] == "paused"

    resume_session("sess-ctl")
    step = replay_next_point("sess-ctl", idempotency_key="k1", context_length=4)
    assert step["status"] == "point_processed"

    cancel_session("sess-ctl", reason="user stop")
    cancelled = replay_next_point("sess-ctl")
    assert cancelled["status"] == "cancelled"
    session = load_session("sess-ctl")
    assert session.status == "cancelled"
    assert session.error == "user stop"


def test_session_entity_overview_counts_replayed_points(tmp_path, monkeypatch):
    from services.timeseries_point.replay_activity import session_to_dict

    _patch_session_root(tmp_path, monkeypatch)
    rows = []
    t = pd.Timestamp("2024-01-01T08:00:00Z")
    for device, n in (("d1", 3), ("d2", 2)):
        for i in range(n):
            rows.append(
                {
                    "site_id": "s1",
                    "device_id": device,
                    "branch_id": "b1",
                    "time": (t + pd.Timedelta(minutes=i * 5)).isoformat(),
                    "value": float(i + 1),
                    "i_cal": float(i),
                }
            )
    profile = {
        "entity_keys": ["site_id", "device_id", "branch_id"],
        "time_column": "time",
        "feature_columns": ["value", "i_cal"],
        "clock_mode": "event_time",
    }
    create_session(session_id="sess-ent", profile=profile, source_df=pd.DataFrame(rows))
    replay_next_point("sess-ent", idempotency_key="e1", context_length=2)
    payload = session_to_dict(load_session("sess-ent"))
    overview = {row["device_id"]: row for row in payload["entity_overview"]}
    assert overview["d1"]["source_points"] == 3
    assert overview["d2"]["source_points"] == 2
    assert overview["d1"]["replayed_points"] == 1
    assert overview["d2"]["replayed_points"] == 0


def test_benchmark_index_clock_replay(tmp_path, monkeypatch):
    _patch_session_root(tmp_path, monkeypatch)
    df = pd.read_csv(
        Path(__file__).resolve().parents[1]
        / "data/timeseries_point/test_fixtures/nasa_smap_msl_demo.csv"
    )
    profile = {
        "entity_keys": ["channel_id"],
        "index_column": "step_index",
        "time_column": None,
        "feature_columns": ["value"],
        "label_column": "anomaly_label",
        "clock_mode": "index",
        "simulation_step": 1,
    }
    session = create_session(
        session_id="bench-replay-1",
        profile=profile,
        source_df=df,
        slot="benchmark_nasa_smap_msl",
        execution_purpose="benchmark_reuse",
    )
    assert session.governance_eligible is False
    assert session.clock_mode == "index"
    assert session.range_start == 0
    assert session.range_end == 5

    first = replay_next_point("bench-replay-1", context_length=4)
    assert first["status"] == "point_processed"
    assert first["governance_eligible"] is False

    loaded = load_session("bench-replay-1")
    assert loaded.entity_cursors["C-1"] == 1
    assert loaded.cursor == 1


def test_benchmark_slot_requires_benchmark_purpose(tmp_path, monkeypatch):
    _patch_session_root(tmp_path, monkeypatch)
    df = pd.DataFrame([{"channel_id": "C-1", "step_index": 0, "value": 0.1}])
    profile = {
        "entity_keys": ["channel_id"],
        "index_column": "step_index",
        "feature_columns": ["value"],
        "clock_mode": "index",
    }
    with pytest.raises(ValueError, match="requires execution_purpose=benchmark_reuse"):
        create_session(
            session_id="bad-bench",
            profile=profile,
            source_df=df,
            slot="benchmark_nasa_smap_msl",
            execution_purpose="product_workflow",
        )
