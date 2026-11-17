# @AI_GENERATED
"""Device-day MultiRocket prediction adapter with per-window evidence."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from services.iterative_labeling.tsc.tsc_predictor import TSCPredictor
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "tsc_predict"
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_DIR.parent


def _resolve_model_ref(value: Any) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "model_ref is required"
        )
    reference = Path(raw)
    candidates = (
        [reference]
        if reference.is_absolute()
        else [_BACKEND_DIR / reference, _PROJECT_ROOT / reference, Path.cwd() / reference]
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise OperatorExecutionError(
        OPERATOR_ID, "ModelNotFoundError", f"model_ref does not exist: {raw}"
    )


def _target_days(frame: pd.DataFrame, configured: Any) -> list:
    if configured not in (None, ""):
        parsed = pd.to_datetime(configured, errors="coerce")
        if pd.isna(parsed):
            raise OperatorExecutionError(
                OPERATOR_ID, "ParameterError", f"invalid target_day: {configured!r}"
            )
        return [parsed.date()]
    return sorted(frame["time"].dt.date.unique().tolist())


def execute(params: dict, inputs: dict) -> dict:
    data = inputs.get("data")
    if not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )
    if "time" not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "data is missing time")

    model_ref = (
        params.get("model_ref")
        or inputs.get("model_ref")
        or inputs.get("model_path")
        or inputs.get("model_artifact_ref")
    )
    model_dir = _resolve_model_ref(model_ref)
    try:
        predictor = TSCPredictor(str(model_dir))
    except Exception as exc:
        raise OperatorExecutionError(OPERATOR_ID, "ModelLoadError", str(exc)) from exc

    frame = data.copy()
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    if frame["time"].isna().any():
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"data contains {int(frame['time'].isna().sum())} invalid time values",
        )
    series_keys = [
        name
        for name in predictor.window_config.get(
            "series_keys", ["site_id", "device_id", "branch_id"]
        )
        if name in frame.columns
    ]
    if not series_keys:
        if "device_id" not in frame.columns:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "InputError",
                "data has no configured series key or device_id",
            )
        series_keys = ["device_id"]

    aggregation = str(params.get("aggregation") or "majority").strip()
    preprocess_method = params.get("preprocess_method") or None
    stride_raw = params.get("stride")
    try:
        stride = int(stride_raw) if stride_raw not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "stride must be an integer"
        ) from exc

    records: list[dict[str, Any]] = []
    successes = 0
    for _, group in frame.groupby(series_keys, sort=False, dropna=False):
        ordered = group.sort_values("time").reset_index(drop=True)
        days = _target_days(ordered, params.get("target_day"))
        for target_day in days:
            context_start = pd.Timestamp(target_day - timedelta(days=1))
            context_end = pd.Timestamp(target_day + timedelta(days=1))
            context = ordered[
                (ordered["time"] >= context_start) & (ordered["time"] < context_end)
            ]
            try:
                outcome = predictor.predict_device_multi_window(
                    context,
                    stride=stride,
                    preprocess_method=preprocess_method,
                    aggregation=aggregation,
                    target_day=target_day,
                )
            except Exception as exc:
                outcome = {
                    "label": None,
                    "confidence": 0.0,
                    "n_windows": 0,
                    "per_window_predictions": [],
                    "per_window_details": [],
                    "aggregation": aggregation,
                    "model_name": predictor.model_name,
                    "error": str(exc),
                }
            record: dict[str, Any] = {
                name: (None if pd.isna(ordered[name].iloc[0]) else str(ordered[name].iloc[0]))
                for name in ("site_id", "device_id", "branch_id")
                if name in ordered.columns
            }
            record.update(
                {
                    "time_window": target_day.isoformat(),
                    "target_day": target_day.isoformat(),
                    "predicted_label": outcome.get("label"),
                    "confidence": float(outcome.get("confidence") or 0.0),
                    "n_windows": int(outcome.get("n_windows") or 0),
                    "per_window_predictions": list(
                        outcome.get("per_window_predictions") or []
                    ),
                    "per_window_details": list(outcome.get("per_window_details") or []),
                    "aggregation": outcome.get("aggregation") or aggregation,
                    "model_name": outcome.get("model_name") or predictor.model_name,
                    "model_window_config": {
                        **predictor.window_config,
                        "inference_stride": stride
                        if stride is not None
                        else predictor.window_config.get("stride"),
                    },
                    "error": outcome.get("error"),
                }
            )
            if record["predicted_label"] is not None and not record["error"]:
                successes += 1
            records.append(record)

    if not records:
        raise OperatorExecutionError(
            OPERATOR_ID, "EmptyPredictionError", "no device-day groups were found"
        )
    if successes == 0:
        reasons = sorted({str(row.get("error") or "no decision") for row in records})
        raise OperatorExecutionError(
            OPERATOR_ID,
            "PredictionError",
            f"all {len(records)} device-day predictions failed: {'; '.join(reasons[:3])}",
        )
    return {
        "predictions": records,
        "prediction_summary": {
            "total_device_days": len(records),
            "successful_device_days": successes,
            "failed_device_days": len(records) - successes,
            "evidence_window_count": sum(int(row.get("n_windows") or 0) for row in records),
            "model_name": predictor.model_name,
            "model_ref": str(model_ref).replace("\\", "/"),
            "model_window_config": {
                **predictor.window_config,
                "inference_stride": stride
                if stride is not None
                else predictor.window_config.get("stride"),
            },
            "aggregation": aggregation,
        },
    }
# @AI_GENERATED: end
