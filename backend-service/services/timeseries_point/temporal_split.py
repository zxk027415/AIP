"""Entity-aware temporal split."""

from __future__ import annotations

from typing import Any


def temporal_entity_split(
    df,
    *,
    entity_keys: list[str],
    time_column: str,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    locked_holdout_entities: set | None = None,
) -> tuple[Any, dict[str, Any]]:
    import pandas as pd

    locked_holdout_entities = locked_holdout_entities or set()
    out = df.copy()
    out[time_column] = pd.to_datetime(out[time_column], errors="coerce", utc=True)
    out["_split"] = "train"

    for entity, group in out.groupby(entity_keys, dropna=False):
        entity_tuple = entity if isinstance(entity, tuple) else (entity,)
        if entity_tuple in locked_holdout_entities:
            out.loc[group.index, "_split"] = "locked_holdout"
            continue
        ordered = group.sort_values(time_column)
        n = len(ordered)
        n_train = max(1, int(n * train_ratio))
        n_val = max(0, int(n * val_ratio))
        train_idx = ordered.index[:n_train]
        val_idx = ordered.index[n_train : n_train + n_val]
        test_idx = ordered.index[n_train + n_val :]
        out.loc[train_idx, "_split"] = "train"
        out.loc[val_idx, "_split"] = "val"
        out.loc[test_idx, "_split"] = "test"

    stats = out["_split"].value_counts().to_dict()
    return out, {"split_counts": stats}
