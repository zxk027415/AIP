"""G6.2 NASA NPY adapter skeleton tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.operator_execution.router import OperatorRouter
from services.timeseries_profiles.adapters.registry import load_nasa_npy_channels, load_via_adapter
from services.timeseries_profiles.loader import load_dataset_from_profile
from services.timeseries_profiles.preflight import run_dataset_profile_preflight
from services.timeseries_profiles.store import TimeseriesProfileStore


def test_npy_adapter_expands_channels():
    fixture = (
        Path(__file__).resolve().parents[1]
        / "data/timeseries_point/test_fixtures/nasa_smap_msl_demo.npy"
    )
    df = load_nasa_npy_channels(
        fixture,
        {
            "index_column": "step_index",
            "feature_columns": ["value"],
            "label_column": "anomaly_label",
        },
    )
    assert len(df) == 12
    assert set(df["channel_id"]) == {"C-0", "C-1"}
    assert "anomaly_label" in df.columns
    assert int(df.loc[df["step_index"] == 3, "anomaly_label"].iloc[0]) == 1


def test_npy_profile_preflight_via_adapter():
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile("benchmark-nasa-smap-msl-npy-demo")
    report = run_dataset_profile_preflight(profile, use_purpose="benchmark_reuse")
    assert report.ready is True
    assert report.row_count == 12


def test_loader_and_operator_registered():
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile("benchmark-nasa-smap-msl-npy-demo")
    df = load_dataset_from_profile(profile)
    assert len(df) == 12

    router = OperatorRouter()
    backends_dir = Path(__file__).resolve().parents[1] / "services" / "operator_backends"
    router.auto_discover(str(backends_dir))
    result = router.execute(
        "load_nasa_npy_channels",
        {
            "file_path": "data/timeseries_point/test_fixtures/nasa_smap_msl_demo.npy",
        },
        {},
    )
    assert len(result["data"]) == 12


def test_unknown_adapter_raises():
    with pytest.raises(KeyError):
        load_via_adapter("missing_adapter", Path("x.npy"), {})
