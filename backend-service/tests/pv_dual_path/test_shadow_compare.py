# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Shadow 双 Champion 对比的只读三层证据和生产快照保护测试。"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from services.iterative_labeling.pv_governance_events import (
    PathSwitchEvent,
    PathSwitchEventStore,
    PromotionEvent,
    PromotionEventStore,
)
from services.iterative_labeling.pv_model_registry import (
    ModelRegistration,
    PathModelState,
    PVModelRegistry,
    PVSlotState,
)
from services.scheduler.pv_dual_path.shadow_compare import (
    CrossPathShadowReport,
    SEQ_PROJECTION_RULE_ID,
    ShadowCompareRunner,
    ShadowReportStore,
)


def _ok_loader(model_ref: str) -> Dict[str, Any]:
    return {"loaded": True, "model_ref": model_ref}


def _make_registry_with_champions(tmp_path: Path) -> PVModelRegistry:
    """构造一个包含双路径 Champion 的临时 Registry。"""
    registry = PVModelRegistry(
        base_dir=tmp_path / "registry",
        events_base_dir=tmp_path / "events",
    )
    legacy_reg = ModelRegistration(
        model_ref="models/legacy-champion.pkl",
        evaluation_id="eval-legacy-1",
        gate_metric_value=0.85,
        registered_at="2026-01-01T00:00:00",
        metric_name="macro_f1_mean",
    )
    seq_reg = ModelRegistration(
        model_ref="models/seq-champion",
        evaluation_id="eval-seq-1",
        gate_metric_value=0.90,
        registered_at="2026-01-01T00:00:00",
        metric_name="point_macro_f1",
    )
    state = PVSlotState(
        production_path="legacy_day",
        fallback_path="seq_annotation",
        path_models={
            "legacy_day": PathModelState(champion=legacy_reg),
            "seq_annotation": PathModelState(champion=seq_reg),
        },
    )
    registry._save_slot("pv_fault", state)
    return registry


def _fake_legacy_reader(
    *,
    model_ref: str,
    start_date: date,
    end_date: date,
    device_scope: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    return [
        {
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "1",
            "business_date": start_date,
            "predicted_label": 0,
            "latency_ms": 50,
        },
        {
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "1",
            "business_date": start_date.replace(day=start_date.day + 1),
            "predicted_label": 1,
            "latency_ms": 60,
        },
    ]


def _fake_seq_reader(
    *,
    model_ref: str,
    start_date: date,
    end_date: date,
    device_scope: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    return [
        {
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "1",
            "business_date": start_date,
            "predicted_label": 0,
            "point_predictions": [{"label": 0}] * 288,
            "latency_ms": 120,
        },
        {
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": "1",
            "business_date": start_date.replace(day=start_date.day + 1),
            "predicted_label": 2,
            "point_predictions": [{"label": 2}] * 288,
            "latency_ms": 130,
        },
    ]


def _runner(tmp_path: Path, **kwargs: Any) -> ShadowCompareRunner:
    registry = kwargs.pop("registry", None) or _make_registry_with_champions(tmp_path)
    store = kwargs.pop("store", None) or ShadowReportStore(base_dir=tmp_path / "shadow", slot="pv_fault")
    return ShadowCompareRunner(
        model_registry=registry,
        legacy_champion_reader=kwargs.pop("legacy_champion_reader", _fake_legacy_reader),
        seq_champion_reader=kwargs.pop("seq_champion_reader", _fake_seq_reader),
        report_store=store,
        slot="pv_fault",
        artifact_loader=kwargs.pop("artifact_loader", _ok_loader),
        **kwargs,
    )


def test_run_compare_resolves_dual_champions_and_produces_three_layer_report(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    report = runner.run_compare(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    assert isinstance(report, CrossPathShadowReport)
    assert report.legacy_model_ref == "models/legacy-champion.pkl"
    assert report.seq_model_ref == "models/seq-champion"
    assert report.device_day_total == 2
    assert report.comparable_total == 2
    assert report.agreement_rate == 0.5
    assert len(report.diff_items) == 1
    assert report.diff_items[0]["legacy_label"] == 1
    assert report.diff_items[0]["seq_label"] == 2
    assert report.coverage_rate == 1.0
    assert report.projection_rule == SEQ_PROJECTION_RULE_ID
    assert report.common_metrics["day_accuracy"] == 0.5
    assert report.common_metrics["fault_recall"] == 1.0
    assert report.common_metrics["confusion_counts"]["0->0"] == 1
    assert report.seq_native_metrics.get("legacy_counterpart") == "无 Legacy 对应值"
    assert report.seq_native_metrics["cross_path_conclusion"] is None
    assert report.seq_native_metrics["point_level_288_contract"] is True
    assert "legacy_day" in report.runtime_metrics
    assert "seq_annotation" in report.runtime_metrics
    assert report.runtime_metrics["legacy_day"]["daily_capacity"] == 1.0
    assert report.generated_at

    loaded = ShadowReportStore(base_dir=tmp_path / "shadow", slot="pv_fault").load(report.comparison_id)
    assert loaded is not None
    assert loaded.comparison_id == report.comparison_id


def test_run_compare_rejects_missing_champion(tmp_path: Path) -> None:
    registry = PVModelRegistry(
        base_dir=tmp_path / "registry",
        events_base_dir=tmp_path / "events",
    )
    runner = ShadowCompareRunner(
        model_registry=registry,
        slot="pv_fault",
        artifact_loader=_ok_loader,
    )
    with pytest.raises(ValueError, match="legacy_day.*无合格 Champion"):
        runner.run_compare(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))


def test_run_compare_rejects_unloadable_champion(tmp_path: Path) -> None:
    def _fail_seq(model_ref: str) -> Dict[str, Any]:
        if "seq" in model_ref:
            raise OSError("missing artifact")
        return _ok_loader(model_ref)

    runner = _runner(tmp_path, artifact_loader=_fail_seq)
    with pytest.raises(ValueError, match="seq_annotation Champion 工件不可加载"):
        runner.run_compare(date(2026, 1, 1), date(2026, 1, 2))


def test_run_compare_handles_uncomparable_items_with_severity(tmp_path: Path) -> None:
    def _legacy_with_error(**kwargs: Any) -> List[Dict[str, Any]]:
        return [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "1",
                "business_date": kwargs["start_date"],
                "predicted_label": 0,
                "error": "artifact_load_failed",
            },
        ]

    def _seq_ok(**kwargs: Any) -> List[Dict[str, Any]]:
        return [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "1",
                "business_date": kwargs["start_date"],
                "predicted_label": 0,
                "point_predictions": [{"label": 0}] * 288,
            },
        ]

    runner = _runner(
        tmp_path,
        legacy_champion_reader=_legacy_with_error,
        seq_champion_reader=_seq_ok,
    )
    report = runner.run_compare(date(2026, 1, 1), date(2026, 1, 1))
    assert report.comparable_total == 0
    assert len(report.uncomparable_items) == 1
    assert report.uncomparable_items[0]["severity"] == "blocking"
    assert report.runtime_metrics["blocking_count"] == 1


def test_missing_result_is_deferred_not_blocking(tmp_path: Path) -> None:
    def _legacy_one(**kwargs: Any) -> List[Dict[str, Any]]:
        return [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "1",
                "business_date": kwargs["start_date"],
                "predicted_label": 0,
            }
        ]

    def _seq_empty(**kwargs: Any) -> List[Dict[str, Any]]:
        return []

    runner = _runner(
        tmp_path,
        legacy_champion_reader=_legacy_one,
        seq_champion_reader=_seq_empty,
    )
    report = runner.run_compare(date(2026, 1, 1), date(2026, 1, 1))
    assert report.uncomparable_items[0]["severity"] == "deferred"
    assert report.uncomparable_items[0]["reason"] == "no_result"
    assert report.runtime_metrics["deferred_count"] == 1


