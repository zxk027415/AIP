# -*- coding: utf-8 -*-
"""选中喂数源必须真正进入 loop_demo 回放，而不是只写 feed_source.json。

覆盖：读选中 parquet、日历游标、源切换重置、悬空引用 fail-closed、
已选外部源时不 ensure 内置 7 日、pv_tsc 回放不写生产 ledger。
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from services.slot_datasets import feed_sources as fs
from services.slot_datasets import loop_demo as ld
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.observability_ledger import OCCUPANCY_READY


DAY_A = "2021-11-18"
DAY_B = "2021-02-01"


def _write_ext(path, *, n_points, day, label=None):
    rows = []
    for step in range(n_points):
        row = {
            "site_id": "s",
            "device_id": "d1",
            "branch_id": "1",
            "time": pd.Timestamp(f"{day} 06:00:00") + pd.Timedelta(minutes=5 * step),
            "date": day,
            "value": 8.0,
            "i_cal": 8.0,
        }
        if label is not None:
            row["label"] = label
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_sel(root, slot, dataset_ref):
    folder = root / "data" / "slot_datasets" / slot
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "feed_source.json").write_text(
        json.dumps({"slot": slot, "dataset_ref": dataset_ref}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_selected_source_is_read_not_builtin_unlabeled(tmp_path, monkeypatch):
    src = tmp_path / "ext.parquet"
    _write_ext(src, n_points=10, day=DAY_A)
    monkeypatch.setattr(fs, "_resolve_ref_path", lambda ref: src)
    _write_sel(tmp_path, "pv_day", "datasets/ext.parquet")

    result = ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)

    unlabeled = tmp_path / "data/slot_datasets/pv_day/loop_demo/unlabeled.parquet"
    assert not unlabeled.is_file(), "已选外部源时不得去读/生成内置 unlabeled.parquet"
    assert result.get("fed_day") is None
    assert result.get("skipped_reason"), "10 点低于 occupancy，应跳过并解释"
    cursor = result.get("cursor") or {}
    assert cursor.get("dataset_ref") == "datasets/ext.parquet"
    assert DAY_A in list(cursor.get("days") or [])
    assert "2024-06-03" not in list(cursor.get("days") or []), "日历必须来自选中源，不是 DEMO_START"


def test_missing_selected_file_fail_closed(tmp_path):
    _write_sel(tmp_path, "pv_day", "datasets/__definitely_missing__.parquet")
    with pytest.raises(SlotDatasetError) as exc:
        ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)
    assert exc.value.code in {"dataset_not_found", "source_not_found", "scope_error", "missing_unlabeled"}


def test_source_switch_resets_arrived_and_fed_days(tmp_path, monkeypatch):
    src_a = tmp_path / "a.parquet"
    src_b = tmp_path / "b.parquet"
    _write_ext(src_a, n_points=OCCUPANCY_READY, day=DAY_A)
    _write_ext(src_b, n_points=OCCUPANCY_READY, day=DAY_B)

    def resolve(ref: str):
        return src_b if "b.parquet" in str(ref) else src_a

    monkeypatch.setattr(fs, "_resolve_ref_path", resolve)
    _write_sel(tmp_path, "pv_day", "datasets/a.parquet")
    first = ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)
    assert first.get("fed_day") == DAY_A

    _write_sel(tmp_path, "pv_day", "datasets/b.parquet")
    second = ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)
    assert second.get("fed_day") == DAY_B
    cursor = second.get("cursor") or {}
    assert list(cursor.get("fed_days") or []) == [DAY_B]
    arrived = pd.read_parquet(tmp_path / "data/slot_datasets/pv_day/loop_demo/arrived.parquet")
    dates = set(arrived["date"].astype(str).str.slice(0, 10))
    assert dates == {DAY_B}, "换源后不得把旧源 arrived 混进来"


def test_point_path_feeds_one_row_from_selected_calendar(tmp_path, monkeypatch):
    src = tmp_path / "ext.parquet"
    _write_ext(src, n_points=4, day=DAY_A, label=1)
    monkeypatch.setattr(fs, "_resolve_ref_path", lambda ref: src)
    _write_sel(tmp_path, "pv_point", "datasets/ext.parquet")

    ld.feed_next_day("pv_point", backend_dir=tmp_path, skip_ensure=True)
    ld.feed_next_day("pv_point", backend_dir=tmp_path, skip_ensure=True)
    arrived = pd.read_parquet(tmp_path / "data/slot_datasets/pv_point/loop_demo/arrived.parquet")
    assert len(arrived) == 2
    cursor = ld.load_cursor("pv_point", backend_dir=tmp_path)
    assert DAY_A not in list(cursor.get("fed_days") or [])
    assert int((cursor.get("point_progress") or {}).get(DAY_A) or 0) == 2
    assert int((cursor.get("point_totals") or {}).get(DAY_A) or 0) == 4


def test_run_next_does_not_ensure_builtin_when_selected(tmp_path, monkeypatch):
    src = tmp_path / "ext.parquet"
    _write_ext(src, n_points=10, day=DAY_A)
    monkeypatch.setattr(fs, "_resolve_ref_path", lambda ref: src)
    _write_sel(tmp_path, "pv_day", "datasets/ext.parquet")

    ld.run_next_demo_day("pv_day", backend_dir=tmp_path)

    folder = tmp_path / "data/slot_datasets/pv_day/loop_demo"
    assert not (folder / "unlabeled.parquet").is_file()
    assert not (folder / "gold.parquet").is_file()


def test_tsc_run_next_does_not_write_production_ledger(tmp_path, monkeypatch):
    src = tmp_path / "ext.parquet"
    _write_ext(src, n_points=260, day=DAY_A, label=0)
    monkeypatch.setattr(fs, "_resolve_ref_path", lambda ref: src)
    _write_sel(tmp_path, "pv_tsc", "datasets/ext.parquet")

    cycle = ld.run_next_demo_day("pv_tsc", backend_dir=tmp_path)
    assert cycle.get("fed_day") == DAY_A
    ledger = tmp_path / "data/slot_datasets/pv_tsc/observability/ledger.json"
    assert not ledger.is_file(), "pv_tsc 回放不得写生产 observability ledger"
    arrived = tmp_path / "data/slot_datasets/pv_tsc/loop_demo/arrived.parquet"
    assert arrived.is_file(), "回放应落在独立 loop_demo 通道"
