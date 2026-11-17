"""G10-S0: labeled dataset version store."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets import labeled_versions as lv


@pytest.fixture()
def g10_tmp(tmp_path, monkeypatch):
    ds_dir = tmp_path / "slot_datasets"
    ds_dir.mkdir()
    monkeypatch.setattr(lv, "_DATA_DIR", ds_dir)
    monkeypatch.setattr(lv, "_BACKEND_DIR", tmp_path)
    return tmp_path


def test_missing_slot_rejected(g10_tmp):
    with pytest.raises(SlotDatasetError) as exc:
        lv.publish_labeled_version(slot="", file_path="data/demo.csv")
    assert exc.value.code == "missing_slot"


def test_load_forecast_slot_rejected(g10_tmp):
    sample = g10_tmp / "sample.csv"
    sample.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(SlotDatasetError) as exc:
        lv.publish_labeled_version(slot="load_forecast", file_path="sample.csv")
    assert exc.value.code == "invalid_slot"


def test_benchmark_slot_rejected(g10_tmp):
    sample = g10_tmp / "sample.csv"
    sample.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(SlotDatasetError) as exc:
        lv.publish_labeled_version(slot="benchmark_pvdaq_demo", file_path="sample.csv")
    assert exc.value.code == "invalid_slot"


def test_pv_point_list_does_not_include_pv_day(g10_tmp):
    day_csv = g10_tmp / "day.csv"
    point_csv = g10_tmp / "point.csv"
    day_csv.write_text("day\n1\n", encoding="utf-8")
    point_csv.write_text("point\n1\n", encoding="utf-8")

    lv.publish_labeled_version(slot="pv_day", file_path="day.csv")
    lv.publish_labeled_version(slot="pv_point", file_path="point.csv")

    point_rows = lv.list_labeled_versions("pv_point")
    day_rows = lv.list_labeled_versions("pv_day")

    assert len(point_rows) == 1
    assert point_rows[0]["slot"] == "pv_point"
    assert all(row["slot"] == "pv_point" for row in point_rows)
    assert len(day_rows) == 1
    assert day_rows[0]["slot"] == "pv_day"


def test_two_publish_allocates_two_distinct_ids(g10_tmp):
    first_csv = g10_tmp / "first.csv"
    second_csv = g10_tmp / "second.csv"
    first_csv.write_text("x\n1\n", encoding="utf-8")
    second_csv.write_text("y\n2\n", encoding="utf-8")

    first = lv.publish_labeled_version(slot="pv_point", file_path="first.csv")
    second = lv.publish_labeled_version(slot="pv_point", file_path="second.csv")

    assert first["dataset_version_id"] != second["dataset_version_id"]
    assert first["dataset_version_id"].startswith("lds-pv_point-")
    assert second["dataset_version_id"].startswith("lds-pv_point-")

    rows = lv.list_labeled_versions("pv_point")
    assert len(rows) == 2
    ids = {row["dataset_version_id"] for row in rows}
    assert ids == {first["dataset_version_id"], second["dataset_version_id"]}


def test_persisted_file_path_is_relative_to_backend(g10_tmp):
    sample = g10_tmp / "data" / "uploads" / "labeled.csv"
    sample.parent.mkdir(parents=True)
    sample.write_text("label\n0\n", encoding="utf-8")

    record = lv.publish_labeled_version(slot="pv_day", file_path="data/uploads/labeled.csv")

    assert record["file_path"] == "data/uploads/labeled.csv"
    assert not Path(record["file_path"]).is_absolute()
    assert record["status"] == "curated"
    assert len(record["content_sha256"]) == 64
