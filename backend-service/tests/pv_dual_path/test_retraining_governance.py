# @AI_GENERATED
# -*- coding: utf-8 -*-
"""共享标签投影、按路径水位、Challenger 精度门控和退化恢复测试。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from services.iterative_labeling.accuracy_gated_retrainer import (
    AccuracyGatedRetrainer,
    EvaluationContract,
)
from services.iterative_labeling.backfill_loop import BackfillLoop, SharedLabelPool
from services.iterative_labeling.cumulative_training import CumulativeTrainingService
from services.iterative_labeling.pv_model_registry import PVModelRegistry
from services.iterative_labeling.pv_recovery_policy import (
    PVRecoveryPolicy,
    PathHealth,
)
from services.iterative_labeling.seq_annotation.dataset_builder import _load_one_indexed


def _facts():
    return [
        {
            "fact_id": "day-1",
            "sequence": 1,
            "site_id": "s",
            "device_id": "d",
            "branch_id": "b",
            "business_date": "2026-01-01",
            "label_id": 2,
            "granularity": "day",
            "source": "human_day",
            "event_time": None,
        },
        {
            "fact_id": "point-1",
            "sequence": 2,
            "site_id": "s",
            "device_id": "d",
            "branch_id": "b",
            "business_date": "2026-01-01",
            "label_id": 2,
            "granularity": "point",
            "source": "human_range",
            "event_time": "2026-01-01T10:00:00",
        },
        {
            "fact_id": "materialized-day-1",
            "sequence": 3,
            "site_id": "s",
            "device_id": "d",
            "branch_id": "b",
            "business_date": "2026-01-01",
            "label_id": 2,
            "granularity": "point",
            "source": "human_day",
            "event_time": "2026-01-01T10:05:00",
        },
        {
            "fact_id": "point-2",
            "sequence": 4,
            "site_id": "s",
            "device_id": "d2",
            "branch_id": "b",
            "business_date": "2026-01-01",
            "label_id": 3,
            "granularity": "point",
            "source": "human_range",
            "event_time": "2026-01-01T11:00:00",
        },
    ]


def test_shared_label_pool_projects_one_truth_by_path_without_day_broadcast() -> None:
    writes = []
    pool = SharedLabelPool(lambda: _facts(), fact_writer=writes.append)
    legacy = pool.list_for_path("legacy_day")
    seq = pool.list_for_path("seq_annotation")
    assert [fact.fact_id for fact in legacy] == [
        "day-1",
        "legacy-day-projection:s:d2:b:2026-01-01",
    ]
    assert all(fact.granularity == "day" for fact in legacy)
    assert [fact.fact_id for fact in seq] == ["point-1", "point-2"]
    assert writes == []

    consumed = []
    loop = BackfillLoop(pool, lambda path, facts: consumed.append((path, len(facts))))
    seq_result = loop.run_once("seq_annotation", consumed_sequence=0)
    assert seq_result.consumed_sequence == 4
    assert seq_result.change_units == 2
    legacy_result = loop.run_once("legacy_day", consumed_sequence=1)
    assert legacy_result.consumed_sequence == 4
    assert consumed == [("seq_annotation", 2), ("legacy_day", 2)]


def test_cumulative_training_tracks_path_watermarks_independently(tmp_path: Path) -> None:
    service = CumulativeTrainingService(
        slot="pv_fault",
        data_root=tmp_path,
        retrain_label_threshold=100,
        pv_model_registry=PVModelRegistry(
            base_dir=tmp_path / "registry",
            events_base_dir=tmp_path / "events",
        ),
    )
    service.admit_point_label_op(
        "review-1",
        "op-1",
        {
            "is_ground_truth": True,
            "action_type": "correct",
            "verdict_label": 1,
            "reviewer": "tester",
        },
    )
    state = service.get_state()
    assert state["retrain_watermarks"]["legacy_day"]["pending_change_count"] == 1
    assert state["retrain_watermarks"]["seq_annotation"]["pending_change_count"] == 1

    service.admit_point_label_op(
        "review-day",
        "op-day",
        {
            "is_ground_truth": True,
            "action_type": "confirm",
            "verdict_label": 2,
            "reviewer": "tester",
        },
        label_source="human_day",
    )
    state = service.get_state()
    assert state["retrain_watermarks"]["legacy_day"]["pending_change_count"] == 2
    assert state["retrain_watermarks"]["seq_annotation"]["pending_change_count"] == 1

    service.admit_verdict(
        "review-2",
        {"prediction_context": {"source_csv_path": "data/uploads/source.csv"}},
        {
            "unit_key": "device-day-1",
            "is_ground_truth": True,
            "action_type": "confirm",
            "verdict_label": 0,
            "reviewer": "tester",
        },
    )
    state = service.get_state()
    assert state["retrain_watermarks"]["legacy_day"]["pending_change_count"] == 3
    assert state["retrain_watermarks"]["seq_annotation"]["pending_change_count"] == 1


def test_retrain_watermark_commits_only_after_target_path_succeeds(tmp_path: Path) -> None:
    registry = PVModelRegistry(
        base_dir=tmp_path / "registry",
        events_base_dir=tmp_path / "events",
    )
    service = CumulativeTrainingService(
        slot="pv_fault",
        data_root=tmp_path,
        retrain_label_threshold=200,
        pv_model_registry=registry,
    )
    service.admit_point_label_op(
        "review-1",
        "op-1",
        {
            "is_ground_truth": True,
            "action_type": "correct",
            "verdict_label": 1,
        },
        label_source="human_range",
    )
    failed = service.reserve_manual_retrain_request("legacy_day")["retrain_request"]
    service.mark_retrain_request(failed["request_id"], "failed", error="boom")
    state_after_failure = service.get_state()
    assert state_after_failure["retrain_watermarks"]["legacy_day"]["pending_change_count"] == 1
    assert state_after_failure["retrain_watermarks"]["seq_annotation"]["pending_change_count"] == 1

    succeeded = service.reserve_manual_retrain_request("legacy_day")["retrain_request"]
    service.mark_retrain_request(
        succeeded["request_id"],
        "completed",
        model_ref="models/legacy-v1.pkl",
        train_summary={
            "modeling_path": "legacy_day",
            "model_path": "data/models/legacy-v1.pkl",
            "artifact_format": "pickle",
            "accuracy_record": {"macro_f1_mean": 0.8},
        },
        promote_to_production=False,
    )
    state_after_success = service.get_state()
    assert state_after_success["retrain_watermarks"]["legacy_day"]["pending_change_count"] == 0
    assert state_after_success["retrain_watermarks"]["seq_annotation"]["pending_change_count"] == 1
    assert state_after_success["retrain_watermarks"]["legacy_day"]["consumed_sequence"] == 1
    assert state_after_success["retrain_watermarks"]["seq_annotation"]["consumed_sequence"] == 0


def _contract(*, split: str = "split-a") -> EvaluationContract:
    return EvaluationContract(
        sample_digest="sample-a",
        split_digest=split,
        random_seed=42,
        metric_name="macro_f1",
        production_contract_digest="contract-a",
        production_contract_valid=True,
    )


def test_accuracy_gate_registers_challenger_then_strictly_promotes_with_same_contract(
    tmp_path: Path,
) -> None:
    registry = PVModelRegistry(
        base_dir=tmp_path / "registry",
        events_base_dir=tmp_path / "events",
    )
    retrainer = AccuracyGatedRetrainer(
        registry,
        retrain_change_threshold=200,
        retrain_period_days=7,
        promotion_margin=0.0,
    )
    first = retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/legacy-v1.pkl",
        evaluation_id="eval-1",
        gate_metric_value=0.80,
        contract=_contract(),
    )
    assert first["registration"].status == "registered"
    assert first["promotion"].status == "promoted"

    tied = retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/legacy-v2.pkl",
        evaluation_id="eval-2",
        gate_metric_value=0.80,
        contract=_contract(),
    )
    assert tied["promotion"].status == "rejected"
    assert tied["promotion"].reason == "promotion_margin_not_met"

    mismatched = retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/legacy-v3.pkl",
        evaluation_id="eval-3",
        gate_metric_value=0.90,
        contract=_contract(split="split-b"),
    )
    assert mismatched["promotion"].status == "rejected"
    assert mismatched["promotion"].reason == "evaluation_contract_not_comparable"
    slot = registry.get_slot("pv_fault")
    assert slot.production_path == "legacy_day"
    assert slot.path_models["legacy_day"].champion.model_ref == "models/legacy-v1.pkl"


def test_trigger_and_recovery_policy_prioritize_same_path() -> None:
    retrainer = AccuracyGatedRetrainer(PVModelRegistry(), retrain_change_threshold=200)
    now = datetime(2026, 1, 10)
    assert retrainer.maybe_trigger(
        pending_change_count=200,
        last_retrained_at=now,
        now=now,
    ).should_trigger is False
    assert retrainer.maybe_trigger(
        pending_change_count=200,
        last_retrained_at=now - timedelta(days=7),
        now=now,
    ).trigger_reason == "auto_threshold_and_period"
    assert retrainer.maybe_trigger(
        pending_change_count=1,
        last_retrained_at=now - timedelta(days=7),
        now=now,
    ).should_trigger is False
    assert retrainer.maybe_trigger(
        pending_change_count=1,
        last_retrained_at=now,
        now=now,
        manual=True,
    ).trigger_reason == "manual"

    policy = PVRecoveryPolicy(no_coverage_failure_cycles=24, path_failed_cycles=3)
    same_path = policy.decide(
        PathHealth(champion_loadable=False, consecutive_failed_cycles=3),
        qualified_challenger_evaluation_ids=["eval-z"],
    )
    assert same_path.action == "promote_within_path"
    assert same_path.fallback_gate_required is False

    fallback = policy.decide(
        PathHealth(champion_loadable=False),
        qualified_challenger_evaluation_ids=[],
    )
    assert fallback.action == "evaluate_fallback_gate"
    assert fallback.fallback_gate_required is True
    assert policy.decide(PathHealth()).action == "hold"


def test_seq_loader_rejects_pure_day_labels_instead_of_filling_288_points() -> None:
    day = date(2026, 1, 1)
    key = ("s", "d", "b", day)
    measurements = pd.DataFrame(
        {
            "time": [pd.Timestamp("2026-01-01T10:00:00")],
            "value": [1.0],
            "i_cal": [0.5],
        }
    )
    day_labels = pd.DataFrame(
        {
            "time": [pd.Timestamp("2026-01-01T10:00:00")],
            "label_id": [2],
            "source": ["human_day"],
        }
    )
    _, _, reason, ok = _load_one_indexed(
        {key: measurements},
        {key: day_labels},
        *key,
        use_labels=True,
    )
    assert ok is False
    assert reason["reason"] == "pure_day_label_not_allowed_for_seq"

    _, _, fill_reason, fill_ok = _load_one_indexed(
        {key: measurements},
        None,
        *key,
        use_labels=False,
        fill_label=2,
    )
    assert fill_ok is False
    assert fill_reason["reason"] == "pure_day_label_not_allowed_for_seq"


def _pv_fault_service(tmp_path: Path) -> tuple[CumulativeTrainingService, PVModelRegistry]:
    registry = PVModelRegistry(
        base_dir=tmp_path / "registry",
        events_base_dir=tmp_path / "events",
    )
    service = CumulativeTrainingService(
        slot="pv_fault",
        data_root=tmp_path,
        retrain_label_threshold=200,
        pv_model_registry=registry,
    )
    return service, registry


def test_pv_fault_completed_retrain_never_switches_production_path(tmp_path: Path) -> None:
    """8.4：pv_fault 完成回调即使 promote_to_production=True 也不得改 production_path。"""

    service, registry = _pv_fault_service(tmp_path)
    first = service.reserve_manual_retrain_request("legacy_day")["retrain_request"]
    completed = service.mark_retrain_request(
        first["request_id"],
        "completed",
        model_ref="models/legacy-v1.pkl",
        train_summary={
            "modeling_path": "legacy_day",
            "artifact_format": "pickle",
            "sample_digest": "sample-a",
            "split_digest": "split-a",
            "production_contract_digest": "contract-a",
            "accuracy_record": {"macro_f1_mean": 0.80},
        },
        promote_to_production=True,
    )
    slot = registry.get_slot("pv_fault")
    assert completed["promote_to_production"] is False
    assert completed["pv_registry_governance"]["promotion_status"] == "promoted"
    assert slot.production_path == "legacy_day"
    assert slot.path_models["legacy_day"].champion.model_ref.endswith("models/legacy-v1.pkl")
    assert service.get_modeling_paths()["production_path"] == "legacy_day"

    seq_req = service.reserve_manual_retrain_request("seq_annotation")["retrain_request"]
    service.mark_retrain_request(
        seq_req["request_id"],
        "completed",
        model_ref="models/seq-v1",
        train_summary={
            "modeling_path": "seq_annotation",
            "trained_full_day": True,
            "sequence_contract": {"seq_len": 288, "trained_full_day": True},
            "sample_digest": "sample-seq",
            "split_digest": "split-seq",
            "production_contract_digest": "contract-seq",
            "accuracy_record": {"point_macro_f1": 0.99},
        },
        promote_to_production=True,
    )
    after_seq = registry.get_slot("pv_fault")
    assert after_seq.production_path == "legacy_day"
    assert after_seq.path_models["seq_annotation"].champion is not None

    weaker = service.reserve_manual_retrain_request("legacy_day")["retrain_request"]
    weaker_completed = service.mark_retrain_request(
        weaker["request_id"],
        "completed",
        model_ref="models/legacy-v2.pkl",
        train_summary={
            "modeling_path": "legacy_day",
            "artifact_format": "pickle",
            "sample_digest": "sample-a",
            "split_digest": "split-a",
            "production_contract_digest": "contract-a",
            "accuracy_record": {"macro_f1_mean": 0.80},
        },
        promote_to_production=True,
    )
    after = registry.get_slot("pv_fault")
    assert weaker_completed["pv_registry_governance"]["promotion_status"] == "rejected"
    assert after.production_path == "legacy_day"
    assert after.path_models["legacy_day"].champion.evaluation_id == first["request_id"]


def test_pv_fault_false_promote_registers_challenger_only(tmp_path: Path) -> None:
    service, registry = _pv_fault_service(tmp_path)
    reserved = service.reserve_manual_retrain_request("seq_annotation")["retrain_request"]
    service.mark_retrain_request(
        reserved["request_id"],
        "completed",
        model_ref="models/seq-v1",
        train_summary={
            "modeling_path": "seq_annotation",
            "trained_full_day": True,
            "sequence_contract": {"seq_len": 288, "trained_full_day": True},
            "sample_digest": "sample-b",
            "split_digest": "split-b",
            "production_contract_digest": "contract-b",
            "accuracy_record": {"point_macro_f1": 0.91},
        },
        promote_to_production=False,
    )
    slot = registry.get_slot("pv_fault")
    path_state = slot.path_models["seq_annotation"]
    assert slot.production_path == "legacy_day"
    assert path_state.champion is None
    assert path_state.challengers[0].evaluation_id == reserved["request_id"]
# @AI_GENERATED: end
