"""Schema validation for real-point tables."""

from __future__ import annotations

from typing import Any


def validate_point_schema(df, contract: dict[str, Any]) -> dict[str, Any]:
    import pandas as pd

    issues: list[dict[str, Any]] = []
    entity_keys = list(contract.get("entity_keys") or [])
    time_column = contract.get("time_column")
    feature_columns = list(contract.get("feature_columns") or [])
    clock_mode = str(contract.get("clock_mode") or "event_time")

    required = entity_keys + ([time_column] if time_column else []) + feature_columns
    missing = [c for c in required if c not in df.columns]
    if missing:
        issues.append({"code": "missing_columns", "columns": missing})

    duplicate_count = 0
    if entity_keys and time_column and time_column in df.columns:
        duplicate_count = int(df.duplicated(subset=entity_keys + [time_column], keep=False).sum())
        if duplicate_count:
            issues.append(
                {
                    "code": "duplicate_entity_time",
                    "count": duplicate_count,
                    "hint": "Resolve conflicting duplicate rows before training",
                }
            )

    if clock_mode == "event_time" and time_column and time_column in df.columns:
        try:
            ts = pd.to_datetime(df[time_column], errors="coerce", utc=True, format="mixed")
        except (TypeError, ValueError):
            ts = pd.to_datetime(df[time_column], errors="coerce", utc=True)
        invalid_ts = int(ts.isna().sum())
        if invalid_ts:
            issues.append({"code": "invalid_timestamps", "count": invalid_ts})
    elif clock_mode == "index" and time_column and time_column in df.columns:
        series = pd.to_numeric(df[time_column], errors="coerce")
        invalid_idx = int(series.isna().sum())
        if invalid_idx:
            issues.append({"code": "invalid_index_values", "count": invalid_idx})

    valid = len(issues) == 0
    return {
        "valid": valid,
        "issues": issues,
        "row_count": int(len(df)),
        "duplicate_point_count": duplicate_count,
    }
