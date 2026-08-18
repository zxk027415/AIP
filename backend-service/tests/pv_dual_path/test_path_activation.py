# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PathActivationService 三模式边界、设备范围和排他车道定向测试。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from itertools import count

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from services.db.models.pv_fault import (
    PathActivationDeviceScope,
    PathActivationEpoch,
    PathActivationLaneClaim,
)
from services.scheduler.pv_dual_path.config import DualPathConfig
from services.scheduler.pv_dual_path.path_activation import (
    ActivationRequest,
    CUTOVER_ONLY,
    FULL_BACKFILL,
    HISTORICAL_BACKFILL_LANE,
    PRODUCTION_LANE,
    RECENT_WINDOW,
    DeviceActivationInput,
    DeviceScope,
    PathActivationService,
    PathActivationValidationError,
)


class _SQLiteAdapter:
    """仅创建本测试需要的三张 Epoch 相关表，并模拟 DBAdapter 事务语义。"""

    def __init__(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        PathActivationEpoch.__table__.create(self.engine)
        PathActivationDeviceScope.__table__.create(self.engine)
        PathActivationLaneClaim.__table__.create(self.engine)
        self.open_count = 0

    @contextmanager
    def get_sync_session(self):
        self.open_count += 1
        session = Session(self.engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _service(adapter: _SQLiteAdapter | None = None) -> PathActivationService:
    ids = count(1)
    return PathActivationService(
        adapter or _SQLiteAdapter(),  # type: ignore[arg-type]
        DualPathConfig(max_backfill_days=14),
        epoch_id_factory=lambda: f"epoch-{next(ids)}",
        now_factory=lambda: datetime(2026, 6, 20, 12, 0, 0),
    )


def _device(name: str, watermark: datetime | None, earliest: date | None = None) -> DeviceActivationInput:
    return DeviceActivationInput(DeviceScope("site", name, "branch"), watermark, earliest)


def test_three_activation_modes_and_per_device_boundaries() -> None:
    """A/B/C 设备分别按自身水位计算，C 无数据时保持空边界且不建 claim。"""
    service = _service()
    devices = (
        _device("A", datetime(2026, 6, 20, 8), date(2026, 1, 1)),
        _device("B", datetime(2026, 6, 18, 8), date(2026, 2, 1)),
        _device("C", None, None),
    )

    cutover = service.preview(ActivationRequest("seq_annotation", CUTOVER_ONLY, devices))
    assert [item.effective_from_date for item in cutover.device_scopes] == [
        date(2026, 6, 19), date(2026, 6, 17), None,
    ]
    assert all(claim.lane == PRODUCTION_LANE for claim in cutover.claims)

    recent = service.preview(
        ActivationRequest("seq_annotation", RECENT_WINDOW, devices, backfill_days=7)
    )
    assert [item.effective_from_date for item in recent.device_scopes] == [
        date(2026, 6, 13), date(2026, 6, 11), None,
    ]

    full = service.preview(ActivationRequest("seq_annotation", FULL_BACKFILL, devices))
    first = full.device_scopes[0]
    assert first.effective_from_date == date(2026, 1, 1)
    assert first.production_cutover_date == date(2026, 6, 19)
    assert [(claim.lane, claim.range_start, claim.range_end) for claim in first.claims] == [
        (HISTORICAL_BACKFILL_LANE, date(2026, 1, 1), date(2026, 6, 19)),
        (PRODUCTION_LANE, date(2026, 6, 19), None),
    ]
    assert first.claims[0].range_end == first.claims[1].range_start


def test_invalid_backfill_rejected_before_opening_transaction() -> None:
    adapter = _SQLiteAdapter()
    service = _service(adapter)
    request = ActivationRequest(
        "seq_annotation",
        RECENT_WINDOW,
        (_device("A", datetime(2026, 6, 20, 8)),),
        backfill_days=15,
    )
    before = adapter.open_count
    with pytest.raises(PathActivationValidationError):
        service.create_epoch(request)
    assert adapter.open_count == before


def test_create_epoch_is_atomic_and_reenable_gets_new_epoch() -> None:
    adapter = _SQLiteAdapter()
    service = _service(adapter)
    request = ActivationRequest(
        "seq_annotation",
        FULL_BACKFILL,
        (_device("A", datetime(2026, 6, 20, 8), date(2026, 6, 1)),),
        operator="tester",
    )
    first = service.create_epoch(request)
    second = service.create_epoch(request)
    assert first.activation_epoch_id != second.activation_epoch_id

    with Session(adapter.engine) as session:
        assert len(session.scalars(select(PathActivationEpoch)).all()) == 2
        assert len(session.scalars(select(PathActivationDeviceScope)).all()) == 2
        claims = session.scalars(select(PathActivationLaneClaim)).all()
        assert len(claims) == 4


def test_first_arrival_fills_empty_boundary_once() -> None:
    adapter = _SQLiteAdapter()
    service = _service(adapter)
    epoch = service.create_epoch(
        ActivationRequest("seq_annotation", CUTOVER_ONLY, (_device("C", None),))
    )
    scope = DeviceScope("site", "C", "branch")
    completed = service.complete_empty_boundary_on_first_arrival(
        epoch.activation_epoch_id, scope, datetime(2026, 6, 25, 9)
    )
    assert completed.effective_from_date == date(2026, 6, 25)
    assert len(completed.claims) == 1
    assert completed.claims[0].range_start == date(2026, 6, 25)

    repeated = service.complete_empty_boundary_on_first_arrival(
        epoch.activation_epoch_id, scope, datetime(2026, 7, 1, 9)
    )
    assert repeated.effective_from_date == date(2026, 6, 25)
# @AI_GENERATED: end
