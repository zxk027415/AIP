# -*- coding: utf-8 -*-
"""
tests/test_label_materializer.py — LabelMaterializer 单元测试

大部分用例用轻量 Stub 仓库跑纯逻辑（不连库，验证物化算法本身）；
最后一组用真实数据库验证 materialize + verify 端到端一致性。

对应 `.kiro/specs/pv-fault-label-segment-redesign/tasks.md` 任务 7。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest

from services.iterative_labeling.label_materializer import LabelMaterializer


class StubPointLabelRepo:
    """轻量 Stub：只实现 LabelMaterializer 用到的接口，内存存储。"""

    def __init__(self, ops: List[Dict[str, Any]]):
        self._ops = ops
        self.points: Dict[tuple, Dict[str, Any]] = {}
        self.upsert_calls: List[List[Dict[str, Any]]] = []
        self.delete_calls: List[tuple] = []

    def query_active_ops(self, site_id, device_id, branch_id, t_start, t_end):
        return [
            op for op in self._ops
            if op["site_id"] == site_id and op["device_id"] == device_id
            and op["branch_id"] == branch_id and op["status"] == "active"
            and op["t_start"] < t_end and op["t_end"] > t_start
        ]

    def upsert_points(self, rows):
        self.upsert_calls.append(rows)
        for r in rows:
            key = (r["site_id"], r["device_id"], r["branch_id"], r["time"])
            self.points[key] = r
        return len(rows)

    def delete_points_in_range(self, site_id, device_id, branch_id, t_start, t_end):
        self.delete_calls.append((site_id, device_id, branch_id, t_start, t_end))
        removed = [k for k in self.points if k[0] == site_id and k[1] == device_id and k[2] == branch_id and t_start <= k[3] < t_end]
        for k in removed:
            del self.points[k]
        return len(removed)

    def query_points(self, site_id, device_id, branch_id, t_start=None, t_end=None):
        result = [
            r for k, r in self.points.items()
            if k[0] == site_id and k[1] == device_id and k[2] == branch_id
            and (t_start is None or k[3] >= t_start) and (t_end is None or k[3] < t_end)
        ]
        return sorted(result, key=lambda r: r["time"])


class StubPvFaultRepo:
    """轻量 Stub：模拟 training_samples 的采样时刻查询。"""

    def __init__(self, sample_times: List[datetime]):
        self._times = sample_times

    def query_sample_times(self, site_id, device_id, branch_id, t_start=None, t_end=None):
        return [
            t for t in self._times
            if (t_start is None or t >= t_start) and (t_end is None or t < t_end)
        ]


def _op(op_id, t_start, t_end, label_id, source="day_label", priority=10, created_at=None, status="active"):
    return {
        "op_id": op_id, "site_id": "S1", "device_id": "D1", "branch_id": "1",
        "t_start": t_start, "t_end": t_end, "label_id": label_id,
        "source": source, "priority": priority, "status": status,
        "created_at": created_at or datetime(2026, 1, 1),
        "label_space_version": "ls-v2",
    }


def _points_5min(day0: datetime, count: int) -> List[datetime]:
    return [day0 + timedelta(minutes=5 * i) for i in range(count)]


def test_higher_priority_wins_on_overlap():
    """K4 场景：human_range(100) 应压过 day_label(10)。"""
    day0 = datetime(2020, 5, 8, 0, 0)
    points = _points_5min(day0, 288)  # 一整天 288 点

    op_day = _op("op-day", day0, day0 + timedelta(days=1), label_id=1, source="day_label", priority=10)
    op_range = _op("op-range", day0 + timedelta(hours=6), day0 + timedelta(hours=18, minutes=45), label_id=1, source="human_range", priority=100)

    labels = StubPointLabelRepo([op_day, op_range])
    samples = StubPvFaultRepo(points)
    m = LabelMaterializer(labels, samples)

    result = m.materialize("S1", "D1", "1", day0, day0 + timedelta(days=1))

    assert result["ops_considered"] == 2
    written = labels.query_points("S1", "D1", "1")
    # 06:00-18:45 范围内的点应来自 op-range
    in_range = [r for r in written if day0 + timedelta(hours=6) <= r["time"] < day0 + timedelta(hours=18, minutes=45)]
    assert all(r["op_id"] == "op-range" for r in in_range)
    assert len(in_range) > 0


def test_same_priority_tiebreak_by_created_at_then_op_id():
    """同 priority 时按 created_at 更新者胜；created_at 也相同则按 op_id 字典序降序。"""
    day0 = datetime(2020, 5, 8, 0, 0)
    points = _points_5min(day0, 12)  # 1 小时

    older = _op("op-a", day0, day0 + timedelta(hours=1), label_id=1, priority=50, created_at=datetime(2026, 1, 1))
    newer = _op("op-b", day0, day0 + timedelta(hours=1), label_id=2, priority=50, created_at=datetime(2026, 1, 2))

    labels = StubPointLabelRepo([older, newer])
    samples = StubPvFaultRepo(points)
    m = LabelMaterializer(labels, samples)
    m.materialize("S1", "D1", "1", day0, day0 + timedelta(hours=1))

    written = labels.query_points("S1", "D1", "1")
    assert all(r["label_id"] == 2 for r in written)  # newer 胜
    assert all(r["op_id"] == "op-b" for r in written)


def test_result_is_order_independent():
    """顺序无关性：打乱输入操作顺序，物化结果应完全一致（需求 4.4）。"""
    day0 = datetime(2020, 5, 8, 0, 0)
    points = _points_5min(day0, 288)

    ops_a = [
        _op("op-1", day0, day0 + timedelta(days=1), 1, priority=10, created_at=datetime(2026, 1, 1)),
        _op("op-2", day0 + timedelta(hours=6), day0 + timedelta(hours=18), 2, priority=80, created_at=datetime(2026, 1, 2)),
        _op("op-3", day0 + timedelta(hours=8), day0 + timedelta(hours=10), 3, priority=100, created_at=datetime(2026, 1, 3)),
    ]
    ops_b = list(reversed(ops_a))

    labels_a = StubPointLabelRepo(ops_a)
    m_a = LabelMaterializer(labels_a, StubPvFaultRepo(points))
    m_a.materialize("S1", "D1", "1", day0, day0 + timedelta(days=1))

    labels_b = StubPointLabelRepo(ops_b)
    m_b = LabelMaterializer(labels_b, StubPvFaultRepo(points))
    m_b.materialize("S1", "D1", "1", day0, day0 + timedelta(days=1))

    result_a = [(r["time"], r["label_id"]) for r in labels_a.query_points("S1", "D1", "1")]
    result_b = [(r["time"], r["label_id"]) for r in labels_b.query_points("S1", "D1", "1")]
    assert result_a == result_b


def test_uncovered_points_are_unknown():
    """未被任何操作覆盖的点不写入 point_labels（或写 NULL），计入 points_unknown。"""
    day0 = datetime(2020, 5, 8, 0, 0)
    points = _points_5min(day0, 288)
    op_partial = _op("op-1", day0, day0 + timedelta(hours=6), label_id=1, priority=10)

    labels = StubPointLabelRepo([op_partial])
    samples = StubPvFaultRepo(points)
    m = LabelMaterializer(labels, samples)
    result = m.materialize("S1", "D1", "1", day0, day0 + timedelta(days=1))

    # op 覆盖 [00:00, 06:00)，即前 72 点（6h × 12 pts/h）；其余 216 点未被覆盖
    assert result["points_unknown"] == 216
    written = labels.query_points("S1", "D1", "1")
    assert len(written) == 72  # 只有前 72 个点被覆盖并写入


def test_no_ops_means_all_unknown_and_no_write():
    day0 = datetime(2020, 5, 8, 0, 0)
    points = _points_5min(day0, 10)
    labels = StubPointLabelRepo([])
    samples = StubPvFaultRepo(points)
    m = LabelMaterializer(labels, samples)
    result = m.materialize("S1", "D1", "1", day0, day0 + timedelta(minutes=50))

    assert result == {"points_written": 0, "points_unknown": 10, "ops_considered": 0}


def test_revoked_ops_are_excluded():
    day0 = datetime(2020, 5, 8, 0, 0)
    points = _points_5min(day0, 12)
    op_revoked = _op("op-1", day0, day0 + timedelta(hours=1), label_id=1, priority=100, status="revoked")
    op_active = _op("op-2", day0, day0 + timedelta(hours=1), label_id=2, priority=10, status="active")

    # StubPointLabelRepo.query_active_ops 已按 status=="active" 过滤
    labels = StubPointLabelRepo([op_revoked, op_active])
    samples = StubPvFaultRepo(points)
    m = LabelMaterializer(labels, samples)
    m.materialize("S1", "D1", "1", day0, day0 + timedelta(hours=1))

    written = labels.query_points("S1", "D1", "1")
    assert all(r["label_id"] == 2 for r in written)  # revoked 的高优先级被排除


def test_materialize_only_recomputes_given_range():
    """重物化只影响指定范围，范围外的旧数据不受影响（需求 4.7）。"""
    day0 = datetime(2020, 5, 8, 0, 0)
    all_points = _points_5min(day0, 288)
    op1 = _op("op-1", day0, day0 + timedelta(days=1), label_id=1, priority=10)

    labels = StubPointLabelRepo([op1])
    samples = StubPvFaultRepo(all_points)
    m = LabelMaterializer(labels, samples)
    m.materialize("S1", "D1", "1", day0, day0 + timedelta(days=1))
    assert len(labels.query_points("S1", "D1", "1")) == 288

    # 只重物化前 1 小时范围，改成 label=2；其余 276 点应保持不变
    op2 = _op("op-2", day0, day0 + timedelta(hours=1), label_id=2, priority=100)
    labels._ops.append(op2)
    m.materialize("S1", "D1", "1", day0, day0 + timedelta(hours=1))

    written = labels.query_points("S1", "D1", "1")
    assert len(written) == 288  # 总点数不变
    first_hour = [r for r in written if r["time"] < day0 + timedelta(hours=1)]
    rest = [r for r in written if r["time"] >= day0 + timedelta(hours=1)]
    assert all(r["label_id"] == 2 for r in first_hour)
    assert all(r["label_id"] == 1 for r in rest)  # 范围外不受影响


# ------------------------------------------------------------------
# 端到端：用真实数据库验证 materialize + verify 一致
# ------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_adapter():
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    a = DBAdapter(DBConfig())
    yield a
    a.dispose()


@pytest.fixture()
def real_device(real_adapter):
    from sqlalchemy import delete
    from services.db.models.pv_fault import LabelOp, PointLabel, TrainingSample

    dev_id = f"TEST-lm-{uuid.uuid4().hex[:8]}"
    site_id, branch_id = "TEST-site", "1"
    yield site_id, dev_id, branch_id
    with real_adapter.get_sync_session() as session:
        session.execute(delete(PointLabel).where(PointLabel.site_id == site_id, PointLabel.device_id == dev_id))
        session.execute(delete(LabelOp).where(LabelOp.site_id == site_id, LabelOp.device_id == dev_id))
        session.execute(delete(TrainingSample).where(TrainingSample.site_id == site_id, TrainingSample.device_id == dev_id))


def test_end_to_end_materialize_and_verify_with_real_db(real_adapter, real_device):
    from services.db.repositories.point_label import PointLabelRepository
    from services.db.repositories.pv_fault import PVFaultRepository
    from services.db.models.pv_fault import TrainingSample

    site_id, dev_id, branch_id = real_device
    day0 = datetime(2020, 5, 8, 0, 0)

    # 写入 6 个真实测量点
    with real_adapter.get_sync_session() as session:
        for i in range(6):
            session.add(TrainingSample(
                time=day0 + timedelta(minutes=5 * i), site_id=site_id,
                device_id=dev_id, branch_id=branch_id, value=10.0, i_cal=1.0, label=None,
            ))

    label_repo = PointLabelRepository(real_adapter)
    pv_repo = PVFaultRepository(real_adapter)
    op_id = f"op-{uuid.uuid4().hex[:12]}"
    label_repo.insert_op({
        "op_id": op_id, "site_id": site_id, "device_id": dev_id, "branch_id": branch_id,
        "t_start": day0, "t_end": day0 + timedelta(minutes=30), "label_id": 1,
        "source": "day_label", "priority": 10, "label_space_version": "ls-v2",
    })

    materializer = LabelMaterializer(label_repo, pv_repo)
    result = materializer.materialize(site_id, dev_id, branch_id, day0, day0 + timedelta(minutes=30))

    assert result == {"points_written": 6, "points_unknown": 0, "ops_considered": 1}

    diffs = materializer.verify(site_id, dev_id, branch_id, day0, day0 + timedelta(minutes=30))
    assert diffs == []  # verify 应与刚物化的结果完全一致，无差异
