# -*- coding: utf-8 -*-
"""三条路径并列总览（GET /api/slot-datasets/overview）。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.slot_datasets import router
from services.slot_datasets.feed_semantics import SUPPORTED_SLOTS
from services.slot_datasets.path_overview import SLOT_LABELS, build_overview, build_slot_row


def test_overview_rows_cover_three_slots_with_identical_keys():
    body = build_overview()
    assert body["total"] == 3
    slots = [row["slot"] for row in body["paths"]]
    assert slots == list(SUPPORTED_SLOTS)

    required = {
        "slot",
        "label",
        "granularity",
        "semantics",
        "champion",
        "challenger",
        "current_model",
        "classifier_accuracy",
        "counted_units",
        "accuracy_source",
        "dataset",
        "available_datasets",
        "available_dataset_count",
    }
    for row in body["paths"]:
        assert required <= set(row), row.keys()
        assert row["label"] == SLOT_LABELS[row["slot"]]
        assert isinstance(row["available_datasets"], list)
        assert row["available_dataset_count"] == len(row["available_datasets"])
        acc = row["classifier_accuracy"]
        counted = row["counted_units"]
        if acc is None:
            assert counted is None or int(counted) == 0
        else:
            assert isinstance(acc, (int, float))
            assert int(counted or 0) > 0


def test_point_row_granularity_is_point():
    row = build_slot_row("pv_point")
    assert row["granularity"] == "point"
    assert row["semantics"]["arrival_gate"]["gate"] == "per_point"


def test_overview_endpoint_returns_200():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/slot-datasets/overview")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(row["slot"] for row in body["paths"]) == set(SUPPORTED_SLOTS)
    for row in body["paths"]:
        assert "dataset" in row
        assert "available_datasets" in row
        assert row["classifier_accuracy"] is None or isinstance(row["classifier_accuracy"], (int, float))
