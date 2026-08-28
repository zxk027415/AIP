"""Canvas trainable dataset registry (G10-S1)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.slot_datasets.errors import SlotDatasetError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_datasets"

_ALLOWED_SLOTS = frozenset({"pv_day", "pv_point"})
_ALLOWED_KINDS = frozenset({"labeled_version", "cumulative_snapshot"})
_SNAPSHOT_ID_RE = re.compile(
    r"^snap-(?P<slot>pv_day|pv_point)(?:-v(?P<version>\d+)|-(?P<stamp>\d{8}-\d{6})(?:-[0-9a-f]{4})?)$"
)


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


def _assert_kind(kind: str) -> str:
    normalized = str(kind or "").strip()
    if normalized not in _ALLOWED_KINDS:
        raise SlotDatasetError(
            "invalid_kind",
            f"kind must be one of {sorted(_ALLOWED_KINDS)!r}, got {normalized!r}",
        )
    return normalized


def _registry_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "trainable_datasets.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_file_path(file_path: str) -> str:
    raw = str(file_path or "").strip()
    if not raw:
        raise SlotDatasetError("missing_file_path", "file_path is required")
    if os.path.isabs(raw):
        rel = os.path.relpath(raw, start=str(_BACKEND_DIR))
        if rel.startswith(".."):
            raise SlotDatasetError(
                "path_outside_backend",
                "file_path must resolve inside backend-service directory",
            )
        return rel.replace("\\", "/")
    return raw.replace("\\", "/")


def _load_datasets(slot: str) -> list[dict[str, Any]]:
    path = _registry_path(slot)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("datasets")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_datasets(slot: str, items: list[dict[str, Any]]) -> None:
    path = _registry_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"slot": slot, "datasets": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _snapshot_version(dataset_id: str) -> int:
    match = _SNAPSHOT_ID_RE.match(str(dataset_id or "").strip())
    if not match:
        return -1
    version = match.group("version")
    if version:
        return int(version)
    stamp = match.group("stamp")
    if stamp:
        digits = stamp.replace("-", "")
        return int(digits) if digits.isdigit() else -1
    return -1


def _sort_group(items: list[dict[str, Any]], *, kind: str) -> list[dict[str, Any]]:
    rows = list(items)
    if kind == "cumulative_snapshot":
        rows.sort(
            key=lambda item: (
                _snapshot_version(str(item.get("dataset_id") or "")),
                str(item.get("created_at") or ""),
            ),
            reverse=True,
        )
    else:
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    for index, row in enumerate(rows):
        row["is_latest"] = index == 0
    return rows


def register_trainable_dataset(
    *,
    dataset_id: str,
    kind: str,
    slot: str,
    ref_id: str,
    file_path: str,
    name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register a trainable canvas dataset row for a pv_day/pv_point slot."""
    key = _assert_pv_slot(slot)
    normalized_kind = _assert_kind(kind)
    normalized_id = str(dataset_id or "").strip()
    if not normalized_id:
        raise SlotDatasetError("missing_dataset_id", "dataset_id is required")
    normalized_ref = str(ref_id or "").strip()
    if not normalized_ref:
        raise SlotDatasetError("missing_ref_id", "ref_id is required")

    rel_path = _normalize_file_path(file_path)
    display_name = str(name or os.path.basename(rel_path) or normalized_id).strip()

    if "/proposal_rows/" in rel_path.replace("\\", "/") or "/proposals/" in rel_path.replace("\\", "/"):
        if normalized_kind == "labeled_version":
            raise SlotDatasetError(
                "proposal_not_trainable",
                "proposal artifacts cannot be registered as trainable labeled_version rows",
            )

    if normalized_kind == "cumulative_snapshot":
        match = _SNAPSHOT_ID_RE.match(normalized_id)
        if not match or match.group("slot") != key:
            raise SlotDatasetError(
                "invalid_snapshot_dataset_id",
                f"cumulative_snapshot dataset_id must match snap-{key}-YYYYMMDD-HHMMSS or snap-{key}-v{{n}}, got {normalized_id!r}",
            )

    datasets = _load_datasets(key)
    for existing in datasets:
        if existing.get("dataset_id") != normalized_id:
            continue
        if existing.get("file_path") != rel_path:
            raise SlotDatasetError(
                "dataset_path_conflict",
                f"dataset_id {normalized_id!r} already registered with a different file_path",
            )
        return dict(existing)

    record: dict[str, Any] = {
        "dataset_id": normalized_id,
        "kind": normalized_kind,
        "slot": key,
        "ref_id": normalized_ref,
        "file_path": rel_path,
        "name": display_name,
        "trainable": True,
        "created_at": _now_iso(),
    }
    if extra:
        for extra_key, extra_value in extra.items():
            if extra_key not in record:
                record[extra_key] = extra_value
    datasets.append(record)
    _save_datasets(key, datasets)
    return dict(record)


def list_trainable_datasets(slot: str) -> dict[str, list[dict[str, Any]]]:
    """List all trainable datasets for a slot, grouped by kind."""
    key = _assert_pv_slot(slot)
    datasets = _load_datasets(key)
    labeled = [dict(item) for item in datasets if item.get("kind") == "labeled_version"]
    cumulative = [dict(item) for item in datasets if item.get("kind") == "cumulative_snapshot"]
    return {
        "labeled_versions": _sort_group(labeled, kind="labeled_version"),
        "cumulative_snapshots": _sort_group(cumulative, kind="cumulative_snapshot"),
    }


def get_trainable_dataset(slot: str, dataset_id: str) -> dict[str, Any] | None:
    """Return one canvas row by dataset_id, or None."""
    key = _assert_pv_slot(slot)
    wanted = str(dataset_id or "").strip()
    if not wanted:
        return None
    for item in _load_datasets(key):
        if str(item.get("dataset_id") or "") == wanted:
            return dict(item)
    return None
