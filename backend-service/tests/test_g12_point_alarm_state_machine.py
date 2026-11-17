"""G12 point alarm state machine tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.timeseries_point.point_alarm_state_machine import (
    AlarmPolicy,
    EntityAlarmState,
    apply_point_outcome,
)
from services.timeseries_point.point_alarm_store import ingest_point_outcome


def _fault(label: int = 1, t: str = "2024-01-01T08:00:00Z") -> dict:
    return {
        "kind": "prediction",
        "label": label,
        "confidence": 0.95,
        "entity_key": "s1|d1|b1",
        "point_time": t,
    }


def _normal(t: str = "2024-01-01T08:05:00Z") -> dict:
    return {
        "kind": "prediction",
        "label": 0,
        "confidence": 0.9,
        "entity_key": "s1|d1|b1",
        "point_time": t,
    }


def test_alarm_open_requires_three_consecutive_faults():
    policy = AlarmPolicy(open_consecutive_points=3, cold_start_alarm_enabled=True)
    state = EntityAlarmState(entity_key="s1|d1|b1")
    events_total = []
    for idx in range(2):
        state, events = apply_point_outcome(state, _fault(t=f"t{idx}"), policy=policy)
        events_total.extend(events)
    assert state.phase == "suspected_open"
    assert not any(event.event_type == "alarm_open" for event in events_total)

    state, events = apply_point_outcome(state, _fault(t="t2"), policy=policy)
    assert state.phase == "active"
    assert any(event.event_type == "alarm_open" for event in events)


def test_alarm_dedupe_while_active():
    policy = AlarmPolicy(open_consecutive_points=2, cold_start_alarm_enabled=True)
    state = EntityAlarmState(entity_key="s1|d1|b1")
    for idx in range(2):
        state, _ = apply_point_outcome(state, _fault(t=f"t{idx}"), policy=policy)
    assert state.phase == "active"
    state, events = apply_point_outcome(state, _fault(t="t3"), policy=policy)
    assert any(event.event_type == "alarm_dedupe" for event in events)
    assert state.phase == "active"


def test_alarm_close_after_consecutive_normal():
    policy = AlarmPolicy(
        open_consecutive_points=2,
        close_consecutive_points=3,
        cold_start_alarm_enabled=True,
    )
    state = EntityAlarmState(entity_key="s1|d1|b1")
    state, _ = apply_point_outcome(state, _fault(t="t0"), policy=policy)
    state, _ = apply_point_outcome(state, _fault(t="t1"), policy=policy)
    assert state.phase == "active"
    for idx in range(2):
        state, events = apply_point_outcome(state, _normal(t=f"n{idx}"), policy=policy)
        assert not any(event.event_type == "alarm_close" for event in events)
    state, events = apply_point_outcome(state, _normal(t="n2"), policy=policy)
    assert state.phase == "normal"
    assert any(event.event_type == "alarm_close" for event in events)


def _alarm_decision_view(state: EntityAlarmState) -> dict:
    return {
        "phase": state.phase,
        "active_alarm_id": state.active_alarm_id,
        "active_label": state.active_label,
        "consecutive_fault": state.consecutive_fault,
        "consecutive_normal": state.consecutive_normal,
        "consecutive_switch": state.consecutive_switch,
    }


def test_future_outcome_does_not_change_past_alarm_decision():
    policy = AlarmPolicy(open_consecutive_points=2, cold_start_alarm_enabled=True)
    outcomes = [_fault(t="t0"), _fault(t="t1"), _normal(t="n0")]
    state_a = EntityAlarmState(entity_key="s1|d1|b1")
    for outcome in outcomes:
        state_a, _ = apply_point_outcome(state_a, outcome, policy=policy)

    state_b = EntityAlarmState(entity_key="s1|d1|b1")
    for outcome in outcomes[:2]:
        state_b, _ = apply_point_outcome(state_b, outcome, policy=policy)
    snapshot = _alarm_decision_view(state_b)

    apply_point_outcome(state_b, _fault(label=99, t="future"), policy=policy)
    assert _alarm_decision_view(state_b) == snapshot


def test_store_persists_events(tmp_path, monkeypatch):
    from services.timeseries_point import point_alarm_store as store_mod

    monkeypatch.setattr(store_mod, "_ALARM_ROOT", tmp_path)
    policy = AlarmPolicy(open_consecutive_points=2, cold_start_alarm_enabled=True)
    ingest_point_outcome("pv_point", _fault(t="t0"), policy=policy)
    result = ingest_point_outcome("pv_point", _fault(t="t1"), policy=policy)
    assert result["phase"] == "active"
    assert any(event["event_type"] == "alarm_open" for event in result["events"])

    summary = store_mod.alarm_summary("pv_point")
    assert summary["active_alarm_count"] >= 1
    assert summary["recent_events"]


def test_pending_feed_drains_into_replay_session(tmp_path, monkeypatch):
    from services.timeseries_point import pending_point_feed as feed_mod
    from services.timeseries_point import replay_activity as replay_mod

    monkeypatch.setattr(feed_mod, "_FEED_ROOT", tmp_path / "feed")
    monkeypatch.setattr(replay_mod, "_SESSION_ROOT", tmp_path / "sessions")

    import pandas as pd

    profile = {
        "entity_keys": ["site_id", "device_id", "branch_id"],
        "time_column": "time",
        "feature_columns": ["value", "i_cal"],
        "clock_mode": "event_time",
    }
    replay_mod.create_session(
        session_id="feed-session",
        profile=profile,
        source_df=pd.DataFrame(
            [
                {
                    "site_id": "s1",
                    "device_id": "d1",
                    "branch_id": "b1",
                    "time": "2024-01-01T08:00:00Z",
                    "value": 1.0,
                    "i_cal": 0.0,
                }
            ]
        ),
        model_ref="artifact-ref",
        slot="pv_point",
    )
    feed_mod.enqueue_pending_point(
        "pv_point",
        {
            "entity_key": "s1|d1|b1",
            "point_time": "2024-01-01T08:05:00Z",
            "value": 2.0,
            "i_cal": 0.1,
        },
    )
    added = replay_mod.append_pending_feed_points("feed-session", "pv_point", limit=1)
    assert added == 1
    session = replay_mod.load_session("feed-session")
    assert len(session.source_rows) == 2
    assert feed_mod.pending_summary("pv_point")["pending"] == 0


def test_session_save_omits_source_rows_when_profile_bound(tmp_path, monkeypatch):
    from services.timeseries_point import replay_activity as replay_mod

    monkeypatch.setattr(replay_mod, "_SESSION_ROOT", tmp_path)

    import pandas as pd

    profile = {
        "entity_keys": ["site_id"],
        "time_column": "time",
        "feature_columns": ["value"],
        "clock_mode": "event_time",
    }
    df = pd.DataFrame([{"site_id": "s1", "time": "2024-01-01T08:00:00Z", "value": 1.0}])
    replay_mod.create_session(
        session_id="hydrate-test",
        profile=profile,
        source_df=df,
        slot="pv_point",
        dataset_profile_id="profile-demo",
    )
    raw = json.loads((tmp_path / "hydrate-test.json").read_text(encoding="utf-8"))
    assert raw.get("source_rows") == []
    assert raw.get("dataset_profile_id") == "profile-demo"


def test_alarm_policy_persist_changes_open_threshold(tmp_path, monkeypatch):
    from services.timeseries_point import point_alarm_store as store_mod

    monkeypatch.setattr(store_mod, "_ALARM_ROOT", tmp_path)
    store_mod.save_alarm_policy(
        "pv_point",
        {"open_consecutive_points": 2, "close_consecutive_points": 2, "cold_start_alarm_enabled": True},
    )
    ingest_point_outcome("pv_point", _fault(t="t0"))
    result = ingest_point_outcome("pv_point", _fault(t="t1"))
    assert result["phase"] == "active"
    policy = store_mod.load_alarm_policy("pv_point")
    assert policy.open_consecutive_points == 2


def test_alarm_events_filter_to_calendar_window(tmp_path, monkeypatch):
    from services.timeseries_point import point_alarm_store as store_mod

    monkeypatch.setattr(store_mod, "_ALARM_ROOT", tmp_path)
    ingest_point_outcome("pv_point", _fault(t="2021-11-10T08:00:00Z"))
    ingest_point_outcome("pv_point", _fault(t="2021-11-18T08:00:00Z"))
    ingest_point_outcome("pv_point", _fault(t="2021-11-18T08:10:00Z"))
    window = store_mod.list_events("pv_point", limit=20, day_from="2021-11-12", day_to="2021-11-18")
    days = {str(item.get("point_time") or "")[:10] for item in window}
    assert "2021-11-10" not in days
    assert "2021-11-18" in days
    summary = store_mod.alarm_summary("pv_point", day_from="2021-11-12", day_to="2021-11-18")
    assert summary["window_from"] == "2021-11-12"
    assert all(str(item.get("point_time") or "")[:10] >= "2021-11-12" for item in summary["recent_events"])
