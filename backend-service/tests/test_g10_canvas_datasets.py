"""G10-S1: canvas trainable dataset registry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets import canvas_datasets as cd


@pytest.fixture()
def g10_canvas_tmp(tmp_path, monkeypatch):
    ds_dir = tmp_path / "slot_datasets"
    ds_dir.mkdir()
    monkeypatch.setattr(cd, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(cd, "_BACKEND_DIR", tmp_path)
    return tmp_path


def _register_labeled(slot: str, dataset_id: str, ref_id: str, file_path: str) -> dict:
    return cd.register_trainable_dataset(
        dataset_id=dataset_id,
        kind="labeled_version",
        slot=slot,
        ref_id=ref_id,
        file_path=file_path,
        name=f"name-{dataset_id}",
    )


def _register_snapshot(slot: str, version: int, file_path: str) -> dict:
    dataset_id = f"snap-{slot}-v{version}"
    return cd.register_trainable_dataset(
        dataset_id=dataset_id,
        kind="cumulative_snapshot",
        slot=slot,
        ref_id=dataset_id,
        file_path=file_path,
        name=f"snapshot v{version}",
    )


def test_same_slot_four_entries_grouped(g10_canvas_tmp):
    _register_labeled("pv_point", "lds-pv_point-a", "lds-pv_point-a", "data/a.csv")
    _register_labeled("pv_point", "lds-pv_point-b", "lds-pv_point-b", "data/b.csv")
    _register_snapshot("pv_point", 1, "data/snapshots/v1.csv")
    _register_snapshot("pv_point", 2, "data/snapshots/v2.csv")

    result = cd.list_trainable_datasets("pv_point")

    assert len(result["labeled_versions"]) == 2
    assert len(result["cumulative_snapshots"]) == 2
    assert result["labeled_versions"][0]["is_latest"] is True
    assert result["labeled_versions"][1]["is_latest"] is False
    assert result["cumulative_snapshots"][0]["dataset_id"] == "snap-pv_point-v2"
    assert result["cumulative_snapshots"][0]["is_latest"] is True
    assert result["cumulative_snapshots"][1]["dataset_id"] == "snap-pv_point-v1"


def test_slot_filtering(g10_canvas_tmp):
    _register_labeled("pv_day", "lds-pv_day-a", "lds-pv_day-a", "data/day.csv")
    _register_labeled("pv_point", "lds-pv_point-a", "lds-pv_point-a", "data/point.csv")

    day_result = cd.list_trainable_datasets("pv_day")
    point_result = cd.list_trainable_datasets("pv_point")

    assert len(day_result["labeled_versions"]) == 1
    assert day_result["labeled_versions"][0]["slot"] == "pv_day"
    assert len(point_result["labeled_versions"]) == 1
    assert point_result["labeled_versions"][0]["slot"] == "pv_point"


def test_dataset_path_conflict_rejected(g10_canvas_tmp):
    cd.register_trainable_dataset(
        dataset_id="lds-pv_point-conflict",
        kind="labeled_version",
        slot="pv_point",
        ref_id="lds-pv_point-conflict",
        file_path="data/first.csv",
    )

    with pytest.raises(SlotDatasetError) as exc:
        cd.register_trainable_dataset(
            dataset_id="lds-pv_point-conflict",
            kind="labeled_version",
            slot="pv_point",
            ref_id="lds-pv_point-conflict",
            file_path="data/second.csv",
        )
    assert exc.value.code == "dataset_path_conflict"


def test_snapshot_v2_does_not_change_v1_path(g10_canvas_tmp):
    first = _register_snapshot("pv_point", 1, "data/snapshots/v1.csv")
    second = _register_snapshot("pv_point", 2, "data/snapshots/v2.csv")

    result = cd.list_trainable_datasets("pv_point")
    by_id = {row["dataset_id"]: row for row in result["cumulative_snapshots"]}

    assert by_id["snap-pv_point-v1"]["file_path"] == first["file_path"] == "data/snapshots/v1.csv"
    assert by_id["snap-pv_point-v2"]["file_path"] == second["file_path"] == "data/snapshots/v2.csv"
