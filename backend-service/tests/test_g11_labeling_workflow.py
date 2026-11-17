"""G11: labeling workflow operators, proposals, load_labeled_dataset, prediction batch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.operator_backends import cluster_profile, emit_label_proposal, emit_prediction_batch, load_labeled_dataset
from services.slot_datasets import canvas_datasets as cd
from services.slot_datasets import label_proposals as lp
from services.slot_datasets.errors import SlotDatasetError


@pytest.fixture()
def g11_env(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend-service"
    slot_dir = backend_dir / "data" / "slot_datasets"
    slot_dir.mkdir(parents=True)

    import services.operator_backends.emit_label_proposal as emit_mod
    import services.operator_backends.emit_prediction_batch as batch_mod
    import services.slot_datasets.dataset_resolver as resolver_mod
    import services.slot_datasets.label_proposals as lp_mod
    import services.slot_datasets.labeled_versions as lv_mod
    import services.slot_datasets.canvas_datasets as cd_mod
    import services.slot_datasets.snapshots as snapshots_mod
    import services.slot_datasets.review_admission as admission_mod

    monkeypatch.setattr(emit_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(batch_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lp_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lp_mod, "_DATA_DIR", slot_dir)
    monkeypatch.setattr(lv_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lv_mod, "_DATA_DIR", slot_dir)
    monkeypatch.setattr(cd_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(cd_mod, "_DATA_DIR", slot_dir)
    monkeypatch.setattr(resolver_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(snapshots_mod, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(snapshots_mod, "_DATA_DIR", slot_dir)
    monkeypatch.setattr(admission_mod, "_BACKEND_DIR", backend_dir)

    return backend_dir


def _sample_frame() -> pd.DataFrame:
    rows = []
    for idx in range(12):
        rows.append(
            {
                "time": f"2024-03-01T08:{idx:02d}:00",
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": 101 if idx % 2 == 0 else 102,
                "value": 1.0 + idx * 0.3,
                "i_cal": 2.0 + idx * 0.1,
            }
        )
    return pd.DataFrame(rows)


def test_cluster_profile_builds_representative_stats():
    frame = _sample_frame()
    labels = [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2]
    result = cluster_profile.execute({}, {"data": frame, "labels": labels})
    profiles = result["cluster_profile"]["clusters"]
    assert set(profiles.keys()) == {"0", "1", "2"}
    assert profiles["0"]["member_count"] == 4


def test_emit_label_proposal_not_trainable(g11_env):
    frame = _sample_frame()
    labels = [0] * 6 + [1] * 6
    profile = cluster_profile.execute({}, {"data": frame, "labels": labels})
    emitted = emit_label_proposal.execute(
        {"slot": "pv_point", "source_execution_id": "exec-test"},
        {"data": frame, "labels": labels, "cluster_profile": profile["cluster_profile"]},
    )
    proposal_id = emitted["proposal_id"]
    assert proposal_id.startswith("lprop-pv_point-")

    trainable = cd.list_trainable_datasets("pv_point")
    assert trainable["labeled_versions"] == []

    with pytest.raises(SlotDatasetError) as excinfo:
        cd.register_trainable_dataset(
            dataset_id=proposal_id,
            kind="labeled_version",
            slot="pv_point",
            ref_id=proposal_id,
            file_path="data/slot_datasets/pv_point/proposal_rows/members-exec-test.csv",
        )
    assert excinfo.value.code == "proposal_not_trainable"


def test_confirm_proposal_then_load_labeled_dataset(g11_env):
    frame = _sample_frame()
    labels = [0] * 6 + [1] * 6
    profile = cluster_profile.execute({}, {"data": frame, "labels": labels})
    emitted = emit_label_proposal.execute(
        {"slot": "pv_point", "source_execution_id": "exec-confirm"},
        {"data": frame, "labels": labels, "cluster_profile": profile["cluster_profile"]},
    )
    proposal_id = emitted["proposal_id"]
    proposal = lp.get_label_proposal("pv_point", proposal_id)
    label_id_map = {
        proposal["clusters"]["0"]["proposed_label_name"]: 1,
        proposal["clusters"]["1"]["proposed_label_name"]: 2,
    }
    confirmed = lp.confirm_label_proposal(
        slot="pv_point",
        proposal_id=proposal_id,
        label_id_map=label_id_map,
    )
    dataset_id = confirmed["dataset_id"]
    loaded = load_labeled_dataset.execute(
        {"slot": "pv_point", "dataset_id": dataset_id},
        {},
    )
    assert "label" in loaded["data"].columns
    assert loaded["dataset_contract"]["slot"] == "pv_point"
    assert loaded["dataset_id"] == dataset_id


def test_load_labeled_dataset_rejects_proposal_id(g11_env):
    frame = _sample_frame()
    labels = [0] * len(frame)
    emitted = emit_label_proposal.execute(
        {"slot": "pv_point", "source_execution_id": "exec-reject"},
        {"data": frame, "labels": labels, "cluster_profile": {"clusters": {}}},
    )
    with pytest.raises(Exception, match="proposal_not_trainable"):
        load_labeled_dataset.execute(
            {"slot": "pv_point", "dataset_id": emitted["proposal_id"]},
            {},
        )


def test_emit_prediction_batch_writes_day_batch(g11_env, monkeypatch):
    import services.operator_backends.emit_prediction_batch as batch_mod

    monkeypatch.setattr(batch_mod, "_BACKEND_DIR", g11_env)

    preds = pd.DataFrame(
        [
            {"site_id": "s1", "device_id": "d1", "branch_id": 1, "time_window": "2024-03-01", "predicted_label": 2},
            {"site_id": "s1", "device_id": "d1", "branch_id": 2, "time_window": "2024-03-02", "predicted_label": 0},
        ]
    )
    result = emit_prediction_batch.execute(
        {
            "slot": "pv_day",
            "prediction_granularity": "day",
            "project_to_review_queue": False,
            "source_workflow_id": "wf-test",
            "source_execution_id": "exec-test",
        },
        {"data": preds},
    )
    batch_path = g11_env / result["batch_path"]
    assert batch_path.is_file()
    payload = json.loads(batch_path.read_text(encoding="utf-8"))
    assert payload["prediction_granularity"] == "day"
    assert len(payload["units"]) == 2

# @AI_GENERATED: pv_tsc proposal confirmation keeps device-day rows unique and records one event
def test_tsc_proposal_confirm_and_load_records_one_cumulative_event(g11_env, monkeypatch):
    from services.operator_backends import emit_tsc_label_proposal
    from services.slot_datasets.snapshots import get_cumulative_ledger

    monkeypatch.setattr(emit_tsc_label_proposal, "_BACKEND_DIR", g11_env)
    times = pd.date_range("2024-03-05T00:00:00Z", periods=12, freq="5min")
    frame = pd.DataFrame(
        {
            "time": times,
            "site_id": ["s1"] * 12,
            "device_id": ["d1"] * 12,
            "branch_id": ["b1"] * 12,
            "value": [float(index) for index in range(12)],
            "i_cal": [float(index + 10) for index in range(12)],
        }
    )
    emitted = emit_tsc_label_proposal.execute(
        {
            "slot": "pv_tsc",
            "source_workflow_id": "workflow-pv-tsc-label-v1",
            "source_execution_id": "exec-tsc-confirm",
        },
        {
            "data": frame,
            "predictions": [
                {
                    "site_id": "s1",
                    "device_id": "d1",
                    "branch_id": "b1",
                    "target_day": "2024-03-05",
                    "predicted_label": 1,
                    "confidence": 0.91,
                    "n_windows": 3,
                    "aggregation": "majority_vote",
                    "model_name": "multirocket",
                    "per_window_details": [
                        {"window_index": 0, "predicted_label": 1},
                        {"window_index": 1, "predicted_label": 1},
                        {"window_index": 2, "predicted_label": 0},
                    ],
                }
            ],
        },
    )
    proposal_id = emitted["proposal_id"]
    confirmed = lp.confirm_label_proposal(
        slot="pv_tsc",
        proposal_id=proposal_id,
        label_id_map={"label_1": 1},
    )
    loaded = load_labeled_dataset.execute(
        {"slot": "pv_tsc", "dataset_id": confirmed["dataset_id"]},
        {},
    )
    assert len(loaded["data"]) == len(frame)
    assert loaded["dataset_contract"]["slot"] == "pv_tsc"
    assert get_cumulative_ledger("pv_tsc")["event_count"] == 1

    with pytest.raises(SlotDatasetError) as replay_error:
        lp.confirm_label_proposal(
            slot="pv_tsc",
            proposal_id=proposal_id,
            label_id_map={"label_1": 1},
        )
    assert replay_error.value.code == "proposal_already_confirmed"
    assert get_cumulative_ledger("pv_tsc")["event_count"] == 1
# @AI_GENERATED: end