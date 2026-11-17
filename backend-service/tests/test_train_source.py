"""Train_eval load nodes bind to cumulative freeze or explicit dataset_id."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets import canvas_datasets as cd
from services.slot_datasets import labeled_versions as lv
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.snapshots import include_labeled_version_in_cumulative
from services.slot_datasets.train_source import apply_train_source_to_workflow, resolve_train_source


@pytest.fixture()
def train_tmp(tmp_path, monkeypatch):
    backend_dir = tmp_path
    ds_dir = backend_dir / "data" / "slot_datasets"
    ds_dir.mkdir(parents=True)
    import services.slot_datasets.snapshots as snapshots
    import services.slot_datasets.train_source as train_source

    monkeypatch.setattr(lv, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lv, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(cd, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(cd, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(snapshots, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(snapshots, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(train_source, "_MIN_DAY_FREEZE_ROWS", 1)
    return backend_dir


def _publish(backend_dir: Path, slot: str, rel_path: str) -> str:
    target = backend_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "time,site_id,device_id,branch_id,value,label\n"
        "2024-03-01T08:00:00,s1,d1,101,1.0,1\n",
        encoding="utf-8",
    )
    labeled = lv.publish_labeled_version(slot=slot, file_path=rel_path, status="curated")
    return labeled["dataset_version_id"]


def test_resolve_latest_freeze(train_tmp):
    slot = "pv_point"
    version_id = _publish(train_tmp, slot, "data/a.csv")
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=version_id,
        source="path_a",
        reviewed_at="2026-08-20T10:00:00+00:00",
        freeze=True,
    )
    source = resolve_train_source(slot=slot)
    assert source is not None
    assert source["reason"] == "latest_cumulative_freeze"
    assert source["file_path"].endswith(".csv")
    assert Path(train_tmp / source["file_path"]).is_file()


def test_apply_patches_placeholder_load_csv(train_tmp):
    slot = "pv_point"
    version_id = _publish(train_tmp, slot, "data/b.csv")
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=version_id,
        source="path_a",
        reviewed_at="2026-08-20T10:00:00+00:00",
        freeze=True,
    )
    load = SimpleNamespace(
        data=SimpleNamespace(
            config={
                "functionId": "load_csv",
                "file_path": "data/timeseries_point/test_fixtures/labeled_points.parquet",
            }
        )
    )
    workflow = SimpleNamespace(
        id="workflow-pv-point-train-eval-v1",
        metadata={"slot": slot, "template_role": "train_eval"},
        nodes=[load],
    )
    source = apply_train_source_to_workflow(workflow, {"slot": slot})
    assert source is not None
    assert load.data.config["file_path"] == source["file_path"]
    assert load.data.config["dataset_id"] == source["dataset_id"]


def test_unknown_dataset_id_raises(train_tmp):
    with pytest.raises(SlotDatasetError):
        resolve_train_source(slot="pv_point", dataset_id="missing-id")
