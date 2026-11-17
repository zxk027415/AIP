# -*- coding: utf-8 -*-
# @AI_GENERATED
"""PointLabelService 单元测试：点路径来源闸门、K4 伴生、撤销与改判。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

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
        existing = self.ops.get(op_data["op_id"])
        if existing is not None:
            return dict(existing)
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
        return [dict(op) for op in self.ops.values() if op.get("parent_op_id") == parent_op_id]

    def query_active_human_range_overlap(self, site_id, device_id, branch_id, t_start, t_end):
        return [
            dict(op)
            for op in self.ops.values()
            if op["site_id"] == site_id
            and op["device_id"] == device_id
            and op["branch_id"] == branch_id
            and op["status"] == "active"
            and op["source"] == "human_range"
            and op["t_start"] < t_end
            and op["t_end"] > t_start
        ]

    def query_active_ops(self, site_id, device_id, branch_id, t_start, t_end):
        return [
            dict(op)
            for op in self.ops.values()
            if op["site_id"] == site_id
            and op["device_id"] == device_id
            and op["branch_id"] == branch_id
            and op["status"] == "active"
            and op["t_start"] < t_end
            and op["t_end"] > t_start
        ]

    def upsert_points(self, rows):
        for row in rows:
            key = (row["site_id"], row["device_id"], row["branch_id"], row["time"])
            self.points[key] = dict(row)
        return len(rows)

    def delete_points_in_range(self, site_id, device_id, branch_id, t_start, t_end):
        keys = [
            key
            for key in self.points
            if key[0] == site_id
            and key[1] == device_id
            and key[2] == branch_id
            and t_start <= key[3] < t_end
        ]
        for key in keys:
            del self.points[key]
        return len(keys)

    def query_points(self, site_id, device_id, branch_id, t_start=None, t_end=None):
        result = [
            dict(row)
            for key, row in self.points.items()
            if key[0] == site_id
            and key[1] == device_id
            and key[2] == branch_id
            and (t_start is None or key[3] >= t_start)
            and (t_end is None or key[3] < t_end)
        ]
        return sorted(result, key=lambda row: row["time"])


class StubSampleRepo:
    def __init__(self, times: List[datetime]):
        self._times = times

    def query_sample_times(self, site_id, device_id, branch_id, t_start=None, t_end=None):
        return [
            timestamp
            for timestamp in self._times
            if (t_start is None or timestamp >= t_start)
            and (t_end is None or timestamp < t_end)
        ]


class StubRegistry:
    def __init__(self, label_ids=(0, 1, 11), version="ls-v2"):
        self._ids = label_ids
        self._version = version

    def get_current(self):
        return {
            "label_space_version": self._version,
            "labels": [{"label_id": label_id, "label_name": f"L{label_id}"} for label_id in self._ids],
        }


DAY0 = datetime(2020, 5, 8, 0, 0)


def _service(sample_times=None, registry=None):
    labels = StubLabelRepo()
    samples = StubSampleRepo(
        sample_times
        if sample_times is not None
        else [DAY0 + timedelta(minutes=5 * index) for index in range(288)]
    )
    service = PointLabelService(labels, samples, registry or StubRegistry())
    return service, labels


def test_rejects_explicit_priority():
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="priority"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(hours=1),
            label_id=1,
            source="human_range",
            reviewer="tester",
            source_ref="rev-1",
            priority=999,
        )


def test_rejects_inference_source():
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="inference"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(hours=1),
            label_id=1,
            source="inference",
        )


@pytest.mark.parametrize("source", ["human_day", "day_label", "day_import", "parquet_day_label"])
def test_rejects_all_day_sources(source):
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="天标签来源"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(hours=1),
            label_id=1,
            source=source,
        )


@pytest.mark.parametrize("source", ["cluster", "cluster_point", "pseudo"])
def test_rejects_legacy_point_sources_for_new_writes(source):
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="历史点来源"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(hours=1),
            label_id=1,
            source=source,
        )


def test_rejects_unknown_source():
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="未知 source"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(hours=1),
            label_id=1,
            source="made_up",
        )


def test_rejects_reversed_or_equal_boundaries():
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="t_start < t_end"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0 + timedelta(hours=1),
            t_end=DAY0,
            label_id=1,
            source="pseudo_point",
            source_ref="pseudo-1",
        )


def test_rejects_boundary_not_aligned_to_sampling_grid():
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="采样栅格"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0 + timedelta(minutes=3),
            t_end=DAY0 + timedelta(hours=1),
            label_id=1,
            source="pseudo_point",
            source_ref="pseudo-1",
        )


def test_rejects_op_span_over_limit():
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="跨度超过上限"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(days=40),
            label_id=1,
            source="pseudo_point",
            source_ref="pseudo-1",
        )


def test_rejects_human_range_without_reviewer_or_ref():
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="reviewer"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(hours=1),
            label_id=1,
            source="human_range",
        )


@pytest.mark.parametrize(
    ("source", "reviewer", "source_ref", "missing"),
    [
        ("peer_residual", None, "candidate-1", "reviewer"),
        ("peer_residual", "tester", None, "source_ref"),
        ("pseudo_point", None, None, "source_ref"),
    ],
)
def test_rejects_assisted_source_without_audit_fields(source, reviewer, source_ref, missing):
    service, _ = _service()
    with pytest.raises(PointLabelValidationError) as exc_info:
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(hours=1),
            label_id=1,
            source=source,
            reviewer=reviewer,
            source_ref=source_ref,
        )
    assert missing in exc_info.value.detail["missing"]


def test_rejects_label_id_outside_label_space():
    service, _ = _service(registry=StubRegistry(label_ids=(0, 1)))
    with pytest.raises(PointLabelValidationError, match="标签空间"):
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0,
            t_end=DAY0 + timedelta(hours=1),
            label_id=99,
            source="pseudo_point",
            source_ref="pseudo-1",
        )


def test_allows_null_label_id_as_unknown():
    service, labels = _service(registry=StubRegistry(label_ids=(0, 1)))
    result = service.submit_op(
        site_id="S1",
        device_id="D1",
        branch_id="1",
        t_start=DAY0,
        t_end=DAY0 + timedelta(hours=1),
        label_id=None,
        source="pseudo_point",
        source_ref="pseudo-1",
    )
    assert result["op_id"] in labels.ops
    assert result["path"] == "point"


def test_priority_is_derived_from_canonical_source():
    service, labels = _service()
    service.submit_op(
        site_id="S1",
        device_id="D1",
        branch_id="1",
        t_start=DAY0,
        t_end=DAY0 + timedelta(hours=1),
        label_id=1,
        source="peer_residual",
        reviewer="tester",
        source_ref="candidate-1",
    )
    op = next(iter(labels.ops.values()))
    assert op["priority"] == 50


def test_rejects_overlapping_active_human_range_across_sessions():
    service, _ = _service()
    service.submit_op(
        site_id="S1",
        device_id="D1",
        branch_id="1",
        t_start=DAY0 + timedelta(hours=6),
        t_end=DAY0 + timedelta(hours=18),
        label_id=1,
        source="human_range",
        reviewer="u1",
        source_ref="rev-A",
    )

    with pytest.raises(PointLabelValidationError, match="重叠") as exc_info:
        service.submit_op(
            site_id="S1",
            device_id="D1",
            branch_id="1",
            t_start=DAY0 + timedelta(hours=10),
            t_end=DAY0 + timedelta(hours=12),
            label_id=11,
            source="human_range",
            reviewer="u2",
            source_ref="rev-B",
        )
    assert "conflicts" in exc_info.value.detail


def test_k4_writes_companion_and_materializes_rest_of_day_as_normal():
    service, labels = _service()
    result = service.submit_op(
        site_id="S1",
        device_id="D1",
        branch_id="1",
        t_start=DAY0 + timedelta(hours=6),
        t_end=DAY0 + timedelta(hours=18, minutes=45),
        label_id=1,
        source="human_range",
        reviewer="tester",
        source_ref="rev-x",
    )

    assert len(result["companion_op_ids"]) == 1
    companion = labels.ops[result["companion_op_ids"][0]]
    assert companion["source"] == "point_rest_normal"
    assert companion["label_id"] == NORMAL_LABEL_ID
    assert companion["priority"] == 80
    assert companion["parent_op_id"] == result["op_id"]
    assert companion["t_start"] == DAY0
    assert companion["t_end"] == DAY0 + timedelta(days=1)

    points = labels.query_points("S1", "D1", "1")
    in_frame = [
        point
        for point in points
        if DAY0 + timedelta(hours=6) <= point["time"] < DAY0 + timedelta(hours=18, minutes=45)
    ]
    out_frame = [point for point in points if point not in in_frame]
    assert len(in_frame) == 153
    assert all(point["label_id"] == 1 and point["source"] == "human_range" for point in in_frame)
    assert len(out_frame) == 135
    assert all(
        point["label_id"] == NORMAL_LABEL_ID and point["source"] == "point_rest_normal"
        for point in out_frame
    )


def test_k4_untouched_policy_writes_no_companion():
    service, labels = _service()
    result = service.submit_op(
        site_id="S1",
        device_id="D1",
        branch_id="1",
        t_start=DAY0 + timedelta(hours=6),
        t_end=DAY0 + timedelta(hours=18),
        label_id=1,
        source="human_range",
        reviewer="tester",
        source_ref="rev-x",
        rest_of_day_policy="untouched",
    )
    assert result["companion_op_ids"] == []
    points = labels.query_points("S1", "D1", "1")
    assert all(
        DAY0 + timedelta(hours=6) <= point["time"] < DAY0 + timedelta(hours=18)
        for point in points
    )


def test_k4_cross_day_selection_writes_one_companion_per_day():
    times = [DAY0 + timedelta(minutes=5 * index) for index in range(288 * 2)]
    service, labels = _service(sample_times=times)
    result = service.submit_op(
        site_id="S1",
        device_id="D1",
        branch_id="1",
        t_start=DAY0 + timedelta(hours=20),
        t_end=DAY0 + timedelta(days=1, hours=4),
        label_id=1,
        source="human_range",
        reviewer="tester",
        source_ref="rev-x",
    )
    assert len(result["companion_op_ids"]) == 2
    companion_days = sorted(labels.ops[op_id]["t_start"] for op_id in result["companion_op_ids"])
    assert companion_days == [DAY0, DAY0 + timedelta(days=1)]


def test_revoke_cascades_to_companion_and_rematerializes():
    service, labels = _service()
    result = service.submit_op(
        site_id="S1",
        device_id="D1",
        branch_id="1",
        t_start=DAY0 + timedelta(hours=6),
        t_end=DAY0 + timedelta(hours=18, minutes=45),
        label_id=1,
        source="human_range",
        reviewer="tester",
        source_ref="rev-x",
    )
    main_id = result["op_id"]
    companion_id = result["companion_op_ids"][0]

    revoke_result = service.revoke_op(main_id)

    assert set(revoke_result["revoked_op_ids"]) == {main_id, companion_id}
    assert labels.ops[main_id]["status"] == "revoked"
    assert labels.ops[companion_id]["status"] == "revoked"
    assert labels.query_points("S1", "D1", "1") == []


def test_revoke_nonexistent_op_raises():
    service, _ = _service()
    with pytest.raises(PointLabelValidationError, match="不存在"):
        service.revoke_op("op-nope")


def test_correct_op_creates_new_and_revokes_old_point_operation():
    service, labels = _service()
    first = service.submit_op(
        site_id="S1",
        device_id="D1",
        branch_id="1",
        t_start=DAY0,
        t_end=DAY0 + timedelta(hours=1),
        label_id=1,
        source="human_range",
        reviewer="tester",
        source_ref="rev-1",
    )

    corrected = service.correct_op(
        old_op_id=first["op_id"],
        label_id=11,
        reviewer="tester-2",
        source_ref="rev-2",
    )

    assert labels.ops[first["op_id"]]["status"] == "revoked"
    assert labels.ops[corrected["op_id"]]["status"] == "active"
    assert labels.ops[corrected["op_id"]]["label_id"] == 11
    points = labels.query_points("S1", "D1", "1", DAY0, DAY0 + timedelta(hours=1))
    assert points
    assert all(point["label_id"] == 11 for point in points)


def test_op_id_is_content_hash_and_idempotent():
    service_1, _ = _service()
    service_2, _ = _service()
    kwargs = {
        "site_id": "S1",
        "device_id": "D1",
        "branch_id": "1",
        "t_start": DAY0,
        "t_end": DAY0 + timedelta(hours=1),
        "label_id": 1,
        "source": "pseudo_point",
        "source_ref": "pseudo-1",
    }
    first = service_1.submit_op(**kwargs)
    second = service_2.submit_op(**kwargs)
    assert first["op_id"] == second["op_id"]
    assert first["op_id"].startswith("op-")
    assert len(first["op_id"]) == 15
# @AI_GENERATED: end
