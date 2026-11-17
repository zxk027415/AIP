# @AI_GENERATED
# -*- coding: utf-8 -*-
"""跨路径切换协调器：同路径 note、九项拒绝无副作用、成功只写 PathSwitchEvent。"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from services.iterative_labeling.pv_governance_events import (
    PathSwitchEventStore,
    PromotionEventStore,
)
from services.iterative_labeling.pv_model_registry import ModelRegistration, PVModelRegistry
from services.scheduler.pv_dual_path.cross_path_switch_coordinator import (
    CrossPathSwitchCoordinator,
    PathSwitchRequest,
)
from services.scheduler.pv_dual_path.path_activation import (
    ActivationPreview,
    DeviceActivationScope,
    DeviceScope,
    LaneClaimSpec,
)
from services.scheduler.pv_dual_path.shadow_compare import (
    CrossPathShadowReport,
    ShadowReportStore,
)


class _FakeEpoch:
    activation_epoch_id = "epoch-switched"


class _FakeActivation:
    def __init__(self) -> None:
        self.created = 0
        self.deleted: list[str] = []

    def preview(self, request):
        scope = request.devices[0].scope
        item = DeviceActivationScope(
            scope=scope,
            activation_watermark=None,
            effective_from_date=date(2026, 1, 1),
            production_cutover_date=date(2026, 1, 1),
            claims=(LaneClaimSpec(scope, "production", date(2026, 1, 1), None),),
        )
        return ActivationPreview(
            slot=request.slot,
            modeling_path=request.modeling_path,
            activation_mode=request.activation_mode,
            backfill_days=request.backfill_days,
            device_scopes=(item,),
            claims=item.claims,
            effective_from_date=date(2026, 1, 1),
            device_scope_digest="digest",
            device_scope_count=1,
        )

    def create_epoch(self, request):
        self.created += 1
        return _FakeEpoch()

    def delete_epoch(self, epoch_id: str) -> None:
        self.deleted.append(epoch_id)


def _seed(registry: PVModelRegistry) -> None:
    registry.register_challenger(
        "legacy_day",
        ModelRegistration("data/models/legacy.pkl", "el", 0.8, "2026-01-01T00:00:00"),
    )
    registry.promote_within_path("legacy_day", "el")
    registry.register_challenger(
        "seq_annotation",
        ModelRegistration("data/models/seq", "es", 0.9, "2026-01-01T00:00:00"),
    )
    registry.promote_within_path("seq_annotation", "es")


def _report(store: ShadowReportStore, registry: PVModelRegistry) -> str:
    state = registry.get_slot()
    legacy = state.path_models["legacy_day"].champion
    seq = state.path_models["seq_annotation"].champion
    report = CrossPathShadowReport(
        comparison_id="cmp-1",
        legacy_model_ref=str(legacy.model_ref if legacy else ""),
        seq_model_ref=str(seq.model_ref if seq else ""),
        device_day_total=250,
        comparable_total=250,
        agreement_rate=0.9,
        coverage_rate=0.95,
        generated_at=datetime.utcnow().isoformat(),
        common_metrics={"agreement_rate": 0.9},
        seq_native_metrics={"legacy_counterpart": None},
        runtime_metrics={"blocking_count": 0},
        uncomparable_items=[],
    )
    store.save(report)
    return report.comparison_id


def test_same_path_put_only_updates_note(tmp_path: Path) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    _seed(registry)
    coordinator = CrossPathSwitchCoordinator(registry=registry, activation=_FakeActivation())
    before = registry.get_slot()
    result = coordinator.apply(
        PathSwitchRequest(modeling_path="legacy_day", note="ops note")
    )
    after = registry.get_slot()
    assert result.status == "same_path_updated"
    assert after.note == "ops note"
    assert after.production_path == before.production_path
    assert after.active_activation_epoch_id == before.active_activation_epoch_id
    assert PathSwitchEventStore(tmp_path / "events").list_recent() == []
    assert PromotionEventStore(tmp_path / "events").list_recent()


def test_gate_failure_has_no_side_effects(tmp_path: Path) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    _seed(registry)
    activation = _FakeActivation()
    coordinator = CrossPathSwitchCoordinator(registry=registry, activation=activation)
    before = registry.get_slot().to_dict()
    result = coordinator.apply(
        PathSwitchRequest(
            modeling_path="seq_annotation",
            activation_mode="cutover_only",
            confirm=True,
            comparison_id="missing",
            device_scope=[{"site_id": "s", "device_id": "d", "branch_id": "b"}],
            operator="op",
            reason="try",
        )
    )
    assert result.status == "rejected"
    assert result.changed is False
    assert activation.created == 0
    assert registry.get_slot().to_dict()["production_path"] == before["production_path"]
    assert PathSwitchEventStore(tmp_path / "events").list_recent() == []


def test_successful_switch_writes_only_path_switch_event(tmp_path: Path) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    _seed(registry)
    store = ShadowReportStore(tmp_path / "shadow")
    comparison_id = _report(store, registry)
    activation = _FakeActivation()
    coordinator = CrossPathSwitchCoordinator(
        registry=registry,
        activation=activation,
        report_store=store,
        artifact_validator=lambda _ref: True,
        contract_validator=lambda _ref: True,
    )
    promotion_before = len(PromotionEventStore(tmp_path / "events").list_recent(limit=1000))
    result = coordinator.apply(
        PathSwitchRequest(
            modeling_path="seq_annotation",
            comparison_id=comparison_id,
            activation_mode="cutover_only",
            confirm=True,
            operator="op",
            reason="shadow ok",
            device_scope=[{"site_id": "s", "device_id": "d", "branch_id": "b"}],
        )
    )
    assert result.status == "switched"
    assert result.event is not None
    after = registry.get_slot()
    assert after.production_path == "seq_annotation"
    assert after.active_activation_epoch_id == "epoch-switched"
    assert activation.created == 1
    assert len(PathSwitchEventStore(tmp_path / "events").list_recent()) == 1
    assert len(PromotionEventStore(tmp_path / "events").list_recent(limit=1000)) == promotion_before


def test_event_failure_rolls_back_registry_and_epoch(tmp_path: Path) -> None:
    class _FailingStore:
        def append(self, _event):
            raise OSError("event write failed")

    registry = PVModelRegistry(
        tmp_path / "registry",
        events_base_dir=tmp_path / "events",
        path_switch_store_factory=lambda _slot: _FailingStore(),  # type: ignore[arg-type]
    )
    _seed(registry)
    store = ShadowReportStore(tmp_path / "shadow")
    comparison_id = _report(store, registry)
    activation = _FakeActivation()
    coordinator = CrossPathSwitchCoordinator(
        registry=registry,
        activation=activation,
        report_store=store,
        artifact_validator=lambda _ref: True,
        contract_validator=lambda _ref: True,
    )
    before = registry.get_slot()
    with pytest.raises(OSError):
        coordinator.apply(
            PathSwitchRequest(
                modeling_path="seq_annotation",
                comparison_id=comparison_id,
                activation_mode="cutover_only",
                confirm=True,
                operator="op",
                reason="shadow ok",
                device_scope=[{"site_id": "s", "device_id": "d", "branch_id": "b"}],
            )
        )
    after = registry.get_slot()
    assert after.production_path == before.production_path
    assert after.active_activation_epoch_id == before.active_activation_epoch_id
    assert activation.deleted == ["epoch-switched"]


def test_fallback_still_requires_gate(tmp_path: Path) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    _seed(registry)
    coordinator = CrossPathSwitchCoordinator(registry=registry, activation=_FakeActivation())
    result = coordinator.apply(
        PathSwitchRequest(
            modeling_path="seq_annotation",
            is_fallback=True,
            confirm=True,
            activation_mode="cutover_only",
            device_scope=[{"site_id": "s", "device_id": "d", "branch_id": "b"}],
        )
    )
    assert result.status == "rejected"
    assert registry.get_slot().production_path == "legacy_day"


def test_simple_switch_flips_path_without_shadow_or_epoch(tmp_path: Path) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    _seed(registry)
    activation = _FakeActivation()
    coordinator = CrossPathSwitchCoordinator(registry=registry, activation=activation)
    result = coordinator.apply(
        PathSwitchRequest(
            modeling_path="seq_annotation",
            switch_mode="simple",
            confirm=True,
        )
    )
    assert result.status == "switched"
    assert result.reason == "lab_unbounded_simple_switch"
    assert activation.created == 0
    after = registry.get_slot()
    assert after.production_path == "seq_annotation"
    assert after.active_activation_epoch_id == "lab-unbounded"
    assert PathSwitchEventStore(tmp_path / "events").list_recent()[0].to_path == "seq_annotation"


def test_simple_switch_rejects_without_champion(tmp_path: Path) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    registry.register_challenger(
        "legacy_day",
        ModelRegistration("data/models/legacy.pkl", "el", 0.8, "2026-01-01T00:00:00"),
    )
    registry.promote_within_path("legacy_day", "el")
    coordinator = CrossPathSwitchCoordinator(registry=registry, activation=_FakeActivation())
    before = registry.get_slot().production_path
    result = coordinator.apply(
        PathSwitchRequest(
            modeling_path="seq_annotation",
            switch_mode="simple",
            confirm=True,
        )
    )
    assert result.status == "rejected"
    assert registry.get_slot().production_path == before
# @AI_GENERATED: end
