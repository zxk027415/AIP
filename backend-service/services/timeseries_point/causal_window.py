"""Build causal windows from real points (no grid)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .contract import WindowResult


def build_causal_window_for_pending_point(
    df,
    *,
    entity_keys: list[str],
    time_column: str,
    feature_columns: list[str],
    pending_row_index: int,
    context_length: int = 8,
    max_gap_seconds: Optional[float] = None,
) -> WindowResult:
    import pandas as pd

    row = df.iloc[pending_row_index]
    entity_values = tuple(row[k] for k in entity_keys)
    point_time = pd.to_datetime(row[time_column], utc=True)

    entity_mask = np.ones(len(df), dtype=bool)
    for i, key in enumerate(entity_keys):
        entity_mask &= df[key].astype(str) == str(entity_values[i])

    history = df[entity_mask].copy()
    history[time_column] = pd.to_datetime(history[time_column], errors="coerce", utc=True)
    history = history[history[time_column] <= point_time].sort_values(time_column)
    if history.empty or history.index[-1] != df.index[pending_row_index]:
        return WindowResult(status="not_ready", reason="pending_point_not_in_history", entity_key=entity_values)

    if len(history) < 2:
        return WindowResult(
            status="not_ready",
            reason="insufficient_history",
            entity_key=entity_values,
            point_time=str(point_time),
        )

    if max_gap_seconds is not None and len(history) >= 2:
        gap = (history[time_column].iloc[-1] - history[time_column].iloc[-2]).total_seconds()
        if gap > max_gap_seconds:
            return WindowResult(
                status="not_ready",
                reason="gap_too_large",
                entity_key=entity_values,
                point_time=str(point_time),
            )

    window_rows = history.tail(context_length)
    from services.timeseries_point.train_adapter import _derive_channels, _rows_to_tensor

    channels = _derive_channels(feature_columns)
    tensor_values = _rows_to_tensor(window_rows, time_column, feature_columns, channels, context_length)
    tensor = tensor_values.reshape(1, context_length, len(channels))
    return WindowResult(
        status="ready",
        window_tensor=tensor,
        entity_key=entity_values,
        point_time=str(point_time),
        context_length=context_length,
    )
