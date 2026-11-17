# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Property 24、28–33：Ledger 权威、独立推进、指纹、分批、frontier 摘要与原子失败。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Generator, List, Type
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.db.models.pv_fault import PathActivationDeviceScope, SeqDeviceDayLedger
from services.scheduler.pv_dual_path.config import DualPathConfig
from services.scheduler.pv_dual_path.immutable_batch_recovery import ImmutableBatchRecovery
from services.scheduler.pv_dual_path.path_isolation import PathIsolationRegistry
from services.scheduler.pv_dual_path.seq_daily_strategy import SeqDailyStrategy
from services.scheduler.pv_dual_path.seq_device_day_ledger import (
    DeviceDayKey,
    DeviceKey,
    LedgerOperationError,
    SeqDeviceDayLedgerRepository,
    stable_input_fingerprint,
)


class _FailAfterFlushSession(Session):
    def flush(self, objects=None) -> None:  # type: ignore[no-untyped-def,override]
        super().flush(objects)
        raise RuntimeError("injected ledger flush failure")


class _SQLiteAdapter:
    def __init__(self, *, engine=None, session_class: Type[Session] = Session) -> None:
        self.engine = engine or create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self._factory = sessionmaker(bind=self.engine, class_=session_class, expire_on_commit=False)

    @contextmanager
    def get_sync_session(self) -> Generator[Session, None, None]:
        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _adapter() -> _SQLiteAdapter:
    result = _SQLiteAdapter()
    SeqDeviceDayLedger.__table__.create(result.engine)
    PathActivationDeviceScope.__table__.create(result.engine)
    return result


def _key(day: int, site: str = "site-a") -> DeviceDayKey:
    return DeviceDayKey(
        slot="pv_fault",
        modeling_path="seq_annotation",
        site_id=site,
        device_id="device-a",
        branch_id="branch-a",
        business_date=date(2026, 1, day),
    )


_STATUSES = frozenset(
    {"waiting_data", "ready", "running", "succeeded", "failed", "revision_pending"}
)
_days = st.integers(min_value=1, max_value=12)
_values = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
_limits = st.integers(min_value=-5, max_value=1200)


# Feature: pv-fault-dual-path-serving, Property 28: Ledger 六元组唯一且记录有效
@given(day_a=_days, day_b=_days, site_b=st.sampled_from(["site-a", "site-b"]))
@settings(max_examples=100, deadline=None)
def test_property_28_ledger_keys_unique_and_status_valid(day_a: int, day_b: int, site_b: str) -> None:
    adapter = _adapter()
    repo = SeqDeviceDayLedgerRepository(adapter, activation_epoch_id="epoch-1")  # type: ignore[arg-type]
    first = repo.upsert_candidate(_key(day_a), "fp-a", is_ready=True)
    second = repo.upsert_candidate(_key(day_b, site=site_b), "fp-b")
    listed = repo.list(slot="pv_fault", page=1, page_size=50)["items"]
    keys = [item.key.as_primary_key() for item in listed]
    serialized = [tuple(sorted(item.items())) for item in keys]
    assert len(serialized) == len(set(serialized))
    for item in listed:
        assert item.status in _STATUSES
        assert item.attempt_count >= 0
        if item.status == "failed":
            assert item.last_error
        if item.status == "succeeded":
            assert item.batch_id
    same_key = day_a == day_b and site_b == "site-a"
    if same_key:
        assert first.key == second.key
        assert len(listed) == 1
    else:
        assert len(listed) == 2


