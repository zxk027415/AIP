# -*- coding: utf-8 -*-
"""tests/test_sample_builder.py — SampleBuilder 与 sample_id 单测。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from services.iterative_labeling.sample_builder import SampleStrategy, build_samples, compute_group_keys
from services.iterative_labeling.sample_id import is_sample_id, make_sample_id, parse_sample_id


def _rows(label_sequence, start=None):
    start = start or datetime(2020, 5, 8, 0, 0)
    records = []
    for i, (label_id, source, op_id) in enumerate(label_sequence):
        records.append({
            "time": start + timedelta(minutes=5 * i),
            "label_id": label_id,
            "source": source,
            "op_id": op_id,
            "site_id": "S1",
            "device_id": "D1",
            "branch_id": "1",
        })
    return pd.DataFrame(records)


def test_make_sample_id_roundtrip():
    sid = make_sample_id("S1", "D1", "1", datetime(2020, 5, 8, 6, 0), "whole", 0)
    assert "#" in sid
    assert sid.startswith("smp-")
    parsed = parse_sample_id(sid)
    assert parsed["period_role"] == "whole"
    assert parsed["seq"] == 0
    assert is_sample_id(sid)


def test_inf_prefix():
    sid = make_sample_id("S1", "D1", "1", datetime(2020, 5, 8, 6, 0), "night", 1, namespace="inf")
    assert sid.startswith("inf-")
    assert parse_sample_id(sid)["namespace"] == "inf"


def test_by_day_splits_on_label_and_day():
    rows = _rows([(1, "day_label", "op1")] * 100 + [(11, "human_range", "op2")] * 50)
    strategy = SampleStrategy(split_mode="by_day", min_points=12)
    samples, discards = build_samples(rows, strategy)
    assert len(samples) == 2
    assert {s.label_id for s in samples} == {1, 11}
    assert not discards


def test_unknown_segments_discarded():
    rows = _rows([(None, "unknown", "op0")] * 20 + [(1, "day_label", "op1")] * 20)
    samples, discards = build_samples(rows, SampleStrategy(min_points=12))
    assert len(samples) == 1
    assert any(d["reason"] == "unknown_label" for d in discards)


def test_min_points_filter():
    rows = _rows([(1, "day_label", "op1")] * 5)
    samples, discards = build_samples(rows, SampleStrategy(min_points=12))
    assert samples == []
    assert discards[0]["reason"] == "min_points"


def test_label_purity_single_source():
    rows = _rows([(1, "day_label", "op-a")] * 30)
    samples, _ = build_samples(rows, SampleStrategy(min_points=12))
    assert samples[0].label_source == "day_label"
    assert samples[0].label_source_purity == 1.0
    assert samples[0].label_op_id == "op-a"


def test_group_key_shared_days():
    rows = _rows([(1, "day_label", "op1")] * 288)
    strategy = SampleStrategy(min_points=12)
    samples, _ = build_samples(rows, strategy)
    gkeys = compute_group_keys(samples, rows, "S1", "D1", "1")
    assert len(set(gkeys.values())) == 1
