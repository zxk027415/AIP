# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Property 17–19、38–39：Shadow 每路一结果、一致率、只读与三层证据。"""
from __future__ import annotations

import copy
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from services.iterative_labeling.pv_model_registry import (
    ModelRegistration,
    PathModelState,
    PVModelRegistry,
    PVSlotState,
)
from services.scheduler.pv_dual_path.cross_path_switch_gate import CrossPathSwitchGate
from services.scheduler.pv_dual_path.shadow_compare import (
    ShadowCompareRunner,
    ShadowReportStore,
)


def _ok_loader(model_ref: str) -> Dict[str, Any]:
    return {"loaded": True, "model_ref": model_ref}


def _registry(tmp_path: Path) -> PVModelRegistry:
    root = tmp_path / uuid.uuid4().hex
    registry = PVModelRegistry(base_dir=root / "registry", events_base_dir=root / "events")
    state = PVSlotState(
        production_path="legacy_day",
        fallback_path="seq_annotation",
        path_models={
            "legacy_day": PathModelState(
                champion=ModelRegistration("models/legacy.pkl", "el", 0.8, "2026-01-01T00:00:00")
            ),
            "seq_annotation": PathModelState(
                champion=ModelRegistration("models/seq", "es", 0.9, "2026-01-01T00:00:00")
            ),
        },
    )
    registry._save_slot("pv_fault", state)
    return registry


def _item(day: date, label: int, *, error: str | None = None, points: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "site_id": "s1",
        "device_id": "d1",
        "branch_id": "1",
        "business_date": day,
        "predicted_label": label,
        "latency_ms": 10,
    }
    if error:
        payload["error"] = error
    if points:
        payload["point_predictions"] = [{"label": label}] * 288
    return payload


_day_counts = st.integers(min_value=1, max_value=6)
_labels = st.integers(min_value=0, max_value=3)


# Feature: pv-fault-dual-path-serving, Property 17: 对比每设备日每路各一结果
@given(n=_day_counts, seed_label=_labels)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_17_each_device_day_has_one_result_per_path(tmp_path: Path, n: int, seed_label: int) -> None:
    start = date(2026, 1, 1)
    days = [start + timedelta(days=i) for i in range(n)]

    def legacy_reader(**kwargs: Any) -> List[Dict[str, Any]]:
        return [_item(day, seed_label) for day in days]

    def seq_reader(**kwargs: Any) -> List[Dict[str, Any]]:
        return [_item(day, seed_label, points=True) for day in days]

    runner = ShadowCompareRunner(
        model_registry=_registry(tmp_path),
        legacy_champion_reader=legacy_reader,
        seq_champion_reader=seq_reader,
        report_store=ShadowReportStore(base_dir=tmp_path / uuid.uuid4().hex / "shadow", slot="pv_fault"),
        artifact_loader=_ok_loader,
    )
    report = runner.run_compare(start, days[-1])
    assert report.device_day_total == n
    assert report.comparable_total == n
    keys = {(item["site_id"], item["device_id"], item["branch_id"], item["business_date"]) for item in report.diff_items}
    assert len(keys) == len(report.diff_items)


