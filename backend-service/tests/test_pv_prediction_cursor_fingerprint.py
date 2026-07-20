# -*- coding: utf-8 -*-
"""预测游标指纹对齐：换数据源时自动重置，避免跨时间线串扰。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import services.scheduler.tasks.pv_fault_tasks as pv_tasks
from services.iterative_labeling.review_session import _review_id_for_prediction_batch


def test_persisted_scheduler_timestamp_is_explicit_utc():
    parsed = datetime.fromisoformat(pv_tasks._utc_now_iso())
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def test_review_id_preserves_prediction_timestamp():
    assert (
        _review_id_for_prediction_batch("pred-20260720092117-9348327a")
        == "rev-20260720092117-9348327a"
    )


def test_prediction_model_lookup_uses_production_pointer(monkeypatch):
    class FakeCumulativeTrainingService:
        def __init__(self, slot):
            assert slot == "pv_fault"

        def get_production_model_ref(self):
            return "pv_fault_rfc_20260720T080000Z_abc123"

    monkeypatch.setattr(pv_tasks, "CumulativeTrainingService", FakeCumulativeTrainingService)
    assert pv_tasks._production_model_ref() == "pv_fault_rfc_20260720T080000Z_abc123"


def test_scheduler_prediction_creates_review_session(monkeypatch):
    captured = {}

    class FakeRegistry:
        def __init__(self, slot):
            assert slot == "pv_fault"

        def get_current(self):
            return {"label_map": {"0": "正常"}}

    class FakeReviewService:
        def __init__(self, slot, registry_service):
            assert slot == "pv_fault"
            assert isinstance(registry_service, FakeRegistry)

        def create_session(self, **kwargs):
            captured.update(kwargs)
            return {"review_id": "rev-scheduled"}

    monkeypatch.setattr(pv_tasks, "LabelRegistryService", FakeRegistry)
    monkeypatch.setattr(pv_tasks, "ReviewSessionService", FakeReviewService)

    session = pv_tasks._create_prediction_review_session(
        "pred-20260720-test",
        source_dataset_path="backend-service/data/input.csv",
        model_ref="pv_fault_rfc_20260720T080000Z_abc123",
        predictions=[
            {
                "site_id": 1.0,
                "device_id": 2.0,
                "branch_id": 3.0,
                "time_window": "2020/5/6 00:00:00 — 2020/5/8 00:00:00",
                "predicted_label": 0,
                "confidence": 0.9,
            }
        ],
    )

    assert session["review_id"] == "rev-scheduled"
    assert captured["prediction_batch_id"] == "pred-20260720-test"
    assert captured["prediction_units"][0]["unit_key"].startswith("1|2|3|")
    assert captured["prediction_context"]["source"] == "scheduled_prediction"


def test_align_prediction_cursor_resets_when_fingerprint_changes(tmp_path: Path, monkeypatch):
    cursor_path = tmp_path / "prediction_cursor.json"
    last_run_path = tmp_path / "prediction_last_run.json"
    monkeypatch.setattr(pv_tasks, "_PREDICTION_CURSOR_PATH", cursor_path)
    monkeypatch.setattr(pv_tasks, "_PREDICTION_LAST_RUN_PATH", last_run_path)

    cursor_path.write_text(
        json.dumps(
            {
                "batch_id": "pred-old",
                "last_predicted_time": "2021-08-29T11:00:00",
                "source_fingerprint": {
                    "source_path": "old.parquet",
                    "date_min": "2021-08-22",
                    "date_max": "2021-08-29",
                    "row_count": 100,
                    "fingerprint": "oldfp1234567890",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    new_fp = {
        "source_path": "backend-service/datasets/dataset_combined.parquet",
        "date_min": "2020-05-06",
        "date_max": "2020-05-12",
        "row_count": 300000,
        "fingerprint": "newfpabcdef1234",
    }
    cursor, reset, previous = pv_tasks._align_prediction_cursor_to_source(new_fp)

    assert reset is True
    assert cursor is None
    assert previous == "oldfp1234567890"

    saved = json.loads(cursor_path.read_text(encoding="utf-8"))
    assert saved["last_predicted_time"] is None
    assert saved["source_fingerprint"]["fingerprint"] == "newfpabcdef1234"
    assert saved["reset_reason"] == "source_fingerprint_changed"


def test_align_prediction_cursor_keeps_time_when_fingerprint_matches(tmp_path: Path, monkeypatch):
    cursor_path = tmp_path / "prediction_cursor.json"
    monkeypatch.setattr(pv_tasks, "_PREDICTION_CURSOR_PATH", cursor_path)

    fp = {
        "source_path": "same.parquet",
        "date_min": "2020-05-06",
        "date_max": "2020-05-12",
        "row_count": 10,
        "fingerprint": "samefp000000001",
    }
    cursor_path.write_text(
        json.dumps(
            {
                "batch_id": "pred-1",
                "last_predicted_time": "2020-05-07T23:59:00",
                "source_fingerprint": fp,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cursor, reset, previous = pv_tasks._align_prediction_cursor_to_source(fp)
    assert reset is False
    assert previous == "samefp000000001"
    assert cursor is not None
    assert cursor.isoformat() == "2020-05-07T23:59:00"


def test_reset_prediction_cursor_clears_watermark(tmp_path: Path, monkeypatch):
    cursor_path = tmp_path / "prediction_cursor.json"
    last_run_path = tmp_path / "prediction_last_run.json"
    monkeypatch.setattr(pv_tasks, "_PREDICTION_CURSOR_PATH", cursor_path)
    monkeypatch.setattr(pv_tasks, "_PREDICTION_LAST_RUN_PATH", last_run_path)
    monkeypatch.setattr(
        pv_tasks,
        "_current_source_fingerprint",
        lambda: {
            "source_path": "backend-service/datasets/dataset_combined.parquet",
            "date_min": "2020-05-06",
            "date_max": "2020-05-12",
            "row_count": 1,
            "fingerprint": "fpmanualreset01",
        },
    )

    cursor_path.write_text(
        json.dumps({"last_predicted_time": "2021-08-29T11:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    payload = pv_tasks.reset_prediction_cursor(reason="manual_reset")
    assert payload["last_predicted_time"] is None
    assert payload["source_fingerprint"]["fingerprint"] == "fpmanualreset01"
    last_run = json.loads(last_run_path.read_text(encoding="utf-8"))
    assert last_run["status"] == "cursor_reset"


def test_normalize_predictions_skips_empty_string_labels():
    raw = [
        {
            "predictions": "1",
            "confidence": 0.8,
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": 1,
            "time_window": "2020-05-07 00:00:00",
        },
        {
            "predictions": "",
            "confidence": 0.5,
            "site_id": "s1",
            "device_id": "d2",
            "branch_id": 1,
            "time_window": "2020-05-08 00:00:00",
        },
    ]
    normalized = pv_tasks._normalize_predictions(raw)
    assert len(normalized) == 1
    assert normalized[0]["predicted_label"] == 1
    assert normalized[0]["device_id"] == "d1"


def test_parse_predicted_label_accepts_unknown_prefix():
    assert pv_tasks._parse_predicted_label("unknown_2") == 2
    assert pv_tasks._parse_predicted_label("unknown_13") == 13
    assert pv_tasks._parse_predicted_label("7") == 7


def test_normalize_predictions_accepts_unknown_prefix_labels():
    raw = [
        {
            "predictions": "unknown_2",
            "confidence": 0.86,
            "site_id": "s1",
            "device_id": "d1",
            "branch_id": 1,
            "time_window": "2020-05-07 00:00:00",
        },
    ]
    normalized = pv_tasks._normalize_predictions(raw)
    assert len(normalized) == 1
    assert normalized[0]["predicted_label"] == 2
