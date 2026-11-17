"""Execution history index: latest + per execution_id lookup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.execution_history.store import (
    load_execution_by_id,
    load_execution_record,
    load_latest_execution,
    persist_execution_record,
)
from services.slot_governance.provenance import ProvenanceError, validate_execution_provenance
from tests._execution_history_test_utils import patch_execution_history_dirs, write_execution_record


@pytest.fixture()
def history_tmp(tmp_path, monkeypatch):
    history_dir = tmp_path / "execution_history"
    history_dir.mkdir()
    patch_execution_history_dirs(monkeypatch, history_dir)
    return history_dir


def test_persist_indexes_by_execution_id(history_tmp):
    wf = "workflow-pv-point-train-eval-v1"
    first = {
        "execution_id": "exec-a",
        "workflow_id": wf,
        "status": "success",
        "slot": "pv_point",
        "governance_eligible": True,
        "nodeResults": {
            "pp-train": {"outputSummary": {"model_path": "data/models/a/model.pt"}},
        },
    }
    second = {
        "execution_id": "exec-b",
        "workflow_id": wf,
        "status": "success",
        "slot": "pv_point",
        "governance_eligible": True,
        "nodeResults": {
            "pp-train": {"outputSummary": {"model_path": "data/models/b/model.pt"}},
        },
    }
    persist_execution_record(first)
    persist_execution_record(second)

    latest = load_latest_execution(wf)
    assert latest is not None
    assert latest["execution_id"] == "exec-b"

    indexed_a = load_execution_by_id("exec-a")
    indexed_b = load_execution_by_id("exec-b")
    assert indexed_a is not None and indexed_a["execution_id"] == "exec-a"
    assert indexed_b is not None and indexed_b["execution_id"] == "exec-b"


def test_provenance_uses_index_not_latest(history_tmp):
    wf = "workflow-pv-point-train-eval-v1"
    write_execution_record(
        {
            "execution_id": "exec-old",
            "workflow_id": wf,
            "status": "success",
            "slot": "pv_point",
            "governance_eligible": True,
            "nodeResults": {
                "pp-train": {"outputSummary": {"model_path": "data/models/old/model.pt"}},
            },
        }
    )
    write_execution_record(
        {
            "execution_id": "exec-new",
            "workflow_id": wf,
            "status": "success",
            "slot": "pv_point",
            "governance_eligible": True,
            "nodeResults": {
                "pp-train": {"outputSummary": {"model_path": "data/models/new/model.pt"}},
            },
        }
    )

    prov = validate_execution_provenance(
        slot="pv_point",
        source_workflow_id=wf,
        source_execution_id="exec-old",
        model_artifact_ref="data/models/old/model.pt",
    )
    assert prov["source_execution_id"] == "exec-old"
    assert prov["model_artifact_ref"].endswith("old/model.pt")

    loaded = load_execution_record(wf, "exec-old")
    assert loaded is not None
    assert loaded["execution_id"] == "exec-old"


def test_reject_governance_ineligible_execution(history_tmp):
    wf = "workflow-pv-point-train-eval-v1"
    write_execution_record(
        {
            "execution_id": "exec-bench",
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
        validate_execution_provenance(
            slot="pv_point",
            source_workflow_id=wf,
            source_execution_id="exec-bench",
            model_artifact_ref="data/models/demo/model.pt",
        )
    assert exc.value.code == "governance_not_eligible"
