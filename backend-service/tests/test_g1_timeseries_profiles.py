"""G1: timeseries profile preflight and path guard tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.timeseries_profiles import router as timeseries_profiles_router
from services.timeseries_profiles.models import DatasetProfile
from services.timeseries_profiles.path_guard import PathGuardError, resolve_profile_source_path
from services.timeseries_profiles.preflight import run_dataset_profile_preflight
from services.timeseries_profiles.store import TimeseriesProfileStore


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(timeseries_profiles_router)
    return TestClient(app)


def test_path_guard_rejects_absolute_path():
    with pytest.raises(PathGuardError) as exc:
        resolve_profile_source_path("C:/tmp/data.parquet")
    assert exc.value.code == "absolute_path_forbidden"


def test_path_guard_rejects_parent_traversal():
    with pytest.raises(PathGuardError) as exc:
        resolve_profile_source_path("../secrets/data.parquet")
    assert exc.value.code == "path_traversal_forbidden"


def test_pv_snapshot_profile_preflight_ready():
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile("pv-point-snapshot-684bf7f6")
    report = run_dataset_profile_preflight(profile, use_purpose="local_validation")
    assert report.ready is True
    assert report.row_count == 92388
    assert report.duplicate_point_count == 0
    assert report.source_digest


def test_preflight_missing_column_fails():
    profile = DatasetProfile(
        profile_id="bad-profile",
        profile_version="v1",
        slot="pv_point",
        source_ref="data/realtime_point_poc/snapshots/point-poc-20260821044728-684bf7f6/measurements.parquet",
        entity_keys=["site_id"],
        feature_columns=["missing_feature_column"],
        time_column="time",
    )
    report = run_dataset_profile_preflight(profile)
    assert report.ready is False
    assert "missing_feature_column" in report.missing_required_columns


def test_api_preflight_pv_snapshot(api_client):
    response = api_client.post(
        "/api/timeseries/profiles/dataset/pv-point-snapshot-684bf7f6/preflight",
        json={"use_purpose": "local_validation"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["report"]["ready"] is True


def test_api_list_and_manifest(api_client):
    datasets = api_client.get("/api/timeseries/profiles/dataset")
    assert datasets.status_code == 200
    assert any(
        item["profile_id"] == "pv-point-snapshot-684bf7f6"
        for item in datasets.json()["items"]
    )

    manifest = api_client.get("/api/timeseries/profiles/manifests/pv-point-acquisition-684bf7f6")
    assert manifest.status_code == 200
    assert manifest.json()["manifest"]["entries"]
