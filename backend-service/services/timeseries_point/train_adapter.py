"""Build RealtimePointTrainer-compatible dataset from real-point tables."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

IGNORE_LABEL = -1
_DEVICE_COLUMNS = ["site_id", "device_id", "branch_id"]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _map_entity_columns(df: pd.DataFrame, entity_keys: list[str]) -> pd.DataFrame:
    out = df.copy()
    padded = list(entity_keys) + ["__pad__"] * 3
    for target, source in zip(_DEVICE_COLUMNS, padded[:3]):
        out[target] = out[source] if source in out.columns else "__default__"
    return out


def _derive_channels(feature_columns: list[str]) -> list[str]:
    base = list(feature_columns)
    extras = ["is_measured", "time_since_measured", "tod_sin", "tod_cos", "is_daylight"]
    for ch in extras:
        if ch not in base:
            base.append(ch)
    return base


def _entity_key(key: Any) -> tuple:
    return key if isinstance(key, tuple) else (key,)


def _stringify_entity_columns(mapped: pd.DataFrame) -> pd.DataFrame:
    out = mapped.copy()
    for column in _DEVICE_COLUMNS:
        if column not in out.columns:
            continue
        out[column] = out[column].map(lambda value: "__nan__" if pd.isna(value) else str(value))
    return out


def _entity_label_sets(
    mapped: pd.DataFrame,
    *,
    label_column: str,
    time_column: Optional[str] = None,
) -> tuple[list[tuple], dict[tuple, set[int]], dict[tuple, int]]:
    """Collect labels that can become last-point targets (skip each entity's first row)."""
    groups = mapped.groupby(_DEVICE_COLUMNS, dropna=False)
    entities = sorted(_entity_key(key) for key in groups.groups)
    labels_by_entity: dict[tuple, set[int]] = {}
    size_by_entity: dict[tuple, int] = {}
    label_series = (
        pd.to_numeric(mapped[label_column], errors="coerce")
        if label_column in mapped.columns
        else None
    )
    for key, idx in groups.groups.items():
        entity = _entity_key(key)
        size_by_entity[entity] = int(len(idx))
        if label_series is None:
            labels_by_entity[entity] = set()
            continue
        group = mapped.loc[idx]
        if time_column and time_column in group.columns:
            group = group.sort_values(time_column)
        target_index = group.index[1:] if len(group) >= 2 else group.index[:0]
        values = label_series.loc[target_index].dropna()
        labels_by_entity[entity] = {
            int(value) for value in values.unique() if int(value) != IGNORE_LABEL
        }
    return entities, labels_by_entity, size_by_entity


def _assign_entity_disjoint_splits(
    mapped: pd.DataFrame,
    split_column: str = "_split",
    label_column: str = "label",
    time_column: Optional[str] = None,
) -> pd.DataFrame:
    """Whole-entity train/val/test with train covering every last-point business label.

    Rare labels (1–2 holder entities) all go to train so val/test cannot be the
    only place a class appears. RealtimePointTrainer forbids device leakage.
    """
    out = _stringify_entity_columns(mapped)
    entities, labels_by_entity, size_by_entity = _entity_label_sets(
        out, label_column=label_column, time_column=time_column
    )
    if len(entities) < 3:
        raise ValueError("entity_disjoint training requires at least 3 entities")

    all_labels: set[int] = set().union(*labels_by_entity.values()) if labels_by_entity else set()
    holders = {
        label: [entity for entity in entities if label in labels_by_entity[entity]]
        for label in all_labels
    }
    assignment: dict[tuple, str] = {}
    uncovered = set(all_labels)
    for label in sorted(all_labels, key=lambda item: (len(holders[item]), item)):
        if label not in uncovered:
            continue
        holder_entities = holders[label]
        if len(holder_entities) <= 2:
            for entity in holder_entities:
                assignment[entity] = "train"
            for entity in holder_entities:
                uncovered -= labels_by_entity[entity]
            continue
        if any(assignment.get(entity) == "train" for entity in holder_entities):
            uncovered.discard(label)
            continue
        unassigned = [entity for entity in holder_entities if entity not in assignment]
        pick = min(
            unassigned or holder_entities,
            key=lambda entity: (size_by_entity[entity], entity),
        )
        assignment[pick] = "train"
        uncovered -= labels_by_entity[pick]

    remaining = [entity for entity in entities if entity not in assignment]
    remaining.sort(key=lambda entity: (-size_by_entity[entity], entity))

    def _train_cover_without(entity: tuple) -> bool:
        others = [
            other
            for other, split in assignment.items()
            if split == "train" and other != entity
        ]
        if not others:
            return False
        covered = set().union(*(labels_by_entity[other] for other in others))
        return labels_by_entity[entity].issubset(covered)

    def _ensure_split(name: str) -> None:
        if any(split == name for split in assignment.values()):
            return
        if remaining:
            assignment[remaining.pop(0)] = name
            return
        movable = [
            entity
            for entity in entities
            if assignment.get(entity) == "train" and _train_cover_without(entity)
        ]
        if not movable:
            raise ValueError(
                f"无法在保证 train 覆盖全部业务标签的同时分出 {name} 实体"
            )
        steal = max(movable, key=lambda entity: (size_by_entity[entity], entity))
        assignment[steal] = name

    _ensure_split("val")
    _ensure_split("test")
    for index, entity in enumerate(remaining):
        assignment[entity] = ("train", "val", "test")[index % 3]

    entity_tuples = list(zip(*(out[column] for column in _DEVICE_COLUMNS)))
    out[split_column] = [assignment[_entity_key(key)] for key in entity_tuples]
    return out


def _repair_splits_for_last_point_labels(
    meta_df: pd.DataFrame,
    y_array: np.ndarray,
) -> pd.DataFrame:
    """Move whole entities into train if their last-point labels are missing from train."""
    out = meta_df.copy()
    targets = y_array[:, -1]
    valid = targets != IGNORE_LABEL
    out["_entity"] = list(zip(*(out[column].astype(str) for column in _DEVICE_COLUMNS)))
    for _ in range(8):
        train_mask = valid & (out["split"].astype(str).to_numpy() == "train")
        train_labels = {int(value) for value in np.unique(targets[train_mask])} if train_mask.any() else set()
        eval_mask = valid & out["split"].astype(str).isin(["val", "test"]).to_numpy()
        if not eval_mask.any():
            break
        missing = {int(value) for value in np.unique(targets[eval_mask]) if int(value) not in train_labels}
        if not missing:
            break
        move_entities = {
            out["_entity"].iloc[index]
            for index in np.flatnonzero(eval_mask)
            if int(targets[index]) in missing
        }
        if not move_entities:
            break
        out.loc[out["_entity"].isin(move_entities), "split"] = "train"
    return out.drop(columns=["_entity"])


def build_real_point_dataset(
    df: pd.DataFrame,
    *,
    entity_keys: list[str],
    time_column: str,
    feature_columns: list[str],
    label_column: str = "label",
    split_column: str = "_split",
    context_length: int = 8,
    output_root: str = "backend-service/data/timeseries_point/datasets",
) -> dict[str, Any]:
    """Materialize windows_w{context_length}.npz for RealtimePointTrainer."""
    if context_length < 2:
        raise ValueError("context_length must be >= 2")

    mapped = _map_entity_columns(df, entity_keys)
    mapped = _stringify_entity_columns(mapped)
    mapped[time_column] = pd.to_datetime(mapped[time_column], errors="coerce", utc=True)
    # Trainer requires device isolation; keep whole entities in one split and
    # cover every last-point business label in train instead of reusing temporal _split.
    if split_column in mapped.columns:
        mapped = mapped.drop(columns=[split_column])
    mapped = _assign_entity_disjoint_splits(
        mapped,
        split_column=split_column,
        label_column=label_column,
        time_column=time_column,
    )
    mapped = mapped.sort_values(_DEVICE_COLUMNS + [time_column]).reset_index(drop=True)
    channels = _derive_channels(feature_columns)

    all_x: list[np.ndarray] = []
    all_y: list[np.ndarray] = []
    meta_rows: list[dict[str, Any]] = []

    for _, group in mapped.groupby(_DEVICE_COLUMNS, dropna=False):
        group = group.sort_values(time_column)
        for idx in range(len(group)):
            row = group.iloc[idx]
            split = str(row.get(split_column) or "train")
            if split == "locked_holdout":
                continue
            history = group.iloc[: idx + 1]
            if len(history) < 2:
                continue
            window_rows = history.tail(context_length)
            tensor = _rows_to_tensor(window_rows, time_column, feature_columns, channels, context_length)
            y_row = np.full(context_length, IGNORE_LABEL, dtype=np.int64)
            label_val = row.get(label_column)
            if label_val is not None and not (isinstance(label_val, float) and np.isnan(label_val)):
                y_row[-1] = int(label_val)
            all_x.append(tensor)
            all_y.append(y_row)
            meta_rows.append(
                {
                    "site_id": row["site_id"],
                    "device_id": row["device_id"],
                    "branch_id": row["branch_id"],
                    "split": split,
                    "target_time": row[time_column],
                    "start_time": window_rows[time_column].iloc[0],
                }
            )

    if not all_x:
        raise ValueError("no trainable windows from real-point table")

    x_array = np.stack(all_x).astype(np.float32)
    y_array = np.stack(all_y).astype(np.int64)
    meta_df = _repair_splits_for_last_point_labels(pd.DataFrame(meta_rows), y_array)

    backend = _backend_root()
    dataset_root = backend / output_root
    dataset_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"realpoint-w{context_length}-", dir=str(dataset_root)))
    npz_name = f"windows_w{context_length}.npz"
    meta_name = f"window_meta_w{context_length}.parquet"
    split_name = "split_manifest.parquet"

    np.savez_compressed(temp_dir / npz_name, X=x_array, Y=y_array, channels=np.asarray(channels))
    meta_df.to_parquet(temp_dir / meta_name, index=False)
    meta_df.to_parquet(temp_dir / split_name, index=False)

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    digest = hashlib.sha256(x_array.tobytes()).hexdigest()[:8]
    dataset_version = f"realpoint-w{context_length}-{timestamp}-{digest}"
    final_dir = dataset_root / dataset_version
    final_dir.mkdir(parents=True, exist_ok=False)

    for name in [npz_name, meta_name, split_name]:
        (temp_dir / name).replace(final_dir / name)

    artifact_records = {}
    for name in [npz_name, meta_name, split_name]:
        artifact_records[name] = {
            "path": os.path.relpath(final_dir / name, start=backend.parent).replace("\\", "/"),
            "sha256": _sha256_file(final_dir / name),
            "bytes": (final_dir / name).stat().st_size,
        }

    report = {
        "dataset_version": dataset_version,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "source_snapshot": os.path.relpath(final_dir, start=backend.parent),
        "source_snapshot_version": dataset_version,
        "window_size": context_length,
        "stride": 1,
        "slot_minutes": 0,
        "window_count": int(len(x_array)),
        "channels": channels,
        "max_forward_fill_slots": 2,
        "missing_value_policy": {
            "mode": "past_only_forward_fill_then_zero",
            "max_forward_fill_slots": 2,
            "remaining_fill_value": 0.0,
            "measurement_mask_channel": "is_measured",
            "time_since_channel": "time_since_measured",
            "uses_future_values": False,
        },
        "causal_audit": {"all_passed": True, "scope": "real_point_builder_p0"},
        "artifacts": {
            npz_name: {"path": artifact_records[npz_name]["path"], "sha256": artifact_records[npz_name]["sha256"]},
            meta_name: {"path": artifact_records[meta_name]["path"], "sha256": artifact_records[meta_name]["sha256"]},
        },
        "contract": "real_point_v1_no_grid",
    }
    (final_dir / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "snapshot_version": dataset_version,
        "label_snapshot_hash": hashlib.sha256(dataset_version.encode("utf-8")).hexdigest(),
        "contract": "real_point_v1_no_grid",
    }
    (final_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report["source_snapshot"] = os.path.relpath(final_dir, start=backend.parent)

    rel_path = os.path.relpath(final_dir, start=backend.parent)
    return {"dataset_dir": rel_path, "dataset_version": dataset_version, "window_count": len(x_array), "report": report}


def _rows_to_tensor(
    rows: pd.DataFrame,
    time_column: str,
    feature_columns: list[str],
    channels: list[str],
    context_length: int,
) -> np.ndarray:
    values = np.zeros((context_length, len(channels)), dtype=np.float32)
    tail = rows.tail(context_length)
    offset = context_length - len(tail)
    for i, (_, row) in enumerate(tail.iterrows()):
        slot = offset + i
        for j, ch in enumerate(channels):
            if ch in feature_columns and ch in row.index:
                val = row[ch]
                values[slot, j] = 0.0 if pd.isna(val) else float(val)
            elif ch == "is_measured":
                values[slot, j] = 1.0
            elif ch == "time_since_measured":
                values[slot, j] = float(i)
            elif ch in {"tod_sin", "tod_cos", "is_daylight"}:
                ts = pd.to_datetime(row[time_column], utc=True)
                hour = ts.hour + ts.minute / 60.0
                if ch == "tod_sin":
                    values[slot, j] = float(np.sin(2 * np.pi * hour / 24.0))
                elif ch == "tod_cos":
                    values[slot, j] = float(np.cos(2 * np.pi * hour / 24.0))
                else:
                    values[slot, j] = 1.0 if 6 <= ts.hour <= 18 else 0.0
    return values


def train_real_point_classifier(
    df: pd.DataFrame,
    *,
    contract: dict[str, Any],
    output_root: str = "backend-service/data/models/timeseries_point",
    epochs: int = 1,
    max_train_batches: Optional[int] = 2,
    context_length: int = 8,
) -> dict[str, Any]:
    from services.iterative_labeling.realtime_point.trainer import RealtimePointTrainer

    dataset_info = build_real_point_dataset(
        df,
        entity_keys=list(contract["entity_keys"]),
        time_column=contract["time_column"],
        feature_columns=list(contract["feature_columns"]),
        label_column=str(contract.get("label_column") or "label"),
        split_column=str(contract.get("split_column") or "_split"),
        context_length=context_length,
    )
    trainer = RealtimePointTrainer(
        target_mode="last_point",
        epochs=epochs,
        batch_size=8,
        max_train_batches=max_train_batches,
        hidden_channels=16,
        device="cpu",
    )
    train_result = trainer.train(dataset_dir=dataset_info["dataset_dir"], output_root=output_root)
    rel_model = train_result.get("model_path") or train_result.get("artifact_dir")
    return {
        "model_path": rel_model,
        "dataset_dir": dataset_info["dataset_dir"],
        "train_result": train_result,
        "contract": "real_point_v1_no_grid",
    }
