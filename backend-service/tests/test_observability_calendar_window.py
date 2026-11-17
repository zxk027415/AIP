"""Calendar window must follow detect watermark, not the machine clock."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets import observability_ledger as ob


@pytest.fixture()
def ledger_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "_BACKEND_DIR", tmp_path)
    return tmp_path


def test_default_calendar_range_uses_watermark_not_today(ledger_tmp):
    path = ledger_tmp / "data/slot_datasets/pv_day/observability/ledger.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"slot": "pv_day", "watermark_day": "2021-11-18", "cells": {}}),
        encoding="utf-8",
    )
    start, end = ob.default_calendar_range("pv_day")
    assert end == "2021-11-18"
    assert start == "2021-11-12"
    assert date.fromisoformat(end).year != date.today().year or end == "2021-11-18"


def test_calendar_grid_without_range_anchors_watermark(ledger_tmp, monkeypatch):
    path = ledger_tmp / "data/slot_datasets/pv_day/observability/ledger.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"slot": "pv_day", "watermark_day": "2021-11-18", "cells": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ob,
        "occupancy_by_device_day",
        lambda _slot, _a, _b: {"s|d|1": {"2021-11-18": 10}},
    )
    body = ob.calendar_grid("pv_day")
    assert body["from"] == "2021-11-12"
    assert body["to"] == "2021-11-18"
    assert body["watermark_day"] == "2021-11-18"
    assert "2026" not in body["from"]


def test_anchor_falls_back_to_source_max_not_today(ledger_tmp, monkeypatch):
    monkeypatch.setattr(
        ob,
        "_read_source_frame",
        lambda _slot: pd.DataFrame({"time": pd.to_datetime(["2022-02-04T00:00:00+00:00"])}),
    )
    assert ob.anchor_calendar_day("pv_point").isoformat() == "2022-02-04"


def test_expire_waiting_uses_watermark_not_gold_max():
    from datetime import date

    cells = {
        "s|d|1|2024-03-01": {
            "device_key": "s|d|1",
            "date": "2024-03-01",
            "status": "waiting",
            "wait_started_on": "2024-03-01",
        },
        "s|d|2|2024-03-03": {
            "device_key": "s|d|2",
            "date": "2024-03-03",
            "status": "waiting",
            "wait_started_on": "2024-03-03",
        },
    }
    skipped = ob._expire_waiting_cells(cells, date(2024, 3, 4))
    assert cells["s|d|1|2024-03-01"]["status"] == "skipped"
    assert cells["s|d|1|2024-03-01"]["skip_reason"] == "expired_incomplete"
    assert cells["s|d|2|2024-03-03"]["status"] == "waiting"
    assert "s|d|1" in skipped
    assert "s|d|2" not in skipped

# @AI_GENERATED: pv_tsc read-only observability contract
def test_pv_tsc_observability_is_daily_and_read_only(ledger_tmp, monkeypatch):
    from services.slot_datasets.errors import SlotDatasetError

    times = pd.date_range("2024-03-05T00:00:00Z", periods=288, freq="5min")
    frame = pd.DataFrame(
        {
            "site_id": ["s1"] * 288,
            "device_id": ["d1"] * 288,
            "branch_id": ["b1"] * 288,
            "time": times,
            "i_cal": [float(index) for index in range(288)],
        }
    )
    monkeypatch.setattr(ob, "_read_source_frame", lambda _slot: frame.copy())

    status = ob.observability_status("pv_tsc")
    assert status["readonly"] is True
    assert status["clock"]["kind"] == "business_day"
    assert status["clock"]["day"] == "2024-03-05"

    grid = ob.calendar_grid("pv_tsc", "2024-03-05", "2024-03-05")
    assert grid["device_total"] == 1
    cell = grid["rows"][0]["cells"][0]
    assert cell["arrived_count"] == 288
    assert cell["expected_count"] == 288
    assert cell["completeness"] == 1.0

    with pytest.raises(SlotDatasetError) as advance_error:
        ob.advance_watermark_day("pv_tsc")
    assert advance_error.value.code == "read_only_slot"

    with pytest.raises(SlotDatasetError) as detect_error:
        ob.record_manual_detect("pv_tsc", device_key="s1|d1|b1", day="2024-03-05")
    assert detect_error.value.code == "read_only_slot"
# @AI_GENERATED: end