# Feature: pv-fault-dual-path-serving, Property 29: 设备日独立推进
@given(early=st.integers(min_value=1, max_value=5), late=st.integers(min_value=6, max_value=12))
@settings(max_examples=100, deadline=None)
def test_property_29_earlier_waiting_does_not_block_later_ready(early: int, late: int) -> None:
    adapter = _adapter()
    repo = SeqDeviceDayLedgerRepository(adapter, activation_epoch_id="epoch-1")  # type: ignore[arg-type]
    repo.upsert_candidate(_key(early), "wait")
    failed_key = _key(early + 0 if early < late else late - 1 if late > 1 else 1)
    # 固定再写一个失败日，确保早于 late
    fail_day = min(early, late - 1) if late > 1 else 1
    fail_key = _key(fail_day, site="site-fail")
    repo.upsert_candidate(fail_key, "fail", is_ready=True)
    repo.mark_running(fail_key)
    repo.mark_failed(fail_key, "temporary")
    late_key = _key(late)
    repo.upsert_candidate(late_key, "ready-late", is_ready=True)
    runnable = repo.list_runnable("pv_fault", 10)
    assert any(item.key == late_key for item in runnable)
    running = repo.mark_running(late_key)
    assert running.status == "running"
    done = repo.mark_succeeded(late_key, "batch-late", "ready-late")
    assert done.status == "succeeded"
    assert repo.query(fail_key).status == "failed"


# Feature: pv-fault-dual-path-serving, Property 30: 输入指纹幂等与不可变修订
@given(base=_values, delta=st.floats(min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_30_fingerprint_idempotent_and_revision_immutable(tmp_path: Path, base: float, delta: float) -> None:
    adapter = _adapter()
    repo = SeqDeviceDayLedgerRepository(adapter, activation_epoch_id="epoch-1")  # type: ignore[arg-type]
    isolation = PathIsolationRegistry(adapter, backend_service_dir=tmp_path / uuid.uuid4().hex)  # type: ignore[arg-type]
    recovery = ImmutableBatchRecovery(repo, isolation)
    key = _key(3)
    ts = datetime(2026, 1, 3, 8, 0, 0)
    points = [(ts, base)]
    first = recovery.prepare_for_inference(key, points, activation_epoch_id="epoch-1")
    assert first.action == "run"
    fp = stable_input_fingerprint(points)
    repo.mark_succeeded(key, "batch-1", fp)
    isolation.write_batch(
        "pv_fault",
        "seq_annotation",
        "batch-1",
        {
            "business_date": "2026-01-03",
            "input_fingerprint": fp,
            "artifact_path": "data/models/a.pkl",
            "supersedes_batch_id": None,
        },
    )
    batch_path = isolation.batch_dir("pv_fault", "seq_annotation") / "batch-1.json"
    original_bytes = batch_path.read_bytes()
    skip = recovery.prepare_for_inference(key, points, activation_epoch_id="epoch-1")
    assert skip.action == "skip"
    changed = recovery.prepare_for_inference(key, [(ts, base + delta)], activation_epoch_id="epoch-1")
    assert changed.action == "run"
    revised = repo.query(key)
    assert revised.status == "running"
    assert batch_path.read_bytes() == original_bytes


# Feature: pv-fault-dual-path-serving, Property 31: 按设备日隔离并按有效上限分批
@given(raw=_limits, count=st.integers(min_value=1, max_value=8))
@settings(max_examples=100, deadline=None)
def test_property_31_cycle_limit_and_date_order(raw: int, count: int) -> None:
    strategy = SeqDailyStrategy(object(), config=DualPathConfig(max_device_days_per_cycle=raw))  # type: ignore[arg-type]
    limit, invalid = strategy._cycle_limit()
    if 1 <= raw <= 1000:
        assert limit == raw
        assert invalid is False
    else:
        assert limit == 50
        assert invalid is True
    adapter = _adapter()
    repo = SeqDeviceDayLedgerRepository(adapter, activation_epoch_id="epoch-1")  # type: ignore[arg-type]
    for day in range(1, count + 1):
        repo.upsert_candidate(_key(day), f"fp-{day}", is_ready=True)
    chosen = repo.list_runnable("pv_fault", limit)
    expected_n = min(limit, count)
    assert len(chosen) == expected_n
    dates = [item.key.business_date for item in chosen]
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)


# Feature: pv-fault-dual-path-serving, Property 32: Continuous Completion Frontier 仅为摘要
@given(gap=st.integers(min_value=1, max_value=4))
@settings(max_examples=100, deadline=None)
def test_property_32_frontier_does_not_exclude_later_ready(gap: int) -> None:
    adapter = _adapter()
    repo = SeqDeviceDayLedgerRepository(adapter, activation_epoch_id="epoch-1")  # type: ignore[arg-type]
    with adapter.get_sync_session() as session:
        session.add(
            PathActivationDeviceScope(
                activation_epoch_id="epoch-1",
                site_id="site-a",
                device_id="device-a",
                branch_id="branch-a",
                effective_from_date=date(2026, 1, 1),
            )
        )
    repo.upsert_candidate(_key(1), "fp-1")
    late = 1 + gap
    repo.upsert_candidate(_key(late), "fp-late", is_ready=True)
    frontier = repo.compute_frontier(
        DeviceKey("pv_fault", "seq_annotation", "site-a", "device-a", "branch-a"),
        "epoch-1",
    )
    runnable = repo.list_runnable("pv_fault", 10)
    assert any(item.key.business_date == date(2026, 1, late) for item in runnable)
    assert frontier != date(2026, 1, late)


# Feature: pv-fault-dual-path-serving, Property 33: Ledger 失败原子且可重试
@given(error_text=st.text(min_size=1, max_size=24))
@settings(max_examples=100, deadline=None)
def test_property_33_write_failure_rolls_back_and_failed_is_retryable(error_text: str) -> None:
    adapter = _adapter()
    repo = SeqDeviceDayLedgerRepository(adapter, activation_epoch_id="epoch-1")  # type: ignore[arg-type]
    target = _key(1)
    other = _key(2, site="site-b")
    repo.upsert_candidate(target, "fp-t", is_ready=True)
    repo.mark_running(target)
    repo.upsert_candidate(other, "fp-o")
    before_t = repo.query(target)
    before_o = repo.query(other)
    failing = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        _SQLiteAdapter(engine=adapter.engine, session_class=_FailAfterFlushSession),
        activation_epoch_id="epoch-1",
    )
    with pytest.raises(LedgerOperationError) as exc:
        failing.mark_failed(target, error_text)
    assert "site_id='site-a'" in str(exc.value)
    assert repo.query(target) == before_t
    assert repo.query(other) == before_o
    failed = repo.mark_failed(target, error_text)
    assert failed.status == "failed"
    assert failed.attempt_count == before_t.attempt_count + 1
    ready = repo.mark_ready(target)
    assert ready.status == "ready"


