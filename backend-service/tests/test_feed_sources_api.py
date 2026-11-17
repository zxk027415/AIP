# -*- coding: utf-8 -*-
"""喂数数据集端点（GET /feed-sources、POST /feed-sources/select）的集成测试。

直接挂载 ``api.slot_datasets.router`` 到临时 FastAPI 应用，用 TestClient 打真实路由——
不依赖运行中的后端进程（其 ``--reload`` 在本机对 services 子目录不生效，见交付报告）。
选中状态的写盘位置重定向到 tmp_path，不触碰真实 ``data/slot_datasets``。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.slot_datasets import router
from services.slot_datasets import feed_sources as fs

_SOURCE = "datasets/pv_mock_feed_unseen.parquet"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_BACKEND_DIR", tmp_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_feed_sources_endpoint_lists_three_slots_with_their_semantics(client):
    resp = client.get("/api/slot-datasets/feed-sources?limit=50")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body["current"]) == {"pv_day", "pv_point", "pv_tsc"}
    assert isinstance(body["candidates"], list)

    # 三条路径各自的到达语义必须随接口返回（前端据此显示不同口径）
    assert body["current"]["pv_point"]["semantics"]["granularity"] == "point"
    assert body["current"]["pv_day"]["semantics"]["granularity"] == "device_day"
    assert body["current"]["pv_tsc"]["semantics"]["granularity"] == "device_day"
    assert body["current"]["pv_tsc"]["semantics"]["arrival_gate"]["min_coverage"] == pytest.approx(0.9)

    # 未选择时明确回落，而不是空壳
    assert body["current"]["pv_day"]["selected"] is False
    assert "回落" in body["current"]["pv_day"]["note"]


def test_select_then_read_back_with_fingerprint(client):
    resp = client.post(
        "/api/slot-datasets/feed-sources/select",
        json={"slot": "pv_point", "dataset_ref": _SOURCE, "operator": "test"},
    )
    assert resp.status_code == 200
    assert resp.json()["selection"]["dataset_ref"] == _SOURCE

    body = client.get("/api/slot-datasets/feed-sources?limit=10").json()
    current = body["current"]["pv_point"]
    assert current["selected"] is True
    assert current["source"]["dataset_ref"] == _SOURCE
    assert current["source"]["row_count"] == 22848
    assert current["source"]["fingerprint"], "当前选择必须带指纹，否则前端无法显式展示数据集"
    assert current["source"]["date_min"] == "2021-11-18"
    # 语义跟着一起回来
    assert current["semantics"]["granularity"] == "point"


def test_select_missing_dataset_returns_400_and_writes_nothing(client):
    resp = client.post(
        "/api/slot-datasets/feed-sources/select",
        json={"slot": "pv_day", "dataset_ref": "datasets/__nope__.parquet"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "dataset_not_found"

    body = client.get("/api/slot-datasets/feed-sources?limit=10").json()
    assert body["current"]["pv_day"]["selected"] is False, "校验失败不得留下悬空选中"


def test_select_invalid_slot_returns_400(client):
    resp = client.post(
        "/api/slot-datasets/feed-sources/select",
        json={"slot": "pv_unknown", "dataset_ref": _SOURCE},
    )
    assert resp.status_code == 400


def test_select_absolute_path_rejected(client):
    resp = client.post(
        "/api/slot-datasets/feed-sources/select",
        json={"slot": "pv_day", "dataset_ref": "C:/windows/system32/drivers/etc/hosts"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] != ""


def test_clear_selection_falls_back(client):
    client.post(
        "/api/slot-datasets/feed-sources/select",
        json={"slot": "pv_day", "dataset_ref": _SOURCE, "operator": "test"},
    )
    resp = client.post(
        "/api/slot-datasets/feed-sources/select",
        json={"slot": "pv_day", "dataset_ref": None, "operator": "test"},
    )
    assert resp.status_code == 200
    assert resp.json()["selection"]["dataset_ref"] is None
    assert resp.json()["current"]["selected"] is False
