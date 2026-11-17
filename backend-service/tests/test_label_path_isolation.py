# -*- coding: utf-8 -*-
# @AI_GENERATED
"""天/点标签隔离分类、来源规范化与迁移作用域对账测试。"""
from __future__ import annotations

from datetime import datetime, timedelta

from services.iterative_labeling.label_path_isolation import (
    classify_op_path,
    compare_path_ledgers,
    materialize_day_labels,
    plan_legacy_ops_by_path,
)
from services.iterative_labeling.point_label_service import K4_COMPANION_SOURCE

DAY0 = datetime(2021, 8, 29)


def _op(**kwargs):
    payload = {
        "op_id": "op-1",
        "site_id": "S1",
        "device_id": "D1",
        "branch_id": "1",
        "t_start": DAY0,
        "t_end": DAY0 + timedelta(days=1),
        "label_id": 1,
        "source": "human_day",
        "priority": 80,
        "status": "active",
        "reviewer": "tester",
        "created_at": DAY0,
        "label_space_version": "ls-v2",
    }
    payload.update(kwargs)
    return payload


def test_classify_splits_point_day_and_unknown_sources():
    for source in ("human_range", K4_COMPANION_SOURCE, "peer_residual", "pseudo_point", "cluster", "cluster_point", "pseudo"):
        assert classify_op_path(source) == "point"
    for source in ("human_day", "day_label", "day_import", "parquet_day_label"):
        assert classify_op_path(source) == "day"
    assert classify_op_path("") == "ambiguous"
    assert classify_op_path("mystery") == "ambiguous"


def test_plan_normalizes_aliases_and_historical_k4_companion():
    plan = plan_legacy_ops_by_path(
        [
            _op(
                op_id="op-range",
                source="human_range",
                t_start=DAY0 + timedelta(hours=6),
                t_end=DAY0 + timedelta(hours=8),
                label_id=11,
                priority=100,
            ),
            _op(
                op_id="op-k4",
                source="human_day",
                label_id=0,
                parent_op_id="op-range",
                rest_of_day_policy="normal",
            ),
            _op(op_id="op-cluster", source="cluster", priority=50),
            _op(op_id="op-pseudo", source="pseudo", priority=0),
            _op(op_id="op-day", source="human_day", label_id=1),
            _op(op_id="op-parquet", source="parquet_day_label", priority=10),
        ]
    )

    point_sources = {op["op_id"]: op["source"] for op in plan["point_ops"]}
    day_sources = {op["op_id"]: op["source"] for op in plan["day_ops"]}
    assert point_sources == {
        "op-range": "human_range",
        "op-k4": "point_rest_normal",
        "op-cluster": "cluster_point",
        "op-pseudo": "pseudo_point",
    }
    assert day_sources == {
        "op-day": "human_day",
        "op-parquet": "day_import",
    }
    assert all(op["business_date"] == DAY0.date() for op in plan["day_ops"])
    assert plan["ambiguous"] == []


def test_plan_reports_missing_source_parent_conflicts_and_bad_boundaries():
    plan = plan_legacy_ops_by_path(
        [
            _op(op_id="op-missing", source=""),
            _op(op_id="op-day-parent", source="day_label", parent_op_id="op-parent"),
            _op(op_id="op-rest-no-parent", source="point_rest_normal", label_id=0),
            _op(
                op_id="op-human-parent-conflict",
                source="human_day",
                parent_op_id="op-parent",
                rest_of_day_policy="normal",
                label_id=1,
            ),
            _op(
                op_id="op-incomplete-day",
                source="human_day",
                t_end=DAY0 + timedelta(hours=6),
            ),
        ]
    )

    reasons = {row["op_id"]: row["reason"] for row in plan["ambiguous"]}
    assert reasons == {
        "op-missing": "missing_source",
        "op-day-parent": "day_source_has_parent_op",
        "op-rest-no-parent": "point_rest_normal_missing_parent",
        "op-human-parent-conflict": "human_day_parent_or_boundary_conflict",
        "op-incomplete-day": "human_day_parent_or_boundary_conflict",
    }
    assert plan["point_ops"] == []
    assert plan["day_ops"] == []


def test_plan_rejects_incomplete_non_human_day_op():
    plan = plan_legacy_ops_by_path(
        [
            _op(
                op_id="op-bad-import",
                source="day_import",
                t_end=DAY0 + timedelta(hours=6),
                priority=10,
            )
        ]
    )
    assert plan["ambiguous"] == [
        {
            "op_id": "op-bad-import",
            "source": "day_import",
            "reason": "day_op_not_full_natural_day",
        }
    ]


def test_day_labels_pick_higher_priority_active_winner():
    rows = materialize_day_labels(
        [
            _op(op_id="op-low", source="day_label", priority=10, label_id=1, business_date=DAY0.date()),
            _op(op_id="op-high", source="human_day", priority=80, label_id=11, business_date=DAY0.date()),
            _op(
                op_id="op-revoked",
                source="human_day",
                priority=100,
                label_id=0,
                status="revoked",
                business_date=DAY0.date(),
            ),
        ]
    )
    assert len(rows) == 1
    assert rows[0]["op_id"] == "op-high"
    assert rows[0]["label_id"] == 11


def test_compare_path_ledgers_detects_missing_and_changed_point_ops():
    legacy = [
        _op(
            op_id="op-range",
            source="human_range",
            t_start=DAY0 + timedelta(hours=1),
            t_end=DAY0 + timedelta(hours=6),
            priority=100,
        ),
        _op(op_id="op-cluster", source="cluster", priority=50),
        _op(op_id="op-day", source="human_day"),
    ]
    plan = plan_legacy_ops_by_path(legacy)
    actual_point = [dict(plan["point_ops"][1], source="cluster")]
    compare = compare_path_ledgers(
        legacy_ops=legacy,
        point_ops=actual_point,
        day_ops=plan["day_ops"],
        day_labels=materialize_day_labels(plan["day_ops"]),
    )

    assert compare["passed"] is False
    assert compare["mismatches"]["point_ops_missing"] == ["op-range"]
    assert compare["mismatches"]["point_ops_changed"][0]["op_id"] == "op-cluster"


def test_compare_ignores_legal_unscoped_records_created_after_cutover():
    legacy = [
        _op(
            op_id="op-range",
            source="human_range",
            t_start=DAY0 + timedelta(hours=1),
            t_end=DAY0 + timedelta(hours=6),
            priority=100,
        ),
        _op(op_id="op-day", source="human_day"),
    ]
    plan = plan_legacy_ops_by_path(legacy)
    new_point = _op(
        op_id="op-new-point",
        source="pseudo_point",
        t_start=DAY0 + timedelta(hours=8),
        t_end=DAY0 + timedelta(hours=9),
        priority=0,
    )
    new_day = _op(
        op_id="op-new-day",
        source="day_import",
        priority=10,
        business_date=(DAY0 + timedelta(days=1)).date(),
        t_start=DAY0 + timedelta(days=1),
        t_end=DAY0 + timedelta(days=2),
    )
    day_ops = [*plan["day_ops"], new_day]

    compare = compare_path_ledgers(
        legacy_ops=legacy,
        point_ops=[*plan["point_ops"], new_point],
        day_ops=day_ops,
        day_labels=materialize_day_labels(day_ops),
    )

    assert compare["passed"] is True
    assert compare["unscoped_point_ops"] == 1
    assert compare["unscoped_day_ops"] == 1
# @AI_GENERATED: end
