# @AI_GENERATED
"""load_labeled_dataset — load curated dataset by id with dataset_contract (G11)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from services.operator_execution.router import OperatorExecutionError
from services.slot_datasets.dataset_resolver import resolve_curated_dataset
from services.slot_datasets.errors import SlotDatasetError

OPERATOR_ID = "load_labeled_dataset"
logger = logging.getLogger(__name__)


def _resolve_slot(params: dict) -> str:
    slot = str(params.get("slot") or params.get("_global_config", {}).get("slot") or "").strip()
    if slot not in ("pv_day", "pv_point", "pv_tsc"):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            "slot must be pv_day, pv_point, or pv_tsc",
        )
    return slot


def execute(params: dict, inputs: dict) -> dict:
    dataset_id = str(
        params.get("dataset_id")
        or params.get("dataset_version_id")
        or params.get("trainable_file_path")
        or ""
    ).strip()
    if not dataset_id:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "dataset_id is required")

    slot = _resolve_slot(params)
    try:
        resolved = resolve_curated_dataset(dataset_id=dataset_id, slot=slot)
    except SlotDatasetError as exc:
        raise OperatorExecutionError(OPERATOR_ID, exc.code, exc.message) from exc

    abs_path = Path(resolved["abs_path"])
    ext = abs_path.suffix.lower()
    if ext == ".parquet":
        frame = pd.read_parquet(abs_path)
    else:
        frame = pd.read_csv(abs_path, encoding="utf-8")

    contract = resolved["dataset_contract"]
    logger.info(
        "[%s] loaded %s rows from %s (%s)",
        OPERATOR_ID,
        len(frame),
        resolved["dataset_id"],
        resolved["file_path"],
    )
    return {
        "data": frame,
        "dataset_contract": contract,
        "dataset_id": resolved["dataset_id"],
        "file_path": resolved["file_path"],
    }
