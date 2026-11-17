# -*- coding: utf-8 -*-
"""Mock 喂数错峰释放水位 —— 三条检测路径拿不到新数据的根因回归测试。

缺陷（修复前，实测于 2022-01-02）：
  services/db/datasources/pv_fault_mock.py::PvFaultMockFeeder.release_next_batch_tick
  以 ``pointer = max(已释放 planned_batch_index) + 1`` 作为本轮释放水位，而
  ``_ensure_release_schedule`` 生成的设备实际批次是
      effective = planned_batch_index + delay_ticks
  最大值为 ``(_RELEASE_BATCH_COUNT - 1) + max(_DELAY_TICKS_RANGE)`` = 6 + 2 = 8。
  已释放批次的 ``planned_batch_index`` 最大只能取到 6，pointer 上界因此是 7 < 8，
  (batch=6, delay=2) 的设备永远不满足 ``(batch + delay) <= pointer``。

后果链（现场证据）：
  1 台设备永久 PENDING → ``_maybe_mark_day_fed`` 的 remaining 永远 ≥ 1 →
  该业务日永不标记「已喂完」→ ``pv_mock_feed_cursor`` 永久停在 2022-01-01 →
  ``training_samples`` 不再新增 → pv_tsc / pv_day / pv_point 游标全部 caught-up
  （pv_tsc/tsc 水位 = 游标 = 2020-05-12）→ 精度运营页永远无数据。

真实表与真实 SQL 语义：本测试用内存 SQLite 承载 ``PvMockReleaseSchedule``
（该模型只用通用列类型），被测对象是生产代码 ``release_next_batch_tick`` 的
释放水位判定本身，不是它的复制品。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.db.datasources import pv_fault_mock as mod
from services.db.datasources.pv_fault_mock import (
    _DELAY_TICKS_RANGE,
    _RELEASE_BATCH_COUNT,
    PvMockFeedResult,
    PvFaultMockFeeder,
)
from services.db.models.pv_fault import PvMockReleaseSchedule

BUSINESS_DATE = date(2022, 1, 2)
_MAX_PLANNED_EFFECTIVE = (_RELEASE_BATCH_COUNT - 1) + max(_DELAY_TICKS_RANGE)
_LEGACY_POINTER_UPPER_BOUND = (_RELEASE_BATCH_COUNT - 1) + 1


class _SqliteAdapter:
    """把 PvFaultMockFeeder 的 get_sync_session() 落到内存 SQLite。"""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def get_sync_session(self):
        return self._session_factory()


@pytest.fixture()
def sqlite_release_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    PvMockReleaseSchedule.__table__.create(engine)
    return sessionmaker(bind=engine)


def test_legacy_watermark_upper_bound_cannot_cover_max_planned_batch():
    """固化缺陷的数学事实：计划批次最大值超出旧水位上界。

    这一条在修复前后都应通过——它证明死区是「口径上界不足」，不是偶发数据。
    """
    assert _MAX_PLANNED_EFFECTIVE == 8
    assert _LEGACY_POINTER_UPPER_BOUND == 7
    assert _MAX_PLANNED_EFFECTIVE > _LEGACY_POINTER_UPPER_BOUND


def test_resolve_release_watermark_returns_smallest_pending_batch():
    """水位取「未释放设备中最小的 effective 批次」，因此不存在够不到的批次。"""
    assert mod.resolve_release_watermark([8]) == 8
    assert mod.resolve_release_watermark([6, 8]) == 6
    assert mod.resolve_release_watermark(iter([3, 1, 2])) == 1
    assert mod.resolve_release_watermark([]) is None


def test_every_planned_effective_batch_is_eventually_released():
    """不变量：按水位逐轮释放，全部计划批次都能被释放干净。"""
    planned = sorted(
        {
            batch_index + delay
            for batch_index in range(_RELEASE_BATCH_COUNT)
            for delay in range(0, max(_DELAY_TICKS_RANGE) + 1)
        }
    )
    pending = list(planned)
    released: list[int] = []
    while (watermark := mod.resolve_release_watermark(pending)) is not None:
        released.extend(value for value in pending if value <= watermark)
        pending = [value for value in pending if value > watermark]

    assert pending == []
    assert sorted(released) == planned


def _seed_schedule(session_factory, pending_device, business_date=BUSINESS_DATE):
    """播种现场形状：常规批次已释放 + 1 台缺失 + 1 台延迟到最大批次未释放。"""
    with session_factory() as session:
        rows = []
        # 常规批次：batch 0.._RELEASE_BATCH_COUNT-1，各 1 台，均已释放
        for batch_index in range(_RELEASE_BATCH_COUNT):
            rows.append(
                PvMockReleaseSchedule(
                    business_date=business_date,
                    site_id="site-regular",
                    device_id=f"device-b{batch_index}",
                    branch_id="1",
                    planned_batch_index=batch_index,
                    delay_ticks=0,
                    is_dropped=False,
                    released_at=datetime(2026, 8, 24, 11, 24),
                    created_at=datetime(2026, 8, 24, 10, 0),
                )
            )
        # 当天缺失设备（不参与「已喂完」判定）
        rows.append(
            PvMockReleaseSchedule(
                business_date=business_date,
                site_id="site-dropped",
                device_id="device-dropped",
                branch_id="1",
                planned_batch_index=0,
                delay_ticks=0,
                is_dropped=True,
                released_at=None,
                created_at=datetime(2026, 8, 24, 10, 0),
            )
        )
        # 致命设备：计划在最后一批且额外延迟到最大 effective 批次
        rows.append(
            PvMockReleaseSchedule(
                business_date=business_date,
                site_id=pending_device[0],
                device_id=pending_device[1],
                branch_id=pending_device[2],
                planned_batch_index=_RELEASE_BATCH_COUNT - 1,
                delay_ticks=max(_DELAY_TICKS_RANGE),
                is_dropped=False,
                released_at=None,
                created_at=datetime(2026, 8, 24, 10, 0),
            )
        )
        session.add_all(rows)
        session.commit()


def test_release_tick_dispatches_last_delayed_device(monkeypatch, sqlite_release_session):
    """RED 主断言：最后一台延迟设备必须被本轮 tick 下发释放。

    修复前 pointer 上界为 7，该设备 effective=8 永远够不到，due_keys 为空。
    """
    pending_device = ("site-delayed", "device-max-effective", "1")
    _seed_schedule(sqlite_release_session, pending_device)

    feeder = PvFaultMockFeeder(
        adapter=_SqliteAdapter(sqlite_release_session),
        parquet_path="datasets/x.parquet",
    )
    monkeypatch.setattr(feeder, "_next_unfed_date", lambda: BUSINESS_DATE)
    monkeypatch.setattr(feeder, "_ensure_release_schedule", lambda _d: None)

    marked: list[date] = []
    monkeypatch.setattr(feeder, "_mark_date_fed", lambda d, _rows: marked.append(d))

    captured: dict = {"due_keys": None}

    def _fake_release(business_date, due_keys):
        captured["due_keys"] = set(due_keys)
        if due_keys:
            with sqlite_release_session() as session:
                session.execute(
                    update(PvMockReleaseSchedule)
                    .where(
                        PvMockReleaseSchedule.business_date == business_date,
                        PvMockReleaseSchedule.site_id == pending_device[0],
                        PvMockReleaseSchedule.device_id == pending_device[1],
                        PvMockReleaseSchedule.branch_id == pending_device[2],
                    )
                    .values(released_at=datetime(2026, 8, 24, 12, 0))
                )
                session.commit()
        return PvMockFeedResult(
            business_date=business_date,
            source_row_count=0,
            inserted_row_count=0,
            skipped_row_count=0,
            device_count=len(due_keys),
            exhausted=False,
        )

    monkeypatch.setattr(feeder, "_release_due_devices", _fake_release)
    # _maybe_mark_day_fed 走真实实现（真实 SQL），只把落游标的原始 SQL 换掉
    monkeypatch.setattr(feeder, "_rows_for_date", lambda _d: [])

    feeder.release_next_batch_tick()

    assert captured["due_keys"] == {pending_device}, (
        "最后一台延迟设备未被下发释放 —— 该业务日将永久无法标记「已喂完」"
    )
    assert marked == [BUSINESS_DATE], (
        "全部非缺失设备释放后仍未标记该业务日已喂完 —— 喂数游标将永久停滞"
    )
