"""Dataset profile source loaders (file + adapter-backed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

import pandas as pd

from services.timeseries_profiles.adapters.registry import load_via_adapter
from services.timeseries_profiles.models import DatasetProfile
from services.timeseries_profiles.path_guard import resolve_profile_source_path


def _profile_dict(profile: Union[DatasetProfile, dict[str, Any]]) -> dict[str, Any]:
    if isinstance(profile, DatasetProfile):
        return profile.model_dump()
    return dict(profile)


def resolve_profile_path(profile: Union[DatasetProfile, dict[str, Any]]) -> Path:
    payload = _profile_dict(profile)
    return resolve_profile_source_path(
        str(payload.get("source_ref") or ""),
        str(payload.get("path_root_alias") or "backend_service"),
    )


def load_dataset_from_profile(profile: Union[DatasetProfile, dict[str, Any]]) -> pd.DataFrame:
    """Load a tabular point dataset described by a dataset profile."""
    payload = _profile_dict(profile)
    path = resolve_profile_path(payload)
    adapter_id = str(payload.get("adapter_id") or "").strip()

    if adapter_id:
        return load_via_adapter(adapter_id, path, payload)

    fmt = str(payload.get("format") or "csv").lower()
    if fmt == "parquet":
        return pd.read_parquet(path)
    if fmt in {"csv", "tsv"}:
        return pd.read_csv(path)
    if fmt == "npy":
        raise ValueError(f"format=npy requires adapter_id on profile {payload.get('profile_id')!r}")

    raise ValueError(f"unsupported profile format={fmt!r}")