# Feature: pv-fault-dual-path-serving, Property 24: 失败后从最后确认事实恢复
@given(value=_values)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_24_restart_skips_confirmed_and_retries_unconfirmed(tmp_path: Path, value: float) -> None:
    adapter = _adapter()
    repo = SeqDeviceDayLedgerRepository(adapter, activation_epoch_id="epoch-1")  # type: ignore[arg-type]
    isolation = PathIsolationRegistry(adapter, backend_service_dir=tmp_path / uuid.uuid4().hex)  # type: ignore[arg-type]
    recovery = ImmutableBatchRecovery(repo, isolation)
    confirmed = _key(1)
    pending = _key(2)
    ts = datetime(2026, 1, 1, 8, 0, 0)
    points = [(ts, value)]
    first = recovery.prepare_for_inference(confirmed, points, activation_epoch_id="epoch-1")
    recovery.persist_success(first, batch_id="batch-ok", payload={"artifact_path": "data/models/a.pkl"})
    second = recovery.prepare_for_inference(pending, points, activation_epoch_id="epoch-1")
    assert second.action == "run"
    recovery.record_failure(second, "predictor boom")
    skip = recovery.prepare_for_inference(confirmed, points, activation_epoch_id="epoch-1")
    retry = recovery.prepare_for_inference(pending, points, activation_epoch_id="epoch-1")
    assert skip.action == "skip"
    assert retry.action == "run"
    assert repo.query(confirmed).status == "succeeded"
    assert repo.query(pending).status == "running"
# @AI_GENERATED: end
