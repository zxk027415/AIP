"""G4 slot governance: registry + model candidate provenance gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_governance.model_candidates import register_model_candidate
from services.slot_governance.provenance import ProvenanceError, validate_execution_provenance
from services.slot_governance.registry import get_registry_store
from tests._execution_history_test_utils import patch_execution_history_dirs, write_execution_record


@pytest.fixture()
def fake_execution(tmp_path, monkeypatch):
    history_dir = tmp_path / "execution_history"
    history_dir.mkdir()
    patch_execution_history_dirs(monkeypatch, history_dir)
    monkeypatch.setattr(
        "services.slot_governance.model_candidates._DATA_DIR",
        tmp_path / "slot_governance",
    )
    monkeypatch.setattr(
        "services.slot_governance.registry._DATA_DIR",
        tmp_path / "slot_governance",
    )
    return history_dir


def _write_execution(history_dir: Path, workflow_id: str, payload: dict) -> None:
    payload.setdefault("workflow_id", workflow_id)
    write_execution_record(payload)


def test_empty_registry_is_diagnostic():
    store = get_registry_store()
    view = store.get("pv_point_demo_missing")
    assert view["empty"] is True
    assert view["slot"] == "pv_point_demo_missing"


def test_reject_benchmark_slot_write(fake_execution):
    with pytest.raises(ProvenanceError) as exc:
        register_model_candidate(
            slot="benchmark_pvdaq_demo",
            source_workflow_id="workflow-pv-point-train-eval-v1",
            source_execution_id="exec-1",
            model_artifact_ref="data/models/demo/model.pt",
        )
    assert exc.value.code == "benchmark_governance_forbidden"


def test_reject_scenario_key(fake_execution):
    with pytest.raises(ProvenanceError) as exc:
        register_model_candidate(
            slot="pv_point",
            source_workflow_id="workflow-pv-point-train-eval-v1",
            source_execution_id="exec-1",
            model_artifact_ref="data/models/demo/model.pt",
            scenario_key="pv_point",
        )
    assert exc.value.code == "scenario_key_not_allowed"


def test_reject_missing_execution(fake_execution):
    with pytest.raises(ProvenanceError) as exc:
        validate_execution_provenance(
            slot="pv_point",
            source_workflow_id="workflow-pv-point-train-eval-v1",
            source_execution_id="exec-missing",
            model_artifact_ref="data/models/demo/model.pt",
        )
    assert exc.value.code == "execution_not_found"


def test_reject_non_success_execution(fake_execution):
    wf = "workflow-pv-point-train-eval-v1"
    _write_execution(
        fake_execution,
        wf,
        {
            "execution_id": "exec-failed",
            "workflow_id": wf,
            "status": "failed",
            "slot": "pv_point",
            "nodeResults": {},
        },
    )
    with pytest.raises(ProvenanceError) as exc:
        validate_execution_provenance(
            slot="pv_point",
            source_workflow_id=wf,
            source_execution_id="exec-failed",
            model_artifact_ref="data/models/demo/model.pt",
        )
    assert exc.value.code == "execution_not_succeeded"


def test_register_candidate_with_valid_provenance(fake_execution):
    wf = "workflow-pv-point-train-eval-v1"
    _write_execution(
        fake_execution,
        wf,
        {
            "execution_id": "exec-ok",
            "workflow_id": wf,
            "status": "success",
            "slot": "pv_point",
            "governance_eligible": True,
            "source_workflow_version": "1",
            "nodeResults": {
                "pp-train": {
                    "status": "success",
                    "outputSummary": {
                        "model_path": "data/models/realtime_point_poc/demo/model.pt",
                    },
                }
            },
        },
    )
    candidate = register_model_candidate(
        slot="pv_point",
        source_workflow_id=wf,
        source_execution_id="exec-ok",
        model_artifact_ref="data/models/realtime_point_poc/demo/model.pt",
    )
    assert candidate["slot"] == "pv_point"
    assert candidate["source_execution_id"] == "exec-ok"
    assert candidate["model_artifact_ref"].endswith("model.pt")
