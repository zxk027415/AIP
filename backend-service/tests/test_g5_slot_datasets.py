"""G5 slot datasets: annotation → review → snapshot loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.annotation_candidates import register_annotation_candidate
from services.slot_datasets.reviewed_annotations import approve_annotation_candidate
from services.slot_datasets.snapshots import bootstrap_snapshot, build_snapshot_increment, get_snapshot_chain
from services.slot_governance.evaluation_contracts import get_evaluation_contract
from services.slot_governance.model_candidates import register_model_candidate
from services.slot_governance.promote import promote_model_candidate
from services.slot_governance.registry import get_registry_store
from services.slot_governance.verification import register_verification
from services.slot_governance.verify_async import complete_verification_async, start_verification_async
from tests._execution_history_test_utils import patch_execution_history_dirs, write_execution_record


@pytest.fixture()
def g5_tmp(tmp_path, monkeypatch):
    history_dir = tmp_path / "execution_history"
    gov_dir = tmp_path / "slot_governance"
    ds_dir = tmp_path / "slot_datasets"
    history_dir.mkdir()
    patch_execution_history_dirs(monkeypatch, history_dir)
    monkeypatch.setattr("services.slot_governance.model_candidates._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.registry._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.verification._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.promote._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.evaluation_contracts._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_governance.verify_async._DATA_DIR", gov_dir)
    monkeypatch.setattr("services.slot_datasets.annotation_candidates._DATA_DIR", ds_dir)
    monkeypatch.setattr("services.slot_datasets.reviewed_annotations._DATA_DIR", ds_dir)
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


def test_annotation_candidate_fingerprint_dedup(g5_tmp):
    wf = "workflow-pv-point-predict-replay-v1"
    _write_exec(g5_tmp, wf, "exec-predict", "pv_point")
    first = register_annotation_candidate(
        slot="pv_point",
        source_workflow_id=wf,
        source_execution_id="exec-predict",
        dataset_profile_ref="pv-point-demo@v1",
        entity_key="s1/d1/b1",
        boundary_start="2024-03-01T08:00:00Z",
        boundary_end="2024-03-01T08:06:00Z",
        suggested_label=1,
        model_ref="mc-demo",
    )
    second = register_annotation_candidate(
        slot="pv_point",
        source_workflow_id=wf,
        source_execution_id="exec-predict",
        dataset_profile_ref="pv-point-demo@v1",
        entity_key="s1/d1/b1",
        boundary_start="2024-03-01T08:00:00Z",
        boundary_end="2024-03-01T08:06:00Z",
        suggested_label=1,
        model_ref="mc-demo",
    )
    assert first["annotation_candidate_id"] == second["annotation_candidate_id"]


def test_snapshot_bootstrap_conflict(g5_tmp):
    bootstrap_snapshot(
        slot="pv_point",
        idempotency_key="bs-1",
        source_digest="digest-v1",
        base_artifact_ref="data/timeseries_point/test_fixtures/labeled_points.parquet",
        dataset_profile_ref="pv-point-demo@v1",
        reason="demo bootstrap",
    )
    chain = get_snapshot_chain("pv_point")
    assert chain["latest_version"] == 1
    assert chain["snapshot_id"] == "snap-pv-point"

    with pytest.raises(SlotDatasetError) as exc:
        bootstrap_snapshot(
            slot="pv_point",
            idempotency_key="bs-2",
            source_digest="digest-v2",
            base_artifact_ref="data/other.parquet",
            dataset_profile_ref="pv-point-demo@v1",
            reason="duplicate bootstrap",
        )
    assert exc.value.code == "snapshot_chain_exists"


def test_pv_point_mini_closed_loop(g5_tmp):
    """candidate → review → snapshot+1 → retrain candidate → verify → promote champion."""
    predict_wf = "workflow-pv-point-predict-replay-v1"
    train_wf = "workflow-pv-point-train-eval-v1"
    _write_exec(g5_tmp, predict_wf, "exec-predict", "pv_point")
    _write_exec(
        g5_tmp,
        train_wf,
        "exec-train",
        "pv_point",
        {
            "nodeResults": {
                "pp-train": {
                    "status": "success",
                    "outputSummary": {"model_path": "data/models/realtime_point_poc/demo/model.pt"},
                }
            }
        },
    )

    bootstrap_snapshot(
        slot="pv_point",
        idempotency_key="bs-loop",
        source_digest="digest-bootstrap",
        base_artifact_ref="data/timeseries_point/test_fixtures/labeled_points.parquet",
        dataset_profile_ref="pv-point-demo@v1",
        reason="loop bootstrap",
    )
    chain = get_snapshot_chain("pv_point")
    snapshot_id = chain["snapshot_id"]

    candidate = register_annotation_candidate(
        slot="pv_point",
        source_workflow_id=predict_wf,
        source_execution_id="exec-predict",
        dataset_profile_ref="pv-point-demo@v1",
        entity_key="s1/d1/b1",
        boundary_start="2024-03-01T08:00:00Z",
        boundary_end="2024-03-01T08:12:00Z",
        suggested_label=1,
    )
    approved = approve_annotation_candidate(
        slot="pv_point",
        annotation_candidate_id=candidate["annotation_candidate_id"],
        reviewer="tester",
        idempotency_key="ap-1",
    )
    reviewed_id = approved["reviewed_annotation"]["reviewed_annotation_id"]

    built = build_snapshot_increment(
        slot="pv_point",
        snapshot_id=snapshot_id,
        base_snapshot_version=1,
        reviewed_annotation_ids=[reviewed_id],
        idempotency_key="build-1",
        reason="add reviewed interval",
    )
    assert built["chain"]["latest_version"] == 2
    assert len(built["chain"]["versions"][1]["added_annotation_refs"]) == 1

    model_candidate = register_model_candidate(
        slot="pv_point",
        source_workflow_id=train_wf,
        source_execution_id="exec-train",
        model_artifact_ref="data/models/realtime_point_poc/demo/model.pt",
    )
    contract = get_evaluation_contract("pv_point")
    verification = register_verification(
        slot="pv_point",
        model_candidate_id=model_candidate["model_candidate_id"],
        evaluation_contract_ref=contract["evaluation_contract_ref"],
        idempotency_key="ver-loop",
    )
    promoted = promote_model_candidate(
        model_candidate["model_candidate_id"],
        verification_id=verification["verification_id"],
        operator="tester",
        reason="demo champion",
        expected_registry_version=0,
        idempotency_key="prom-loop",
        set_as_production=True,
    )
    registry = promoted["registry"]
    assert registry["champion"]["champion_model_ref"] == model_candidate["model_ref"]
    assert get_registry_store().get("pv_point")["registry_version"] == 1


def test_pv_day_mini_closed_loop_with_verify_async(g5_tmp):
    predict_wf = "workflow-pv-day-predict-v1"
    train_wf = "workflow-pv-day-train-eval-v1"
    _write_exec(g5_tmp, predict_wf, "exec-day-predict", "pv_day")
    _write_exec(
        g5_tmp,
        train_wf,
        "exec-day-train",
        "pv_day",
        {
            "nodeResults": {
                "qv-stratified_cv_eval-n10": {
                    "status": "success",
                    "outputSummary": {
                        "model_path": "data/models/pv_day_demo/model.pkl",
                        "macro_f1_mean": 0.88,
                    },
                }
            }
        },
    )

    bootstrap_snapshot(
        slot="pv_day",
        idempotency_key="bs-day",
        source_digest="digest-day",
        base_artifact_ref="fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet",
        dataset_profile_ref="pv-day-demo@v1",
        reason="day bootstrap",
    )
    snapshot_id = get_snapshot_chain("pv_day")["snapshot_id"]

    ann = register_annotation_candidate(
        slot="pv_day",
        source_workflow_id=predict_wf,
        source_execution_id="exec-day-predict",
        dataset_profile_ref="pv-day-demo@v1",
        entity_key="site1/device1/branch1",
        boundary_start="2024-06-01",
        boundary_end="2024-06-01",
        suggested_label=3,
    )
    approved = approve_annotation_candidate(
        slot="pv_day",
        annotation_candidate_id=ann["annotation_candidate_id"],
        reviewer="tester",
        idempotency_key="ap-day",
    )
    built = build_snapshot_increment(
        slot="pv_day",
        snapshot_id=snapshot_id,
        base_snapshot_version=1,
        reviewed_annotation_ids=[approved["reviewed_annotation"]["reviewed_annotation_id"]],
        idempotency_key="build-day",
        reason="add day label",
    )
    assert built["chain"]["latest_version"] == 2

    model_candidate = register_model_candidate(
        slot="pv_day",
        source_workflow_id=train_wf,
        source_execution_id="exec-day-train",
        model_artifact_ref="data/models/pv_day_demo/model.pkl",
    )
    job = start_verification_async(
        slot="pv_day",
        model_candidate_id=model_candidate["model_candidate_id"],
        idempotency_key="ver-day-async",
    )
    _write_exec(
        g5_tmp,
        train_wf,
        "exec-day-verify",
        "pv_day",
        {
            "nodeResults": {
                "qv-stratified_cv_eval-n10": {
                    "status": "success",
                    "outputSummary": {"macro_f1_mean": 0.91},
                }
            }
        },
    )
    completed = complete_verification_async(
        job["comparison_id"],
        verification_execution_id="exec-day-verify",
    )
    assert completed["verification"]["verification_source_execution_id"] == "exec-day-verify"
    assert completed["verification"]["passed"] is True

    promoted = promote_model_candidate(
        model_candidate["model_candidate_id"],
        verification_id=completed["verification"]["verification_id"],
        operator="tester",
        reason="day champion",
        expected_registry_version=0,
        idempotency_key="prom-day",
        set_as_production=True,
    )
    assert promoted["registry"]["champion"]["champion_model_ref"] == model_candidate["model_ref"]
    assert get_registry_store().get("pv_day")["registry_version"] == 1
