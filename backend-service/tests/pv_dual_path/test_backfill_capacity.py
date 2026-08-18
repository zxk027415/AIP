# @AI_GENERATED
# -*- coding: utf-8 -*-
"""BackfillCapacityArbiter 的生产保留、历史限流与低水位让行测试。"""
from __future__ import annotations

import math

import pytest

from services.scheduler.pv_dual_path.backfill_capacity import (
    BackfillCapacityArbiter,
    CapacityResources,
)


def _resources(total: int, *, low_resource: bool = False) -> CapacityResources:
    return CapacityResources(
        worker_slots=total,
        db_connection_slots=total,
        memory_slots=total,
        model_load_slots=total,
        low_resource=low_resource,
    )


def test_total_uses_all_four_bottlenecks_and_reserve_uses_ceil() -> None:
    resources = CapacityResources(
        worker_slots=12,
        db_connection_slots=9,
        memory_slots=7,
        model_load_slots=10,
    )
    arbiter = BackfillCapacityArbiter(
        resources,
        production_capacity_reserved_ratio=0.8,
    )
    snapshot = arbiter.snapshot()
    assert snapshot.total_tokens == 7
    assert snapshot.production_reserved_tokens == math.ceil(7 * 0.8) == 6
    assert snapshot.backfill_limit_tokens == 1
    assert snapshot.pressure_state == "throttled"


@pytest.mark.parametrize(
    ("ratio", "reserved", "backfill"),
    [(0.0, 0, 10), (0.8, 8, 2), (1.0, 10, 0)],
)
def test_reservation_ratio_boundaries(ratio: float, reserved: int, backfill: int) -> None:
    snapshot = BackfillCapacityArbiter(
        _resources(10),
        production_capacity_reserved_ratio=ratio,
    ).snapshot()
    assert snapshot.production_reserved_tokens == reserved
    assert snapshot.backfill_limit_tokens == backfill


def test_historical_cannot_consume_reserved_tokens_and_production_keeps_capacity() -> None:
    arbiter = BackfillCapacityArbiter(
        _resources(10),
        production_capacity_reserved_ratio=0.8,
    )
    historical = arbiter.acquire("historical_backfill", 2)
    assert historical.granted is True
    rejected = arbiter.acquire("historical_backfill", 1)
    assert rejected.granted is False
    assert rejected.reason == "production_capacity_reserved"

    production = arbiter.acquire("production", 8)
    assert production.granted is True
    full = arbiter.snapshot()
    assert full.production_in_use == 8
    assert full.backfill_in_use == 2
    assert full.free_tokens == 0


def test_memory_watermark_pauses_new_backfill_and_requests_existing_lease_yield() -> None:
    normal = CapacityResources.from_memory_watermark(
        worker_slots=8,
        db_connection_slots=8,
        memory_available_mb=4096,
        memory_reserved_mb=1024,
        memory_mb_per_token=512,
        model_load_slots=8,
    )
    assert normal.memory_slots == 8
    assert normal.low_resource is False
    arbiter = BackfillCapacityArbiter(normal, production_capacity_reserved_ratio=0.5)
    lease = arbiter.acquire("historical_backfill", 2)
    assert lease.granted is True

    pressure = CapacityResources.from_memory_watermark(
        worker_slots=8,
        db_connection_slots=8,
        memory_available_mb=1024,
        memory_reserved_mb=1024,
        memory_mb_per_token=512,
        model_load_slots=8,
    )
    snapshot = arbiter.refresh(pressure)
    assert snapshot.total_tokens == 2
    assert snapshot.pressure_state == "paused"
    assert snapshot.backfill_should_yield is True
    rejected = arbiter.acquire("historical_backfill")
    assert rejected.granted is False
    assert rejected.reason == "resource_pressure"
    assert lease.lease_id and arbiter.release(lease.lease_id) is True
    assert arbiter.acquire("production", 2).granted is True


def test_refresh_never_revokes_lease_but_enters_draining_until_backfill_releases() -> None:
    arbiter = BackfillCapacityArbiter(
        _resources(10),
        production_capacity_reserved_ratio=0.5,
    )
    lease = arbiter.acquire("historical_backfill", 5)
    assert lease.granted and lease.lease_id

    snapshot = arbiter.refresh(_resources(6))
    assert snapshot.backfill_in_use == 5
    assert snapshot.backfill_limit_tokens == 3
    assert snapshot.pressure_state == "draining"
    assert snapshot.backfill_should_yield is True
    assert arbiter.acquire("historical_backfill").granted is False

    assert arbiter.release(lease.lease_id) is True
    assert arbiter.release(lease.lease_id) is False
    after = arbiter.snapshot()
    assert after.backfill_in_use == 0
    assert after.backfill_should_yield is False
    assert arbiter.acquire("production", 3).granted is True


def test_invalid_resources_lane_tokens_and_ratio_are_rejected() -> None:
    with pytest.raises(ValueError):
        CapacityResources(-1, 1, 1, 1)
    with pytest.raises(ValueError):
        BackfillCapacityArbiter(_resources(1), production_capacity_reserved_ratio=1.1)
    arbiter = BackfillCapacityArbiter(_resources(1))
    with pytest.raises(ValueError):
        arbiter.acquire("unknown")
    with pytest.raises(ValueError):
        arbiter.acquire("production", 0)
# @AI_GENERATED: end
