# @AI_GENERATED
# -*- coding: utf-8 -*-
"""Property 26、27：回流单一真相、按路径水位，以及天级标注不供序列训练。"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from services.iterative_labeling.backfill_loop import SharedLabelPool
from services.iterative_labeling.seq_annotation.dataset_builder import _load_one_indexed


def _facts(include_point: bool) -> list[dict]:
    rows = [
        {
            "fact_id": "day-1",
            "sequence": 1,
            "site_id": "s",
            "device_id": "d",
            "branch_id": "b",
            "business_date": "2026-01-01",
            "label_id": 2,
            "granularity": "day",
            "source": "human_day",
            "event_time": None,
        }
    ]
    if include_point:
        rows.append(
            {
                "fact_id": "point-1",
                "sequence": 2,
                "site_id": "s",
                "device_id": "d",
                "branch_id": "b",
                "business_date": "2026-01-01",
                "label_id": 3,
                "granularity": "point",
                "source": "human_range",
                "event_time": "2026-01-01T10:00:00",
            }
        )
    return rows


# Feature: pv-fault-dual-path-serving, Property 26: 回流单一真相与按路径水位
@given(include_point=st.booleans(), after=st.integers(min_value=0, max_value=2))
@settings(max_examples=100, deadline=None)
def test_property_26_single_truth_and_path_watermarks(include_point: bool, after: int) -> None:
    writes: list = []
    facts = _facts(include_point)
    pool = SharedLabelPool(lambda: facts, fact_writer=writes.append)
    legacy = pool.list_for_path("legacy_day", after_sequence=after)
    seq = pool.list_for_path("seq_annotation", after_sequence=after)
    assert writes == []
    if after >= 1:
        assert all(item.fact_id != "day-1" or item.sequence > after for item in legacy)
    if include_point and after < 2:
        assert any(item.fact_id == "point-1" for item in seq)
    else:
        assert all(item.fact_id != "point-1" for item in seq)
    if legacy:
        pool.write_once(legacy[0])
        assert writes == [legacy[0].to_dict()]


# Feature: pv-fault-dual-path-serving, Property 27: 天级标注不供序列训练
@given(label=st.integers(min_value=0, max_value=5))
@settings(max_examples=100, deadline=None)
def test_property_27_day_labels_are_not_broadcast_to_seq(label: int) -> None:
    pool = SharedLabelPool(lambda: _facts(include_point=False))
    seq = pool.list_for_path("seq_annotation")
    legacy = pool.list_for_path("legacy_day")
    assert seq == []
    assert [item.granularity for item in legacy] == ["day"]
    day = date(2026, 1, 1)
    key = ("s", "d", "b", day)
    measurements = pd.DataFrame(
        {"time": [pd.Timestamp("2026-01-01T10:00:00")], "value": [1.0], "i_cal": [0.5]}
    )
    day_labels = pd.DataFrame(
        {"time": [pd.Timestamp("2026-01-01T10:00:00")], "label_id": [label], "source": ["human_day"]}
    )
    _, _, reason, ok = _load_one_indexed({key: measurements}, {key: day_labels}, *key, use_labels=True)
    assert ok is False
    assert reason["reason"] == "pure_day_label_not_allowed_for_seq"
# @AI_GENERATED: end
