"""Focused tests for proposal review, champion detect, replay interleave, snapshot preview, day gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets.errors import SlotDatasetError


@pytest.fixture()
def slot_env(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend-service"
    slot_dir = backend_dir / "data" / "slot_datasets"
    slot_dir.mkdir(parents=True)
    import services.slot_datasets.label_proposals as lp_mod
    import services.slot_datasets.snapshots as snapshots_mod
    import services.slot_datasets.observability_ledger as obs_mod

    monkeypatch.setattr(lp_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lp_mod, "_DATA_DIR", slot_dir)
    monkeypatch.setattr(snapshots_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(snapshots_mod, "_DATA_DIR", slot_dir)
    monkeypatch.setattr(obs_mod, "_BACKEND_DIR", backend_dir)
    return backend_dir, slot_dir


def test_reject_label_proposal_isolates_slot(slot_env):
    from services.slot_datasets import label_proposals as lp

    backend_dir, _ = slot_env
    members = backend_dir / "data" / "slot_datasets" / "pv_point" / "proposal_rows" / "m.csv"
    members.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"cluster_id": [0], "member_key": ["a"], "value": [1.0]}).to_csv(members, index=False)
    rec = lp.save_label_proposal(
        slot="pv_point",
        clusters={"0": {"proposed_label_name": "cluster_0", "selected_member_keys": ["a"], "member_keys": ["a"]}},
        member_rows_path="data/slot_datasets/pv_point/proposal_rows/m.csv",
    )
    rejected = lp.reject_label_proposal("pv_point", rec["proposal_id"], reason="nope")
    assert rejected["status"] == "rejected"
    with pytest.raises(SlotDatasetError) as exc:
        lp.confirm_label_proposal(slot="pv_point", proposal_id=rec["proposal_id"], label_id_map={"cluster_0": 1})
    assert exc.value.code == "proposal_rejected"
    with pytest.raises(SlotDatasetError):
        lp.get_label_proposal("pv_day", rec["proposal_id"])


def test_resolve_prefers_champion_then_rolling(monkeypatch):
    from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model

    fake = {
        "slot": "pv_point",
        "registry_version": 4,
        "champion": {
            "champion_model_ref": "mc-prod",
            "champion_model_artifact_ref": "data/models/timeseries_point/prod",
        },
        "challenger": {
            "challenger_model_candidate_id": "mc-cand",
            "challenger_model_artifact_ref": "data/models/timeseries_point/cand",
        },
        "rolling_detect_model": {
            "model_candidate_id": "mc-roll",
            "model_artifact_ref": "data/models/timeseries_point/roll",
        },
    }

    class _Store:
        def get(self, _slot):
            return fake

    monkeypatch.setattr("services.slot_governance.registry.get_registry_store", lambda: _Store())
    monkeypatch.setattr(
        "services.slot_governance.model_candidates.find_model_candidate",
        lambda cid: (None, None),
    )
    ctx = resolve_slot_scheduler_model("pv_point")
    assert ctx["source"] == "champion"
    assert "prod" in str(ctx["model_artifact_ref"])

    fake["champion"] = None
    ctx2 = resolve_slot_scheduler_model("pv_point")
    assert ctx2["source"] == "rolling_detect_model"


def test_replay_picks_earliest_event_across_devices(tmp_path, monkeypatch):
    from services.timeseries_point import replay_activity as mod
    from services.timeseries_point.replay_activity import create_session, replay_next_point

    monkeypatch.setattr(mod, "_SESSION_ROOT", tmp_path)
    rows = [
        {"site_id": "s1", "device_id": "d1", "branch_id": "b1", "time": "2024-01-01T08:00:00Z", "value": 1.0, "i_cal": 1.0},
        {"site_id": "s1", "device_id": "d1", "branch_id": "b1", "time": "2024-01-01T08:10:00Z", "value": 2.0, "i_cal": 2.0},
        {"site_id": "s1", "device_id": "d2", "branch_id": "b1", "time": "2024-01-01T08:05:00Z", "value": 3.0, "i_cal": 3.0},
        {"site_id": "s1", "device_id": "d2", "branch_id": "b1", "time": "2024-01-01T08:15:00Z", "value": 4.0, "i_cal": 4.0},
    ]
    profile = {
        "entity_keys": ["site_id", "device_id", "branch_id"],
        "time_column": "time",
        "feature_columns": ["value", "i_cal"],
        "clock_mode": "event_time",
    }
    session = create_session(session_id="sess-interleave", profile=profile, source_df=pd.DataFrame(rows), model_ref=None)
    assert session.selection_policy == "earliest_event_time"
    first = replay_next_point("sess-interleave", context_length=2)
    second = replay_next_point("sess-interleave", context_length=2)
    assert "d1" in str(first["point_outcome"].get("entity_key"))
    assert "d2" in str(second["point_outcome"].get("entity_key"))


def test_legacy_replay_session_keeps_entity_then_time(tmp_path, monkeypatch):
    from services.timeseries_point import replay_activity as mod
    from services.timeseries_point.replay_activity import ReplaySession, replay_next_point

    monkeypatch.setattr(mod, "_SESSION_ROOT", tmp_path)
    rows = [
        {"site_id": "s1", "device_id": "d1", "branch_id": "b1", "time": "2024-01-01T08:00:00Z", "value": 1.0, "i_cal": 1.0},
        {"site_id": "s1", "device_id": "d1", "branch_id": "b1", "time": "2024-01-01T08:10:00Z", "value": 2.0, "i_cal": 2.0},
        {"site_id": "s1", "device_id": "d2", "branch_id": "b1", "time": "2024-01-01T08:05:00Z", "value": 3.0, "i_cal": 3.0},
    ]
    session = ReplaySession(
        session_id="legacy-sess",
        selection_policy="legacy_entity_then_time",
        status="running",
        profile={"entity_keys": ["site_id", "device_id", "branch_id"], "time_column": "time", "feature_columns": ["value", "i_cal"], "clock_mode": "event_time"},
        source_rows=rows,
        cursor=0,
        entity_cursors={"s1|d1|b1": 0, "s1|d2|b1": 0},
        use_frozen_graph=False,
    )
    mod._save_session(session)
    first = replay_next_point("legacy-sess", context_length=2)
    second = replay_next_point("legacy-sess", context_length=2)
    assert "d1" in str(first["point_outcome"].get("entity_key"))
    assert "d1" in str(second["point_outcome"].get("entity_key"))


def test_snapshot_preview_reads_parquet(slot_env):
    from services.slot_datasets import snapshots as snaps

    _backend_dir, slot_dir = slot_env
    freeze_id = "snap-pv_point-v9"
    artifact = slot_dir / "pv_point" / "snapshots" / f"{freeze_id}.parquet"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-01T08:00:00Z", "2024-01-01T08:05:00Z"]),
            "site_id": ["s1", "s1"],
            "device_id": ["d1", "d1"],
            "branch_id": ["b1", "b1"],
            "label": [1, 2],
            "value": [1.0, 2.0],
        }
    ).to_parquet(artifact, index=False)
    chain = {
        "versions": [
            {
                "freeze_id": freeze_id,
                "artifact_ref": f"data/slot_datasets/pv_point/snapshots/{freeze_id}.parquet",
                "included_events": [],
            }
        ]
    }
    chain_path = slot_dir / "pv_point" / "snapshot_chain.json"
    chain_path.parent.mkdir(parents=True, exist_ok=True)
    chain_path.write_text(json.dumps(chain), encoding="utf-8")
    preview = snaps.preview_snapshot("pv_point", freeze_id)
    assert preview["row_count"] == 2
    assert preview["label_distribution"]["1"] == 1
    assert preview["sample_rows"]


def test_day_gate_skips_incomplete_before_predict(slot_env, monkeypatch):
    from services.slot_datasets import observability_ledger as obs

    frame = pd.DataFrame(
        {
            "site_id": ["s1"] * 10 + ["s1"] * 180,
            "device_id": ["low"] * 10 + ["ok"] * 180,
            "branch_id": ["b1"] * 190,
            "time": pd.date_range("2024-03-01 08:00", periods=190, freq="5min"),
            "value": [1.0] * 190,
        }
    )
    monkeypatch.setattr(obs, "_read_calendar_frame", lambda _slot: frame)
    monkeypatch.setattr(obs, "_read_source_frame", lambda _slot: frame)
    monkeypatch.setattr(obs, "load_ledger", lambda _slot: {"cells": {}})
    monkeypatch.setattr(obs, "_latest_source_day", lambda _slot: pd.Timestamp("2024-03-01").date())
    saved = {}

    def _save(_slot, payload):
        saved.update(payload)
        return payload

    monkeypatch.setattr(obs, "save_ledger", _save)
    batch = obs.prepare_day_detect_batch("pv_day")
    assert "s1|ok|b1" in batch["ready_devices"]
    assert "s1|low|b1" in batch["waiting_devices"]
    assert batch["input_file_path"]


def test_waiting_expires_after_hold_days_by_watermark(slot_env, monkeypatch):
    from services.slot_datasets import observability_ledger as obs

    frame = pd.DataFrame(
        {
            "site_id": ["s1"] * 10,
            "device_id": ["low"] * 10,
            "branch_id": ["b1"] * 10,
            "time": pd.date_range("2024-03-04 08:00", periods=10, freq="5min"),
            "value": [1.0] * 10,
        }
    )
    monkeypatch.setattr(obs, "_read_calendar_frame", lambda _slot: frame)
    monkeypatch.setattr(
        obs,
        "load_ledger",
        lambda _slot: {
            "watermark_day": "2024-03-04",
            "cells": {
                "s1|low|b1|2024-03-01": {
                    "device_key": "s1|low|b1",
                    "date": "2024-03-01",
                    "status": "waiting",
                    "wait_started_on": "2024-03-01",
                    "arrived_count": 10,
                }
            },
        },
    )
    saved: dict = {}
    monkeypatch.setattr(obs, "save_ledger", lambda _slot, payload: saved.update(payload) or payload)
    batch = obs.prepare_day_detect_batch("pv_day")
    expired = saved["cells"]["s1|low|b1|2024-03-01"]
    assert expired["status"] == "skipped"
    assert expired["skip_reason"] == "expired_incomplete"
    assert "s1|low|b1" in batch["skipped_devices"]


def test_proposal_detail_rejects_slot_mismatch(slot_env):
    from services.slot_datasets import label_proposals as lp

    backend_dir, _ = slot_env
    members = backend_dir / "data" / "slot_datasets" / "pv_point" / "proposal_rows" / "m.csv"
    members.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"cluster_id": [0], "member_key": ["a"], "value": [1.0]}).to_csv(members, index=False)
    rec = lp.save_label_proposal(
        slot="pv_point",
        clusters={"0": {"proposed_label_name": "cluster_0", "selected_member_keys": ["a"], "member_keys": ["a"]}},
        member_rows_path="data/slot_datasets/pv_point/proposal_rows/m.csv",
    )
    path = lp._proposals_path("pv_point")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["proposals"][0]["slot"] = "pv_day"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SlotDatasetError) as exc:
        lp.get_label_proposal_detail("pv_point", rec["proposal_id"])
    assert exc.value.code == "slot_mismatch"


def test_day_proposal_waveforms_use_feature_bars(slot_env):
    from services.slot_datasets import label_proposals as lp

    backend_dir, _ = slot_env
    members = backend_dir / "data" / "slot_datasets" / "pv_day" / "proposal_rows" / "m.csv"
    members.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"cluster_id": [0], "member_key": ["a"], "time": ["t1"], "i_cal": [1.0]}).to_csv(members, index=False)
    rec = lp.save_label_proposal(
        slot="pv_day",
        clusters={
            "0": {
                "proposed_label_name": "cluster_0",
                "selected_member_keys": ["a"],
                "member_keys": ["a"],
                "representative_member_key": "a",
                "representative_stats": {"mean_i": 1.2, "std_i": 0.4},
            }
        },
        member_rows_path="data/slot_datasets/pv_day/proposal_rows/m.csv",
    )
    detail = lp.get_label_proposal_detail("pv_day", rec["proposal_id"])
    bars = detail["waveforms"]["a"]
    assert [item["time"] for item in bars] == ["mean_i", "std_i"]
    assert bars[0]["value"] == 1.2


def test_point_cluster_waveform_uses_all_selected_members(slot_env):
    from services.slot_datasets import label_proposals as lp

    backend_dir, _ = slot_env
    members = backend_dir / "data" / "slot_datasets" / "pv_point" / "proposal_rows" / "m.csv"
    members.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "time": ["2024-03-01T08:00:00", "2024-03-01T08:05:00", "2024-03-01T08:10:00"],
            "member_key": ["s1|d1|1", "s1|d1|1", "s1|d2|1"],
            "value": [1.0, 3.0, 2.0],
            "i_cal": [1.1, 3.1, 2.1],
        }
    ).to_csv(members, index=False)
    rec = lp.save_label_proposal(
        slot="pv_point",
        clusters={
            "0": {
                "proposed_label_name": "cluster_0",
                "selected_member_keys": ["s1|d1|1", "s1|d2|1"],
                "member_keys": ["s1|d1|1", "s1|d2|1"],
                "representative_member_key": "s1|d1|1",
            }
        },
        member_rows_path="data/slot_datasets/pv_point/proposal_rows/m.csv",
    )
    detail = lp.get_label_proposal_detail("pv_point", rec["proposal_id"])
    curve = detail["waveforms"]["0"]
    assert len(curve) == 3
    assert [item["value"] for item in curve] == [1.0, 3.0, 2.0]
    assert curve[0]["i_cal"] == 1.1
    assert len(detail["members_by_cluster"]["0"]) == 3


def test_proposal_catalog_fallback_when_registry_empty(slot_env, monkeypatch):
    from services.slot_datasets import label_proposals as lp

    monkeypatch.setattr(lp, "_file_registry_names", lambda _slot: {})
    backend_dir, _ = slot_env
    members = backend_dir / "data" / "slot_datasets" / "pv_point" / "proposal_rows" / "m.csv"
    members.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"cluster_id": [0], "member_key": ["a"], "value": [4.1], "i_cal": [4.1]}).to_csv(members, index=False)
    rec = lp.save_label_proposal(
        slot="pv_point",
        clusters={
            "0": {
                "proposed_label_name": "cluster_0",
                "selected_member_keys": ["a"],
                "member_keys": ["a"],
                "representative_stats": {"i_cal": {"mean": 4.1}},
            }
        },
        member_rows_path="data/slot_datasets/pv_point/proposal_rows/m.csv",
    )
    listed = lp.list_label_proposals("pv_point")
    names = listed[0]["clusters"]["0"]["suggested_label_names"]
    assert names
    assert "组串失配" in names
    detail = lp.get_label_proposal_detail("pv_point", rec["proposal_id"])
    assert "正常" in detail["registry_label_names"]
    assert "组串失配" in detail["registry_label_names"]
