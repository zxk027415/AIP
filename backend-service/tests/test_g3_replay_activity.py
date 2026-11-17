"""Tests for replay_activity state machine."""

from __future__ import annotations

import pandas as pd

from services.timeseries_point.replay_activity import create_session, load_session, replay_next_point, session_to_dict


def test_replay_causal_and_idempotent(tmp_path, monkeypatch):
    from services.timeseries_point import replay_activity as mod

    monkeypatch.setattr(mod, "_SESSION_ROOT", tmp_path)

    rows = []
    t = pd.Timestamp("2024-01-01T08:00:00Z")
    for i in range(6):
        rows.append(
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
                "time": t.isoformat(),
                "value": float(i + 1),
                "i_cal": float(i),
            }
        )
        t += pd.Timedelta(minutes=5 + i)
    df = pd.DataFrame(rows)
    profile = {
        "entity_keys": ["site_id", "device_id", "branch_id"],
        "time_column": "time",
        "feature_columns": ["value", "i_cal"],
        "clock_mode": "event_time",
    }
    create_session(session_id="sess-1", profile=profile, source_df=df, model_ref=None)
    first = replay_next_point("sess-1", idempotency_key="k1", context_length=4)
    assert first["status"] == "point_processed"
    assert first["point_outcome"]["kind"] == "no_decision"

    again = replay_next_point("sess-1", idempotency_key="k1", context_length=4)
    assert again["status"] == "idempotent_replay"

    session = load_session("sess-1")
    assert session.cursor == 1
    assert len(session.committed_history) == 1
    payload = session_to_dict(session)
    assert payload["outcome_count"] == 1
    assert len(payload["recent_outcomes"]) == 1
    assert payload["recent_outcomes"][0]["kind"] == "no_decision"
    empty_window = session_to_dict(session, day_from="2021-11-12", day_to="2021-11-18")
    assert empty_window["recent_outcomes"] == []
    assert empty_window["window_from"] == "2021-11-12"
    assert "2024-01-01" in (payload.get("latest_outcome_days") or [])
    assert empty_window.get("latest_outcome_days") == payload.get("latest_outcome_days")
