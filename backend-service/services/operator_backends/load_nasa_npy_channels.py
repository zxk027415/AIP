# @AI_GENERATED
"""
load_nasa_npy_channels — visible source operator for NASA SMAP/MSL-style NPY arrays.

Reads a T x C float array and emits long-form channel/step/value rows for ts_point_* graphs.
"""
from __future__ import annotations

from loguru import logger

from services.operator_backends._path_utils import resolve_file_path
from services.operator_execution.router import OperatorExecutionError
from services.timeseries_profiles.adapters.registry import load_nasa_npy_channels

OPERATOR_ID = "load_nasa_npy_channels"


def execute(params: dict, inputs: dict) -> dict:
    file_path = params.get("file_path")
    if not file_path:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "file_path parameter is required")

    try:
        resolved = resolve_file_path(file_path)
    except FileNotFoundError as exc:
        raise OperatorExecutionError(OPERATOR_ID, "FileNotFoundError", str(exc)) from exc

    profile = {
        "index_column": params.get("index_column") or "step_index",
        "feature_columns": [params.get("value_column") or "value"],
        "label_column": params.get("label_column") or "anomaly_label",
        "entity_prefix": params.get("entity_prefix") or "C",
    }
    try:
        df = load_nasa_npy_channels(resolved, profile)
    except Exception as exc:
        raise OperatorExecutionError(OPERATOR_ID, "ParseError", str(exc)) from exc

    logger.info(f"[{OPERATOR_ID}] Loaded {len(df)} rows from '{resolved}'")
    return {"data": df}
# @AI_GENERATED: end
