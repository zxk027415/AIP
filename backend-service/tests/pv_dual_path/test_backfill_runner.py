# @AI_GENERATED
# -*- coding: utf-8 -*-
"""BackfillRunner 独立历史通道、认领保留/释放与生产隔离测试。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from itertools import count
from pathlib import Path

import pytest
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
from services.scheduler.pv_dual_path.backfill_runner import BackfillRunner, BackfillRunnerError
from services.scheduler.pv_dual_path.config import DualPathConfig
from services.scheduler.pv_dual_path.path_activation import (
    ActivationRequest,
    CUTOVER_ONLY,
    FULL_BACKFILL,
    HISTORICAL_BACKFILL_LANE,
    PRODUCTION_LANE,
    DeviceActivationInput,
    DeviceScope,
    PathActivationService,
)


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


def _activation(adapter: _SQLiteAdapter) -> PathActivationService:
    ids = count(1)
    return PathActivationService(
        adapter,  # type: ignore[arg-type]
        DualPathConfig(max_backfill_days=14),
        epoch_id_factory=lambda: f"epoch-{next(ids)}",
        now_factory=lambda: datetime(2026, 6, 20, 12, 0, 0),
    )


def _full_epoch(adapter: _SQLiteAdapter) -> str:
    epoch = _activation(adapter).create_epoch(
        ActivationRequest(
            "seq_annotation",
            FULL_BACKFILL,
            (
                DeviceActivationInput(
                    DeviceScope("site", "A", "branch"),
                    datetime(2026, 1, 4, 8),
                    date(2026, 1, 1),
                ),
            ),
        )
    )
    return epoch.activation_epoch_id


def _runner(tmp_path: Path, adapter: _SQLiteAdapter, detector, arbiter=None) -> BackfillRunner:
    return BackfillRunner(
        adapter,
        detector=detector,
        arbiter=arbiter,
        task_dir=tmp_path / "backfill_tasks",
        now_factory=lambda: datetime(2026, 6, 21, 0, 0, 0),
        task_id_factory=lambda: "bft-test",
    )


def _claims(adapter: _SQLiteAdapter, epoch_id: str):
    with adapter.get_sync_session() as session:
        return list(
            session.execute(
                select(PathActivationLaneClaim).where(
                    PathActivationLaneClaim.activation_epoch_id == epoch_id
                )
            ).scalars().all()
        )


def test_runner_only_consumes_historical_claims_and_never_writes_production_progress(
    tmp_path: Path,
) -> None:
    adapter = _SQLiteAdapter()
    epoch_id = _full_epoch(adapter)
    seen = []

    def detector(scope: DeviceScope, business_date: date):
        seen.append((scope.device_id, business_date.isoformat()))
        return {"namespace": "historical_backfill", "label": 1}

    runner = _runner(tmp_path, adapter, detector)
    task_id = runner.submit_full_backfill(epoch_id)
    task = runner.run(task_id)

    assert task.namespace == "historical_backfill"
    assert task.writes_production_ledger is False
    assert task.advances_production_frontier is False
    assert task.status == "succeeded"
    assert seen == [
        ("A", "2026-01-01"),
        ("A", "2026-01-02"),
    ]
    persisted = runner.get_status(task_id)
    assert persisted is not None
    assert all(item["namespace"] == "historical_backfill" for item in persisted.results)

    claims = {item.lane: item for item in _claims(adapter, epoch_id)}
    assert claims[HISTORICAL_BACKFILL_LANE].claim_status == "succeeded"
    assert claims[HISTORICAL_BACKFILL_LANE].backfill_task_id == task_id
    assert claims[PRODUCTION_LANE].claim_status == "claimed"
    assert claims[PRODUCTION_LANE].backfill_task_id is None
    assert claims[PRODUCTION_LANE].range_start == date(2026, 1, 3)


def test_cutover_only_has_no_historical_channel(tmp_path: Path) -> None:
    adapter = _SQLiteAdapter()
    epoch = _activation(adapter).create_epoch(
        ActivationRequest(
            "seq_annotation",
            CUTOVER_ONLY,
            (
                DeviceActivationInput(
                    DeviceScope("site", "A", "branch"),
                    datetime(2026, 1, 4, 8),
                    date(2026, 1, 1),
                ),
            ),
        )
    )
    runner = _runner(tmp_path, adapter, lambda *_: {})
    with pytest.raises(BackfillRunnerError, match="historical_backfill"):
        runner.submit_full_backfill(epoch.activation_epoch_id)


def test_failed_run_keeps_claim_until_cancel_and_release(tmp_path: Path) -> None:
    adapter = _SQLiteAdapter()
    epoch_id = _full_epoch(adapter)

    def boom(*_args):
        raise RuntimeError("injected detector failure")

    runner = _runner(tmp_path, adapter, boom)
    task_id = runner.submit_full_backfill(epoch_id)
    failed = runner.run(task_id)
    assert failed.status == "failed"
    hist = next(item for item in _claims(adapter, epoch_id) if item.lane == HISTORICAL_BACKFILL_LANE)
    assert hist.claim_status == "failed"
    assert hist.backfill_task_id == task_id

    recovered_calls = []

    def ok(scope, business_date):
        recovered_calls.append(business_date.isoformat())
        return {}

    runner._detector = ok
    runner.retry(task_id)
    succeeded = runner.run(task_id)
    assert succeeded.status == "succeeded"
    assert recovered_calls == ["2026-01-01", "2026-01-02"]

    queued_id_factory = {"n": 0}

    def next_id():
        queued_id_factory["n"] += 1
        return f"bft-{queued_id_factory['n']}"

    cancel_runner = BackfillRunner(
        adapter,
        detector=ok,
        task_dir=tmp_path / "backfill_tasks",
        task_id_factory=next_id,
    )
    # 已成功的范围不能再提交占用
    with pytest.raises(BackfillRunnerError, match="已被任务"):
        cancel_runner.submit_full_backfill(epoch_id)


def test_cancel_keeps_claim_and_release_is_explicit(tmp_path: Path) -> None:
    adapter = _SQLiteAdapter()
    epoch_id = _full_epoch(adapter)
    runner = _runner(tmp_path, adapter, lambda *_: {})
    task_id = runner.submit_full_backfill(epoch_id)
    runner.cancel(task_id)
    hist = next(item for item in _claims(adapter, epoch_id) if item.lane == HISTORICAL_BACKFILL_LANE)
    assert hist.claim_status == "claimed"
    assert runner.get_status(task_id).status == "cancelled"

    runner.release(task_id)
    hist = next(item for item in _claims(adapter, epoch_id) if item.lane == HISTORICAL_BACKFILL_LANE)
    assert hist.claim_status == "cancelled"


def test_capacity_shortage_does_not_start_history_or_touch_production(tmp_path: Path) -> None:
    adapter = _SQLiteAdapter()
    epoch_id = _full_epoch(adapter)
    arbiter = BackfillCapacityArbiter(
        CapacityResources(10, 10, 10, 10),
        production_capacity_reserved_ratio=1.0,
    )
    seen = []
    runner = _runner(tmp_path, adapter, lambda *args: seen.append(args) or {}, arbiter=arbiter)
    task_id = runner.submit_full_backfill(epoch_id)
    task = runner.run(task_id)
    assert task.status == "queued"
    assert task.last_error == "historical_capacity_unavailable"
    assert seen == []
    claims = {item.lane: item.claim_status for item in _claims(adapter, epoch_id)}
    assert claims[HISTORICAL_BACKFILL_LANE] == "claimed"
    assert claims[PRODUCTION_LANE] == "claimed"
# @AI_GENERATED: end