# Feature: pv-fault-dual-path-serving, Property 18: 一致率与差异划分正确
@given(
    agree=st.integers(min_value=0, max_value=4),
    differ=st.integers(min_value=0, max_value=4),
    missing=st.integers(min_value=0, max_value=3),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_18_agreement_and_partition(tmp_path: Path, agree: int, differ: int, missing: int) -> None:
    start = date(2026, 2, 1)
    offset = 0
    legacy_items: List[Dict[str, Any]] = []
    seq_items: List[Dict[str, Any]] = []
    for _ in range(agree):
        day = start + timedelta(days=offset)
        offset += 1
        legacy_items.append(_item(day, 1))
        seq_items.append(_item(day, 1, points=True))
    for _ in range(differ):
        day = start + timedelta(days=offset)
        offset += 1
        legacy_items.append(_item(day, 0))
        seq_items.append(_item(day, 2, points=True))
    for _ in range(missing):
        day = start + timedelta(days=offset)
        offset += 1
        seq_items.append(_item(day, 1, points=True))
    if offset == 0:
        return

    runner = ShadowCompareRunner(
        model_registry=_registry(tmp_path),
        legacy_champion_reader=lambda **_: legacy_items,
        seq_champion_reader=lambda **_: seq_items,
        report_store=ShadowReportStore(base_dir=tmp_path / uuid.uuid4().hex / "shadow", slot="pv_fault"),
        artifact_loader=_ok_loader,
    )
    report = runner.run_compare(start, start + timedelta(days=offset - 1))
    comparable = agree + differ
    assert report.comparable_total == comparable
    expected_rate = (agree / comparable) if comparable else 0.0
    assert abs(report.agreement_rate - round(expected_rate, 6)) < 1e-9
    assert len(report.diff_items) == differ
    assert len(report.uncomparable_items) == missing
    diff_dates = {item["business_date"] for item in report.diff_items}
    uncomp_dates = {item["business_date"] for item in report.uncomparable_items}
    assert diff_dates.isdisjoint(uncomp_dates)
    assert report.device_day_total == comparable + missing


# Feature: pv-fault-dual-path-serving, Property 19: Shadow 不污染生产检测事实
@given(label=_labels)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_19_shadow_does_not_mutate_production(tmp_path: Path, label: int) -> None:
    registry = _registry(tmp_path)
    external = {"cursor": "2026-01-01", "ledger": ["ready"], "epoch": "e1"}
    snapshot = {"external": copy.deepcopy(external)}

    def snapshot_fn() -> Dict[str, Any]:
        return external

    runner = ShadowCompareRunner(
        model_registry=registry,
        legacy_champion_reader=lambda **_: [_item(date(2026, 1, 1), label)],
        seq_champion_reader=lambda **_: [_item(date(2026, 1, 1), label, points=True)],
        report_store=ShadowReportStore(base_dir=tmp_path / uuid.uuid4().hex / "shadow", slot="pv_fault"),
        artifact_loader=_ok_loader,
        production_snapshot_fn=snapshot_fn,
    )
    before = registry.get_slot().to_dict()
    before.pop("updated_at", None)
    runner.run_compare(date(2026, 1, 1), date(2026, 1, 1))
    after = registry.get_slot().to_dict()
    after.pop("updated_at", None)
    assert after == before
    assert external == snapshot["external"]


# Feature: pv-fault-dual-path-serving, Property 38: Shadow 只使用双 Champion 且完全只读
@given(drop=st.sampled_from(["legacy_day", "seq_annotation", "none"]))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_38_requires_dual_champions_and_stays_readonly(tmp_path: Path, drop: str) -> None:
    registry = PVModelRegistry(base_dir=tmp_path / uuid.uuid4().hex / "registry", events_base_dir=tmp_path / uuid.uuid4().hex / "events")
    path_models = {}
    if drop != "legacy_day":
        path_models["legacy_day"] = PathModelState(
            champion=ModelRegistration("models/legacy.pkl", "el", 0.8, "2026-01-01T00:00:00")
        )
    if drop != "seq_annotation":
        path_models["seq_annotation"] = PathModelState(
            champion=ModelRegistration("models/seq", "es", 0.9, "2026-01-01T00:00:00")
        )
    registry._save_slot("pv_fault", PVSlotState(production_path="legacy_day", fallback_path="seq_annotation", path_models=path_models))
    loaded: List[str] = []
    runner = ShadowCompareRunner(
        model_registry=registry,
        legacy_champion_reader=lambda **kw: [_item(date(2026, 1, 1), 0)],
        seq_champion_reader=lambda **kw: [_item(date(2026, 1, 1), 0, points=True)],
        report_store=ShadowReportStore(base_dir=tmp_path / uuid.uuid4().hex / "shadow", slot="pv_fault"),
        artifact_loader=lambda ref: loaded.append(ref) or _ok_loader(ref),
    )
    before = registry.get_slot().to_dict()
    before.pop("updated_at", None)
    if drop != "none":
        try:
            runner.run_compare(date(2026, 1, 1), date(2026, 1, 1))
            raise AssertionError("missing champion must reject")
        except ValueError:
            pass
        after = registry.get_slot().to_dict()
        after.pop("updated_at", None)
        assert after == before
        return
    report = runner.run_compare(date(2026, 1, 1), date(2026, 1, 1))
    assert set(loaded) == {"models/legacy.pkl", "models/seq"}
    assert report.legacy_model_ref == "models/legacy.pkl"
    assert report.seq_model_ref == "models/seq"
    after = registry.get_slot().to_dict()
    after.pop("updated_at", None)
    assert after == before


# Feature: pv-fault-dual-path-serving, Property 39: Shadow 三层证据完整且口径不伪造
@given(label=_labels)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_39_three_layers_and_no_forged_seq_cross(tmp_path: Path, label: int) -> None:
    runner = ShadowCompareRunner(
        model_registry=_registry(tmp_path),
        legacy_champion_reader=lambda **_: [_item(date(2026, 1, 1), label)],
        seq_champion_reader=lambda **_: [_item(date(2026, 1, 1), label, points=True)],
        report_store=ShadowReportStore(base_dir=tmp_path / uuid.uuid4().hex / "shadow", slot="pv_fault"),
        artifact_loader=_ok_loader,
    )
    report = runner.run_compare(date(2026, 1, 1), date(2026, 1, 1))
    payload = report.to_dict()
    assert payload["common_metrics"]
    assert payload["seq_native_metrics"]
    assert payload["runtime_metrics"]
    assert payload["seq_native_metrics"]["cross_path_conclusion"] is None
    gate = CrossPathSwitchGate(artifact_validator=lambda _: True, contract_validator=lambda _: True)
    missing = dict(payload)
    missing["common_metrics"] = {}
    failed = gate.evaluate(
        target_champion_model_ref=report.seq_model_ref,
        report=missing,
        current_legacy_champion_ref=report.legacy_model_ref,
        current_seq_champion_ref=report.seq_model_ref,
        activation_mode="cutover_only",
        device_scope=[{
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "1",
            "effective_from_date": "2026-01-01",
        }],
        confirm=True,
    )
    assert failed.all_passed is False
    assert any("evidence_layers_incomplete" in (c.reason or "") for c in failed.failed_conditions)
# @AI_GENERATED: end
