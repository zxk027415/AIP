# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PV Deployment Arena 只读适配、写拒绝，以及非 pv_fault 槽位回归。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from services.deployment.models import DeploymentSlot, ModelVersion, SwitchEvent
from services.deployment.pv_read_adapter import (
    PV_FAULT_READ_ONLY_CODE,
    PV_FAULT_READ_ONLY_MESSAGE,
    PVDeploymentReadAdapter,
    PvFaultRegistryReadOnlyError,
)
from services.deployment.store import DeploymentSlotStore, SwitchEventLog
from services.deployment.switch_decision import SwitchDecisionEngine, SwitchDecisionError
from services.iterative_labeling.pv_model_registry import ModelRegistration, PVModelRegistry


def _model(ref: str, evaluation: str, score: float) -> ModelRegistration:
    return ModelRegistration(ref, evaluation, score, "2026-08-13T00:00:00")


def _registry(tmp_path: Path) -> PVModelRegistry:
    return PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")


def _store(tmp_path: Path, registry: PVModelRegistry) -> DeploymentSlotStore:
    return DeploymentSlotStore(
        slots_path=tmp_path / "slots.json",
        pv_adapter=PVDeploymentReadAdapter(registry),
    )


def _load_forecast_slot() -> DeploymentSlot:
    production = ModelVersion(
        workflow_id="wf-prod",
        version_tag="v1",
        status="production",
        deployed_at="2026-08-01T00:00:00",
        accuracy_score=4.2,
    )
    shadow = ModelVersion(
        workflow_id="wf-shadow",
        version_tag="v2",
        status="shadow",
        deployed_at="2026-08-02T00:00:00",
        accuracy_score=3.8,
        consecutive_better_days=7,
    )
    return DeploymentSlot(
        slot="load_forecast",
        production_model=production,
        shadow_models=[shadow],
        auto_switch_enabled=True,
        updated_at="2026-08-02T00:00:00",
    )


