"""Resolve canvas dataset_id to file path + contract (G11)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pandas as pd

from services.operator_execution.pv_data_contracts import build_dataset_contract
from services.slot_datasets.canvas_datasets import list_trainable_datasets
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.labeled_versions import list_labeled_versions

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SNAPSHOT_ID_RE = re.compile(r"^snap-(?P<slot>[^-]+(?:_[^-]+)*?)-v(?P<version>\d+)$")
_PROPOSAL_PREFIX = "lprop-"


def _assert_slot(slot: str) -> str:
    key = str(slot or "").strip()
    if key not in ("pv_day", "pv_point"):
        raise SlotDatasetError("invalid_slot", f"unsupported slot: {key!r}")
    return key


def _read_columns(abs_path: Path) -> list[str]:
    ext = abs_path.suffix.lower()
    if ext == ".parquet":
        return list(pd.read_parquet(abs_path).columns)
    if ext in (".csv", ".tsv"):
        return list(pd.read_csv(abs_path, nrows=0, encoding="utf-8").columns)
    raise SlotDatasetError("unsupported_format", f"unsupported dataset format: {ext}")


def resolve_curated_dataset(*, dataset_id: str, slot: str) -> dict[str, Any]:
    """Resolve a curated labeled_version or cumulative_snapshot id for training."""
    key = _assert_slot(slot)
    normalized_id = str(dataset_id or "").strip()
    if not normalized_id:
        raise SlotDatasetError("missing_dataset_id", "dataset_id is required")
    if normalized_id.startswith(_PROPOSAL_PREFIX):
        raise SlotDatasetError(
            "proposal_not_trainable",
            f"proposal {normalized_id!r} is not curated; confirm before training",
        )

    trainable = list_trainable_datasets(key)
    rows = list(trainable.get("labeled_versions") or []) + list(trainable.get("cumulative_snapshots") or [])
    matched = next((row for row in rows if row.get("dataset_id") == normalized_id), None)
    if matched is None:
        labeled = list_labeled_versions(key)
        matched_lv = next((row for row in labeled if row.get("dataset_version_id") == normalized_id), None)
        if matched_lv:
            matched = {
                "dataset_id": matched_lv["dataset_version_id"],
                "file_path": matched_lv["file_path"],
                "kind": "labeled_version",
                "slot": key,
            }
    if matched is None:
        raise SlotDatasetError("dataset_not_found", f"dataset_id {normalized_id!r} not found for slot {key!r}")
    if matched.get("slot") and matched.get("slot") != key:
        raise SlotDatasetError("slot_mismatch", f"dataset {normalized_id!r} belongs to another slot")

    rel_path = str(matched.get("file_path") or "").strip()
    if not rel_path:
        raise SlotDatasetError("missing_file_path", f"dataset {normalized_id!r} has no file_path")
    abs_path = _BACKEND_DIR / rel_path.replace("\\", "/")
    if not abs_path.is_file():
        raise SlotDatasetError("file_not_found", f"dataset file not found: {rel_path}")

    columns = _read_columns(abs_path)
    contract = build_dataset_contract(
        slot=key,
        kind=str(matched.get("kind") or "labeled_version"),
        dataset_id=normalized_id,
        columns=columns,
    )
    return {
        "dataset_id": normalized_id,
        "file_path": rel_path.replace("\\", "/"),
        "kind": matched.get("kind"),
        "slot": key,
        "dataset_contract": contract,
        "abs_path": str(abs_path),
    }
