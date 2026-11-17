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

# @AI_GENERATED: seq_annotation 逐点详情与审核上下文兼容测试
def test_normalize_predictions_preserves_valid_point_detail():
    timestamps = ["2026-08-01T00:00:00", "2026-08-01T00:05:00"]
    normalized = pv_tasks._normalize_predictions(
        [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
                "time_window": "2026-08-01",
                "predicted_label": 1,
                "confidence": 0.75,
                "prediction_detail": {
                    "timestamps": timestamps,
                    "point_predictions": [0, 1],
                    "point_confidences": [0.8, 0.7],
                    "segment_predictions": [
                        {
                            "t_start": timestamps[0],
                            "t_end": timestamps[0],
                            "label": 0,
                            "n_points": 1,
                        },
                        {
                            "t_start": timestamps[1],
                            "t_end": timestamps[1],
                            "label": 1,
                            "n_points": 1,
                        },
                    ],
                    "model_name": "bilstm_attn",
                    "seq_len_used": 288,
                    "trained_full_day": True,
                },
            }
        ]
    )
    detail = normalized[0]["prediction_detail"]
    assert detail["granularity"] == "point"
    assert detail["point_predictions"] == [0, 1]
    assert detail["n_points_predicted"] == 2
    assert detail["trained_full_day"] is True


def test_normalize_predictions_rejects_misaligned_point_detail():
    import pytest

    with pytest.raises(RuntimeError, match="逐点详情长度不一致"):
        pv_tasks._normalize_predictions(
            [
                {
                    "site_id": "s1",
                    "device_id": "d1",
                    "branch_id": "b1",
                    "time_window": "2026-08-01",
                    "predicted_label": 1,
                    "confidence": 0.75,
                    "prediction_detail": {
                        "timestamps": ["2026-08-01T00:00:00"],
                        "point_predictions": [0, 1],
                        "point_confidences": [0.8],
                        "segment_predictions": [],
                    },
                }
            ]
        )

    with pytest.raises(RuntimeError, match="trained_full_day 必须为 JSON boolean"):
        pv_tasks._normalize_predictions(
            [
                {
                    "site_id": "s1",
                    "device_id": "d1",
                    "branch_id": "b1",
                    "time_window": "2026-08-01",
                    "predicted_label": 1,
                    "confidence": 0.75,
                    "prediction_detail": {
                        "timestamps": ["2026-08-01T00:00:00"],
                        "point_predictions": [1],
                        "point_confidences": [0.8],
                        "segment_predictions": [],
                        "trained_full_day": "false",
                    },
                }
            ]
        )


def test_seq_review_session_marks_point_granularity(monkeypatch):
    captured = {}

    class FakeRegistry:
        def __init__(self, slot):
            assert slot == "pv_fault"

        def get_current(self):
            return {"label_map": {"正常": 0}}

    class FakeReviewService:
        def __init__(self, slot, registry_service):
            assert slot == "pv_fault"

        def create_session(self, **kwargs):
            captured.update(kwargs)
            return {"review_id": "rev-seq"}

    monkeypatch.setattr(pv_tasks, "LabelRegistryService", FakeRegistry)
    monkeypatch.setattr(pv_tasks, "ReviewSessionService", FakeReviewService)
    pv_tasks._create_prediction_review_session(
        "pred-seq-test",
        source_dataset_path="backend-service/data/seq-input.csv",
        model_ref="seqann-test",
        predictions=[
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
                "time_window": "2026-08-01",
                "predicted_label": 1,
                "confidence": 0.8,
            }
        ],
        modeling_path="seq_annotation",
    )
    assert captured["prediction_context"]["modeling_path"] == "seq_annotation"
    assert captured["prediction_context"]["prediction_granularity"] == "point"
    assert len(captured["prediction_units"]) == 1


# ============================================================================
# 安全修复回归测试（2026-08-12）：缺口 1 — seq 预测幂等键
# ============================================================================
def test_seq_sample_key_parses_iso_date():
    business_date, sample_id = pv_tasks._seq_sample_key("2026-08-12")
    assert business_date.isoformat() == "2026-08-12"
    assert sample_id == "2026-08-12#point"


