"""G6 benchmark slot governance skeleton."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.benchmark.governance import (
    BENCHMARK_EXECUTION_PURPOSE,
    compute_governance_eligible,
    is_benchmark_slot,
    resolve_execution_purpose,
)
from services.slot_datasets.annotation_candidates import register_annotation_candidate
from services.slot_datasets.snapshots import bootstrap_snapshot
from services.slot_governance.model_candidates import register_model_candidate
from services.slot_governance.promote import promote_model_candidate
from services.slot_governance.provenance import ProvenanceError
from services.slot_governance.verification import register_verification
from services.slot_governance.verify_async import start_verification_async
from tests._execution_history_test_utils import patch_execution_history_dirs, write_execution_record


@pytest.fixture()
def g6_tmp(tmp_path, monkeypatch):
    history_dir = tmp_path / "execution_history"
    gov_dir = tmp_path / "slot_governance"
    ds_dir = tmp_path / "slot_datasets"
    history_dir.mkdir()
    patch_execution_history_dirs(monkeypatch, history_dir)
    monkeypatch.setattr("services.slot_governance.model_candidates._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.registry._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.verification._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.promote._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.verify_async._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_datasets.annotation_candidates._DATA_DIR", ds_dir)
    monkeypatch.setattr("services.slot_datasets.snapshots._DATA_DIR", ds_dir)
    return history_dir


def test_benchmark_slot_iff_benchmark_reuse_purpose():
    assert is_benchmark_slot("benchmark_nasa_smap_msl")
    assert not is_benchmark_slot("pv_point")

    ctx = resolve_execution_purpose(
        slot="benchmark_nasa_smap_msl",
        execution_purpose=BENCHMARK_EXECUTION_PURPOSE,
    )
    assert ctx["execution_purpose"] == BENCHMARK_EXECUTION_PURPOSE
    assert ctx["governance_eligible"] is False

    with pytest.raises(ValueError, match="requires execution_purpose=benchmark_reuse"):
        resolve_execution_purpose(slot="benchmark_nasa_smap_msl", execution_purpose="product_workflow")

    with pytest.raises(ValueError, match="only allowed for benchmark_\\* slots"):
        resolve_execution_purpose(slot="pv_point", execution_purpose=BENCHMARK_EXECUTION_PURPOSE)


def test_product_slot_default_governance_eligible():
    ctx = resolve_execution_purpose(slot="pv_point", execution_purpose=None)
    assert ctx["execution_purpose"] == "product_workflow"
    assert ctx["governance_eligible"] is True
    assert compute_governance_eligible(slot="pv_point", execution_purpose="product_workflow") is True


@pytest.mark.parametrize(
    "write_fn,kwargs,error_type",
    [
        (
            register_model_candidate,
            {
                "slot": "benchmark_nasa_smap_msl",
                "source_workflow_id": "workflow-pv-point-train-eval-v1",
                "source_execution_id": "exec-1",
                "model_artifact_ref": "data/models/demo/model.pt",
            },
            ProvenanceError,
        ),
        (
            register_annotation_candidate,
            {
                "slot": "benchmark_nasa_smap_msl",
                "source_workflow_id": "workflow-pv-point-predict-replay-v1",
                "source_execution_id": "exec-1",
                "dataset_profile_ref": "nasa-demo@v1",
                "entity_key": "e1",
                "boundary_start": "2021-01-01T00:00:00Z",
                "boundary_end": "2021-01-01T01:00:00Z",
                "suggested_label": "fault",
            },
            ProvenanceError,
        ),
        (
            bootstrap_snapshot,
            {
                "slot": "benchmark_nasa_smap_msl",
                "idempotency_key": "bs-1",
                "dataset_profile_ref": "nasa-demo@v1",
                "source_digest": "digest-1",
                "base_artifact_ref": "data/demo.parquet",
                "reason": "bootstrap",
            },
            ProvenanceError,
        ),
        (
            register_verification,
            {
                "slot": "benchmark_nasa_smap_msl",
                "model_candidate_id": "mc-demo",
                "evaluation_contract_ref": "pv-point-eval@v1",
                "idempotency_key": "ver-1",
                "verification_source_workflow_id": "workflow-pv-point-train-eval-v1",
                "verification_source_execution_id": "exec-1",
                "evaluation_artifact_ref": "data/demo/eval.json",
            },
            ProvenanceError,
        ),
        (
            promote_model_candidate,
            {
                "model_candidate_id": "mc-demo",
                "verification_id": "ver-demo",
                "expected_registry_version": 0,
                "idempotency_key": "promote-1",
                "operator": "tester",
                "reason": "test",
                "production_slot": "benchmark_nasa_smap_msl",
            },
            ProvenanceError,
        ),
        (
            start_verification_async,
            {
                "slot": "benchmark_nasa_smap_msl",
                "model_candidate_id": "mc-demo",
                "idempotency_key": "async-1",
            },
            ProvenanceError,
        ),
    ],
)
def test_benchmark_slot_write_entries_rejected(g6_tmp, write_fn, kwargs, error_type):
    with pytest.raises(error_type) as exc:
        write_fn(**kwargs)
    assert exc.value.code == "benchmark_governance_forbidden"


def test_benchmark_execution_cannot_back_product_governance(g6_tmp):
    wf = "workflow-pv-point-train-eval-v1"
    write_execution_record(
        {
            "execution_id": "exec-bench-run",
            "workflow_id": wf,
            "status": "success",
            "slot": "pv_point",
            "execution_purpose": "benchmark_reuse",
            "governance_eligible": False,
            "nodeResults": {
                "pp-train": {"outputSummary": {"model_path": "data/models/demo/model.pt"}},
            },
        }
    )
    with pytest.raises(ProvenanceError) as exc:
        register_model_candidate(
            slot="pv_point",
            source_workflow_id=wf,
            source_execution_id="exec-bench-run",
            model_artifact_ref="data/models/demo/model.pt",
        )
    assert exc.value.code == "governance_not_eligible"
