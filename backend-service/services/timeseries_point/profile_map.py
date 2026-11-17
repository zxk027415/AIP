"""Map raw dataframe columns to profile contract."""

from __future__ import annotations

from typing import Any


def apply_profile_map(df, profile: dict[str, Any]):
    import pandas as pd

    if df is None or not isinstance(df, pd.DataFrame):
        raise ValueError("profile_map expects dataframe input")

    entity_keys = list(profile.get("entity_keys") or [])
    time_column = profile.get("time_column")
    feature_columns = list(profile.get("feature_columns") or [])
    label_column = profile.get("label_column")
    index_column = profile.get("index_column")

    clock_mode = profile.get("clock_mode", "event_time")
    order_column = time_column if clock_mode == "event_time" else index_column

    keep = []
    for col in entity_keys:
        if col in df.columns:
            keep.append(col)
    if order_column and order_column in df.columns:
        keep.append(order_column)
    elif time_column and time_column in df.columns:
        keep.append(time_column)
    for col in feature_columns:
        if col in df.columns:
            keep.append(col)
    if label_column and label_column in df.columns:
        keep.append(label_column)

    mapped = df[list(dict.fromkeys(keep))].copy()
    return mapped, {
        "entity_keys": entity_keys,
        "time_column": order_column,
        "feature_columns": feature_columns,
        "label_column": label_column,
        "clock_mode": clock_mode,
        "index_column": index_column,
        "simulation_step": profile.get("simulation_step"),
    }
