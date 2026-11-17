# @AI_GENERATED
"""TSC sample builder with an explicit 288-slot clock-grid production contract.

``representation=clock_grid_288_mask`` creates exactly one sample per physical
series/day with channels ``value``, ``i_cal`` and ``is_measured``. The legacy
continuous-row sliding window remains available only when explicitly selected.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from services.iterative_labeling.tsc.data_loader import (
    preprocess_X,
    split_labeled_dataframe,
)
from services.iterative_labeling.tsc.grid_day_builder import (
    TSC_GRID_CHANNELS,
    build_tsc_grid_dataset,
    preprocess_grid_X,
)
from services.iterative_labeling.tsc.sliding_window_sampler import SamplerConfig
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "tsc_sliding_window"
GRID_REPRESENTATION = "clock_grid_288_mask"
LEGACY_REPRESENTATION = "continuous_sliding_window"


def _as_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _number(params: dict, key: str, cast, default: Any) -> Any:
    raw = params.get(key)
    try:
        return cast(default if raw in (None, "") else raw)
    except (TypeError, ValueError) as exc:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"{key} has an invalid value: {raw!r}",
        ) from exc


def _preprocess_method(params: dict) -> str:
    method = str(params.get("preprocess_method") or "per_sample_zscore").strip()
    if method not in {"per_sample_zscore", "per_sample_minmax", "none"}:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            "preprocess_method must be per_sample_zscore, per_sample_minmax, or none",
        )
    return method


def _series_keys(params: dict) -> list[str]:
    raw = params.get("series_keys") or ["site_id", "device_id", "branch_id"]
    if isinstance(raw, str):
        keys = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, (list, tuple)):
        keys = [str(part).strip() for part in raw if str(part).strip()]
    else:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            "series_keys must be a list or comma-separated string",
        )
    if not keys:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "series_keys cannot be empty")
    return keys


def _sampler_config(params: dict) -> SamplerConfig:
    values = {
        key: params[key]
        for key in SamplerConfig.__dataclass_fields__
        if key in params and params[key] not in (None, "")
    }
    try:
        config = SamplerConfig.from_dict(values)
        config.window_length = int(config.window_length)
        config.stride = int(config.stride)
        config.min_coverage = float(config.min_coverage)
        config.min_std = float(config.min_std)
        config.purity_threshold = float(config.purity_threshold)
        config.fault_priority_min_ratio = float(config.fault_priority_min_ratio)
        config.normal_label = int(config.normal_label)
        config.max_gap_multiplier = float(config.max_gap_multiplier)
    except (TypeError, ValueError) as exc:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", f"invalid sampler configuration: {exc}"
        ) from exc
    if config.window_length <= 0 or config.stride <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "window_length and stride must be positive"
        )
    if not config.channels:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "channels must contain at least one column"
        )
    return config


def _execute_clock_grid(params: dict, data: pd.DataFrame) -> dict:
    purity_threshold = _number(params, "purity_threshold", float, 0.7)
    series_keys = _series_keys(params)
    preprocess_method = _preprocess_method(params)
    try:
        X, y, meta, grid_stats = build_tsc_grid_dataset(
            data,
            purity_threshold=purity_threshold,
            series_keys=series_keys,
            min_occupied_slots=_number(params, "min_occupied_slots", int, 173),
            min_daytime_occupancy=_number(params, "min_daytime_occupancy", float, 0.8),
            max_daytime_gap_slots=_number(params, "max_daytime_gap_slots", int, 6),
            require_all_hours_covered=_as_bool(
                params.get("require_all_hours_covered"), True
            ),
        )
    except Exception as exc:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", str(exc)) from exc
    if len(y) == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "EmptySamplesError", "no valid TSC clock-grid device-days were produced"
        )
    if X.ndim != 3 or tuple(X.shape[1:]) != (288, 3):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "GridContractError",
            f"expected [N,288,3] clock-grid samples, got {tuple(X.shape)}",
        )
    if list(grid_stats.get("channels") or []) != list(TSC_GRID_CHANNELS):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "GridContractError",
            f"expected channels={list(TSC_GRID_CHANNELS)!r}",
        )
    if "t_start" not in meta.columns or "device_id" not in meta.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "GridContractError",
            "grid metadata must contain device_id and t_start for strict evaluation",
        )
    try:
        X = preprocess_grid_X(X, method=preprocess_method)
    except Exception as exc:
        raise OperatorExecutionError(OPERATOR_ID, "PreprocessError", str(exc)) from exc

    grid_stats = dict(grid_stats)
    grid_stats["representation"] = GRID_REPRESENTATION
    sampler_payload = {
        "window_length": 288,
        "stride": 288,
        "channels": list(TSC_GRID_CHANNELS),
        "series_keys": series_keys,
        "purity_threshold": purity_threshold,
        "min_std": 0.0,
    }
    return {
        "samples": {
            "X": X,
            "y": y,
            "meta": meta,
            "load_stats": grid_stats,
            "sampler_config": sampler_payload,
            "preprocess_method": preprocess_method,
            "preprocessed": True,
            "representation": GRID_REPRESENTATION,
            "channels": list(TSC_GRID_CHANNELS),
        }
    }


def _execute_legacy_sliding_window(params: dict, data: pd.DataFrame) -> dict:
    config = _sampler_config(params)
    fault_oversample = _as_bool(params.get("fault_oversample"), True)
    fault_stride_divisor = _number(params, "fault_stride_divisor", int, 6)
    if fault_stride_divisor <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "fault_stride_divisor must be positive"
        )
    try:
        X, y, meta, load_stats = split_labeled_dataframe(
            data,
            sampler_config=config,
            fault_oversample=fault_oversample,
            fault_stride_divisor=fault_stride_divisor,
        )
    except Exception as exc:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", str(exc)) from exc
    if len(y) == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "EmptySamplesError", "no valid TSC windows were produced"
        )
    preprocess_method = _preprocess_method(params)
    try:
        X = preprocess_X(X, method=preprocess_method)
    except Exception as exc:
        raise OperatorExecutionError(OPERATOR_ID, "PreprocessError", str(exc)) from exc
    return {
        "samples": {
            "X": X,
            "y": y,
            "meta": meta,
            "load_stats": load_stats,
            "sampler_config": config.to_dict(),
            "preprocess_method": preprocess_method,
            "preprocessed": True,
            "representation": LEGACY_REPRESENTATION,
            "channels": list(config.channels),
        }
    }


def execute(params: dict, inputs: dict) -> dict:
    data = inputs.get("data")
    if not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )
    representation = str(
        params.get("representation") or LEGACY_REPRESENTATION
    ).strip()
    if representation == GRID_REPRESENTATION:
        return _execute_clock_grid(params, data)
    if representation == LEGACY_REPRESENTATION:
        return _execute_legacy_sliding_window(params, data)
    raise OperatorExecutionError(
        OPERATOR_ID,
        "ParameterError",
        f"unsupported representation={representation!r}; expected {GRID_REPRESENTATION!r} or {LEGACY_REPRESENTATION!r}",
    )
# @AI_GENERATED: end