def test_seq_sample_key_deterministic_for_failure_retry(monkeypatch):
    # 同一 time_window 重复解析必须得到完全一致的键，保证失败重试幂等。
    first = pv_tasks._seq_sample_key("2026-08-12")
    second = pv_tasks._seq_sample_key("2026-08-12")
    assert first == second

    predictions = [
        {
            "site_id": "site-a",
            "device_id": "device-1",
            "branch_id": "branch-1",
            "time_window": "2026-08-12",
            "predicted_label": 1,
            "confidence": 0.8,
        }
    ]
    batch_id = pv_tasks._seq_prediction_batch_id("seqann-v1", predictions)
    assert batch_id == pv_tasks._seq_prediction_batch_id(
        "seqann-v1", list(reversed(predictions))
    )

    import services.iterative_labeling.review_explanations as review_explanations

    immutable_payload = {
        "model_ref": "seqann-v1",
        "modeling_path": "seq_annotation",
        "dataset_version": "backend-service/data/immutable-source.csv",
        "predictions": predictions,
        "cursor_advance_times": [
            {
                "site_id": "site-a",
                "device_id": "device-1",
                "branch_id": "branch-1",
                "last_predicted_time": "2026-08-12T23:55:00",
            }
        ],
    }
    monkeypatch.setattr(
        review_explanations,
        "load_prediction_batch",
        lambda slot, requested_batch_id: immutable_payload,
    )
    recovered, source_path, advances = pv_tasks._load_seq_recovery_batch(
        batch_id, "seqann-v1"
    )
    assert recovered == predictions
    assert source_path == "backend-service/data/immutable-source.csv"
    assert advances[("site-a", "device-1", "branch-1")] == datetime(
        2026, 8, 12, 23, 55
    )

    # 本轮集合从旧批次 A 扩展为 A+B 时，A 必须从数据库记录引用恢复，
    # B 必须保留在新增集合中，不能用 A+B 的重算 batch ID 覆盖 A。
    new_prediction = {
        "site_id": "site-a",
        "device_id": "device-2",
        "branch_id": "branch-1",
        "time_window": "2026-08-13",
        "predicted_label": 0,
        "confidence": 0.9,
    }

    class ExistingRecord:
        input_feature_json = {
            "prediction_batch_id": batch_id,
            "model_ref": "seqann-v1",
        }

    class FakeRepo:
        def find_prediction_record(self, **kwargs):
            if kwargs["device_id"] == "device-1":
                return ExistingRecord()
            return None

    new_only, recovery_ids = pv_tasks._partition_seq_predictions_for_recovery(
        FakeRepo(), "seqann-v1", [predictions[0], new_prediction]
    )
    assert recovery_ids == {batch_id: "seqann-v1"}
    assert new_only == [new_prediction]
    assert pv_tasks._seq_prediction_batch_id(
        "seqann-v1", [predictions[0], new_prediction]
    ) != batch_id

    # 即使 A 在本轮质量门控后没有进入 predictions，也必须通过候选设备日定位旧批次。
    gated_new, gated_recovery_ids = pv_tasks._partition_seq_predictions_for_recovery(
        FakeRepo(),
        "seqann-v1",
        [],
        recovery_candidates=[predictions[0]],
    )
    assert gated_new == []
    assert gated_recovery_ids == {batch_id: "seqann-v1"}

    # 数据库提交 M1 后即使生产已切换到 M2，仍须用记录保存的 M1 恢复 A。
    cross_model_new, cross_model_recovery = (
        pv_tasks._partition_seq_predictions_for_recovery(
            FakeRepo(),
            "seqann-v2",
            [],
            recovery_candidates=[predictions[0]],
        )
    )
    assert cross_model_new == []
    assert cross_model_recovery == {batch_id: "seqann-v1"}


def test_seq_sample_key_falls_back_deterministically_when_unparseable():
    # 异常 time_window 不能导致幂等键随机化；仍应给出确定性键。
    from datetime import date as _date
    first = pv_tasks._seq_sample_key("not-a-date")
    second = pv_tasks._seq_sample_key("not-a-date")
    assert first == second
    assert isinstance(first[0], _date)
    assert first[1].endswith("#point")


def test_seq_sample_key_unparseable_still_deterministic_and_point_suffixed():
    # 不可解析输入不能导致幂等键随机化；同一次运行内解析结果必须稳定。
    import services.scheduler.tasks.pv_fault_tasks as pv
    first = pv._seq_sample_key("garbage::input")
    second = pv._seq_sample_key("garbage::input")
    assert first == second
    assert first[1].endswith("#point")
# @AI_GENERATED: end