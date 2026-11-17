"""G4 verify-async: must bind real evaluation workflow execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_governance.model_candidates import register_model_candidate
from services.slot_governance.provenance import ProvenanceError
from services.slot_governance.verify_async import complete_verification_async, start_verification_async
from services.slot_governance.verification import VerificationError
from services.slot_datasets.snapshots import complete_bootstrap_async, start_bootstrap_async
from tests._execution_history_test_utils import patch_execution_history_dirs, write_execution_record


@pytest.fixture()
def async_tmp(tmp_path, monkeypatch):
    history_dir = tmp_path / "execution_history"
    gov_dir = tmp_path / "slot_governance"
    ds_dir = tmp_path / "slot_datasets"
    history_dir.mkdir()
    patch_execution_history_dirs(monkeypatch, history_dir)
    monkeypatch.setattr("services.slot_governance.model_candidates._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.verification._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.verify_async._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_datasets.snapshots._DATA_DIR", ds_dir)
    return history_dir


def _write_exec(history_dir: Path, wf: str, exec_id: str, slot: str, extra: dict | None = None) -> None:
    payload = {
        "execution_id": exec_id,
        "workflow_id": wf,
        "status": "success",
        "slot": slot,
        "governance_eligible": True,
        "nodeResults": {},
    }
    if extra:
        payload.update(extra)
    write_execution_record(payload)


def test_verify_async_rejects_missing_execution(async_tmp):
    train_wf = "workflow-pv-point-train-eval-v1"
    _write_exec(
        async_tmp,
        train_wf,
        "exec-train",
        "pv_point",
        {"nodeResults": {"pp-train": {"outputSummary": {"model_path": "data/models/demo/model.pt"}}}},
    )
    candidate = register_model_candidate(
        slot="pv_point",
        source_workflow_id=train_wf,
        source_execution_id="exec-train",
        model_artifact_ref="data/models/demo/model.pt",
    )
    job = start_verification_async(
        slot="pv_point",
        model_candidate_id=candidate["model_candidate_id"],
        idempotency_key="async-1",
    )
    with pytest.raises(ProvenanceError):
        complete_verification_async(job["comparison_id"], verification_execution_id="exec-missing")


def test_verify_async_binds_execution(async_tmp):
    train_wf = "workflow-pv-point-train-eval-v1"
    _write_exec(
        async_tmp,
        train_wf,
        "exec-train",
        "pv_point",
        {"nodeResults": {"pp-train": {"outputSummary": {"model_path": "data/models/demo/model.pt"}}}},
    )
    candidate = register_model_candidate(
        slot="pv_point",
        source_workflow_id=train_wf,
        source_execution_id="exec-train",
        model_artifact_ref="data/models/demo/model.pt",
    )
    _write_exec(
        async_tmp,
        train_wf,
        "exec-verify",
        "pv_point",
        {"nodeResults": {"pp-train": {"outputSummary": {"point_accuracy": 0.95}}}},
    )
    job = start_verification_async(
        slot="pv_point",
        model_candidate_id=candidate["model_candidate_id"],
        idempotency_key="async-2",
    )
    done = complete_verification_async(job["comparison_id"], verification_execution_id="exec-verify")
    assert done["verification"]["verification_source_execution_id"] == "exec-verify"


def test_list_verification_jobs(async_tmp):
    from services.slot_governance.verify_async import list_verification_jobs

    train_wf = "workflow-pv-point-train-eval-v1"
    _write_exec(
        async_tmp,
        train_wf,
        "exec-train",
        "pv_point",
        {"nodeResults": {"pp-train": {"outputSummary": {"model_path": "data/models/demo/model.pt"}}}},
    )
    candidate = register_model_candidate(
        slot="pv_point",
        source_workflow_id=train_wf,
        source_execution_id="exec-train",
        model_artifact_ref="data/models/demo/model.pt",
    )
    job = start_verification_async(
        slot="pv_point",
        model_candidate_id=candidate["model_candidate_id"],
        idempotency_key="async-list",
    )
    pending = list_verification_jobs("pv_point", status="pending")
    assert any(item["comparison_id"] == job["comparison_id"] for item in pending)


def test_bootstrap_async_requires_execution(async_tmp):
    train_wf = "workflow-pv-day-train-eval-v1"
    job = start_bootstrap_async(
        slot="pv_day",
        idempotency_key="bs-async",
        dataset_profile_ref="pv-day-demo@v1",
        reason="async bootstrap",
    )
    with pytest.raises(ProvenanceError):
        complete_bootstrap_async(
            job["bootstrap_job_id"],
            bootstrap_execution_id="exec-missing",
            source_digest="d1",
            base_artifact_ref="data/demo.parquet",
        )

    _write_exec(async_tmp, train_wf, "exec-bs", "pv_day")
    done = complete_bootstrap_async(
        job["bootstrap_job_id"],
        bootstrap_execution_id="exec-bs",
        source_digest="d1",
        base_artifact_ref="data/demo.parquet",
    )
    assert done["chain"]["snapshot_id"] == "snap-pv-day"
