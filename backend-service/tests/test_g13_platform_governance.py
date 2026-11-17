"""G13.2 platform governance tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.iterative_labeling.pv_model_registry import ModelRegistration, PVModelRegistry
from services.scheduler.pv_dual_path.cross_path_switch_coordinator import (
    CrossPathSwitchCoordinator,
    PathSwitchRequest,
)


def _seed(registry: PVModelRegistry) -> None:
    registry.register_challenger(
        "legacy_day",
        ModelRegistration("data/models/legacy.pkl", "el", 0.8, "2026-01-01T00:00:00"),
    )
    registry.promote_within_path("legacy_day", "el")
    registry.register_challenger(
        "seq_annotation",
        ModelRegistration("data/models/seq.pkl", "es", 0.7, "2026-01-01T00:00:00"),
    )
    registry.promote_within_path("seq_annotation", "es")


class _FakeActivation:
    created = 0

    def create_epoch(self, *_args, **_kwargs):
        type(self).created += 1
        return {"activation_epoch_id": "epoch-1"}


def test_simple_switch_blocked_in_production_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "production")
    monkeypatch.delenv("AIP_ALLOW_SIMPLE_PATH_SWITCH", raising=False)
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    _seed(registry)
    coordinator = CrossPathSwitchCoordinator(registry=registry, activation=_FakeActivation())
    result = coordinator.apply(
        PathSwitchRequest(
            modeling_path="seq_annotation",
            switch_mode="simple",
            confirm=True,
        )
    )
    assert result.status == "rejected"
    assert result.reason == "simple_switch_disabled_in_production"
    assert registry.get_slot().production_path == "legacy_day"


def test_modeling_paths_put_requires_auth_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "production")
    monkeypatch.setenv("AIP_REQUIRE_MODELING_PATH_AUTH", "1")

    import api.iterative_labeling as labeling_api

    app = FastAPI()
    app.include_router(labeling_api.router)
    client = TestClient(app)

    response = client.put(
        "/api/iterative-labeling/cumulative-training/modeling-paths",
        json={"modeling_path": "legacy_day", "note": "noop"},
    )
    assert response.status_code == 401


def test_get_modeling_paths_includes_governance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "development")
    monkeypatch.delenv("AIP_REQUIRE_MODELING_PATH_AUTH", raising=False)

    import api.iterative_labeling as labeling_api

    app = FastAPI()
    app.include_router(labeling_api.router)
    client = TestClient(app)

    response = client.get("/api/iterative-labeling/cumulative-training/modeling-paths?slot=pv_day")
    assert response.status_code == 200
    body = response.json()
    assert "governance" in body
    assert body["governance"]["simple_switch_allowed"] is True
    assert body["governance"]["write_auth_required"] is False
