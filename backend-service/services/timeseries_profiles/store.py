"""JSON-backed profile store."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from .models import AcquisitionManifest, DatasetProfile, DomainProfile

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "timeseries_profiles"


class TimeseriesProfileStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else _DATA_ROOT
        self.dataset_dir = self.root / "dataset"
        self.domain_dir = self.root / "domain"
        self.manifest_dir = self.root / "manifests"

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list_dataset_profiles(self) -> list[dict[str, Any]]:
        if not self.dataset_dir.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.dataset_dir.glob("*.json")):
            payload = self._read_json(path)
            items.append(
                {
                    "profile_id": payload.get("profile_id"),
                    "profile_version": payload.get("profile_version"),
                    "slot": payload.get("slot"),
                    "status": payload.get("status", "published"),
                    "description": payload.get("description"),
                }
            )
        return items

    def get_dataset_profile(self, profile_id: str, version: Optional[str] = None) -> DatasetProfile:
        path = self.dataset_dir / f"{profile_id}.json"
        if not path.exists():
            raise KeyError(f"Dataset profile not found: {profile_id}")
        payload = self._read_json(path)
        if version and payload.get("profile_version") != version:
            raise KeyError(f"Dataset profile version mismatch: {profile_id}@{version}")
        return DatasetProfile(**payload)

    def list_domain_profiles(self) -> list[dict[str, Any]]:
        if not self.domain_dir.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.domain_dir.glob("*.json")):
            payload = self._read_json(path)
            items.append(
                {
                    "domain_profile_id": payload.get("domain_profile_id"),
                    "profile_version": payload.get("profile_version"),
                    "slot": payload.get("slot"),
                    "status": payload.get("status", "published"),
                }
            )
        return items

    def get_domain_profile(self, profile_id: str, version: Optional[str] = None) -> DomainProfile:
        path = self.domain_dir / f"{profile_id}.json"
        if not path.exists():
            raise KeyError(f"Domain profile not found: {profile_id}")
        payload = self._read_json(path)
        if version and payload.get("profile_version") != version:
            raise KeyError(f"Domain profile version mismatch: {profile_id}@{version}")
        return DomainProfile(**payload)

    def get_manifest(self, manifest_id: str) -> AcquisitionManifest:
        path = self.manifest_dir / f"{manifest_id}.json"
        if not path.exists():
            raise KeyError(f"Acquisition manifest not found: {manifest_id}")
        return AcquisitionManifest(**self._read_json(path))

    def ensure_seed_layout(self) -> None:
        for directory in (self.dataset_dir, self.domain_dir, self.manifest_dir):
            os.makedirs(directory, exist_ok=True)
