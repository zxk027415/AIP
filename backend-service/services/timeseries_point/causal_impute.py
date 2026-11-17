"""Causal imputation on existing rows only (no new timestamps)."""

from __future__ import annotations

from typing import Any


def causal_impute_existing_rows(
    df,
    *,
    entity_keys: list[str],
    time_column: str,
    feature_columns: list[str],
) -> tuple[Any, dict[str, Any]]:
    import pandas as pd

    out = df.copy()
    out[time_column] = pd.to_datetime(out[time_column], errors="coerce", utc=True)
    out = out.sort_values(entity_keys + [time_column]).reset_index(drop=True)

    missing_masks = {}
    time_gaps = {}
    for col in feature_columns:
        if col not in out.columns:
            continue
        mask_col = f"{col}__missing"
        out[mask_col] = out[col].isna().astype(int)
        missing_masks[col] = mask_col
        filled = out.groupby(entity_keys, dropna=False)[col].ffill()
        out[col] = filled
        gap_col = f"{col}__time_gap_sec"
        out[gap_col] = (
            out.groupby(entity_keys, dropna=False)[time_column]
            .diff()
            .dt.total_seconds()
            .fillna(0)
        )
        time_gaps[col] = gap_col

    assert len(out) == len(df), "causal_impute must not change row count"
    return out, {"missing_masks": missing_masks, "time_gaps": time_gaps}
