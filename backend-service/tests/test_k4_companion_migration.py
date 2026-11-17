# -*- coding: utf-8 -*-
# @AI_GENERATED
"""K4 伴生来源拆分：human_day companion → point_rest_normal。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services.iterative_labeling.k4_companion_migration import (
    apply_k4_companion_source_rewrite,
    classify_human_day_op,
    plan_k4_companion_source_rewrite,
)
from services.iterative_labeling.point_label_service import (
    DAY_PATH_LABEL_SOURCES,
    K4_COMPANION_SOURCE,
    POINT_PATH_LABEL_SOURCES,
)
from services.iterative_labeling.seq_annotation.dataset_builder import EXPLICIT_POINT_SOURCES


DAY0 = datetime(2020, 5, 8)


def test_point_path_sources_include_k4_companion_and_exclude_true_day() -> None:
    assert K4_COMPANION_SOURCE in POINT_PATH_LABEL_SOURCES
    assert K4_COMPANION_SOURCE in EXPLICIT_POINT_SOURCES
    assert "human_day" in DAY_PATH_LABEL_SOURCES
    assert "human_day" not in POINT_PATH_LABEL_SOURCES
    assert "human_day" not in EXPLICIT_POINT_SOURCES
    assert "cluster_rest_normal" not in POINT_PATH_LABEL_SOURCES


def test_classify_k4_companion_and_true_day() -> None:
    companion = {
        "source": "human_day",
        "parent_op_id": "op-parent",
        "rest_of_day_policy": "normal",
        "label_id": 0,
        "t_start": DAY0,
        "t_end": DAY0 + timedelta(days=1),
    }
    true_day = {
        "source": "human_day",
        "parent_op_id": None,
        "rest_of_day_policy": None,
        "label_id": 1,
        "t_start": DAY0,
        "t_end": DAY0 + timedelta(days=1),
    }
    ambiguous = {
        "source": "human_day",
        "parent_op_id": "op-parent",
        "rest_of_day_policy": "untouched",
        "label_id": 0,
        "t_start": DAY0,
        "t_end": DAY0 + timedelta(days=1),
    }
    assert classify_human_day_op(companion) == K4_COMPANION_SOURCE
    assert classify_human_day_op(true_day) == "human_day"
    assert classify_human_day_op(ambiguous) == "ambiguous"


def test_apply_rewrite_updates_ops_and_points_and_rejects_ambiguous() -> None:
    ops = [
        {
            "op_id": "op-k4",
            "source": "human_day",
            "parent_op_id": "op-range",
            "rest_of_day_policy": "normal",
            "label_id": 0,
            "t_start": DAY0,
            "t_end": DAY0 + timedelta(days=1),
        },
        {
            "op_id": "op-day",
            "source": "human_day",
            "parent_op_id": None,
            "rest_of_day_policy": None,
            "label_id": 1,
            "t_start": DAY0,
            "t_end": DAY0 + timedelta(days=1),
        },
    ]
    points = [
        {"op_id": "op-k4", "source": "human_day", "label_id": 0},
        {"op_id": "op-day", "source": "human_day", "label_id": 1},
    ]
    counts = apply_k4_companion_source_rewrite(ops, points)
    assert counts == {"ops_rewritten": 1, "points_rewritten": 1}
    assert ops[0]["source"] == K4_COMPANION_SOURCE
    assert ops[1]["source"] == "human_day"
    assert points[0]["source"] == K4_COMPANION_SOURCE
    assert points[1]["source"] == "human_day"

    ops.append(
        {
            "op_id": "op-bad",
            "source": "human_day",
            "parent_op_id": "op-range",
            "rest_of_day_policy": "untouched",
            "label_id": 0,
            "t_start": DAY0,
            "t_end": DAY0 + timedelta(hours=6),
        }
    )
    with pytest.raises(ValueError, match="无法判定"):
        apply_k4_companion_source_rewrite(ops, points)


def test_plan_separates_migrate_keep_and_ambiguous() -> None:
    plan = plan_k4_companion_source_rewrite(
        [
            {
                "op_id": "a",
                "source": "human_day",
                "parent_op_id": "p",
                "rest_of_day_policy": "normal",
                "label_id": 0,
            },
            {
                "op_id": "b",
                "source": "human_day",
                "parent_op_id": None,
                "t_start": DAY0,
                "t_end": DAY0 + timedelta(days=1),
            },
            {
                "op_id": "c",
                "source": "human_range",
            },
        ]
    )
    assert [item["op_id"] for item in plan["migrate_to_point_rest_normal"]] == ["a"]
    assert [item["op_id"] for item in plan["keep_human_day"]] == ["b"]
    assert plan["ambiguous"] == []
# @AI_GENERATED: end
