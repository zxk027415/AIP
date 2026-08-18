# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Property 21、22、37、41：路径内晋升门控、隔离与退化恢复优先级。"""
from __future__ import annotations

import uuid
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from services.iterative_labeling.accuracy_gated_retrainer import (
    AccuracyGatedRetrainer,
    EvaluationContract,
)
from services.iterative_labeling.pv_model_registry import (
    ModelRegistration,
    PathModelState,
    PVModelRegistry,
)
from services.iterative_labeling.pv_recovery_policy import PathHealth, PVRecoveryPolicy


def _contract(*, split: str = "split-a", metric: str = "macro_f1") -> EvaluationContract:
    return EvaluationContract(
        sample_digest="sample-a",
        split_digest=split,
        random_seed=42,
        metric_name=metric,
        production_contract_digest="contract-a",
        production_contract_valid=True,
    )


def _retrainer(tmp_path: Path, margin: float = 0.0) -> tuple[AccuracyGatedRetrainer, PVModelRegistry]:
    root = tmp_path / uuid.uuid4().hex
    registry = PVModelRegistry(base_dir=root / "registry", events_base_dir=root / "events")
    return AccuracyGatedRetrainer(registry, promotion_margin=margin), registry


_metrics = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_paths = st.sampled_from(["legacy_day", "seq_annotation"])


# Feature: pv-fault-dual-path-serving, Property 21: 同路径晋升当且仅当严格更优且过契约
@given(
    champion=st.floats(min_value=0.1, max_value=0.8, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-0.2, max_value=0.2, allow_nan=False, allow_infinity=False),
    mismatch=st.booleans(),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_21_promote_iff_strictly_better_same_contract(
    tmp_path: Path,
    champion: float,
    delta: float,
    mismatch: bool,
) -> None:
    retrainer, registry = _retrainer(tmp_path)
    first = retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/legacy-a.pkl",
        evaluation_id="eval-a",
        gate_metric_value=champion,
        contract=_contract(),
    )
    assert first["promotion"].status == "promoted"
    challenger = champion + delta
    second = retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/legacy-b.pkl",
        evaluation_id="eval-b",
        gate_metric_value=challenger,
        contract=_contract(split="split-b" if mismatch else "split-a"),
    )
    should_promote = (not mismatch) and challenger > champion
    if should_promote:
        assert second["promotion"].status == "promoted"
        assert registry.get_slot().path_models["legacy_day"].champion.evaluation_id == "eval-b"
    else:
        assert second["promotion"].status == "rejected"
        assert registry.get_slot().path_models["legacy_day"].champion.evaluation_id == "eval-a"
    assert registry.get_slot().production_path == "legacy_day"
    replay = retrainer.promote_if_qualified("legacy_day", "eval-a", slot="pv_fault")
    assert replay.status in {"already_promoted", "not_found", "rejected"}
    if replay.status == "already_promoted":
        assert registry.get_slot().path_models["legacy_day"].champion.evaluation_id == "eval-a"


# Feature: pv-fault-dual-path-serving, Property 22: 按路径独立累计与门控
@given(
    legacy_metric=st.integers(min_value=20, max_value=80),
    seq_metric=st.integers(min_value=20, max_value=80),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_22_path_promotion_does_not_change_other_path(
    tmp_path: Path,
    legacy_metric: int,
    seq_metric: int,
) -> None:
    retrainer, registry = _retrainer(tmp_path)
    retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/legacy.pkl",
        evaluation_id=f"el-{uuid.uuid4().hex}",
        gate_metric_value=legacy_metric / 100.0,
        contract=_contract(),
    )
    state = registry.get_slot()
    state.path_models["seq_annotation"] = PathModelState(
        champion=ModelRegistration(
            "models/seq",
            f"es-{uuid.uuid4().hex}",
            seq_metric / 100.0,
            "2026-01-01T00:00:00",
            metric_name="point_macro_f1",
        )
    )
    registry._save_slot("pv_fault", state)
    before_seq = registry.get_slot().path_models["seq_annotation"].champion.model_ref
    production_before = registry.get_slot().production_path
    retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/legacy-2.pkl",
        evaluation_id=f"el2-{uuid.uuid4().hex}",
        gate_metric_value=(legacy_metric + 5) / 100.0,
        contract=_contract(),
    )
    after = registry.get_slot()
    assert after.path_models["seq_annotation"].champion.model_ref == before_seq
    assert after.production_path == production_before


# Feature: pv-fault-dual-path-serving, Property 37: 每路径模型生命周期与路径内换将
@given(better=st.booleans())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_37_qualified_challenger_becomes_unique_champion(tmp_path: Path, better: bool) -> None:
    retrainer, registry = _retrainer(tmp_path)
    retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/old.pkl",
        evaluation_id="old",
        gate_metric_value=0.70,
        contract=_contract(),
    )
    result = retrainer.register_and_evaluate(
        "legacy_day",
        slot="pv_fault",
        model_ref="models/new.pkl",
        evaluation_id="new",
        gate_metric_value=0.80 if better else 0.70,
        contract=_contract(),
    )
    state = registry.get_slot().path_models["legacy_day"]
    if better:
        assert result["promotion"].status == "promoted"
        assert state.champion.model_ref == "models/new.pkl"
        assert any(item.model_ref == "models/old.pkl" for item in state.retired)
        assert all(item.evaluation_id != "new" for item in state.challengers)
    else:
        assert result["promotion"].status == "rejected"
        assert state.champion.model_ref == "models/old.pkl"
    assert registry.get_slot().production_path == "legacy_day"


# Feature: pv-fault-dual-path-serving, Property 41: 退化恢复优先同路径换将
@given(
    has_challenger=st.booleans(),
    loadable=st.booleans(),
    contract_ok=st.booleans(),
    no_coverage=st.integers(min_value=0, max_value=30),
    failed=st.integers(min_value=0, max_value=6),
)
@settings(max_examples=100, deadline=None)
def test_property_41_recovery_prefers_same_path_promotion(
    has_challenger: bool,
    loadable: bool,
    contract_ok: bool,
    no_coverage: int,
    failed: int,
) -> None:
    policy = PVRecoveryPolicy(no_coverage_failure_cycles=24, path_failed_cycles=3)
    decision = policy.decide(
        PathHealth(
            champion_loadable=loadable,
            production_contract_valid=contract_ok,
            no_coverage_cycles=no_coverage,
            consecutive_failed_cycles=failed,
        ),
        qualified_challenger_evaluation_ids=["eval-z"] if has_challenger else [],
    )
    if has_challenger:
        assert decision.action == "promote_within_path"
        assert decision.fallback_gate_required is False
        return
    whole_path_down = (
        (not loadable)
        or (not contract_ok)
        or no_coverage >= 24
        or failed >= 3
    )
    if whole_path_down:
        assert decision.action == "evaluate_fallback_gate"
        assert decision.fallback_gate_required is True
        assert decision.whole_path_unavailable is True
    else:
        assert decision.action == "hold"
        assert decision.fallback_gate_required is False
# @AI_GENERATED: end
