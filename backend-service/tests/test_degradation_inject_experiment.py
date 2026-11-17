# @AI_GENERATED
"""劣化注入实验：activate → inject → alert → restore。"""
from __future__ import annotations

import json

import pytest

from services.accuracy_operations.degradation_experiment import (
    activate_slot_metrics_from_deployment,
    get_degradation_status,
    inject_degradation,
    restore_degradation,
)
from services.accuracy_operations.models import (
    AccuracyAlert,
    AlertSeverity,
    AlertStatus,
    DegradationTrend,
    ModelForm,
)
from services.accuracy_operations.store import AccuracyOperationsStore
from services.deployment.models import DeploymentSlot, ModelVersion
from services.precision_ops.accuracy_tracker import AccuracyTracker


class _FakeSlotStore:
    def __init__(self, slot: DeploymentSlot):
        self._slot = slot

    def get(self, name: str):
        return self._slot if name == self._slot.slot else None


class _FakeMonitor:
    def __init__(self, store: AccuracyOperationsStore, tracker: AccuracyTracker, slot_obj: DeploymentSlot):
        self._store = store
        self._tracker = tracker
        self._slot = slot_obj

    def evaluate(self, slot: str):
        prod = self._slot.production_model
        metrics = self._tracker.get_rolling_metrics(slot, prod.workflow_id, prod.version_tag)
        baseline = float(prod.baseline_mape)
        current = float(metrics["rolling_mape"])
        degradation_pct = (current - baseline) / baseline * 100
        if degradation_pct < 15:
            return []
        alert = AccuracyAlert(
            alert_id="alert-test0001",
            slot=slot,
            model_form=ModelForm.production,
            workflow_id=prod.workflow_id,
            version_tag=prod.version_tag,
            baseline_mape=baseline,
            current_rolling_mape=current,
            metric_name="mape",
            baseline_metric=baseline,
            current_metric=current,
            degradation_pct=degradation_pct,
            degradation_trend=DegradationTrend.sudden,
            severity=AlertSeverity.warning,
            status=AlertStatus.open,
        )
        self._store.save_alert(slot, alert)
        return [alert]


@pytest.fixture()
def slot_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "precision_ops"
    monkeypatch.setattr("services.precision_ops.utils.BASE_DATA_DIR", data_dir)
    monkeypatch.setattr("services.accuracy_operations.degradation_experiment.BASE_DATA_DIR", data_dir)
    monkeypatch.setattr("services.accuracy_operations.store.BASE_DATA_DIR", data_dir)
    monkeypatch.setattr("services.precision_ops.accuracy_tracker.BASE_DATA_DIR", data_dir)

    slot = DeploymentSlot(
        slot="load_forecast",
        production_model=ModelVersion(
            workflow_id="wf-prod",
            version_tag="prod-v1",
            status="production",
            deployed_at="2026-07-23T00:00:00+00:00",
            baseline_mape=5.0,
            accuracy_score=5.0,
        ),
        shadow_models=[
            ModelVersion(
                workflow_id="wf-prod",
                version_tag="shadow-v1",
                status="shadow",
                deployed_at="2026-07-23T00:00:00+00:00",
                baseline_mape=4.0,
                accuracy_score=4.0,
            )
        ],
        updated_at="2026-07-23T00:00:00+00:00",
    )
    tracker = AccuracyTracker()
    store = AccuracyOperationsStore()
    slot_store = _FakeSlotStore(slot)
    monitor = _FakeMonitor(store, tracker, slot)
    return {
        "slot": "load_forecast",
        "tracker": tracker,
        "store": store,
        "slot_store": slot_store,
        "monitor": monitor,
        "data_dir": data_dir,
    }


def test_inject_restore_creates_and_clears_alert(slot_env):
    slot = slot_env["slot"]
    tracker = slot_env["tracker"]
    store = slot_env["store"]
    slot_store = slot_env["slot_store"]
    monitor = slot_env["monitor"]

    activated = activate_slot_metrics_from_deployment(
        slot=slot, tracker=tracker, slot_store=slot_store, min_valid_cycles=3
    )
    assert activated["count"] == 2
    metrics = tracker.get_rolling_metrics(slot, "wf-prod", "prod-v1")
    assert metrics["status"] == "active"
    assert metrics["valid_cycle_count"] >= 3

    injected = inject_degradation(
        slot=slot,
        tracker=tracker,
        monitor=monitor,
        slot_store=slot_store,
        target_degradation_pct=20.0,
        mode="metric_rewrite",
        note="unit-test",
    )
    assert injected["injected"] is True
    assert injected["degradation_pct"] >= 20.0 - 1e-6
    assert len(injected["alerts_created"]) == 1

    status = get_degradation_status(slot, tracker, slot_store)
    assert status["injected"] is True

    restored = restore_degradation(slot=slot, tracker=tracker, store=store, close_open_alerts=True)
    assert restored["restored"] is True
    metrics_after = tracker.get_rolling_metrics(slot, "wf-prod", "prod-v1")
    assert abs(float(metrics_after["rolling_mape"]) - 5.0) < 1e-6

    status2 = get_degradation_status(slot, tracker, slot_store)
    assert status2["injected"] is False

    snap_path = slot_env["data_dir"] / slot / "accuracy_ops" / "experiments" / "degradation_inject_snapshot.json"
    assert snap_path.exists()
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    assert snap["active"] is False


def test_inject_rejects_double_inject(slot_env):
    slot = slot_env["slot"]
    tracker = slot_env["tracker"]
    slot_store = slot_env["slot_store"]
    monitor = slot_env["monitor"]
    activate_slot_metrics_from_deployment(slot=slot, tracker=tracker, slot_store=slot_store)
    inject_degradation(
        slot=slot,
        tracker=tracker,
        monitor=monitor,
        slot_store=slot_store,
        target_degradation_pct=20,
        mode="metric_rewrite",
    )
    with pytest.raises(ValueError, match="未恢复"):
        inject_degradation(
            slot=slot,
            tracker=tracker,
            monitor=monitor,
            slot_store=slot_store,
            target_degradation_pct=25,
            mode="metric_rewrite",
        )
# @AI_GENERATED: end