def test_adapter_maps_registry_champion_challenger_retired(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.register_challenger("legacy_day", _model("data/models/legacy.pkl", "e-legacy", 0.70))
    assert registry.promote_within_path("legacy_day", "e-legacy").status == "promoted"
    registry.register_challenger("legacy_day", _model("data/models/legacy-new.pkl", "e-legacy-2", 0.80))
    assert registry.promote_within_path("legacy_day", "e-legacy-2").status == "promoted"
    registry.register_challenger("seq_annotation", _model("data/models/seq.pkl", "e-seq", 0.90))

    view = PVDeploymentReadAdapter(registry).get_slot_view("pv_fault")
    slot = view.to_deployment_slot()

    assert view.read_only is True
    assert view.production_path == "legacy_day"
    assert slot.slot == "pv_fault"
    assert slot.auto_switch_enabled is False
    assert slot.production_model is not None
    assert slot.production_model.workflow_id == "data/models/legacy-new.pkl"
    assert slot.production_model.version_tag == "legacy_day:e-legacy-2"
    assert slot.production_model.status == "production"

    statuses = {item.version_tag: item.status for item in slot.shadow_models}
    assert statuses["seq_annotation:e-seq"] == "shadow"
    assert statuses["legacy_day:e-legacy"] == "retired"
    assert slot.prelaunch_models == []


def test_store_get_overlays_registry_and_does_not_write_slots_json(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.register_challenger("legacy_day", _model("data/models/legacy.pkl", "e1", 0.71))
    registry.promote_within_path("legacy_day", "e1")
    store = _store(tmp_path, registry)

    stale = DeploymentSlot(
        slot="load_forecast",
        production_model=None,
        updated_at="2026-01-01T00:00:00",
    )
    store.upsert(stale)

    # 人为在 slots.json 塞一份过期 pv_fault，读路径必须忽略它
    raw = json.loads((tmp_path / "slots.json").read_text(encoding="utf-8"))
    raw["pv_fault"] = {
        "slot": "pv_fault",
        "production_model": {
            "workflow_id": "stale-from-slots-json",
            "version_tag": "stale",
            "status": "production",
            "deployed_at": "2020-01-01T00:00:00",
        },
        "shadow_models": [],
        "updated_at": "2020-01-01T00:00:00",
    }
    (tmp_path / "slots.json").write_text(json.dumps(raw), encoding="utf-8")

    loaded = store.get("pv_fault")
    assert loaded is not None
    assert loaded.production_model is not None
    assert loaded.production_model.workflow_id == "data/models/legacy.pkl"
    persisted = json.loads((tmp_path / "slots.json").read_text(encoding="utf-8"))
    assert persisted["pv_fault"]["production_model"]["workflow_id"] == "stale-from-slots-json"


def test_store_and_engine_reject_pv_fault_writes(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    store = _store(tmp_path, registry)
    log = SwitchEventLog(log_path=tmp_path / "switch_log.json")
    engine = SwitchDecisionEngine(slot_store=store, event_log=log)

    pv_slot = DeploymentSlot(slot="pv_fault", production_model=None, updated_at="2026-08-01T00:00:00")
    with pytest.raises(PvFaultRegistryReadOnlyError) as upsert_exc:
        store.upsert(pv_slot)
    assert upsert_exc.value.code == PV_FAULT_READ_ONLY_CODE
    assert "PV 双路径控制台" in str(upsert_exc.value)

    with pytest.raises(PvFaultRegistryReadOnlyError):
        store.save_all({"pv_fault": pv_slot})
    with pytest.raises(PvFaultRegistryReadOnlyError):
        store.promote_prelaunch_to_shadow("pv_fault", "wf-x")
    with pytest.raises(PvFaultRegistryReadOnlyError):
        store.fail_prelaunch("pv_fault", "wf-x")
    with pytest.raises(PvFaultRegistryReadOnlyError):
        log.append(
            SwitchEvent(
                event_id="evt-1",
                slot="pv_fault",
                trigger_type="manual",
                switch_time="2026-08-01T00:00:00",
                from_workflow_id="a",
                from_version_tag="v1",
                to_workflow_id="b",
                to_version_tag="v2",
            )
        )

    with pytest.raises(SwitchDecisionError) as switch_exc:
        engine.execute_switch(
            slot="pv_fault",
            target_workflow_id="any",
            trigger_type="manual",
            reason="should fail",
        )
    assert switch_exc.value.code == PV_FAULT_READ_ONLY_CODE
    assert switch_exc.value.message == PV_FAULT_READ_ONLY_MESSAGE

    with pytest.raises(SwitchDecisionError) as rollback_exc:
        engine.execute_rollback("pv_fault")
    assert rollback_exc.value.code == PV_FAULT_READ_ONLY_CODE

    eligibility = engine.check_switch_eligibility("pv_fault")
    assert eligibility.eligible is False
    assert eligibility.reason == PV_FAULT_READ_ONLY_CODE
    assert not (tmp_path / "switch_log.json").exists()


def test_load_forecast_upsert_and_switch_still_work(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.register_challenger("legacy_day", _model("data/models/legacy.pkl", "e1", 0.71))
    store = _store(tmp_path, registry)
    log = SwitchEventLog(log_path=tmp_path / "switch_log.json")
    engine = SwitchDecisionEngine(
        slot_store=store,
        event_log=log,
        now=lambda: datetime(2026, 8, 17, 12, 0, 0),
    )

    store.upsert(_load_forecast_slot())
    event = engine.execute_switch(
        slot="load_forecast",
        target_workflow_id="wf-shadow",
        trigger_type="manual",
        reason="regression",
        force=True,
    )
    assert event.slot == "load_forecast"
    assert event.to_workflow_id == "wf-shadow"

    persisted = json.loads((tmp_path / "slots.json").read_text(encoding="utf-8"))
    assert "load_forecast" in persisted
    assert persisted["load_forecast"]["production_model"]["workflow_id"] == "wf-shadow"
    assert "pv_fault" not in persisted or persisted.get("pv_fault", {}).get("production_model") is None

    overlay = store.get("pv_fault")
    assert overlay is not None
    assert overlay.production_model is None
    reloaded = json.loads((tmp_path / "slots.json").read_text(encoding="utf-8"))
    assert "pv_fault" not in reloaded
# @AI_GENERATED: end
