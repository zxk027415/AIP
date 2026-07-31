# -*- coding: utf-8 -*-
"""
tests/db/test_point_label_repository.py — PointLabelRepository 单元测试

用真实 DBAdapter 连接（复用 backend-service 现有 DB 配置），对 point_labels /
label_ops 两张表做增删查验证。测试设备 ID 使用专属前缀 `TEST-plr-`，
每个用例结束后清理自己写入的数据，不污染其他数据。

对应 `.kiro/specs/pv-fault-label-segment-redesign/tasks.md` 任务 4。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.models.pv_fault import LabelOp, PointLabel
from services.db.repositories.point_label import PointLabelRepository


@pytest.fixture(scope="module")
def adapter():
    a = DBAdapter(DBConfig())
    yield a
    a.dispose()


@pytest.fixture()
def repo(adapter):
    return PointLabelRepository(adapter)


@pytest.fixture()
def device(adapter):
    """每个用例生成唯一设备三元组，用例结束后清理该设备下所有测试数据。"""
    dev_id = f"TEST-plr-{uuid.uuid4().hex[:8]}"
    site_id, branch_id = "TEST-site", "1"
    yield site_id, dev_id, branch_id
    with adapter.get_sync_session() as session:
        session.execute(
            delete(PointLabel).where(
                PointLabel.site_id == site_id, PointLabel.device_id == dev_id
            )
        )
        session.execute(
            delete(LabelOp).where(
                LabelOp.site_id == site_id, LabelOp.device_id == dev_id
            )
        )


def _mk_op(site_id, dev_id, branch_id, op_id, t_start, t_end, label_id, source="day_label", priority=10, status="active", **extra):
    payload = dict(
        op_id=op_id, site_id=site_id, device_id=dev_id, branch_id=branch_id,
        t_start=t_start, t_end=t_end, label_id=label_id, source=source,
        priority=priority, status=status, label_space_version="ls-v2",
    )
    payload.update(extra)
    return payload


def test_insert_and_query_op_by_id(repo, device):
    site_id, dev_id, branch_id = device
    t0 = datetime(2020, 5, 8, 0, 0)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    written = repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_id, t0, t0 + timedelta(days=1), 1))

    assert written["op_id"] == op_id
    assert written["status"] == "active"

    fetched = repo.query_op_by_id(op_id)
    assert fetched is not None
    assert fetched["label_id"] == 1
    assert fetched["source"] == "day_label"
    assert fetched["priority"] == 10


def test_revoke_op_marks_status_and_is_idempotent_on_missing(repo, device):
    site_id, dev_id, branch_id = device
    t0 = datetime(2020, 5, 8, 0, 0)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_id, t0, t0 + timedelta(hours=6), 1))

    assert repo.revoke_op(op_id) is True
    fetched = repo.query_op_by_id(op_id)
    assert fetched["status"] == "revoked"

    # 不存在的 op_id 返回 False，不抛异常
    assert repo.revoke_op("op-does-not-exist") is False


def test_query_active_ops_filters_by_time_overlap_and_status(repo, device):
    site_id, dev_id, branch_id = device
    day0 = datetime(2020, 5, 8, 0, 0)

    op_a = f"op-{uuid.uuid4().hex[:12]}"  # 整天，priority 10（day_label）
    op_b = f"op-{uuid.uuid4().hex[:12]}"  # 06:00-18:40，priority 100（human_range）
    op_c = f"op-{uuid.uuid4().hex[:12]}"  # 已撤销，不应出现在结果里
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_a, day0, day0 + timedelta(days=1), 1, source="day_label", priority=10))
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_b, day0 + timedelta(hours=6), day0 + timedelta(hours=18, minutes=40), 1, source="human_range", priority=100, reviewer="tester", source_ref="rev-x"))
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_c, day0, day0 + timedelta(days=1), 1, source="day_label", priority=10, status="revoked"))

    active = repo.query_active_ops(site_id, dev_id, branch_id, day0, day0 + timedelta(days=1))
    active_ids = {r["op_id"] for r in active}

    assert op_a in active_ids
    assert op_b in active_ids
    assert op_c not in active_ids
    # 按 priority DESC 排序，human_range(100) 应排在 day_label(10) 前面
    assert active[0]["op_id"] == op_b


def test_query_active_human_range_overlap_only_matches_human_range_source(repo, device):
    site_id, dev_id, branch_id = device
    day0 = datetime(2020, 5, 8, 0, 0)

    op_range = f"op-{uuid.uuid4().hex[:12]}"
    op_day = f"op-{uuid.uuid4().hex[:12]}"
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_range, day0 + timedelta(hours=6), day0 + timedelta(hours=18), 1, source="human_range", priority=100, reviewer="t", source_ref="r"))
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_day, day0, day0 + timedelta(days=1), 1, source="day_label", priority=10))

    # 与 op_range 重叠的查询区间
    overlap = repo.query_active_human_range_overlap(
        site_id, dev_id, branch_id, day0 + timedelta(hours=10), day0 + timedelta(hours=12)
    )
    overlap_ids = {r["op_id"] for r in overlap}
    assert op_range in overlap_ids
    assert op_day not in overlap_ids  # day_label 不是 human_range，不应命中

    # 不重叠的查询区间应为空
    no_overlap = repo.query_active_human_range_overlap(
        site_id, dev_id, branch_id, day0 + timedelta(hours=20), day0 + timedelta(hours=22)
    )
    assert no_overlap == []


def test_query_ops_by_parent_returns_companion_op(repo, device):
    site_id, dev_id, branch_id = device
    day0 = datetime(2020, 5, 8, 0, 0)
    parent_op = f"op-{uuid.uuid4().hex[:12]}"
    companion_op = f"op-{uuid.uuid4().hex[:12]}"
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, parent_op, day0 + timedelta(hours=6), day0 + timedelta(hours=18, minutes=40), 1, source="human_range", priority=100, reviewer="t", source_ref="r"))
    repo.insert_op(_mk_op(
        site_id, dev_id, branch_id, companion_op, day0, day0 + timedelta(days=1), 0,
        source="human_day", priority=80, reviewer="t", source_ref="r",
        rest_of_day_policy="normal", parent_op_id=parent_op,
    ))

    companions = repo.query_ops_by_parent(parent_op)
    assert len(companions) == 1
    assert companions[0]["op_id"] == companion_op
    assert companions[0]["label_id"] == 0


def test_upsert_points_writes_and_updates(repo, device):
    site_id, dev_id, branch_id = device
    t0 = datetime(2020, 5, 8, 6, 0)
    op_id = f"op-{uuid.uuid4().hex[:12]}"

    rows = [
        {
            "site_id": site_id, "device_id": dev_id, "branch_id": branch_id,
            "time": t0 + timedelta(minutes=5 * i),
            "label_id": 1, "source": "human_range", "priority": 100,
            "op_id": op_id, "label_space_version": "ls-v2",
            "updated_at": datetime.utcnow(),
        }
        for i in range(3)
    ]
    affected = repo.upsert_points(rows)
    assert affected >= 3  # MySQL upsert rowcount：新插入计 1，更新计 2；首次写入应 >= 3

    fetched = repo.query_points(site_id, dev_id, branch_id)
    assert len(fetched) == 3
    assert all(r["label_id"] == 1 for r in fetched)
    assert [r["time"] for r in fetched] == sorted(r["time"] for r in fetched)  # 按 time 升序

    # upsert 覆盖：同主键第二次写入改标签，行数不应增加
    rows2 = [dict(r, label_id=0, source="human_day", priority=80) for r in rows]
    repo.upsert_points(rows2)
    fetched2 = repo.query_points(site_id, dev_id, branch_id)
    assert len(fetched2) == 3
    assert all(r["label_id"] == 0 for r in fetched2)


def test_query_points_respects_time_range(repo, device):
    site_id, dev_id, branch_id = device
    t0 = datetime(2020, 5, 8, 0, 0)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    rows = [
        {
            "site_id": site_id, "device_id": dev_id, "branch_id": branch_id,
            "time": t0 + timedelta(hours=h),
            "label_id": 1, "source": "day_label", "priority": 10,
            "op_id": op_id, "label_space_version": "ls-v2",
            "updated_at": datetime.utcnow(),
        }
        for h in range(0, 24, 6)  # 00:00, 06:00, 12:00, 18:00
    ]
    repo.upsert_points(rows)

    subset = repo.query_points(site_id, dev_id, branch_id, t0 + timedelta(hours=6), t0 + timedelta(hours=18))
    hours = sorted((r["time"] - t0).total_seconds() / 3600 for r in subset)
    assert hours == [6.0, 12.0]  # 半开区间 [06:00, 18:00)，18:00 不含


def test_delete_points_in_range_removes_only_target_range(repo, device):
    site_id, dev_id, branch_id = device
    t0 = datetime(2020, 5, 8, 0, 0)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    rows = [
        {
            "site_id": site_id, "device_id": dev_id, "branch_id": branch_id,
            "time": t0 + timedelta(hours=h),
            "label_id": 1, "source": "day_label", "priority": 10,
            "op_id": op_id, "label_space_version": "ls-v2",
            "updated_at": datetime.utcnow(),
        }
        for h in (0, 6, 12, 18)
    ]
    repo.upsert_points(rows)

    deleted = repo.delete_points_in_range(site_id, dev_id, branch_id, t0 + timedelta(hours=6), t0 + timedelta(hours=18))
    assert deleted == 2  # 06:00, 12:00 两点在 [6,18) 内

    remaining = repo.query_points(site_id, dev_id, branch_id)
    remaining_hours = sorted((r["time"] - t0).total_seconds() / 3600 for r in remaining)
    assert remaining_hours == [0.0, 18.0]


def test_query_ops_by_migration_batch(repo, device):
    site_id, dev_id, branch_id = device
    day0 = datetime(2020, 5, 8, 0, 0)
    batch_id = f"mig-{uuid.uuid4().hex[:12]}"
    op_in_batch = f"op-{uuid.uuid4().hex[:12]}"
    op_manual = f"op-{uuid.uuid4().hex[:12]}"
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_in_batch, day0, day0 + timedelta(days=1), 1, migration_batch_id=batch_id))
    repo.insert_op(_mk_op(site_id, dev_id, branch_id, op_manual, day0, day0 + timedelta(days=1), 1))  # migration_batch_id=None

    batch_ops = repo.query_ops_by_migration_batch(batch_id)
    batch_ids = {r["op_id"] for r in batch_ops}
    assert op_in_batch in batch_ids
    assert op_manual not in batch_ids
