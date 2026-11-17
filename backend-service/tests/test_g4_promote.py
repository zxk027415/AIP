"""G4 promote + verification skeleton tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_governance.evaluation_contracts import get_evaluation_contract
from services.slot_governance.model_candidates import register_model_candidate
from services.slot_governance.promote import PromoteError, promote_model_candidate
from services.slot_governance.registry import get_registry_store
from services.slot_governance.verification import register_verification
from tests._execution_history_test_utils import patch_execution_history_dirs, write_execution_record


@pytest.fixture()
def gov_tmp(tmp_path, monkeypatch):
    history_dir = tmp_path / "execution_history"
    gov_dir = tmp_path / "slot_governance"
    history_dir.mkdir()
    patch_execution_history_dirs(monkeypatch, history_dir)
    monkeypatch.setattr("services.slot_governance.model_candidates._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.registry._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.verification._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.promote._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.evaluation_contracts._DATA_DIR", gov_dir)
    return history_dir


def _seed_execution(history_dir: Path, wf: str, exec_id: str, slot: str, model_path: str) -> None:
    write_execution_record(
        {
            "execution_id": exec_id,
            "workflow_id": wf,
            "status": "success",
            "slot": slot,
            "governance_eligible": True,
            "nodeResults": {
                "train": {
                    "status": "success",
                    "outputSummary": {"model_path": model_path},
                }
            },
        }
    )


def test_evaluation_contract_defaults():
    contract = get_evaluation_contract("pv_point")
    assert contract["slot"] == "pv_point"
    assert "evaluation_contract_ref" in contract


def test_promote_challenger_only(gov_tmp):
    wf = "workflow-pv-point-train-eval-v1"
    _seed_execution(gov_tmp, wf, "exec-1", "pv_point", "data/models/demo/model.pt")
    candidate = register_model_candidate(
        slot="pv_point",
        source_workflow_id=wf,
        source_execution_id="exec-1",
        model_artifact_ref="data/models/demo/model.pt",
    )
    contract = get_evaluation_contract("pv_point")
    verification = register_verification(
        slot="pv_point",
        model_candidate_id=candidate["model_candidate_id"],
        evaluation_contract_ref=contract["evaluation_contract_ref"],
        idempotency_key="ver-key-1",
        registry_version_at_start=0,
    )

    result = promote_model_candidate(
        candidate["model_candidate_id"],
        verification_id=verification["verification_id"],
        operator="tester",
        reason="adopt challenger",
        expected_registry_version=0,
        idempotency_key="prom-key-1",
        set_as_production=False,
    )
    assert result["idempotent_replay"] is False
    registry = result["registry"]
    assert registry["registry_version"] == 1
    assert registry["champion"] is None
    assert registry["challenger"]["challenger_model_ref"] == candidate["model_ref"]
    assert result["promotion"]["champion_changed"] is False
    assert result["promotion"]["new_champion_model_ref"] is None


def test_promote_set_as_production(gov_tmp):
    wf = "workflow-pv-day-train-eval-v1"
    _seed_execution(gov_tmp, wf, "exec-2", "pv_day", "data/models/demo/day.pkl")
    candidate = register_model_candidate(
        slot="pv_day",
        source_workflow_id=wf,
        source_execution_id="exec-2",
        model_artifact_ref="data/models/demo/day.pkl",
    )
    contract = get_evaluation_contract("pv_day")
    verification = register_verification(
        slot="pv_day",
        model_candidate_id=candidate["model_candidate_id"],
        evaluation_contract_ref=contract["evaluation_contract_ref"],
        idempotency_key="ver-key-2",
        registry_version_at_start=0,
    )

    result = promote_model_candidate(
        candidate["model_candidate_id"],
        verification_id=verification["verification_id"],
        operator="tester",
        reason="switch champion",
        expected_registry_version=0,
        idempotency_key="prom-key-2",
        set_as_production=True,
    )
    registry = result["registry"]
    assert registry["champion"]["champion_model_ref"] == candidate["model_ref"]
    assert registry["challenger"] is None
    assert result["promotion"]["champion_changed"] is True


def test_promote_idempotent_replay(gov_tmp):
    wf = "workflow-pv-point-train-eval-v1"
    _seed_execution(gov_tmp, wf, "exec-3", "pv_point", "data/models/demo/model.pt")
    candidate = register_model_candidate(
        slot="pv_point",
        source_workflow_id=wf,
        source_execution_id="exec-3",
        model_artifact_ref="data/models/demo/model.pt",
    )
    contract = get_evaluation_contract("pv_point")
    verification = register_verification(
        slot="pv_point",
        model_candidate_id=candidate["model_candidate_id"],
        evaluation_contract_ref=contract["evaluation_contract_ref"],
        idempotency_key="ver-key-3",
    )
    kwargs = dict(
        verification_id=verification["verification_id"],
        operator="tester",
        reason="once",
        expected_registry_version=0,
        idempotency_key="prom-key-3",
    )
    first = promote_model_candidate(candidate["model_candidate_id"], **kwargs)
    second = promote_model_candidate(candidate["model_candidate_id"], **kwargs)
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert get_registry_store().get("pv_point")["registry_version"] == 1


def test_promote_rejects_stale_registry_version(gov_tmp):
    wf = "workflow-pv-point-train-eval-v1"
    _seed_execution(gov_tmp, wf, "exec-4", "pv_point", "data/models/demo/model.pt")
    candidate = register_model_candidate(
        slot="pv_point",
        source_workflow_id=wf,
        source_execution_id="exec-4",
        model_artifact_ref="data/models/demo/model.pt",
    )
    contract = get_evaluation_contract("pv_point")
    verification = register_verification(
        slot="pv_point",
        model_candidate_id=candidate["model_candidate_id"],
        evaluation_contract_ref=contract["evaluation_contract_ref"],
        idempotency_key="ver-key-4",
    )
    with pytest.raises(PromoteError) as exc:
        promote_model_candidate(
            candidate["model_candidate_id"],
            verification_id=verification["verification_id"],
            operator="tester",
            reason="bad version",
            expected_registry_version=99,
            idempotency_key="prom-key-4",
        )
    assert exc.value.code == "registry_version_conflict"
