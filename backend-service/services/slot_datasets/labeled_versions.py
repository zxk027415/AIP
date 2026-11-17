"""Labeled dataset version store (G10-S0)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.slot_datasets.errors import SlotDatasetError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_datasets"

# @AI_GENERATED: pv_tsc confirmed device-day rows are curated versions too.
_ALLOWED_SLOTS = frozenset({"pv_day", "pv_point", "pv_tsc"})
# @AI_GENERATED: end
_ALLOWED_STATUS = frozenset({"curated"})


def _assert_pv_slot(slot: str) -> str:
    key = str(slot or "").strip()
    if not key:
        raise SlotDatasetError("missing_slot", "slot is required")
    if key not in _ALLOWED_SLOTS:
        raise SlotDatasetError(
            "invalid_slot",
            f"slot must be one of {sorted(_ALLOWED_SLOTS)!r}, got {key!r}",
        )
    return key


def _versions_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "labeled_versions.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_versions(slot: str) -> list[dict[str, Any]]:
    path = _versions_path(slot)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("versions")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_versions(slot: str, items: list[dict[str, Any]]) -> None:
    path = _versions_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"slot": slot, "versions": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _resolve_source_path(file_path: str) -> Path:
    raw = str(file_path or "").strip()
    if not raw:
        raise SlotDatasetError("missing_file_path", "file_path is required")
    if os.path.isabs(raw):
        abs_path = Path(raw)
    else:
        abs_path = _BACKEND_DIR / raw
    if not abs_path.is_file():
        raise SlotDatasetError("file_not_found", f"source file not found: {raw}")
    return abs_path


def _relative_backend_path(abs_path: Path) -> str:
    rel = os.path.relpath(str(abs_path.resolve()), start=str(_BACKEND_DIR))
    if rel.startswith(".."):
        raise SlotDatasetError(
            "path_outside_backend",
            "file_path must resolve inside backend-service directory",
        )
    return rel.replace("\\", "/")


def _content_sha256(abs_path: Path) -> str:
    digest = hashlib.sha256()
    with abs_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allocate_dataset_version_id(slot: str) -> str:
    """Allocate a monotonic, never-reused labeled dataset version id."""
    key = _assert_pv_slot(slot)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"lds-{key}-{stamp}-{suffix}"


def publish_labeled_version(
    *,
    slot: str,
    file_path: str,
    status: str = "curated",
    dataset_version_id: str | None = None,
) -> dict[str, Any]:
    """Publish a curated labeled dataset version for a PV product slot."""
    key = _assert_pv_slot(slot)
    normalized_status = str(status or "").strip()
    if normalized_status not in _ALLOWED_STATUS:
        raise SlotDatasetError(
            "invalid_status",
            f"status must be one of {sorted(_ALLOWED_STATUS)!r}, got {normalized_status!r}",
        )

    abs_path = _resolve_source_path(file_path)
    rel_path = _relative_backend_path(abs_path)
    version_id = str(dataset_version_id or allocate_dataset_version_id(key)).strip()
    if not version_id:
        raise SlotDatasetError("missing_dataset_version_id", "dataset_version_id is required")

    record: dict[str, Any] = {
        "dataset_version_id": version_id,
        "slot": key,
        "status": normalized_status,
        "file_path": rel_path,
        "content_sha256": _content_sha256(abs_path),
        "created_at": _now_iso(),
    }

    versions = _load_versions(key)
    if any(item.get("dataset_version_id") == version_id for item in versions):
        raise SlotDatasetError(
            "dataset_version_id_conflict",
            f"dataset_version_id already exists: {version_id!r}",
        )
    versions.append(record)
    _save_versions(key, versions)
    return dict(record)


def list_labeled_versions(slot: str) -> list[dict[str, Any]]:
    """List all labeled versions for a slot, newest first."""
    key = _assert_pv_slot(slot)
    items = list(_load_versions(key))
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items
