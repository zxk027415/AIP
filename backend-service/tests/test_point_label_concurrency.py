# -*- coding: utf-8 -*-
"""
tests/test_point_label_concurrency.py — 设备维度写入串行化测试（任务 29）

验证「写操作 + 重物化」这段临界区在并发下被串行化，使需求 21.7 的一致性成立：
- 进程内层：`threading.RLock` 挡同进程并发
- 跨进程层：MySQL 顾问锁 `GET_LOCK` 挡多 worker/多进程并发

对应 `docs/specs/pv-fault-label-segment-redesign/tasks.md` 任务 29、需求 21.6、21.7。
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.models.pv_fault import LabelOp, PointLabel, TrainingSample
from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.point_label_service import PointLabelService

DAY0 = datetime(2020, 5, 8, 0, 0)


class _StubRegistry:
    def get_current(self):
        return {
            "label_space_version": "ls-v2",
            "labels": [{"label_id": i, "label_name": f"L{i}"} for i in (0, 1, 11)],
        }


@pytest.fixture(scope="module")
def adapter():
    a = DBAdapter(DBConfig())
    yield a
    a.dispose()


@pytest.fixture()
def device(adapter):
    dev_id = f"TEST-conc-{uuid.uuid4().hex[:8]}"
    site_id, branch_id = "TEST-site", "1"
    # 造 288 个测量点，供物化使用
    with adapter.get_sync_session() as s:
        for i in range(288):
            s.add(TrainingSample(
                time=DAY0 + timedelta(minutes=5 * i), site_id=site_id,
                device_id=dev_id, branch_id=branch_id, value=10.0, i_cal=1.0, label=None,
            ))
    yield site_id, dev_id, branch_id
    with adapter.get_sync_session() as s:
        s.execute(delete(PointLabel).where(PointLabel.site_id == site_id, PointLabel.device_id == dev_id))
        s.execute(delete(LabelOp).where(LabelOp.site_id == site_id, LabelOp.device_id == dev_id))
        s.execute(delete(TrainingSample).where(TrainingSample.site_id == site_id, TrainingSample.device_id == dev_id))


def test_device_advisory_lock_is_exclusive_across_connections(adapter, device):
    """同一设备的顾问锁在两个独立连接间互斥（跨进程串行化的基础能力）。"""
    site_id, dev_id, branch_id = device
    repo_a = PointLabelRepository(adapter)
    repo_b = PointLabelRepository(adapter)

    with repo_a.device_advisory_lock(site_id, dev_id, branch_id) as got_a:
        if not got_a:
            pytest.skip("当前数据库不支持 GET_LOCK，跳过跨连接互斥断言")
        # 第二个连接在 1 秒超时内应拿不到同名锁
        with repo_b.device_advisory_lock(site_id, dev_id, branch_id, timeout_seconds=1) as got_b:
            assert got_b is False, "同一设备的顾问锁未能在两个连接间互斥"

    # 释放后应能重新取到
    with repo_a.device_advisory_lock(site_id, dev_id, branch_id, timeout_seconds=1) as got_again:
        assert got_again is True


def test_different_devices_do_not_block_each_other(adapter, device):
    """不同设备的顾问锁互不阻塞（串行化只在设备维度，不是全局串行）。"""
    site_id, dev_id, branch_id = device
    repo = PointLabelRepository(adapter)
    other_dev = f"{dev_id}-other"

    with repo.device_advisory_lock(site_id, dev_id, branch_id) as got_a:
        if not got_a:
            pytest.skip("当前数据库不支持 GET_LOCK")
        with repo.device_advisory_lock(site_id, other_dev, branch_id, timeout_seconds=1) as got_b:
            assert got_b is True, "不同设备之间不应互相阻塞"


def test_concurrent_submits_keep_point_labels_consistent(adapter, device):
    """并发提交同设备操作后，逐点标签仍自洽：每个采样点只有一条记录、
    且标签等于按优先级裁决的赢家（需求 21.7）。"""
    site_id, dev_id, branch_id = device
    label_repo = PointLabelRepository(adapter)
    pv_repo = PVFaultRepository(adapter)
    svc = PointLabelService(label_repo, pv_repo, _StubRegistry())

    errors = []

    def _submit(hour_offset: int, label_id: int, source: str):
        try:
            kwargs = dict(
                site_id=site_id, device_id=dev_id, branch_id=branch_id,
                t_start=DAY0 + timedelta(hours=hour_offset),
                t_end=DAY0 + timedelta(hours=hour_offset + 2),
                label_id=label_id, source=source,
            )
            if source.startswith("human_"):
                kwargs.update(reviewer="tester", source_ref=f"rev-{hour_offset}")
                kwargs.update(rest_of_day_policy="untouched")  # 避免伴生操作互相重叠
            svc.submit_op(**kwargs)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    # 4 个线程并发写同一设备的不同时段
    threads = [
        threading.Thread(target=_submit, args=(0, 1, "day_label")),
        threading.Thread(target=_submit, args=(4, 11, "day_label")),
        threading.Thread(target=_submit, args=(8, 1, "cluster")),
        threading.Thread(target=_submit, args=(12, 11, "cluster")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert not errors, f"并发提交出现异常: {errors}"

    # 一致性断言：同一采样点不得有多条记录（主键保证），且每个点标签与最高优先级 op 一致
    points = label_repo.query_points(site_id, dev_id, branch_id, DAY0, DAY0 + timedelta(days=1))
    times = [p["time"] for p in points]
    assert len(times) == len(set(times)), "同一采样点出现多条逐点标签记录"

    # cluster(50) 覆盖的 08:00-10:00 与 12:00-14:00 应压过 day_label(10)（若范围重叠）
    for p in points:
        assert p["label_id"] in (0, 1, 11)
        assert p["priority"] in (10, 50, 80, 100)

    # verify 应零差异：并发写完后物化结果与重算结果一致
    from services.iterative_labeling.label_materializer import LabelMaterializer
    diffs = LabelMaterializer(label_repo, pv_repo).verify(
        site_id, dev_id, branch_id, DAY0, DAY0 + timedelta(days=1)
    )
    assert diffs == [], f"并发写入后物化结果不自洽: {diffs[:5]}"
