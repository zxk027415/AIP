"""G6.2 NASA SMAP/MSL profile placeholder tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.timeseries_profiles import router as timeseries_profiles_router
from services.timeseries_profiles.preflight import run_dataset_profile_preflight
from services.timeseries_profiles.store import TimeseriesProfileStore


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(timeseries_profiles_router)
    return TestClient(app)


def test_nasa_demo_profile_loads():
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile("benchmark-nasa-smap-msl-demo")
    assert profile.slot == "benchmark_nasa_smap_msl"
    assert profile.clock_mode == "index"
    assert profile.time_column is None
    assert profile.index_column == "step_index"
    assert profile.label_semantics == "benchmark_ground_truth"
    assert "benchmark_reuse" in profile.allowed_use_purposes


def test_nasa_demo_preflight_local_validation():
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile("benchmark-nasa-smap-msl-demo")
    report = run_dataset_profile_preflight(profile, use_purpose="local_validation")
    assert report.ready is True
    assert report.row_count == 12
    assert report.time_range_start == "0"
    assert report.time_range_end == "5"
    assert report.entity_count == 2


def test_nasa_demo_preflight_blocks_product_workflow():
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile("benchmark-nasa-smap-msl-demo")
    report = run_dataset_profile_preflight(profile, use_purpose="product_workflow")
    assert report.ready is False
    codes = [issue.code for issue in report.issues]
    assert "benchmark_product_purpose_forbidden" in codes


def test_nasa_manifest_and_api(api_client):
    manifest = api_client.get("/api/timeseries/profiles/manifests/benchmark-nasa-smap-msl-acquisition-v1")
    assert manifest.status_code == 200
    body = manifest.json()
    assert body["manifest"]["slot"] == "benchmark_nasa_smap_msl"

    preflight = api_client.post(
        "/api/timeseries/profiles/dataset/benchmark-nasa-smap-msl-demo/preflight",
        json={"use_purpose": "benchmark_reuse"},
    )
    assert preflight.status_code == 200
    assert preflight.json()["report"]["ready"] is True
