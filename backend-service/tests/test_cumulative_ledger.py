"""Cumulative ledger: source + reviewed_at + freeze-by-cutoff."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets import canvas_datasets as cd
from services.slot_datasets import labeled_versions as lv
from services.slot_datasets.snapshots import (
    SOURCE_DAILY_REVIEW,
    SOURCE_PATH_A,
    freeze_cumulative_at,
    get_cumulative_ledger,
    include_labeled_version_in_cumulative,
)
import pandas as pd


@pytest.fixture()
def ledger_tmp(tmp_path, monkeypatch):
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


def _publish(backend_dir: Path, slot: str, rel_path: str, label: int) -> str:
    target = backend_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "time,site_id,device_id,branch_id,value,label\n"
        f"2024-03-01T08:00:00,s1,d1,101,1.0,{label}\n",
        encoding="utf-8",
    )
    labeled = lv.publish_labeled_version(slot=slot, file_path=rel_path, status="curated")
    return labeled["dataset_version_id"]


def test_ledger_records_source_and_reviewed_at(ledger_tmp):
    slot = "pv_point"
    version_a = _publish(ledger_tmp, slot, "data/a.csv", 1)
    version_b = _publish(ledger_tmp, slot, "data/b.csv", 2)

    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=version_a,
        source=SOURCE_PATH_A,
        reviewed_at="2026-08-20T10:00:00+00:00",
        freeze=True,
    )
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=version_b,
        source=SOURCE_DAILY_REVIEW,
        reviewed_at="2026-08-25T12:00:00+00:00",
        freeze=True,
    )

    ledger = get_cumulative_ledger(slot)
    assert ledger["event_count"] == 2
    sources = [item["source"] for item in ledger["events"]]
    assert sources == [SOURCE_PATH_A, SOURCE_DAILY_REVIEW]
    assert ledger["events"][0]["reviewed_at"] == "2026-08-20T10:00:00+00:00"
    assert ledger["latest_freeze"]["reviewed_at_cutoff"] == "2026-08-25T12:00:00+00:00"
    assert str(ledger["latest_freeze"].get("freeze_id") or "").startswith("snap-pv_point-")


def test_freeze_cutoff_excludes_later_review_events(ledger_tmp):
    slot = "pv_day"
    version_a = _publish(ledger_tmp, slot, "data/a.csv", 1)
    version_b = _publish(ledger_tmp, slot, "data/b.csv", 2)
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=version_a,
        source=SOURCE_PATH_A,
        reviewed_at="2026-08-20T10:00:00+00:00",
    )
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=version_b,
        source=SOURCE_DAILY_REVIEW,
        reviewed_at="2026-08-25T12:00:00+00:00",
    )

    freeze = freeze_cumulative_at(slot=slot, reviewed_at_cutoff="2026-08-20T10:00:00+00:00")
    included = freeze["chain"]["versions"][-1]["included_labeled_version_ids"]
    assert included == [version_a]
    freeze_id = str(freeze.get("freeze_id") or freeze["chain"]["versions"][-1].get("freeze_id") or "")
    assert freeze_id.startswith("snap-pv_day-")
    replay = freeze_cumulative_at(slot=slot, reviewed_at_cutoff="2026-08-20T10:00:00+00:00")
    assert replay["idempotent_replay"] is True


def test_pv_point_freeze_excludes_cluster_day_boxes(ledger_tmp):
    slot = "pv_point"
    gold_id = _publish(ledger_tmp, slot, "data/slot_datasets/pv_point/gold/keep.csv", 9)
    cluster_id = _publish(
        ledger_tmp,
        slot,
        "data/slot_datasets/pv_point/confirmed/lprop-pv_point-x/labeled.csv",
        1,
    )
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=gold_id,
        source=SOURCE_PATH_A,
        reviewed_at="2026-08-20T10:00:00+00:00",
    )
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=cluster_id,
        source=SOURCE_PATH_A,
        reviewed_at="2026-08-21T10:00:00+00:00",
    )

    freeze = freeze_cumulative_at(slot=slot, reviewed_at_cutoff="2026-08-21T10:00:00+00:00")
    version = freeze["chain"]["versions"][-1]
    assert version["included_labeled_version_ids"] == [gold_id]
    assert version["excluded_cluster_day_version_ids"] == [cluster_id]
    artifact = ledger_tmp / version["artifact_ref"]
    frame = pd.read_csv(artifact)
    assert set(frame["label"].astype(int)) == {9}


def test_pv_day_freeze_keeps_cluster_confirm(ledger_tmp):
    slot = "pv_day"
    cluster_id = _publish(
        ledger_tmp,
        slot,
        "data/slot_datasets/pv_day/confirmed/lprop-pv_day-x/labeled.csv",
        1,
    )
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=cluster_id,
        source=SOURCE_PATH_A,
        reviewed_at="2026-08-20T10:00:00+00:00",
        freeze=True,
    )
    ledger = get_cumulative_ledger(slot)
    included = ledger["latest_freeze"]["included_labeled_version_ids"]
    assert included == [cluster_id]


def test_freeze_drops_rows_on_or_after_time_wall(ledger_tmp):
    from services.slot_datasets.time_wall import save_time_wall

    slot = "pv_day"
    save_time_wall(
        slot,
        {
            "holdout_start_day": "2024-03-09",
            "holdout_end_day": "2024-03-10",
            "fraction": 0.2,
            "train_end_day": "2024-03-08",
        },
        backend_dir=ledger_tmp,
    )
    target = ledger_tmp / "data/days.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = ["time,site_id,device_id,branch_id,value,label"]
    for day in range(1, 11):
        rows.append(f"2024-03-{day:02d}T08:00:00,s1,d1,101,1.0,{day % 3}")
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")
    labeled = lv.publish_labeled_version(slot=slot, file_path="data/days.csv", status="curated")
    include_labeled_version_in_cumulative(
        slot=slot,
        dataset_version_id=labeled["dataset_version_id"],
        source=SOURCE_PATH_A,
        reviewed_at="2026-08-20T10:00:00+00:00",
    )

    freeze = freeze_cumulative_at(slot=slot, reviewed_at_cutoff="2026-08-20T10:00:00+00:00")
    version = freeze["chain"]["versions"][-1]
    artifact = ledger_tmp / version["artifact_ref"]
    frame = pd.read_csv(artifact)
    days = pd.to_datetime(frame["time"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
    assert days.max() == "2024-03-08"
    assert "2024-03-09" not in set(days)
    assert "2024-03-10" not in set(days)
    assert int(version["time_wall"]["dropped_row_count"]) == 2
    assert freeze["sample_time_before"] == "2024-03-09"
