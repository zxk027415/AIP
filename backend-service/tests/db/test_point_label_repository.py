# -*- coding: utf-8 -*-
# @AI_GENERATED
"""PointLabelRepository 真实数据库测试：点账本独占、物化与幂等撤销。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.models.pv_fault import DayLabel, DayLabelOp, LabelOp, PointLabel, PointLabelOp
from services.db.repositories.point_label import PointLabelRepository


@pytest.fixture(scope="module")
def adapter():
    db_adapter = DBAdapter(DBConfig())
    yield db_adapter
    db_adapter.dispose()


@pytest.fixture()
def repo(adapter):
    return PointLabelRepository(adapter)


@pytest.fixture()
def device(adapter):
    """每例使用独立设备三元组，并清理本例写入的天/点及旧账本记录。"""
    device_id = f"TEST-plr-{uuid.uuid4().hex[:8]}"
    site_id, branch_id = "TEST-site", "1"
    yield site_id, device_id, branch_id
    with adapter.get_sync_session() as session:
        session.execute(
            delete(PointLabel).where(
                PointLabel.site_id == site_id,
                PointLabel.device_id == device_id,
            )
        )
        session.execute(
            delete(PointLabelOp).where(
                PointLabelOp.site_id == site_id,
                PointLabelOp.device_id == device_id,
            )
        )
        session.execute(
            delete(DayLabel).where(
                DayLabel.site_id == site_id,
                DayLabel.device_id == device_id,
            )
        )
        session.execute(
            delete(DayLabelOp).where(
                DayLabelOp.site_id == site_id,
                DayLabelOp.device_id == device_id,
            )
        )
        session.execute(
            delete(LabelOp).where(
                LabelOp.site_id == site_id,
                LabelOp.device_id == device_id,
            )
        )


def _mk_op(
    site_id,
    device_id,
    branch_id,
    op_id,
    t_start,
    t_end,
    label_id,
    source="pseudo_point",
    priority=0,
    status="active",
    **extra,
):
    payload = {
        "op_id": op_id,
        "site_id": site_id,
        "device_id": device_id,
        "branch_id": branch_id,
        "t_start": t_start,
        "t_end": t_end,
        "label_id": label_id,
        "source": source,
        "priority": priority,
        "status": status,
        "label_space_version": "ls-v2",
    }
    payload.update(extra)
    return payload


def test_insert_and_query_uses_only_point_label_ops(repo, adapter, device):
    site_id, device_id, branch_id = device
    start = datetime(2020, 5, 8)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    payload = _mk_op(site_id, device_id, branch_id, op_id, start, start + timedelta(hours=1), 1)

    written = repo.insert_op(payload)
    fetched = repo.query_op_by_id(op_id)

    assert written["op_id"] == op_id
    assert written["status"] == "active"
    assert fetched is not None
    assert fetched["source"] == "pseudo_point"
    assert fetched["priority"] == 0
    with adapter.get_sync_session() as session:
        assert session.get(PointLabelOp, op_id) is not None
        assert session.get(LabelOp, op_id) is None


@pytest.mark.parametrize(
    "source",
    ["human_day", "day_label", "day_import", "parquet_day_label", "cluster", "cluster_point", "pseudo"],
)
def test_insert_op_rejects_day_and_legacy_sources(repo, device, source):
    site_id, device_id, branch_id = device
    start = datetime(2020, 5, 8)
    with pytest.raises(ValueError, match="point_label_ops 禁止新写"):
        repo.insert_op(
            _mk_op(
                site_id,
                device_id,
                branch_id,
                f"op-{uuid.uuid4().hex[:12]}",
                start,
                start + timedelta(hours=1),
                1,
                source=source,
            )
        )


def test_revoke_then_idempotent_insert_does_not_reactivate(repo, device):
    site_id, device_id, branch_id = device
    start = datetime(2020, 5, 8)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    payload = _mk_op(site_id, device_id, branch_id, op_id, start, start + timedelta(hours=1), 1)
    repo.insert_op(payload)

    assert repo.revoke_op(op_id) is True
    retried = repo.insert_op(payload)

    assert retried["status"] == "revoked"
    assert repo.query_op_by_id(op_id)["status"] == "revoked"
    assert repo.revoke_op("op-does-not-exist") is False


def test_existing_op_id_with_different_immutable_content_is_rejected(repo, device):
    site_id, device_id, branch_id = device
    start = datetime(2020, 5, 8)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    payload = _mk_op(site_id, device_id, branch_id, op_id, start, start + timedelta(hours=1), 1)
    repo.insert_op(payload)

    with pytest.raises(ValueError, match="字段不一致"):
        repo.insert_op(dict(payload, label_id=11))


def test_query_active_ops_filters_overlap_status_and_orders_priority(repo, device):
    site_id, device_id, branch_id = device
    day_start = datetime(2020, 5, 8)
    low_id = f"op-{uuid.uuid4().hex[:12]}"
    high_id = f"op-{uuid.uuid4().hex[:12]}"
    revoked_id = f"op-{uuid.uuid4().hex[:12]}"
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            low_id,
            day_start,
            day_start + timedelta(days=1),
            0,
            source="point_rest_normal",
            priority=80,
            parent_op_id="op-parent",
        )
    )
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            high_id,
            day_start + timedelta(hours=6),
            day_start + timedelta(hours=18),
            1,
            source="human_range",
            priority=100,
            reviewer="tester",
            source_ref="rev-x",
        )
    )
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            revoked_id,
            day_start,
            day_start + timedelta(hours=1),
            1,
            status="revoked",
        )
    )

    active = repo.query_active_ops(site_id, device_id, branch_id, day_start, day_start + timedelta(days=1))
    active_ids = {row["op_id"] for row in active}
    assert low_id in active_ids
    assert high_id in active_ids
    assert revoked_id not in active_ids
    assert active[0]["op_id"] == high_id


def test_query_active_human_range_overlap_ignores_other_point_sources(repo, device):
    site_id, device_id, branch_id = device
    day_start = datetime(2020, 5, 8)
    range_id = f"op-{uuid.uuid4().hex[:12]}"
    pseudo_id = f"op-{uuid.uuid4().hex[:12]}"
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            range_id,
            day_start + timedelta(hours=6),
            day_start + timedelta(hours=18),
            1,
            source="human_range",
            priority=100,
            reviewer="tester",
            source_ref="rev-x",
        )
    )
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            pseudo_id,
            day_start,
            day_start + timedelta(days=1),
            1,
        )
    )

    overlap = repo.query_active_human_range_overlap(
        site_id,
        device_id,
        branch_id,
        day_start + timedelta(hours=10),
        day_start + timedelta(hours=12),
    )
    assert {row["op_id"] for row in overlap} == {range_id}
    assert repo.query_active_human_range_overlap(
        site_id,
        device_id,
        branch_id,
        day_start + timedelta(hours=20),
        day_start + timedelta(hours=22),
    ) == []


def test_query_ops_by_parent_returns_point_rest_normal(repo, device):
    site_id, device_id, branch_id = device
    day_start = datetime(2020, 5, 8)
    parent_id = f"op-{uuid.uuid4().hex[:12]}"
    companion_id = f"op-{uuid.uuid4().hex[:12]}"
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            parent_id,
            day_start + timedelta(hours=6),
            day_start + timedelta(hours=18),
            1,
            source="human_range",
            priority=100,
            reviewer="tester",
            source_ref="rev-x",
        )
    )
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            companion_id,
            day_start,
            day_start + timedelta(days=1),
            0,
            source="point_rest_normal",
            priority=80,
            reviewer="tester",
            source_ref="rev-x",
            rest_of_day_policy="normal",
            parent_op_id=parent_id,
        )
    )

    companions = repo.query_ops_by_parent(parent_id)
    assert len(companions) == 1
    assert companions[0]["op_id"] == companion_id
    assert companions[0]["source"] == "point_rest_normal"


def test_upsert_points_writes_and_updates_only_point_sources(repo, device):
    site_id, device_id, branch_id = device
    start = datetime(2020, 5, 8, 6)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    rows = [
        {
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "time": start + timedelta(minutes=5 * index),
            "label_id": 1,
            "source": "human_range",
            "priority": 100,
            "op_id": op_id,
            "label_space_version": "ls-v2",
            "updated_at": datetime.utcnow(),
        }
        for index in range(3)
    ]
    assert repo.upsert_points(rows) >= 3
    assert len(repo.query_points(site_id, device_id, branch_id)) == 3

    updated_rows = [
        dict(row, label_id=0, source="point_rest_normal", priority=80)
        for row in rows
    ]
    repo.upsert_points(updated_rows)
    fetched = repo.query_points(site_id, device_id, branch_id)
    assert len(fetched) == 3
    assert all(row["label_id"] == 0 and row["source"] == "point_rest_normal" for row in fetched)


@pytest.mark.parametrize("source", ["human_day", "day_label", "day_import", "parquet_day_label"])
def test_upsert_points_rejects_day_sources(repo, device, source):
    site_id, device_id, branch_id = device
    with pytest.raises(ValueError, match="point_labels 禁止写入非点来源"):
        repo.upsert_points(
            [
                {
                    "site_id": site_id,
                    "device_id": device_id,
                    "branch_id": branch_id,
                    "time": datetime(2020, 5, 8),
                    "label_id": 1,
                    "source": source,
                    "priority": 10,
                    "op_id": f"op-{uuid.uuid4().hex[:12]}",
                    "label_space_version": "ls-v2",
                    "updated_at": datetime.utcnow(),
                }
            ]
        )


def test_query_and_delete_points_respect_half_open_range(repo, device):
    site_id, device_id, branch_id = device
    start = datetime(2020, 5, 8)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    rows = [
        {
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "time": start + timedelta(hours=hour),
            "label_id": 1,
            "source": "pseudo_point",
            "priority": 0,
            "op_id": op_id,
            "label_space_version": "ls-v2",
            "updated_at": datetime.utcnow(),
        }
        for hour in (0, 6, 12, 18)
    ]
    repo.upsert_points(rows)

    subset = repo.query_points(
        site_id,
        device_id,
        branch_id,
        start + timedelta(hours=6),
        start + timedelta(hours=18),
    )
    assert [(row["time"] - start).total_seconds() / 3600 for row in subset] == [6.0, 12.0]
    assert repo.delete_points_in_range(
        site_id,
        device_id,
        branch_id,
        start + timedelta(hours=6),
        start + timedelta(hours=18),
    ) == 2
    remaining = repo.query_points(site_id, device_id, branch_id)
    assert [(row["time"] - start).total_seconds() / 3600 for row in remaining] == [0.0, 18.0]


def test_query_ops_by_migration_batch(repo, device):
    site_id, device_id, branch_id = device
    start = datetime(2020, 5, 8)
    batch_id = f"mig-{uuid.uuid4().hex[:12]}"
    in_batch_id = f"op-{uuid.uuid4().hex[:12]}"
    manual_id = f"op-{uuid.uuid4().hex[:12]}"
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            in_batch_id,
            start,
            start + timedelta(hours=1),
            1,
            migration_batch_id=batch_id,
        )
    )
    repo.insert_op(
        _mk_op(
            site_id,
            device_id,
            branch_id,
            manual_id,
            start,
            start + timedelta(hours=1),
            1,
        )
    )

    assert {row["op_id"] for row in repo.query_ops_by_migration_batch(batch_id)} == {in_batch_id}
# @AI_GENERATED: end
