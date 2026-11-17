"""G10-S3: cumulative snapshot registration after labeled-version build."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets import canvas_datasets as cd
from services.slot_datasets import labeled_versions as lv
from services.slot_datasets.snapshots import (
    build_labeled_versions_snapshot,
    include_labeled_version_in_cumulative,
)


@pytest.fixture()
def g10_cumulative_tmp(tmp_path, monkeypatch):
    backend_dir = tmp_path
    ds_dir = backend_dir / "data" / "slot_datasets"
    ds_dir.mkdir(parents=True)
    import services.slot_datasets.snapshots as snapshots

    monkeypatch.setattr(lv, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(lv, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(cd, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(cd, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(snapshots, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(snapshots, "_DATA_DIR", ds_dir)
    return backend_dir


def _write_labeled_csv(backend_dir: Path, rel_path: str, label: int) -> Path:
    target = backend_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "time,site_id,device_id,branch_id,value,label\n"
        f"2024-03-01T08:00:00,s1,d1,101,1.0,{label}\n",
        encoding="utf-8",
    )
    return target


def _publish_and_register(backend_dir: Path, slot: str, rel_path: str, label: int) -> str:
    _write_labeled_csv(backend_dir, rel_path, label=label)
    labeled = lv.publish_labeled_version(slot=slot, file_path=rel_path, status="curated")
    cd.register_trainable_dataset(
        dataset_id=labeled["dataset_version_id"],
        kind="labeled_version",
        slot=slot,
        ref_id=labeled["dataset_version_id"],
        file_path=rel_path,
        name=f"box-{label}",
    )
    return labeled["dataset_version_id"]


def test_build_v1_and_v2_register_two_cumulative_rows_without_changing_labeled_group(g10_cumulative_tmp):
    slot = "pv_point"
    version_a = _publish_and_register(
        g10_cumulative_tmp,
        slot,
        "data/labeled/a.csv",
        1,
    )
    version_b = _publish_and_register(
        g10_cumulative_tmp,
        slot,
        "data/labeled/b.csv",
        2,
    )

    before = cd.list_trainable_datasets(slot)
    assert len(before["labeled_versions"]) == 2
    assert before["cumulative_snapshots"] == []

    include_labeled_version_in_cumulative(slot=slot, dataset_version_id=version_a)
    build_labeled_versions_snapshot(
        slot=slot,
        idempotency_key="build-v1",
        reason="first cumulative build",
    )

    include_labeled_version_in_cumulative(slot=slot, dataset_version_id=version_b)
    build_labeled_versions_snapshot(
        slot=slot,
        idempotency_key="build-v2",
        reason="second cumulative build",
    )

    after = cd.list_trainable_datasets(slot)
    assert len(after["labeled_versions"]) == 2
    assert len(after["cumulative_snapshots"]) == 2
    cumulative_ids = [row["dataset_id"] for row in after["cumulative_snapshots"]]
    assert all(str(item).startswith("snap-pv_point-") for item in cumulative_ids)
    assert len(set(cumulative_ids)) == 2
    assert after["cumulative_snapshots"][0]["is_latest"] is True
    assert after["cumulative_snapshots"][1]["is_latest"] is False
    assert (g10_cumulative_tmp / after["cumulative_snapshots"][0]["file_path"]).is_file()
    assert (g10_cumulative_tmp / after["cumulative_snapshots"][1]["file_path"]).is_file()


def test_freeze_parquet_keep_last_label_on_entity_time(g10_cumulative_tmp):
    import pandas as pd

    slot = "pv_day"
    first_rel = "data/labeled/first.parquet"
    second_rel = "data/labeled/second.parquet"
    columns = {
        "time": ["2024-03-01T08:00:00Z"],
        "site_id": ["s1"],
        "device_id": ["d1"],
        "branch_id": [101],
        "value": [1.0],
    }
    first = g10_cumulative_tmp / first_rel
    first.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({**columns, "label": [1]}).to_parquet(first, index=False)
    pd.DataFrame({**columns, "label": [9]}).to_parquet(g10_cumulative_tmp / second_rel, index=False)

    version_a = lv.publish_labeled_version(slot=slot, file_path=first_rel, status="curated")
    version_b = lv.publish_labeled_version(slot=slot, file_path=second_rel, status="curated")
    include_labeled_version_in_cumulative(slot=slot, dataset_version_id=version_a["dataset_version_id"])
    include_labeled_version_in_cumulative(slot=slot, dataset_version_id=version_b["dataset_version_id"])
    freeze = build_labeled_versions_snapshot(
        slot=slot,
        idempotency_key="gold-keep-last",
        reason="gold overwrites earlier sample",
    )
    artifact = freeze["artifact_ref"]
    assert artifact.endswith(".parquet")
    snap = pd.read_parquet(g10_cumulative_tmp / artifact)
    assert len(snap) == 1
    assert int(snap.iloc[0]["label"]) == 9


def test_freeze_csv_then_parquet_coerces_branch_id(g10_cumulative_tmp):
    import pandas as pd

    slot = "pv_day"
    csv_rel = "data/labeled/sample.csv"
    parquet_rel = "data/labeled/gold.parquet"
    csv_path = g10_cumulative_tmp / csv_rel
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "time,site_id,device_id,branch_id,value,label\n"
        "2024-03-01T08:00:00Z,s1,d1,1,1.0,1\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        {
            "time": ["2024-03-01T08:00:00Z"],
            "site_id": ["s1"],
            "device_id": ["d1"],
            "branch_id": [1],
            "value": [1.0],
            "label": [9],
        }
    ).to_parquet(g10_cumulative_tmp / parquet_rel, index=False)
    version_a = lv.publish_labeled_version(slot=slot, file_path=csv_rel, status="curated")
    version_b = lv.publish_labeled_version(slot=slot, file_path=parquet_rel, status="curated")
    include_labeled_version_in_cumulative(slot=slot, dataset_version_id=version_a["dataset_version_id"])
    include_labeled_version_in_cumulative(slot=slot, dataset_version_id=version_b["dataset_version_id"])
    freeze = build_labeled_versions_snapshot(slot=slot, idempotency_key="mixed-dtypes", reason="csv+parquet")
    snap = pd.read_parquet(g10_cumulative_tmp / freeze["artifact_ref"])
    assert len(snap) == 1
    assert int(snap.iloc[0]["label"]) == 9
