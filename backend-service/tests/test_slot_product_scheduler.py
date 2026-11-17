"""Tests for pv_day / pv_point scheduler task factories."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model
from services.scheduler.tasks.slot_product_tasks import (
    _ensure_replay_session,
    make_pv_day_predict_task,
    make_pv_point_replay_tick_task,
)


def test_resolve_slot_scheduler_model_uses_challenger_artifact():
    ctx = resolve_slot_scheduler_model("pv_point")
    assert ctx.get("model_artifact_ref")
    assert "timeseries_point" in str(ctx["model_artifact_ref"])


def test_resolve_slot_scheduler_model_prefers_rolling_detect(monkeypatch):
    fake = {
        "slot": "pv_point",
        "registry_version": 3,
        "champion": None,
        "challenger": {
            "challenger_model_candidate_id": "mc-061e1ed64284",
            "challenger_model_artifact_ref": "backend-service/data/models/timeseries_point/newer",
        },
        "rolling_detect_model": {
            "model_candidate_id": "mc-8c103f4d30cf",
            "model_artifact_ref": "backend-service/data/models/timeseries_point/rtpoint-tcn-last_point-20260824093918-2a2e056e",
        },
    }

    class _Store:
        def get(self, _slot):
            return fake

    monkeypatch.setattr("services.slot_governance.registry.get_registry_store", lambda: _Store())
    ctx = resolve_slot_scheduler_model("pv_point")
    assert ctx["source"] == "rolling_detect_model"
    assert "20260824093918" in str(ctx["model_artifact_ref"])



def test_pv_day_predict_skips_without_model(monkeypatch):
    monkeypatch.setattr(
        "services.scheduler.tasks.slot_product_tasks.resolve_slot_scheduler_model",
        lambda _slot: {"model_artifact_ref": None, "model_id": None},
    )
    from services.scheduler.exceptions import SchedulerTaskSkipped

    with pytest.raises(SchedulerTaskSkipped):
        make_pv_day_predict_task()()


def test_pv_point_replay_tick_advances_session(monkeypatch, tmp_path):
    from services.timeseries_point import replay_activity as replay_mod

    monkeypatch.setattr(replay_mod, "_SESSION_ROOT", tmp_path)
    monkeypatch.setattr(
        "services.scheduler.tasks.slot_product_tasks._BINDINGS_PATH",
        tmp_path / "bindings.json",
    )
    monkeypatch.setattr(
        "services.scheduler.tasks.slot_product_tasks.resolve_slot_scheduler_model",
        lambda _slot: {
            "model_artifact_ref": "backend-service/data/models/timeseries_point/demo-artifact",
        },
    )

    rows = []
    t = pd.Timestamp("2024-01-01T08:00:00Z")
    for i in range(3):
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
        t += pd.Timedelta(minutes=5)
    profile = {
        "entity_keys": ["site_id", "device_id", "branch_id"],
        "time_column": "time",
        "feature_columns": ["value", "i_cal"],
        "clock_mode": "event_time",
    }
    replay_mod.create_session(
        session_id="sched-pv_point-default",
        profile=profile,
        source_df=pd.DataFrame(rows),
        model_ref="backend-service/data/models/timeseries_point/demo-artifact",
        slot="pv_point",
    )

    make_pv_point_replay_tick_task()()
    session = replay_mod.load_session("sched-pv_point-default")
    assert session.cursor >= 1

    from services.execution_history.store import load_latest_execution

    latest = load_latest_execution("workflow-pv-point-predict-replay-v1")
    assert latest is not None
    assert latest.get("scheduler_trigger") is True
    assert latest.get("metrics", {}).get("cursor", 0) >= 1


def test_ensure_replay_session_recreates_after_completed(monkeypatch, tmp_path):
    from services.timeseries_point import replay_activity as replay_mod

    monkeypatch.setattr(replay_mod, "_SESSION_ROOT", tmp_path)

    profile = {
        "entity_keys": ["site_id", "device_id", "branch_id"],
        "time_column": "time",
        "feature_columns": ["value", "i_cal"],
        "clock_mode": "event_time",
    }
    df = pd.DataFrame(
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
    )
    replay_mod.create_session(
        session_id="sched-pv_point-default",
        profile=profile,
        source_df=df,
        model_ref="artifact-ref",
        slot="pv_point",
    )
    session = replay_mod.load_session("sched-pv_point-default")
    session.status = "completed"
    replay_mod._save_session(session)

    class _Profile:
        profile_id = "pv-point-snapshot-684bf7f6"

        def model_dump(self):
            return profile

    class _Store:
        def get_dataset_profile(self, _pid):
            return _Profile()

    monkeypatch.setattr(
        "services.timeseries_profiles.store.TimeseriesProfileStore",
        _Store,
    )
    monkeypatch.setattr(
        "services.timeseries_profiles.loader.load_dataset_from_profile",
        lambda _obj: df,
    )

    binding = {"session_id": "sched-pv_point-default", "dataset_profile_id": "pv-point-snapshot-684bf7f6"}
    sid = _ensure_replay_session("pv_point", model_artifact_ref="artifact-ref", binding=binding)
    assert sid == "sched-pv_point-default"
    fresh = replay_mod.load_session(sid)
    assert fresh.status != "completed"
    assert fresh.cursor == 0


def test_patch_workflow_predict_model_writes_pydantic_node_config():
    from api.workflows_enhanced import load_workflow_from_file
    from services.scheduler.slot_workflow_runner import _patch_workflow_predict_model

    workflow = load_workflow_from_file("workflow-pv-day-predict-v1")
    assert workflow is not None
    _patch_workflow_predict_model(
        workflow,
        model_id="pv_fault_rfc_20260825T093215Z_2d79bc",
        model_ref=r"data\models\pv_fault_rfc_20260825T093215Z_2d79bc.pkl",
    )
    node = next(item for item in workflow.nodes if item.id == "qvp-feature_select-p8")
    config = node.data.config
    mapping = config.dict() if hasattr(config, "dict") else dict(config)
    assert str(mapping.get("model_path") or "").replace("\\", "/").endswith(
        "pv_fault_rfc_20260825T093215Z_2d79bc.pkl"
    )
    rfc = next(
        item for item in workflow.nodes
        if (item.data.config.dict() if hasattr(item.data.config, "dict") else {}).get("functionId")
        == "random_forest_classifier"
    )
    rfc_cfg = rfc.data.config.dict()
    assert rfc_cfg.get("model_id") == "pv_fault_rfc_20260825T093215Z_2d79bc"


def test_feature_select_transform_pkl_uses_global_model_ref():
    from services.operator_backends.feature_select import _resolve_transform_pkl

    path, source = _resolve_transform_pkl(
        {
            "slot": "pv_day",
            "feature_list": "latest",
            "_global_config": {
                "model_ref": "data/models/pv_fault_rfc_20260825T093215Z_2d79bc.pkl",
                "model_id": "pv_fault_rfc_20260825T093215Z_2d79bc",
            },
        }
    )
    assert path is not None
    assert "2d79bc" in str(path).replace("\\", "/")
    assert "xgbr_" not in str(path)
    assert source in {"global_config.model_ref", "model_id"}

# @AI_GENERATED: pv_tsc scheduler run-status and fixed control contract
def _pv_tsc_model_context(*, artifact: bool = True) -> dict:
    return {
        "slot": "pv_tsc",
        "model_artifact_ref": (
            "data/models/tsc/multirocket-demo" if artifact else None
        ),
        "model_candidate_id": "mc-tsc-demo" if artifact else None,
        "registry_version": 7,
        "source": "challenger",
    }


def test_pv_tsc_run_status_four_state_contract(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    from services.scheduler.tasks import slot_product_tasks as tasks

    status_path = tmp_path / "prediction_last_run.json"
    monkeypatch.setattr(tasks, "_PV_TSC_STATUS_PATH", status_path)
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        tasks,
        "resolve_slot_scheduler_model",
        lambda _slot: _pv_tsc_model_context(artifact=False),
    )
    pending = tasks.get_pv_tsc_predict_run_status(now=now, cron_expr="0 4 * * *")
    assert pending["state"] == "model_pending"

    monkeypatch.setattr(
        tasks,
        "resolve_slot_scheduler_model",
        lambda _slot: _pv_tsc_model_context(),
    )
    never_run = tasks.get_pv_tsc_predict_run_status(now=now, cron_expr="0 4 * * *")
    assert never_run["state"] == "no_run_yet"
    assert Path(never_run["status_file"]).is_absolute() is False

    status_path.write_text(
        json.dumps(
            {
                "status": "success",
                "reason": "success",
                "modeling_path": "tsc",
                "strategy_name": "TscDailyStrategy",
                "updated_at": (now - timedelta(hours=1)).isoformat(),
                "started_at": (now - timedelta(hours=2)).isoformat(),
                "model_candidate_id": "mc-tsc-demo",
                "registry_version": 7,
                "points_detected": 4,
                "devices_processed": 2,
                "batch_ids": ["pb-tsc"],
                "review_ids": ["rev-tsc"],
            }
        ),
        encoding="utf-8",
    )
    fresh = tasks.get_pv_tsc_predict_run_status(now=now, cron_expr="0 4 * * *")
    assert fresh["state"] == "success"
    assert fresh["last_run"]["devices_processed"] == 2
    assert "model_artifact_ref" not in fresh["model"]

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["updated_at"] = (now - timedelta(days=2)).isoformat()
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    stale = tasks.get_pv_tsc_predict_run_status(now=now, cron_expr="0 4 * * *")
    assert stale["state"] == "stale"
    assert stale["reason"] == "status_receipt_expired"

    status_path.write_text("{broken", encoding="utf-8")
    malformed = tasks.get_pv_tsc_predict_run_status(now=now, cron_expr="0 4 * * *")
    assert malformed["state"] == "stale"
    assert malformed["reason"] == "invalid_status_payload"


def test_scheduler_api_exposes_fixed_pv_tsc_control_contract():
    import inspect
    from api import scheduler as scheduler_api

    assert "pv_tsc" in scheduler_api._VALID_PIPELINES
    route = next(
        item
        for item in scheduler_api.router.routes
        if item.path == "/api/scheduler/tasks/pv_tsc_predict/run-status"
    )
    assert inspect.signature(route.endpoint).parameters == {}
# @AI_GENERATED: end