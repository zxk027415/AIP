# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Property 15、16、36、40：覆盖写拒绝、九项原子门控与双事件分离。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from services.iterative_labeling.pv_governance_events import (
    PathSwitchEventStore,
    PromotionEventStore,
)
from services.iterative_labeling.pv_model_registry import ModelRegistration, PVModelRegistry
from services.scheduler.pv_dual_path.cross_path_switch_coordinator import (
    CrossPathSwitchCoordinator,
    PathSwitchRequest,
)
from services.scheduler.pv_dual_path.cross_path_switch_gate import CrossPathSwitchGate
from services.scheduler.pv_dual_path.path_activation import (
    ActivationPreview,
    DeviceActivationScope,
    DeviceScope,
    LaneClaimSpec,
)
from services.scheduler.pv_dual_path.shadow_compare import CrossPathShadowReport, ShadowReportStore


class _FakeEpoch:
    activation_epoch_id = "epoch-switched"


class _FakeActivation:
    def __init__(self) -> None:
        self.created = 0

    def preview(self, request):
        scope = request.devices[0].scope
        item = DeviceActivationScope(
            scope=scope,
            activation_watermark=None,
            effective_from_date=datetime.utcnow().date(),
            production_cutover_date=datetime.utcnow().date(),
            claims=(LaneClaimSpec(scope, "production", datetime.utcnow().date(), None),),
        )
        return ActivationPreview(
            slot=request.slot,
            modeling_path=request.modeling_path,
            activation_mode=request.activation_mode,
            backfill_days=request.backfill_days,
            device_scopes=(item,),
            claims=item.claims,
            effective_from_date=item.effective_from_date,
            device_scope_digest="digest",
            device_scope_count=1,
        )

    def create_epoch(self, request):
        self.created += 1
        return _FakeEpoch()

    def delete_epoch(self, epoch_id: str) -> None:
        del epoch_id


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


def _valid_report() -> dict:
    return {
        "legacy_model_ref": "models/legacy-v1.pkl",
        "seq_model_ref": "models/seq-v1",
        "comparable_total": 250,
        "coverage_rate": 0.95,
        "uncomparable_items": [],
        "generated_at": datetime.utcnow().isoformat(),
        "common_metrics": {"agreement_rate": 0.8},
        "seq_native_metrics": {"legacy_counterpart": None},
        "runtime_metrics": {"blocking_count": 0},
    }


def _scope() -> List[Dict[str, Any]]:
    return [{
        "site_id": "s1",
        "device_id": "d1",
        "branch_id": "1",
        "effective_from_date": "2026-01-05",
        "lane": "production",
        "range_start": "2026-01-05",
        "range_end": "",
    }]


