# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Property 34、35、42：Epoch 责任边界、三种启用模式与 full_backfill 车道/容量。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from itertools import count
from math import ceil

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from services.db.models.pv_fault import (
    PathActivationDeviceScope,
    PathActivationEpoch,
    PathActivationLaneClaim,
)
from services.scheduler.pv_dual_path.backfill_capacity import (
    BackfillCapacityArbiter,
    CapacityResources,
)
from services.scheduler.pv_dual_path.config import DualPathConfig
from services.scheduler.pv_dual_path.path_activation import (
    CUTOVER_ONLY,
    FULL_BACKFILL,
    HISTORICAL_BACKFILL_LANE,
    PRODUCTION_LANE,
    RECENT_WINDOW,
    ActivationRequest,
    DeviceActivationInput,
    DeviceScope,
    PathActivationService,
    PathActivationValidationError,
)
from services.scheduler.pv_dual_path.production_window import is_production_responsible_date


class _SQLiteAdapter:
    def __init__(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        PathActivationEpoch.__table__.create(self.engine)
        PathActivationDeviceScope.__table__.create(self.engine)
        PathActivationLaneClaim.__table__.create(self.engine)

    @contextmanager
    def get_sync_session(self):
        session = Session(self.engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _service(max_backfill: int = 14) -> PathActivationService:
    ids = count(1)
    return PathActivationService(
        _SQLiteAdapter(),  # type: ignore[arg-type]
        DualPathConfig(max_backfill_days=max_backfill),
        epoch_id_factory=lambda: f"epoch-{next(ids)}",
        now_factory=lambda: datetime(2026, 6, 20, 12, 0, 0),
    )


_watermarks = st.dates(min_value=date(2026, 2, 10), max_value=date(2026, 6, 20))
_days = st.integers(min_value=1, max_value=14)
_tokens = st.integers(min_value=1, max_value=20)
_ratios = st.sampled_from([0.0, 0.5, 0.8, 1.0])


# Feature: pv-fault-dual-path-serving, Property 35: 三种启用模式计算正确
@given(watermark=_watermarks, backfill=_days, earliest_offset=st.integers(min_value=10, max_value=40))
@settings(max_examples=100, deadline=None)
def test_property_35_activation_mode_formulas(watermark: date, backfill: int, earliest_offset: int) -> None:
    service = _service(max_backfill=14)
    wm = datetime(watermark.year, watermark.month, watermark.day, 8, 0, 0)
    earliest = watermark - timedelta(days=earliest_offset)
    closed = watermark - timedelta(days=1)
    assert service.effective_from(CUTOVER_ONLY, wm, earliest, None) == closed
    assert service.effective_from(RECENT_WINDOW, wm, earliest, backfill) == closed - timedelta(days=backfill - 1)
    assert service.effective_from(FULL_BACKFILL, wm, earliest, None) == earliest
    with pytest.raises(PathActivationValidationError):
        service.preview(
            ActivationRequest(
                modeling_path="seq_annotation",
                activation_mode=RECENT_WINDOW,
                backfill_days=15,
                devices=(DeviceActivationInput(DeviceScope("s", "d", "b"), wm, earliest),),
            )
        )
    with pytest.raises(PathActivationValidationError):
        service.create_epoch(
            ActivationRequest(
                modeling_path="seq_annotation",
                activation_mode=RECENT_WINDOW,
                backfill_days=15,
                devices=(DeviceActivationInput(DeviceScope("s", "d", "b"), wm, earliest),),
            )
        )


# Feature: pv-fault-dual-path-serving, Property 34: Epoch 按设备限定生产责任
@given(watermark=_watermarks)
@settings(max_examples=100, deadline=None)
def test_property_34_epoch_limits_responsibility_per_device(watermark: date) -> None:
    service = _service()
    wm = datetime(watermark.year, watermark.month, watermark.day, 8, 0, 0)
    epoch = service.create_epoch(
        ActivationRequest(
            modeling_path="seq_annotation",
            activation_mode=CUTOVER_ONLY,
            devices=(
                DeviceActivationInput(DeviceScope("s", "A", "b"), wm, date(2026, 1, 1)),
                DeviceActivationInput(DeviceScope("s", "C", "b"), None, None),
            ),
        )
    )
    boundary = watermark - timedelta(days=1)
    scope_a = DeviceScope("s", "A", "b")
    assert is_production_responsible_date(service, epoch.activation_epoch_id, scope_a, boundary) is True
    assert is_production_responsible_date(
        service, epoch.activation_epoch_id, scope_a, boundary - timedelta(days=1)
    ) is False
    assert is_production_responsible_date(
        service, epoch.activation_epoch_id, DeviceScope("s", "C", "b"), boundary
    ) is False
    with service._adapter.get_sync_session() as session:  # type: ignore[attr-defined]
        skipped = session.execute(select(PathActivationLaneClaim)).scalars().all()
    assert all(claim.range_start >= boundary or claim.device_id != "A" for claim in skipped)
    second = service.create_epoch(
        ActivationRequest(
            modeling_path="seq_annotation",
            activation_mode=CUTOVER_ONLY,
            devices=(DeviceActivationInput(DeviceScope("s", "A", "b"), wm, date(2026, 1, 1)),),
        )
    )
    assert second.activation_epoch_id != epoch.activation_epoch_id


# Feature: pv-fault-dual-path-serving, Property 42: full_backfill 车道排他且生产容量受保护
@given(watermark=_watermarks, earliest_offset=st.integers(min_value=3, max_value=10), tokens=_tokens, ratio=_ratios)
@settings(max_examples=100, deadline=None)
def test_property_42_lanes_disjoint_and_capacity_reserved(
    watermark: date,
    earliest_offset: int,
    tokens: int,
    ratio: float,
) -> None:
    service = _service(max_backfill=3650)
    wm = datetime(watermark.year, watermark.month, watermark.day, 8, 0, 0)
    earliest = watermark - timedelta(days=earliest_offset)
    preview = service.preview(
        ActivationRequest(
            modeling_path="seq_annotation",
            activation_mode=FULL_BACKFILL,
            devices=(DeviceActivationInput(DeviceScope("s", "d", "b"), wm, earliest),),
        )
    )
    hist = [c for c in preview.claims if c.lane == HISTORICAL_BACKFILL_LANE]
    prod = [c for c in preview.claims if c.lane == PRODUCTION_LANE]
    assert len(prod) == 1
    if hist:
        assert hist[0].range_end == prod[0].range_start
        assert hist[0].range_start < hist[0].range_end
        cursor = hist[0].range_start
        while cursor < hist[0].range_end:
            assert prod[0].contains(cursor) is False
            cursor += timedelta(days=1)
    arbiter = BackfillCapacityArbiter(
        CapacityResources(tokens, tokens, tokens, tokens),
        production_capacity_reserved_ratio=ratio,
    )
    snap = arbiter.snapshot()
    assert snap.production_reserved_tokens == ceil(tokens * ratio)
    assert snap.backfill_limit_tokens == tokens - snap.production_reserved_tokens
    if snap.backfill_limit_tokens:
        granted = arbiter.acquire("historical_backfill", snap.backfill_limit_tokens)
        assert granted.granted is True
        denied = arbiter.acquire("historical_backfill", 1)
        assert denied.granted is False
# @AI_GENERATED: end
