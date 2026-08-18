# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PVModelRegistry Challenger/Champion 生命周期、双事件隔离和旧状态迁移测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.iterative_labeling.pv_governance_events import (
    PathSwitchEventStore,
    PromotionEventStore,
)
from services.iterative_labeling.pv_model_registry import (
    ModelRegistration,
    PVModelRegistry,
    ProductionPathPointer,
)


def _model(ref: str, evaluation: str, score: float) -> ModelRegistration:
    return ModelRegistration(ref, evaluation, score, "2026-08-13T00:00:00")


def test_register_is_idempotent_and_does_not_change_production_path(tmp_path: Path) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    before = registry.get_slot()
    first = registry.register_challenger("seq_annotation", _model("data/models/a.pkl", "e1", 0.8))
    duplicate = registry.register_challenger("seq_annotation", _model("data/models/a.pkl", "e1", 0.8))
    conflict = registry.register_challenger("seq_annotation", _model("data/models/b.pkl", "e1", 0.9))
    after = registry.get_slot()

    assert first.status == "registered"
    assert duplicate.status == "duplicate" and not duplicate.changed
    assert conflict.status == "evaluation_id_conflict" and not conflict.changed
    assert after.production_path == before.production_path == "legacy_day"
    assert after.active_activation_epoch_id == before.active_activation_epoch_id
    assert len(after.path_models["seq_annotation"].challengers) == 1


def test_promote_strictly_better_moves_old_champion_to_retired_and_only_writes_promotion_event(
    tmp_path: Path,
) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    registry.register_challenger("seq_annotation", _model("data/models/a.pkl", "e1", 0.8))
    assert registry.promote_within_path("seq_annotation", "e1").status == "promoted"
    registry.register_challenger("seq_annotation", _model("data/models/tie.pkl", "e2", 0.8))
    tie = registry.promote_within_path("seq_annotation", "e2", promotion_margin=0.0)
    assert tie.status == "rejected"

    registry.register_challenger("seq_annotation", _model("data/models/b.pkl", "e3", 0.9))
    promoted = registry.promote_within_path(
        "seq_annotation", "e3", production_contract_validator=lambda *_: True
    )
    state = registry.get_slot()
    path_state = state.path_models["seq_annotation"]
    assert promoted.status == "promoted"
    assert path_state.champion is not None and path_state.champion.evaluation_id == "e3"
    assert [item.evaluation_id for item in path_state.retired] == ["e1"]
    assert state.production_path == "legacy_day"
    assert len(PromotionEventStore(tmp_path / "events").list_recent()) == 2
    assert PathSwitchEventStore(tmp_path / "events").list_recent() == []


def test_promotion_event_failure_restores_registry(tmp_path: Path) -> None:
    class _FailingStore:
        def append_if_absent(self, _event):
            raise OSError("injected event failure")

    registry = PVModelRegistry(
        tmp_path / "registry",
        events_base_dir=tmp_path / "events",
        promotion_store_factory=lambda _slot: _FailingStore(),  # type: ignore[arg-type]
    )
    registry.register_challenger("seq_annotation", _model("data/models/a.pkl", "e1", 0.8))
    with pytest.raises(RuntimeError, match="已补偿恢复"):
        registry.promote_within_path("seq_annotation", "e1")
    state = registry.get_slot()
    assert state.path_models["seq_annotation"].champion is None
    assert [item.evaluation_id for item in state.path_models["seq_annotation"].challengers] == ["e1"]


def test_legacy_migration_is_conservative_and_idempotent(tmp_path: Path) -> None:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    old = {
        "slot": "pv_fault",
        "production_path": "legacy_day",
        "fallback_path": "seq_annotation",
        "path_models": {
            "legacy_day": {"model_ref": "data/models/legacy.pkl", "evaluation_id": "old-1", "gate_metric_value": 0.7},
            "seq_annotation": {"model_ref": "data/models/seq.pkl", "evaluation_id": "old-2", "gate_metric_value": 0.9},
        },
        "path_switch_audit": [{"action": "unknown_legacy_action", "at": "2026-01-01"}],
    }
    result = registry.migrate_legacy_state(
        old,
        artifact_validator=lambda ref, *_: not ref.endswith("seq.pkl"),
        contract_validator=lambda *_: True,
    )
    repeated = registry.migrate_legacy_state(old, lambda *_: True, lambda *_: True)
    state = registry.get_slot()

    assert result.status == "migrated"
    assert repeated.status == "already_migrated" and not repeated.changed
    assert state.path_models["legacy_day"].champion is not None
    assert state.path_models["seq_annotation"].champion is None
    assert state.path_models["seq_annotation"].challengers[0].qualified is False
    assert state.legacy_audit == old["path_switch_audit"]


def test_production_pointer_is_stateless_delegate(tmp_path: Path) -> None:
    calls = []
    registry = PVModelRegistry(tmp_path / "registry", switch_coordinator=lambda request: calls.append(request) or "ok")
    pointer = ProductionPathPointer(registry)
    assert pointer.get() == "legacy_day"
    assert pointer.switch({"to_path": "seq_annotation"}) == "ok"
    assert calls == [{"to_path": "seq_annotation"}]
# @AI_GENERATED: end
