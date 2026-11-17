"""Join point-level labels; forbid day-label broadcast."""

from __future__ import annotations

from typing import Any, Optional


def join_point_labels(
    measurements,
    labels=None,
    *,
    entity_keys: list[str],
    time_column: str,
    label_column: str = "label",
    label_source_column: Optional[str] = "source",
    forbidden_sources: Optional[set[str]] = None,
):
    import pandas as pd

    forbidden = forbidden_sources or {"day_label", "human_day", "day_import", "parquet_day_label"}
    out = measurements.copy()
    if labels is None or not isinstance(labels, pd.DataFrame) or labels.empty:
        if label_column not in out.columns:
            out[label_column] = None
        return out, {"joined_rows": 0, "forbidden_sources_rejected": 0}

    label_df = labels.copy()
    if label_source_column and label_source_column in label_df.columns:
        bad = label_df[label_source_column].astype(str).isin(forbidden)
        rejected = int(bad.sum())
        label_df = label_df[~bad]
    else:
        rejected = 0

    join_keys = [k for k in entity_keys + [time_column] if k in out.columns and k in label_df.columns]
    if not join_keys:
        raise ValueError("label_join: no common entity/time keys between measurements and labels")

    merged = out.merge(
        label_df[join_keys + [c for c in label_df.columns if c not in join_keys]],
        on=join_keys,
        how="left",
        suffixes=("", "_label"),
    )
    if label_column not in merged.columns and f"{label_column}_label" in merged.columns:
        merged[label_column] = merged[f"{label_column}_label"]
    return merged, {"joined_rows": int(len(label_df)), "forbidden_sources_rejected": rejected}
