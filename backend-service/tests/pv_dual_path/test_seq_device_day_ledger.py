# @AI_GENERATED
# -*- coding: utf-8 -*-
"""SeqDeviceDayLedgerRepository 定向单元测试。

测试使用 SQLite 内存数据库和轻量 DBAdapter 兼容夹具，不连接生产库。覆盖稳定输入指纹、
六态迁移、失败计数隔离、事务回滚、稳定分页、无队头阻塞 runnable 查询和连续完成前沿。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Generator, Optional, Type

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.db.models.pv_fault import PathActivationDeviceScope, SeqDeviceDayLedger
from services.scheduler.pv_dual_path.immutable_batch_recovery import ImmutableBatchRecovery
from services.scheduler.pv_dual_path.path_isolation import PathIsolationRegistry
from services.scheduler.pv_dual_path.seq_device_day_ledger import (
    DeviceDayKey,
    DeviceKey,
    LedgerOperationError,
    SeqDeviceDayLedgerRepository,
    stable_input_fingerprint,
)


class _FailAfterFlushSession(Session):
    """先把 ORM 变更 flush 到事务，再注入异常以验证外层 rollback。"""

    def flush(self, objects=None) -> None:  # type: ignore[no-untyped-def,override]
        super().flush(objects)
        raise RuntimeError("injected ledger flush failure")


class _SQLiteAdapter:
    """只实现仓储所需同步 Session 协议的 SQLite 内存适配器。"""

    def __init__(
        self,
        *,
        engine=None,
        session_class: Type[Session] = Session,
    ) -> None:
        self.engine = engine or create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self._factory = sessionmaker(
            bind=self.engine,
            class_=session_class,
            expire_on_commit=False,
        )

    @contextmanager
    def get_sync_session(self) -> Generator[Session, None, None]:
        """模拟 DBAdapter 的成功提交、异常回滚和最终关闭语义。"""

        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@pytest.fixture()
def adapter() -> _SQLiteAdapter:
    """创建只含本测试所需两张 ORM 表的内存数据库。"""

    result = _SQLiteAdapter()
    SeqDeviceDayLedger.__table__.create(result.engine)
    PathActivationDeviceScope.__table__.create(result.engine)
    return result


def _key(day: int, *, site: str = "site-a", device: str = "device-a") -> DeviceDayKey:
    """构造固定槽位和路径的测试六元组键。"""

    return DeviceDayKey(
        slot="pv_fault",
        modeling_path="seq_annotation",
        site_id=site,
        device_id=device,
        branch_id="branch-a",
        business_date=date(2026, 1, day),
    )


def _succeed(
    repository: SeqDeviceDayLedgerRepository,
    key: DeviceDayKey,
    fingerprint: str,
    batch_id: str,
) -> None:
    """通过公开状态接口把一个新候选推进到 succeeded。"""

    repository.upsert_candidate(key, fingerprint, is_ready=True)
    repository.mark_running(key)
    repository.mark_succeeded(key, batch_id, fingerprint)


def test_stable_input_fingerprint_is_order_independent_and_change_sensitive() -> None:
    """重复时间戳按完整点稳定排序；相同集合重排同摘要，增删改均异摘要。"""

    timestamp = datetime(2026, 1, 2, 3, 4, 5)
    points = [
        (timestamp, 2.0),
        (timestamp, 1.0),
        (datetime(2026, 1, 2, 3, 9, 5), 3.5),
    ]
    original = stable_input_fingerprint(points)

    assert len(original) == 64
    assert stable_input_fingerprint(list(reversed(points))) == original
    assert stable_input_fingerprint([points[1], points[2], points[0]]) == original
    assert stable_input_fingerprint(points + [(timestamp, 1.0)]) != original
    assert stable_input_fingerprint(points[:-1]) != original
    assert stable_input_fingerprint([(timestamp, 2.0), (timestamp, 1.1), points[2]]) != original


def test_state_machine_retry_revision_and_full_key_errors(adapter: _SQLiteAdapter) -> None:
    """状态机只走合法边，失败只计一次，成功同指纹幂等且变更进入待修订。"""

    repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        adapter,
        activation_epoch_id="epoch-1",
    )
    key = _key(1)

    waiting = repository.upsert_candidate(key, "fingerprint-v1")
    assert waiting.status == "waiting_data"
    ready = repository.upsert_candidate(key, "fingerprint-v1", is_ready=True)
    assert ready.status == "ready"
    assert repository.mark_running(key).status == "running"

    failed = repository.mark_failed(key, "predictor timeout")
    assert failed.status == "failed"
    assert failed.attempt_count == 1
    assert failed.last_error == "predictor timeout"

    assert repository.mark_ready(key).status == "ready"
    repository.mark_running(key)
    succeeded = repository.mark_succeeded(key, "batch-1", "fingerprint-v1")
    assert succeeded.status == "succeeded"
    assert succeeded.attempt_count == 1
    assert succeeded.last_error is None

    unchanged = repository.upsert_candidate(key, "fingerprint-v1", is_ready=True)
    assert unchanged == succeeded
    revision = repository.upsert_candidate(key, "fingerprint-v2", is_ready=True)
    assert revision.status == "revision_pending"
    assert revision.input_fingerprint == "fingerprint-v1"
    assert revision.supersedes_batch_id == "batch-1"

    repository.mark_running(key)
    revised = repository.mark_succeeded(key, "batch-2", "fingerprint-v2")
    assert revised.status == "succeeded"
    assert revised.batch_id == "batch-2"
    assert revised.supersedes_batch_id == "batch-1"
    assert revised.attempt_count == 1

    with pytest.raises(LedgerOperationError) as exc_info:
        repository.mark_running(key)
    message = str(exc_info.value)
    for expected in (
        "slot='pv_fault'",
        "modeling_path='seq_annotation'",
        "site_id='site-a'",
        "device_id='device-a'",
        "branch_id='branch-a'",
        "business_date=datetime.date(2026, 1, 1)",
    ):
        assert expected in message


def test_list_runnable_skips_earlier_waiting_and_failed_and_is_stable(
    adapter: _SQLiteAdapter,
) -> None:
    """更早 waiting/failed 不阻塞更晚 ready，并按日期与设备键稳定排序和限额。"""

    repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        adapter,
        activation_epoch_id="epoch-1",
    )
    repository.upsert_candidate(_key(1), "wait")
    failed_key = _key(2)
    repository.upsert_candidate(failed_key, "failed", is_ready=True)
    repository.mark_running(failed_key)
    repository.mark_failed(failed_key, "temporary")

    repository.upsert_candidate(_key(4, site="site-b"), "ready-b", is_ready=True)
    repository.upsert_candidate(_key(3, site="site-z"), "ready-z", is_ready=True)
    repository.upsert_candidate(_key(3, site="site-a"), "ready-a", is_ready=True)

    runnable = repository.list_runnable("pv_fault", 2)
    assert [(item.key.business_date, item.key.site_id) for item in runnable] == [
        (date(2026, 1, 3), "site-a"),
        (date(2026, 1, 3), "site-z"),
    ]
    assert all(item.status == "ready" for item in runnable)

    first_page = repository.list(page=1, page_size=2, slot="pv_fault")
    second_page = repository.list(page=2, page_size=2, slot="pv_fault")
    assert first_page["total"] == 5
    assert [item.key.business_date for item in first_page["items"]] == [
        date(2026, 1, 1),
        date(2026, 1, 2),
    ]
    assert [(item.key.business_date, item.key.site_id) for item in second_page["items"]] == [
        (date(2026, 1, 3), "site-a"),
        (date(2026, 1, 3), "site-z"),
    ]


def test_failed_write_rolls_back_target_and_other_records(adapter: _SQLiteAdapter) -> None:
    """flush 后异常会回滚目标失败计数/状态，目标及其他设备日都保持写前状态。"""

    normal_repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        adapter,
        activation_epoch_id="epoch-1",
    )
    target_key = _key(1)
    other_key = _key(2, site="site-b")
    normal_repository.upsert_candidate(target_key, "target", is_ready=True)
    normal_repository.mark_running(target_key)
    normal_repository.upsert_candidate(other_key, "other")
    before_target = normal_repository.query(target_key)
    before_other = normal_repository.query(other_key)

    failing_adapter = _SQLiteAdapter(
        engine=adapter.engine,
        session_class=_FailAfterFlushSession,
    )
    failing_repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        failing_adapter,
        activation_epoch_id="epoch-1",
    )
    with pytest.raises(LedgerOperationError) as exc_info:
        failing_repository.mark_failed(target_key, "boom")

    assert "site_id='site-a'" in str(exc_info.value)
    assert "business_date=datetime.date(2026, 1, 1)" in str(exc_info.value)
    assert normal_repository.query(target_key) == before_target
    assert normal_repository.query(other_key) == before_other


def test_compute_frontier_stops_at_first_gap_or_non_succeeded(
    adapter: _SQLiteAdapter,
) -> None:
    """frontier 从当前 Epoch 责任起始日连续派生，遇未成功日期即停止。"""

    repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        adapter,
        activation_epoch_id="epoch-1",
    )
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

    _succeed(repository, _key(1), "fp-1", "batch-1")
    _succeed(repository, _key(2), "fp-2", "batch-2")
    repository.upsert_candidate(_key(3), "waiting")
    _succeed(repository, _key(4), "fp-4", "batch-4")

    device_key = DeviceKey(
        slot="pv_fault",
        modeling_path="seq_annotation",
        site_id="site-a",
        device_id="device-a",
        branch_id="branch-a",
    )
    assert repository.compute_frontier(device_key, "epoch-1") == date(2026, 1, 2)

    repository.upsert_candidate(_key(3), "fp-3", is_ready=True)
    repository.mark_running(_key(3))
    repository.mark_succeeded(_key(3), "batch-3", "fp-3")
    assert repository.compute_frontier(device_key, "epoch-1") == date(2026, 1, 4)


def test_compute_frontier_requires_scope_start(adapter: _SQLiteAdapter) -> None:
    """缺少设备责任起始日时不从最早 Ledger 猜测 frontier。"""

    repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        adapter,
        activation_epoch_id="epoch-1",
    )
    _succeed(repository, _key(2), "fp-2", "batch-2")
    device_key = DeviceKey(
        slot="pv_fault",
        modeling_path="seq_annotation",
        site_id="site-a",
        device_id="device-a",
        branch_id="branch-a",
    )

    assert repository.compute_frontier(device_key, "epoch-1") is None


def test_reconcile_succeeded_from_orphan_batch_is_idempotent_and_chain_safe(
    adapter: _SQLiteAdapter,
) -> None:
    """孤儿首批可建 succeeded；连续修订可补齐；无关旧批次不得覆盖较新事实。"""

    repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        adapter,
        activation_epoch_id="epoch-1",
    )
    key = _key(1)
    first = repository.reconcile_succeeded_from_batch(
        key,
        batch_id="batch-1",
        fingerprint="fingerprint-v1",
        activation_epoch_id="epoch-1",
    )
    assert first.status == "succeeded"
    assert first.batch_id == "batch-1"
    assert repository.reconcile_succeeded_from_batch(
        key,
        batch_id="batch-1",
        fingerprint="fingerprint-v1",
        activation_epoch_id="epoch-1",
    ) == first

    revised = repository.reconcile_succeeded_from_batch(
        key,
        batch_id="batch-2",
        fingerprint="fingerprint-v2",
        activation_epoch_id="epoch-1",
        supersedes_batch_id="batch-1",
    )
    assert revised.batch_id == "batch-2"
    assert revised.supersedes_batch_id == "batch-1"
    assert revised.input_fingerprint == "fingerprint-v2"

    with pytest.raises(LedgerOperationError, match="修订链不连续"):
        repository.reconcile_succeeded_from_batch(
            key,
            batch_id="stale-branch",
            fingerprint="stale",
            activation_epoch_id="epoch-1",
            supersedes_batch_id="batch-1",
        )
    assert repository.query(key) == revised


def test_revision_failure_restores_old_succeeded_fact(adapter: _SQLiteAdapter) -> None:
    """晚到数据修订失败只记错误和次数，旧成功批次与指纹继续作为已确认事实。"""

    repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        adapter,
        activation_epoch_id="epoch-1",
    )
    key = _key(1)
    _succeed(repository, key, "fingerprint-v1", "batch-1")
    revision = repository.upsert_candidate(key, "fingerprint-v2", is_ready=True)
    assert revision.status == "revision_pending"
    repository.mark_running(key)

    restored = repository.mark_failed(key, "revision predictor failed")
    assert restored.status == "succeeded"
    assert restored.batch_id == "batch-1"
    assert restored.input_fingerprint == "fingerprint-v1"
    assert restored.supersedes_batch_id is None
    assert restored.attempt_count == 1
    assert restored.last_error == "revision predictor failed"


class _FailOnceReconcileLedger:
    """在批次写完后的首次 Ledger 对账注入崩溃，其他接口委托真实仓储。"""

    def __init__(self, delegate: SeqDeviceDayLedgerRepository) -> None:
        self._delegate = delegate
        self.failed = False

    def __getattr__(self, name):  # type: ignore[no-untyped-def]
        return getattr(self._delegate, name)

    def reconcile_succeeded_from_batch(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self.failed:
            self.failed = True
            raise LedgerOperationError(args[0], "injected post-batch ledger failure")
        return self._delegate.reconcile_succeeded_from_batch(*args, **kwargs)


def test_orphan_batch_recovery_skips_predictor_and_preserves_revision_chain(
    adapter: _SQLiteAdapter,
    tmp_path,
) -> None:
    """批次落盘后 Ledger 失败可在下轮补齐；同指纹不再推理，变化写不可变修订链。"""

    repository = SeqDeviceDayLedgerRepository(  # type: ignore[arg-type]
        adapter,
        activation_epoch_id="epoch-1",
    )
    registry = PathIsolationRegistry(  # type: ignore[arg-type]
        adapter,
        backend_service_dir=tmp_path,
    )
    key = _key(1)
    points_v1 = [
        {"time": datetime(2026, 1, 1, 0, 0), "value": 1.0},
        {"time": datetime(2026, 1, 1, 0, 5), "value": 2.0},
    ]
    failing = ImmutableBatchRecovery(
        _FailOnceReconcileLedger(repository),  # type: ignore[arg-type]
        registry,
    )
    first_decision = failing.prepare_for_inference(
        key,
        points_v1,
        activation_epoch_id="epoch-1",
    )
    assert first_decision.action == "run"
    with pytest.raises(LedgerOperationError, match="post-batch ledger failure"):
        failing.persist_success(
            first_decision,
            batch_id="batch-1",
            payload={"predictions": [{"label": 0}]},
        )
    assert registry.list_batch_ids("pv_fault", "seq_annotation") == ["batch-1"]
    assert repository.query(key).status == "running"  # type: ignore[union-attr]

    recovery = ImmutableBatchRecovery(repository, registry)
    recovered = recovery.prepare_for_inference(
        key,
        list(reversed(points_v1)),
        activation_epoch_id="epoch-1",
    )
    assert recovered.action == "skip"
    assert recovered.recovered_batch_id == "batch-1"
    assert repository.query(key).batch_id == "batch-1"  # type: ignore[union-attr]
    old_batch_bytes = (
        registry.batch_dir("pv_fault", "seq_annotation") / "batch-1.json"
    ).read_bytes()

    points_v2 = [*points_v1, {"time": datetime(2026, 1, 1, 0, 10), "value": 3.0}]
    revision = recovery.prepare_for_inference(
        key,
        points_v2,
        activation_epoch_id="epoch-1",
    )
    assert revision.action == "run"
    assert revision.supersedes_batch_id == "batch-1"
    revised = recovery.persist_success(
        revision,
        batch_id="batch-2",
        payload={"predictions": [{"label": 1}]},
    )
    assert revised.status == "succeeded"
    assert revised.batch_id == "batch-2"
    assert revised.supersedes_batch_id == "batch-1"
    assert (
        registry.batch_dir("pv_fault", "seq_annotation") / "batch-1.json"
    ).read_bytes() == old_batch_bytes
# @AI_GENERATED: end
