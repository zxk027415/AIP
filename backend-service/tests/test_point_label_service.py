# -*- coding: utf-8 -*-
"""
tests/test_point_label_service.py — PointLabelService 单元测试（含 K4 双操作机制）

用轻量 Stub 跑纯逻辑，不连库。覆盖 7 类不变量校验、K4 伴生操作、撤销联动、改判。

对应 `.kiro/specs/pv-fault-label-segment-redesign/tasks.md` 任务 8、9、10。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest

from services.iterative_labeling.point_label_service import (
    NORMAL_LABEL_ID,
    PointLabelService,
    PointLabelValidationError,
)


class StubLabelRepo:
    def __init__(self):
        self.ops: Dict[str, Dict[str, Any]] = {}
        self.points: Dict[tuple, Dict[str, Any]] = {}

    def insert_op(self, op_data):
        self.ops[op_data["op_id"]] = dict(op_data)
        return dict(op_data)

    def query_op_by_id(self, op_id):
        op = self.ops.get(op_id)
        return dict(op) if op else None

    def revoke_op(self, op_id):
        if op_id not in self.ops:
            return False
        self.ops[op_id]["status"] = "revoked"
        return True

    def query_ops_by_parent(self, parent_op_id):
        return [dict(o) for o in self.ops.values() if o.get("parent_op_id") == parent_op_id]

    def query_active_human_range_overlap(self, site_id, device_id, branch_id, t_start, t_end):
        return [
            dict(o) for o in self.ops.values()
            if o["site_id"] == site_id and o["device_id"] == device_id
            and o["branch_id"] == branch_id and o["status"] == "active"
            and o["source"] == "human_range"
            and o["t_start"] < t_end and o["t_end"] > t_start
        ]

    def query_active_ops(self, site_id, device_id, branch_id, t_start, t_end):
        return [
            dict(o) for o in self.ops.values()
            if o["site_id"] == site_id and o["device_id"] == device_id
            and o["branch_id"] == branch_id and o["status"] == "active"
            and o["t_start"] < t_end and o["t_end"] > t_start
        ]

    def upsert_points(self, rows):
        for r in rows:
            self.points[(r["site_id"], r["device_id"], r["branch_id"], r["time"])] = dict(r)
        return len(rows)

    def delete_points_in_range(self, site_id, device_id, branch_id, t_start, t_end):
        keys = [k for k in self.points if k[0] == site_id and k[1] == device_id and k[2] == branch_id and t_start <= k[3] < t_end]
        for k in keys:
            del self.points[k]
        return len(keys)

    def query_points(self, site_id, device_id, branch_id, t_start=None, t_end=None):
        result = [
            dict(r) for k, r in self.points.items()
            if k[0] == site_id and k[1] == device_id and k[2] == branch_id
            and (t_start is None or k[3] >= t_start) and (t_end is None or k[3] < t_end)
        ]
        return sorted(result, key=lambda r: r["time"])


class StubSampleRepo:
    def __init__(self, times: List[datetime]):
        self._times = times

    def query_sample_times(self, site_id, device_id, branch_id, t_start=None, t_end=None):
        return [t for t in self._times if (t_start is None or t >= t_start) and (t_end is None or t < t_end)]


class StubRegistry:
    def __init__(self, label_ids=(0, 1, 11), version="ls-v2"):
        self._ids, self._version = label_ids, version

    def get_current(self):
        return {
            "label_space_version": self._version,
            "labels": [{"label_id": i, "label_name": f"L{i}"} for i in self._ids],
        }


DAY0 = datetime(2020, 5, 8, 0, 0)


def _service(sample_times=None, registry=None):
    labels = StubLabelRepo()
    samples = StubSampleRepo(sample_times if sample_times is not None else
                             [DAY0 + timedelta(minutes=5 * i) for i in range(288)])
    svc = PointLabelService(labels, samples, registry or StubRegistry())
    return svc, labels


# ------------------------------------------------------------------
# 不变量校验（task 8）
# ------------------------------------------------------------------

def test_rejects_explicit_priority():
    svc, _ = _service()
    with pytest.raises(PointLabelValidationError, match="priority"):
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                      label_id=1, source="day_label", priority=999)


def test_rejects_inference_source():
    svc, _ = _service()
    with pytest.raises(PointLabelValidationError, match="inference"):
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                      label_id=1, source="inference")


def test_rejects_unknown_source():
    svc, _ = _service()
    with pytest.raises(PointLabelValidationError, match="未知 source"):
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                      label_id=1, source="made_up")


def test_rejects_reversed_or_equal_boundaries():
    svc, _ = _service()
    with pytest.raises(PointLabelValidationError, match="t_start < t_end"):
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0 + timedelta(hours=1), t_end=DAY0,
                      label_id=1, source="day_label")


def test_rejects_boundary_not_aligned_to_sampling_grid():
    svc, _ = _service()
    with pytest.raises(PointLabelValidationError, match="采样栅格"):
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0 + timedelta(minutes=3),  # 3 分钟不对齐 5 分钟栅格
                      t_end=DAY0 + timedelta(hours=1),
                      label_id=1, source="day_label")


def test_rejects_op_span_over_limit():
    svc, _ = _service()
    with pytest.raises(PointLabelValidationError, match="跨度超过上限"):
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0, t_end=DAY0 + timedelta(days=40),
                      label_id=1, source="day_label")


def test_rejects_human_source_without_reviewer_or_ref():
    svc, _ = _service()
    with pytest.raises(PointLabelValidationError, match="reviewer"):
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                      label_id=1, source="human_day")  # 缺 reviewer/source_ref


def test_rejects_label_id_outside_label_space():
    svc, _ = _service(registry=StubRegistry(label_ids=(0, 1)))
    with pytest.raises(PointLabelValidationError, match="标签空间"):
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                      label_id=99, source="day_label")


def test_allows_null_label_id_as_unknown():
    """label_id=None（unknown）跳过标签空间校验（需求 18.4）。"""
    svc, labels = _service(registry=StubRegistry(label_ids=(0, 1)))
    result = svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                           t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                           label_id=None, source="day_label")
    assert result["op_id"] in labels.ops


def test_priority_is_derived_from_source():
    svc, labels = _service()
    svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                  t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                  label_id=1, source="cluster")
    op = next(iter(labels.ops.values()))
    assert op["priority"] == 50  # cluster → 50


def test_rejects_overlapping_active_human_range_across_sessions():
    """跨会话重叠检查：不同 source_ref（review_id）也要拦住（修复现状漏检）。"""
    svc, _ = _service()
    svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                  t_start=DAY0 + timedelta(hours=6), t_end=DAY0 + timedelta(hours=18),
                  label_id=1, source="human_range", reviewer="u1", source_ref="rev-A")

    with pytest.raises(PointLabelValidationError, match="重叠") as exc:
        svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                      t_start=DAY0 + timedelta(hours=10), t_end=DAY0 + timedelta(hours=12),
                      label_id=11, source="human_range", reviewer="u2", source_ref="rev-B")
    assert "conflicts" in exc.value.detail


# ------------------------------------------------------------------
# K4：未框选即正常（task 9）
# ------------------------------------------------------------------

def test_k4_writes_companion_op_and_materializes_rest_of_day_as_normal():
    """真实案例复现：框选 06:00~18:40 标 label=1，当日其余点应变为 label=0（正常）。"""
    svc, labels = _service()
    result = svc.submit_op(
        site_id="S1", device_id="D1", branch_id="1",
        t_start=DAY0 + timedelta(hours=6),
        t_end=DAY0 + timedelta(hours=18, minutes=45),  # 含 18:40 采样点（半开区间）
        label_id=1, source="human_range", reviewer="tester", source_ref="rev-x",
    )

    assert len(result["companion_op_ids"]) == 1
    companion = labels.ops[result["companion_op_ids"][0]]
    assert companion["source"] == "human_day"
    assert companion["label_id"] == NORMAL_LABEL_ID
    assert companion["priority"] == 80
    assert companion["parent_op_id"] == result["op_id"]
    # 伴生操作范围恰好是该自然日
    assert companion["t_start"] == DAY0
    assert companion["t_end"] == DAY0 + timedelta(days=1)

    points = labels.query_points("S1", "D1", "1")
    in_frame = [p for p in points if DAY0 + timedelta(hours=6) <= p["time"] < DAY0 + timedelta(hours=18, minutes=45)]
    out_frame = [p for p in points if p not in in_frame]

    assert len(in_frame) == 153  # 06:00~18:40 共 153 个 5 分钟采样点
    assert all(p["label_id"] == 1 and p["source"] == "human_range" for p in in_frame)
    assert len(out_frame) == 135  # 288 - 153
    assert all(p["label_id"] == NORMAL_LABEL_ID and p["source"] == "human_day" for p in out_frame)


def test_k4_untouched_policy_writes_no_companion():
    svc, labels = _service()
    result = svc.submit_op(
        site_id="S1", device_id="D1", branch_id="1",
        t_start=DAY0 + timedelta(hours=6), t_end=DAY0 + timedelta(hours=18),
        label_id=1, source="human_range", reviewer="t", source_ref="r",
        rest_of_day_policy="untouched",
    )
    assert result["companion_op_ids"] == []
    points = labels.query_points("S1", "D1", "1")
    # 只有框内点被写入，框外无标签（unknown）
    assert all(DAY0 + timedelta(hours=6) <= p["time"] < DAY0 + timedelta(hours=18) for p in points)


def test_k4_cross_day_selection_writes_one_companion_per_day():
    """跨两个自然日的框选，应为每个自然日各生成一条伴生操作（需求 5.6）。"""
    times = [DAY0 + timedelta(minutes=5 * i) for i in range(288 * 2)]  # 两天
    svc, labels = _service(sample_times=times)
    result = svc.submit_op(
        site_id="S1", device_id="D1", branch_id="1",
        t_start=DAY0 + timedelta(hours=20),
        t_end=DAY0 + timedelta(days=1, hours=4),  # 跨越午夜
        label_id=1, source="human_range", reviewer="t", source_ref="r",
    )
    assert len(result["companion_op_ids"]) == 2
    companion_days = sorted(labels.ops[cid]["t_start"] for cid in result["companion_op_ids"])
    assert companion_days == [DAY0, DAY0 + timedelta(days=1)]


def test_k4_human_range_beats_existing_day_label():
    """K4 伴生操作(80) 应压过历史批量导入的 day_label(10)。"""
    svc, labels = _service()
    # 先写一条整天 day_label=1（模拟历史批量导入）
    svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                  t_start=DAY0, t_end=DAY0 + timedelta(days=1),
                  label_id=1, source="day_label")
    # 再框选 06:00~18:45 标 label=11
    svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                  t_start=DAY0 + timedelta(hours=6), t_end=DAY0 + timedelta(hours=18, minutes=45),
                  label_id=11, source="human_range", reviewer="t", source_ref="r")

    points = labels.query_points("S1", "D1", "1")
    night = [p for p in points if p["time"] < DAY0 + timedelta(hours=6)]
    day = [p for p in points if DAY0 + timedelta(hours=6) <= p["time"] < DAY0 + timedelta(hours=18, minutes=45)]

    assert all(p["label_id"] == 11 for p in day)  # 框内取 human_range
    assert all(p["label_id"] == NORMAL_LABEL_ID for p in night)  # 框外被 K4 改写为正常，压过 day_label=1


# ------------------------------------------------------------------
# 生命周期与撤销联动（task 10）
# ------------------------------------------------------------------

def test_revoke_cascades_to_companion_and_rematerializes():
    svc, labels = _service()
    result = svc.submit_op(
        site_id="S1", device_id="D1", branch_id="1",
        t_start=DAY0 + timedelta(hours=6), t_end=DAY0 + timedelta(hours=18, minutes=45),
        label_id=1, source="human_range", reviewer="t", source_ref="r",
    )
    main_id, companion_id = result["op_id"], result["companion_op_ids"][0]

    revoke_result = svc.revoke_op(main_id)

    assert set(revoke_result["revoked_op_ids"]) == {main_id, companion_id}
    assert labels.ops[main_id]["status"] == "revoked"
    assert labels.ops[companion_id]["status"] == "revoked"
    # 撤销后该设备该天不应再有任何逐点标签（两条操作都失效）
    assert labels.query_points("S1", "D1", "1") == []


def test_revoke_nonexistent_op_raises():
    svc, _ = _service()
    with pytest.raises(PointLabelValidationError, match="不存在"):
        svc.revoke_op("op-nope")


def test_correct_op_creates_new_and_revokes_old():
    svc, labels = _service()
    first = svc.submit_op(site_id="S1", device_id="D1", branch_id="1",
                          t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                          label_id=1, source="human_day", reviewer="t", source_ref="r")

    corrected = svc.correct_op(old_op_id=first["op_id"], label_id=11, reviewer="t2", source_ref="r2")

    assert labels.ops[first["op_id"]]["status"] == "revoked"
    assert labels.ops[corrected["op_id"]]["status"] == "active"
    assert labels.ops[corrected["op_id"]]["label_id"] == 11
    points = labels.query_points("S1", "D1", "1", DAY0, DAY0 + timedelta(hours=1))
    assert all(p["label_id"] == 11 for p in points)


def test_op_id_is_content_hash_and_idempotent():
    """同源同内容重复提交产生相同 op_id（幂等基础，需求 14.15）。"""
    svc1, _ = _service()
    svc2, _ = _service()
    kwargs = dict(site_id="S1", device_id="D1", branch_id="1",
                  t_start=DAY0, t_end=DAY0 + timedelta(hours=1),
                  label_id=1, source="day_label")
    r1 = svc1.submit_op(**kwargs)
    r2 = svc2.submit_op(**kwargs)
    assert r1["op_id"] == r2["op_id"]
    assert r1["op_id"].startswith("op-")
    assert len(r1["op_id"]) == 3 + 12  # "op-" + hex12
