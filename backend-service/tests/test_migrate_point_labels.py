# -*- coding: utf-8 -*-
"""migrate_point_labels 纯函数单测（不连库）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from scripts.migrate_point_labels import (
    _human_day_ops_from_verdicts,
    _human_range_ops_from_slices,
    _make_op_id,
    _day_label_ops,
)


def test_make_op_id_is_stable():
    t0 = datetime(2020, 5, 8, 6, 0, 0)
    t1 = datetime(2020, 5, 8, 18, 45, 0)
    a = _make_op_id("s", "d", "1", t0, t1, 1, "human_range")
    b = _make_op_id("s", "d", "1", t0, t1, 1, "human_range")
    assert a == b
    assert a.startswith("op-")


def test_day_label_ops_one_group():
    df = pd.DataFrame([
        {
            "time": "2020-05-08 06:00:00",
            "site_id": "武当湖",
            "device_id": "04#",
            "branch_id": "1",
            "label": 1,
        },
        {
            "time": "2020-05-08 06:05:00",
            "site_id": "武当湖",
            "device_id": "04#",
            "branch_id": "1",
            "label": 1,
        },
    ])
    ops = _day_label_ops(df, "mig-test")
    assert len(ops) == 1
    assert ops[0]["source"] == "day_label"
    assert ops[0]["label_id"] == 1


def test_human_range_ops_from_meta(tmp_path):
    slice_dir = tmp_path / "time_slices"
    slice_dir.mkdir(parents=True)
    meta = {
        "slice_id": "slice-test",
        "time_start": "2020-05-08 06:00:00",
        "time_end": "2020-05-08 18:40:00",
        "label_id": 1,
        "site_id": "武当湖",
        "device_id": "04#",
        "branch_id": "1",
        "row_count": 153,
        "reviewer": "operator",
    }
    (slice_dir / "slice-test.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    ops, failures = _human_range_ops_from_slices(tmp_path, "mig-test")
    assert not failures
    assert len(ops) == 2  # human_range + K4 companion point_rest_normal
    assert ops[0]["source"] == "human_range"
    assert ops[1]["source"] == "point_rest_normal"
    assert ops[1]["parent_op_id"] == ops[0]["op_id"]


def test_human_day_ops_from_verdict_state(tmp_path):
    state = {
        "verdict_entries": {
            "rev|unit": {
                "review_id": "rev-1",
                "unit_key": "pv|dev|1|2021-08-29T00:00:00",
                "verdict_label": 2,
                "action_type": "confirm",
                "reviewer": "tester",
            }
        }
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    ops, failures = _human_day_ops_from_verdicts(state_path, "mig-test")
    assert not failures
    assert len(ops) == 1
    assert ops[0]["source"] == "human_day"
    assert ops[0]["label_id"] == 2
