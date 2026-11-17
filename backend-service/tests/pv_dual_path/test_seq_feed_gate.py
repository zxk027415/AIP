# -*- coding: utf-8 -*-
# @AI_GENERATED
"""点级喂数闸门：占用门槛放行，不再用 288×90% 卡死白天完整日。"""

from __future__ import annotations

from datetime import date, datetime

from services.db.models.pv_fault import MeasurementIngestionDaily
from services.db.repositories.ingestion_tracker import (
    SEQ_MIN_OCCUPIED_SLOTS,
    IngestionTrackerRepository,
)
from services.iterative_labeling.seq_annotation.grid_align import MIN_OCCUPIED_SLOTS
from services.scheduler.pv_dual_path.completeness_gate import CompletenessGate, GateDecision
from services.scheduler.pv_dual_path.config import DualPathConfig


def test_seq_occupancy_threshold_matches_training() -> None:
    assert SEQ_MIN_OCCUPIED_SLOTS == MIN_OCCUPIED_SLOTS == 173


def test_seq_admits_daytime_full_day_below_90pct() -> None:
    """光伏白天完整日约 204/288，过不了 90%，但应放行点级检测。"""
    gate = CompletenessGate(
        tracker=None,  # type: ignore[arg-type]
        config=DualPathConfig(completeness_ratio=0.9, expected_point_count=288),
    )
    daytime = GateDecision(
        is_complete=False,
        ratio=204 / 288,
        point_count=204,
        expected_point_count=288,
    )
    assert gate.admissible_for_path(daytime, "seq_annotation") is True
    assert gate.admissible_for_path(daytime, "legacy_day") is True

    too_sparse = GateDecision(
        is_complete=False,
        ratio=100 / 288,
        point_count=100,
        expected_point_count=288,
    )
    assert gate.admissible_for_path(too_sparse, "seq_annotation") is False
    assert gate.admissible_for_path(too_sparse, "legacy_day") is True


def test_legacy_path_does_not_use_completeness_gate() -> None:
    """天级检测恒放行，不要求 90%/288。占用闸门只作用于点级。"""
    gate = CompletenessGate(
        tracker=None,  # type: ignore[arg-type]
        config=DualPathConfig(completeness_ratio=0.9, expected_point_count=288),
    )
    sparse = GateDecision(
        is_complete=False,
        ratio=10 / 288,
        point_count=10,
        expected_point_count=288,
    )
    assert gate.admissible_for_path(sparse, "legacy_day") is True
    assert gate.admissible_for_path(sparse, "seq_annotation") is False


def test_seq_complete_90pct_is_still_sufficient() -> None:
    gate = CompletenessGate(
        tracker=None,  # type: ignore[arg-type]
        config=DualPathConfig(completeness_ratio=0.9, expected_point_count=288),
    )
    complete = GateDecision(
        is_complete=True,
        ratio=0.95,
        point_count=160,
        expected_point_count=288,
    )
    assert gate.admissible_for_path(complete, "seq_annotation") is True


def test_row_to_dict_marks_seq_ready_at_occupancy_threshold() -> None:
    now = datetime(2021, 11, 24, 12, 0, 0)
    row = MeasurementIngestionDaily(
        site_id="HRZzKE4v",
        device_id="dev-1",
        branch_id="0",
        business_date=date(2021, 11, 24),
        point_count=173,
        expected_point_count=288,
        is_complete=False,
        first_seen_at=now,
        completed_at=None,
        updated_at=now,
    )
    payload = IngestionTrackerRepository._row_to_dict(row)
    assert payload["is_complete"] is False
    assert payload["is_seq_ready"] is True

    row.point_count = 172
    sparse = IngestionTrackerRepository._row_to_dict(row)
    assert sparse["is_seq_ready"] is False
