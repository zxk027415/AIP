"""Adapter-backed dataset loaders for non-tabular profile sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

AdapterFn = Callable[[Path, dict[str, Any]], pd.DataFrame]


def load_nasa_npy_channels(path: Path, profile: dict[str, Any]) -> pd.DataFrame:
    """
    Read NASA-style channel-major NPY (shape T x C) into long-form point table.

    Columns: channel_id, step_index, value
    Optional label npy sidecar: {stem}_labels.npy with same T x C or T x 1.
    """
    path = Path(path)
    arr = np.load(path)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2:
        raise ValueError(f"expected 1D or 2D npy array, got shape={arr.shape}")

    time_steps, channel_count = arr.shape
    entity_prefix = str(profile.get("entity_prefix") or "C")
    index_column = str(profile.get("index_column") or "step_index")
    value_column = str((profile.get("feature_columns") or ["value"])[0])

    rows: list[dict[str, Any]] = []
    for channel_idx in range(channel_count):
        channel_id = f"{entity_prefix}-{channel_idx}"
        for step in range(time_steps):
            row = {
                "channel_id": channel_id,
                index_column: int(step),
                value_column: float(arr[step, channel_idx]),
            }
            rows.append(row)

    label_path = path.with_name(f"{path.stem}_labels.npy")
    if label_path.is_file():
        labels = np.load(label_path)
        if labels.ndim == 1:
            labels = labels.reshape(-1, 1)
        label_column = profile.get("label_column") or "anomaly_label"
        for row in rows:
            step = int(row[index_column])
            channel_idx = int(str(row["channel_id"]).split("-")[-1])
            if labels.shape[0] > step:
                if labels.shape[1] > channel_idx:
                    row[str(label_column)] = int(labels[step, channel_idx])
                else:
                    row[str(label_column)] = int(labels[step, 0])

    return pd.DataFrame(rows)


ADAPTER_REGISTRY: dict[str, AdapterFn] = {
    "nasa_npy_channel_adapter": load_nasa_npy_channels,
}


def load_via_adapter(adapter_id: str, path: Path, profile: dict[str, Any]) -> pd.DataFrame:
    fn = ADAPTER_REGISTRY.get(str(adapter_id or "").strip())
    if fn is None:
        raise KeyError(f"unknown adapter_id={adapter_id!r}")
    return fn(path, profile)
