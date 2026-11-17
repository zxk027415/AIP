# @AI_GENERATED
"""
sliding_window operator backend — Slices time series into sliding windows.

Params: window_size (required), step (default 1), target_column (default "load").
No future data leakage. Discards incomplete samples at the head.
Error if window_size <= 0 or window_size > data rows.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "sliding_window"


def _to_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return bool(v)


def execute(params: dict, inputs: dict) -> dict:
    """
    Slice time series data into sliding windows for model input.

    Each output row represents a complete window of historical data.
    Incomplete windows at the head of the data are discarded.

    Args:
        params: Operator parameters including:
            - window_size (int, required): Number of time steps per window.
            - step (int, optional): Sliding step size. Default 1.
            - target_column (str, optional): Target column name. Default "load".
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} — rows starting from index (window_size - 1),
        stepped by `step`, preserving all original columns.
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # Parse options
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    window_size_raw = params.get("window_size") or options.get("window_size")
    if window_size_raw is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "window_size parameter is required"
        )

    window_size = int(window_size_raw)
    step = int(params.get("step") or options.get("step") or 1)
    target_column = params.get("target_column") or options.get("target_column") or "load"
    gcfg = params.get("_global_config") or {}
    strict_alignment_raw = params.get("strict_alignment_mode")
    if strict_alignment_raw is None:
        strict_alignment_raw = options.get("strict_alignment_mode")
    if strict_alignment_raw is None and isinstance(gcfg, dict):
        strict_alignment_raw = gcfg.get("strict_alignment_mode")
    strict_alignment_mode = _to_bool(strict_alignment_raw, False)
    skip_when_strict = _to_bool(
        params.get("skip_when_strict_alignment")
        if params.get("skip_when_strict_alignment") is not None
        else options.get("skip_when_strict_alignment"),
        False,
    )

    # Validate window_size
    if window_size <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"window_size must be > 0, got {window_size}",
        )

    n_rows = len(data)
    if window_size > n_rows:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"window_size ({window_size}) exceeds available data rows ({n_rows})",
        )

    if step <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"step must be > 0, got {step}",
        )

    df = data.copy()
    if strict_alignment_mode and skip_when_strict:
        logger.info(f"[{OPERATOR_ID}] strict_alignment_mode enabled, bypass sliding window")
        return {"data": df}

    # Discard incomplete samples at the head:
    # Only keep rows from index (window_size - 1) onward, stepped by `step`.
    # Each kept row at position i represents a window of [i - window_size + 1, i].
    valid_indices = list(range(window_size - 1, n_rows, step))
    result = df.iloc[valid_indices].reset_index(drop=True)

    logger.info(
        f"[{OPERATOR_ID}] Windowed {n_rows} rows -> {len(result)} samples "
        f"(window_size={window_size}, step={step})"
    )

    return {"data": result}
# @AI_GENERATED: end