# Feature: pv-fault-dual-path-serving, Property 15: 切换覆盖写与非法拒绝
@given(
    note=st.text(min_size=0, max_size=40),
    illegal=st.sampled_from(["", "other_path", "legacy"]),
    too_long=st.booleans(),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_15_legal_update_or_reject(tmp_path: Path, note: str, illegal: str, too_long: bool) -> None:
    root = tmp_path / uuid.uuid4().hex
    registry = PVModelRegistry(root / "registry", events_base_dir=root / "events")
    _seed(registry)
    coordinator = CrossPathSwitchCoordinator(registry=registry, activation=_FakeActivation())
    production_before = registry.get_slot().production_path
    if too_long:
        with pytest.raises(ValueError):
            coordinator.apply(PathSwitchRequest(modeling_path="legacy_day", note="x" * 501))
        assert registry.get_slot().production_path == production_before
        return
    with pytest.raises(ValueError):
        coordinator.apply(PathSwitchRequest(modeling_path=illegal, note=note))
    assert registry.get_slot().production_path == production_before
    result = coordinator.apply(PathSwitchRequest(modeling_path="legacy_day", note=note or None))
    assert result.status == "same_path_updated"
    assert registry.get_slot().production_path == "legacy_day"


# Feature: pv-fault-dual-path-serving, Property 36: 九项跨路径准入全真且原子
@given(flags=st.lists(st.booleans(), min_size=9, max_size=9))
@settings(max_examples=100, deadline=None)
def test_property_36_all_nine_must_pass(flags: List[bool]) -> None:
    report = _valid_report()
    confirm: Any = True
    mode = "cutover_only"
    scope = _scope()
    artifact_ok = True
    contract_ok = True
    if not flags[0]:
        artifact_ok = False
    if not flags[1]:
        contract_ok = False
    if not flags[2]:
        report["seq_model_ref"] = "models/other"
    if not flags[3]:
        report["generated_at"] = "2020-01-01T00:00:00"
    if not flags[4]:
        report["comparable_total"] = 1
        report["coverage_rate"] = 0.1
    if not flags[5]:
        report["uncomparable_items"] = [{"severity": "blocking"}]
    if not flags[6]:
        mode = "not_a_mode"
    if not flags[7]:
        scope = [{"site_id": "s1", "device_id": "d1", "branch_id": "1"}]
    if not flags[8]:
        confirm = "true"
    gate = CrossPathSwitchGate(
        artifact_validator=lambda _: artifact_ok,
        contract_validator=lambda _: contract_ok,
    )
    result = gate.evaluate(
        target_champion_model_ref="models/seq-v1",
        report=report,
        current_legacy_champion_ref="models/legacy-v1.pkl",
        current_seq_champion_ref="models/seq-v1",
        activation_mode=mode,
        device_scope=scope,
        confirm=confirm,
        now=datetime(2026, 1, 12),
    )
    assert result.all_passed is all(flags)
    assert len(result.conditions) == 9
    if not result.all_passed:
        assert result.failed_conditions


# Feature: pv-fault-dual-path-serving, Property 16 + 40: 路径切换审计只追加且与晋升分离
@given(reason=st.text(alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=1, max_size=12))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_16_and_40_events_append_only_and_separated(tmp_path: Path, reason: str) -> None:
    root = tmp_path / uuid.uuid4().hex
    registry = PVModelRegistry(root / "registry", events_base_dir=root / "events")
    _seed(registry)
    store = ShadowReportStore(root / "shadow")
    state = registry.get_slot()
    report = CrossPathShadowReport(
        comparison_id=f"cmp-{reason}",
        legacy_model_ref=str(state.path_models["legacy_day"].champion.model_ref),
        seq_model_ref=str(state.path_models["seq_annotation"].champion.model_ref),
        device_day_total=250,
        comparable_total=250,
        agreement_rate=0.9,
        coverage_rate=0.95,
        generated_at=datetime.utcnow().isoformat(),
        common_metrics={"agreement_rate": 0.9},
        seq_native_metrics={"legacy_counterpart": None},
        runtime_metrics={"blocking_count": 0},
    )
    store.save(report)
    promotion_before = len(PromotionEventStore(root / "events").list_recent(limit=1000))
    switch_before = len(PathSwitchEventStore(root / "events").list_recent(limit=1000))
    coordinator = CrossPathSwitchCoordinator(
        registry=registry,
        activation=_FakeActivation(),
        report_store=store,
        artifact_validator=lambda _ref: True,
        contract_validator=lambda _ref: True,
    )
    result = coordinator.apply(
        PathSwitchRequest(
            modeling_path="seq_annotation",
            comparison_id=report.comparison_id,
            activation_mode="cutover_only",
            confirm=True,
            operator="op",
            reason=reason,
            device_scope=[{"site_id": "s", "device_id": "d", "branch_id": "b"}],
        )
    )
    assert result.status == "switched"
    promotion_after = PromotionEventStore(root / "events").list_recent(limit=1000)
    switch_after = PathSwitchEventStore(root / "events").list_recent(limit=1000)
    assert len(switch_after) == switch_before + 1
    assert len(promotion_after) == promotion_before
    assert all(hasattr(item, "path_switch_event_id") for item in switch_after)
    assert all(hasattr(item, "promotion_event_id") for item in promotion_after)
# @AI_GENERATED: end