def test_seq_native_metrics_use_point_labels_and_do_not_invent_legacy(tmp_path: Path) -> None:
    truth = [0] * 200 + [1] * 88
    pred = [0] * 196 + [1] * 92

    def _legacy(**kwargs: Any) -> List[Dict[str, Any]]:
        return [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "1",
                "business_date": kwargs["start_date"],
                "predicted_label": 1,
            }
        ]

    def _seq(**kwargs: Any) -> List[Dict[str, Any]]:
        return [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "1",
                "business_date": kwargs["start_date"],
                "point_predictions": [{"label": label} for label in pred],
                "point_labels": [{"label": label} for label in truth],
            }
        ]

    runner = _runner(tmp_path, legacy_champion_reader=_legacy, seq_champion_reader=_seq)
    report = runner.run_compare(date(2026, 1, 1), date(2026, 1, 1))
    assert report.seq_native_metrics["point_macro_f1"] is not None
    assert report.seq_native_metrics["fault_segment_iou"] is not None
    assert report.seq_native_metrics["legacy_counterpart"] == "无 Legacy 对应值"
    assert "seq_better_than_legacy" not in report.seq_native_metrics


def test_shadow_report_does_not_modify_registry_or_events(tmp_path: Path) -> None:
    registry = _make_registry_with_champions(tmp_path)
    PromotionEventStore(tmp_path / "events").append(
        PromotionEvent(
            promotion_event_id="pvprom-keep",
            modeling_path="legacy_day",
            champion_model_ref="models/legacy-champion.pkl",
            challenger_model_ref="models/legacy-champion.pkl",
            evaluation_id="eval-legacy-1",
            promoted_at="2026-01-01T00:00:00",
        )
    )
    PathSwitchEventStore(tmp_path / "events").append(
        PathSwitchEvent(
            path_switch_event_id="pvsw-keep",
            from_path="seq_annotation",
            to_path="legacy_day",
            comparison_id="shadow-old",
            activation_epoch_id="epoch-1",
            effective_from_date="2026-01-01",
            device_scope_digest="abc",
            device_scope_count=1,
            activation_mode="cutover_only",
            operator="tester",
            reason="setup",
            switched_at="2026-01-01T00:00:00",
        )
    )
    production_facts = {"cursors": 3, "ledger": 4, "epochs": ["epoch-1"]}
    runner = _runner(
        tmp_path,
        registry=registry,
        production_snapshot_fn=lambda: production_facts,
    )
    state_before = registry.get_slot("pv_fault").to_dict()
    promo_before = [event.promotion_event_id for event in PromotionEventStore(tmp_path / "events").list_recent()]
    switch_before = [
        event.path_switch_event_id for event in PathSwitchEventStore(tmp_path / "events").list_recent()
    ]

    runner.run_compare(date(2026, 1, 1), date(2026, 1, 2))

    state_after = registry.get_slot("pv_fault").to_dict()
    for key in ("production_path", "fallback_path", "active_activation_epoch_id"):
        assert state_before[key] == state_after[key]
    assert [event.promotion_event_id for event in PromotionEventStore(tmp_path / "events").list_recent()] == promo_before
    assert [
        event.path_switch_event_id for event in PathSwitchEventStore(tmp_path / "events").list_recent()
    ] == switch_before
    assert production_facts == {"cursors": 3, "ledger": 4, "epochs": ["epoch-1"]}
# @AI_GENERATED: end
