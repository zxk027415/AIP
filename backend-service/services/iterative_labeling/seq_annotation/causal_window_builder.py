# @AI_GENERATED
# -*- coding: utf-8 -*-
"""实时点路径 Phase 0 因果窗口数据集构建器。

窗口可以跨午夜但不能跨长缺口；所有填充只读取当前或过去。衍生数据集写入独立、
版本化目录，不修改已发布的原始 POC 快照。
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from services.iterative_labeling.point_label_service import POINT_PATH_LABEL_SOURCES

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _BACKEND.parent
_DEFAULT_DATASET_ROOT = _BACKEND / "data" / "realtime_point_poc" / "datasets"

DEFAULT_WINDOW_SIZE = 72
DEFAULT_STRIDE = 6
DEFAULT_SLOT_MINUTES = 5
DEFAULT_MIN_MEASURED_RATIO = 0.6
DEFAULT_MAX_FORWARD_FILL = 2
DEFAULT_MAX_GAP_MULTIPLIER = 6
IGNORE_LABEL = -1
PHASE0_POINT_SOURCES = frozenset(POINT_PATH_LABEL_SOURCES)
_DEVICE_COLUMNS = ["site_id", "device_id", "branch_id"]
CHANNELS = [
    "value",
    "i_cal",
    "is_measured",
    "time_since_measured",
    "tod_sin",
    "tod_cos",
    "is_daylight",
]
DAYLIGHT_START_HOUR = 6
DAYLIGHT_END_HOUR = 19


def _normalise_relative_arg(path: str, param_name: str) -> str:
    if not path or Path(path).is_absolute() or os.path.isabs(path):
        raise ValueError(f"参数 {param_name} 必须是项目根相对路径: {path!r}")
    normalised = Path(path.replace("\\", "/")).as_posix()
    resolved = (_PROJECT_ROOT / normalised).resolve()
    try:
        resolved.relative_to(_PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"参数 {param_name} 越界项目根: {path}") from exc
    return normalised


def _resolve_relative(path: str, param_name: str) -> Path:
    return (_PROJECT_ROOT / _normalise_relative_arg(path, param_name)).resolve()


def _to_project_relative(path: Path) -> str:
    return path.resolve().relative_to(_PROJECT_ROOT.resolve()).as_posix()


def _file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_parameters(
    *,
    window_size: int,
    stride: int,
    slot_minutes: int,
    min_measured_ratio: float,
    max_forward_fill_slots: int,
    max_gap_multiplier: int,
) -> None:
    if window_size <= 0:
        raise ValueError("window_size 必须大于 0")
    if stride <= 0:
        raise ValueError("stride 必须大于 0")
    if slot_minutes <= 0 or 1440 % slot_minutes != 0:
        raise ValueError("slot_minutes 必须为可整除 1440 的正整数")
    if not 0.0 <= min_measured_ratio <= 1.0:
        raise ValueError("min_measured_ratio 必须位于 [0, 1]")
    if max_forward_fill_slots < 0:
        raise ValueError("max_forward_fill_slots 不能小于 0")
    if max_gap_multiplier <= 0:
        raise ValueError("max_gap_multiplier 必须大于 0")


def _verify_snapshot(snapshot_path: Path) -> Dict[str, Any]:
    """重算快照 artifact digest，防止从损坏或被修改的介质构建。"""
    manifest_path = snapshot_path / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"快照缺少 manifest.json: {_to_project_relative(snapshot_path)}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "point-poc-snapshot-v1":
        raise ValueError(f"不支持的快照 schema_version: {manifest.get('schema_version')}")

    artifacts = manifest.get("artifacts") or {}
    required = {"index.parquet", "measurements.parquet", "point_labels.parquet", "label_ops.parquet"}
    if set(artifacts) != required:
        raise ValueError(f"快照 artifacts 不完整，期望 {sorted(required)}，实际 {sorted(artifacts)}")
    for filename, record in artifacts.items():
        artifact_path = _resolve_relative(str(record["path"]), f"artifacts.{filename}.path")
        expected_parent = snapshot_path.resolve()
        if artifact_path.parent != expected_parent:
            raise ValueError(f"artifact 不在快照目录内: {record['path']}")
        actual = _file_sha256(artifact_path)
        if actual != record.get("sha256"):
            raise RuntimeError(f"快照 artifact digest 不匹配: {filename}")
    return manifest


def _deterministic_device_split(
    index_df: pd.DataFrame,
    *,
    seed: int,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
) -> pd.DataFrame:
    """按设备三元组确定性划分，保证同一设备不会跨 train/val/test。"""
    devices = index_df[_DEVICE_COLUMNS].drop_duplicates().copy()
    if len(devices) < 3:
        raise ValueError("至少需要 3 台独立设备才能划分 train/val/test")
    devices["_score"] = devices.apply(
        lambda row: hashlib.sha256(
            f"{row['site_id']}|{row['device_id']}|{row['branch_id']}|{seed}".encode("utf-8")
        ).hexdigest(),
        axis=1,
    )
    devices = devices.sort_values("_score").reset_index(drop=True)
    n_devices = len(devices)
    n_train = max(1, int(n_devices * train_ratio))
    n_val = max(1, int(n_devices * val_ratio))
    if n_train + n_val >= n_devices:
        n_train = n_devices - 2
        n_val = 1
    devices["split"] = "test"
    devices.loc[: n_train - 1, "split"] = "train"
    devices.loc[n_train : n_train + n_val - 1, "split"] = "val"

    result = index_df.merge(devices[_DEVICE_COLUMNS + ["split"]], on=_DEVICE_COLUMNS, how="left", validate="many_to_one")
    split_sets = {
        split: set(map(tuple, group[_DEVICE_COLUMNS].drop_duplicates().to_numpy()))
        for split, group in result.groupby("split")
    }
    for left, right in [("train", "val"), ("train", "test"), ("val", "test")]:
        overlap = split_sets.get(left, set()) & split_sets.get(right, set())
        if overlap:
            raise AssertionError(f"设备 split 泄漏: {left}/{right} 重叠 {len(overlap)} 台")
    if set(split_sets) != {"train", "val", "test"}:
        raise ValueError(f"split 不完整: {sorted(split_sets)}")
    return result


def _time_grid(start: pd.Timestamp, end: pd.Timestamp, slot_minutes: int) -> pd.DatetimeIndex:
    return pd.date_range(start=start, end=end - pd.Timedelta(minutes=slot_minutes), freq=f"{slot_minutes}min")


def _align_causal_grid(
    measurements: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    slot_minutes: int,
    max_forward_fill_slots: int,
) -> pd.DataFrame:
    """在连续区间上做 past-only 对齐；绝不使用未来锚点。"""
    grid = pd.DataFrame({"time": _time_grid(start, end, slot_minutes)})
    values = measurements[["time", "value", "i_cal"]].copy()
    values = values.sort_values("time").drop_duplicates("time", keep="last")
    aligned = grid.merge(values, on="time", how="left", validate="one_to_one")
    aligned["is_measured"] = (
        aligned["value"].notna() & aligned["i_cal"].notna()
    ).astype(np.float32)

    for column in ["value", "i_cal"]:
        if max_forward_fill_slots:
            aligned[column] = aligned[column].ffill(limit=max_forward_fill_slots)
        aligned[column] = aligned[column].fillna(0.0).astype(np.float32)

    time_since = np.empty(len(aligned), dtype=np.float32)
    last_measured = -1
    for position, measured in enumerate(aligned["is_measured"].to_numpy()):
        if measured > 0.5:
            last_measured = position
            time_since[position] = 0.0
        else:
            time_since[position] = float(position + 1 if last_measured < 0 else position - last_measured)
    aligned["time_since_measured"] = time_since

    minute_of_day = aligned["time"].dt.hour * 60 + aligned["time"].dt.minute
    aligned["tod_sin"] = np.sin(2.0 * math.pi * minute_of_day / 1440.0).astype(np.float32)
    aligned["tod_cos"] = np.cos(2.0 * math.pi * minute_of_day / 1440.0).astype(np.float32)
    aligned["is_daylight"] = (
        (aligned["time"].dt.hour >= DAYLIGHT_START_HOUR)
        & (aligned["time"].dt.hour < DAYLIGHT_END_HOUR)
    ).astype(np.float32)
    return aligned


def _longest_missing_run(is_measured: np.ndarray) -> int:
    longest = 0
    current = 0
    for measured in is_measured:
        if measured > 0.5:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def _label_map(labels: Optional[pd.DataFrame]) -> Dict[pd.Timestamp, int]:
    if labels is None or labels.empty:
        return {}
    unexpected = sorted(set(labels["source"].astype(str)) - PHASE0_POINT_SOURCES)
    if unexpected:
        raise ValueError(f"点路径标签快照包含未准入来源: {unexpected}")
    return {
        pd.Timestamp(row.time): int(row.label_id)
        for row in labels.itertuples(index=False)
        if row.label_id is not None and not pd.isna(row.label_id)
    }


def _extract_target_windows(
    aligned: pd.DataFrame,
    *,
    labels: Optional[pd.DataFrame],
    target_start: pd.Timestamp,
    target_end: pd.Timestamp,
    window_size: int,
    stride: int,
    slot_minutes: int,
    min_measured_ratio: float,
    max_gap_multiplier: int,
    require_label: bool,
) -> Tuple[List[np.ndarray], List[np.ndarray], List[Dict[str, Any]]]:
    labels_by_time = _label_map(labels)
    windows: List[np.ndarray] = []
    targets: List[np.ndarray] = []
    metadata: List[Dict[str, Any]] = []
    target_times = _time_grid(target_start, target_end, slot_minutes)
    aligned_start = pd.Timestamp(aligned.iloc[0]["time"])
    slot_delta = pd.Timedelta(minutes=slot_minutes)

    for target_position in range(0, len(target_times), stride):
        target_time = target_times[target_position]
        end_position = int((target_time - aligned_start) / slot_delta) + 1
        start_position = end_position - window_size
        if start_position < 0 or end_position > len(aligned):
            continue
        chunk = aligned.iloc[start_position:end_position]
        if len(chunk) != window_size or pd.Timestamp(chunk.iloc[-1]["time"]) != target_time:
            raise AssertionError("窗口时标与目标时刻不一致")

        measured = chunk["is_measured"].to_numpy(dtype=np.float32)
        measured_ratio = float(measured.mean())
        longest_gap = _longest_missing_run(measured)
        if measured_ratio < min_measured_ratio or longest_gap > max_gap_multiplier:
            continue

        x = chunk[CHANNELS].to_numpy(dtype=np.float32)
        y = np.full(window_size, IGNORE_LABEL, dtype=np.int16)
        for offset, timestamp in enumerate(chunk["time"]):
            label = labels_by_time.get(pd.Timestamp(timestamp))
            if label is not None:
                y[offset] = label
        if require_label and not np.any(y != IGNORE_LABEL):
            continue

        windows.append(x)
        targets.append(y)
        metadata.append(
            {
                "start_time": pd.Timestamp(chunk.iloc[0]["time"]),
                "target_time": target_time,
                "measured_ratio": measured_ratio,
                "longest_missing_run": int(longest_gap),
                "labeled_points": int(np.sum(y != IGNORE_LABEL)),
                "target_label": int(y[-1]),
            }
        )
    return windows, targets, metadata


def _cross_midnight_contract_audit(
    *,
    window_size: int,
    slot_minutes: int,
    max_forward_fill_slots: int,
    max_gap_multiplier: int,
) -> bool:
    """用确定性合成序列断言 00:00 目标确实读取前一日已发生上下文。"""
    target_start = pd.Timestamp("2026-01-02 00:00:00")
    interval_start = target_start - pd.Timedelta(minutes=(window_size - 1) * slot_minutes)
    interval_end = target_start + pd.Timedelta(minutes=slot_minutes)
    times = _time_grid(interval_start, interval_end, slot_minutes)
    synthetic = pd.DataFrame(
        {
            "time": times,
            "value": np.arange(len(times), dtype=np.float32),
            "i_cal": np.arange(len(times), dtype=np.float32) * 0.1,
        }
    )
    aligned = _align_causal_grid(
        synthetic,
        start=interval_start,
        end=interval_end,
        slot_minutes=slot_minutes,
        max_forward_fill_slots=max_forward_fill_slots,
    )
    labels = pd.DataFrame(
        {"time": [target_start], "label_id": [1], "source": ["human_range"]}
    )
    windows, _, metadata = _extract_target_windows(
        aligned,
        labels=labels,
        target_start=target_start,
        target_end=interval_end,
        window_size=window_size,
        stride=1,
        slot_minutes=slot_minutes,
        min_measured_ratio=1.0,
        max_gap_multiplier=max_gap_multiplier,
        require_label=True,
    )
    passed = (
        len(windows) == 1
        and len(metadata) == 1
        and pd.Timestamp(metadata[0]["start_time"]).date() < target_start.date()
        and pd.Timestamp(metadata[0]["target_time"]) == target_start
    )
    if not passed:
        raise RuntimeError("跨午夜窗口契约审计失败")
    return True


def _causal_audit(
    *,
    measurements_df: pd.DataFrame,
    index_df: pd.DataFrame,
    window_size: int,
    stride: int,
    slot_minutes: int,
    min_measured_ratio: float,
    max_forward_fill_slots: int,
    max_gap_multiplier: int,
    requested_samples: int = 8,
) -> Dict[str, Any]:
    """修改目标时刻之后的测量，断言此前实际窗口全部通道完全不变。"""
    passed = 0
    tested = 0
    candidates = index_df.sort_values([*_DEVICE_COLUMNS, "target_start"]).head(requested_samples * 3)
    for row in candidates.itertuples(index=False):
        if tested >= requested_samples:
            break
        start = pd.Timestamp(row.target_start) - pd.Timedelta(minutes=(window_size - 1) * slot_minutes)
        end = pd.Timestamp(row.target_end)
        mask = (
            (measurements_df["site_id"] == row.site_id)
            & (measurements_df["device_id"] == row.device_id)
            & (measurements_df["branch_id"] == row.branch_id)
            & (measurements_df["time"] >= start)
            & (measurements_df["time"] < end)
        )
        device_rows = measurements_df.loc[mask].copy()
        cutoff = pd.Timestamp(row.target_start) + pd.Timedelta(hours=12)
        future_mask = device_rows["time"] > cutoff
        if device_rows.empty or not future_mask.any():
            continue

        mutated = device_rows.copy()
        mutated.loc[future_mask, "value"] = mutated.loc[future_mask, "value"].fillna(0.0) + 1_000_000.0
        mutated.loc[future_mask, "i_cal"] = mutated.loc[future_mask, "i_cal"].fillna(0.0) - 1_000_000.0
        full = _align_causal_grid(
            device_rows,
            start=start,
            end=end,
            slot_minutes=slot_minutes,
            max_forward_fill_slots=max_forward_fill_slots,
        )
        changed = _align_causal_grid(
            mutated,
            start=start,
            end=end,
            slot_minutes=slot_minutes,
            max_forward_fill_slots=max_forward_fill_slots,
        )
        audit_end = cutoff + pd.Timedelta(minutes=slot_minutes)
        full_windows, _, full_meta = _extract_target_windows(
            full,
            labels=None,
            target_start=pd.Timestamp(row.target_start),
            target_end=audit_end,
            window_size=window_size,
            stride=stride,
            slot_minutes=slot_minutes,
            min_measured_ratio=min_measured_ratio,
            max_gap_multiplier=max_gap_multiplier,
            require_label=False,
        )
        changed_windows, _, changed_meta = _extract_target_windows(
            changed,
            labels=None,
            target_start=pd.Timestamp(row.target_start),
            target_end=audit_end,
            window_size=window_size,
            stride=stride,
            slot_minutes=slot_minutes,
            min_measured_ratio=min_measured_ratio,
            max_gap_multiplier=max_gap_multiplier,
            require_label=False,
        )
        tested += 1
        same_meta = [m["target_time"] for m in full_meta] == [m["target_time"] for m in changed_meta]
        same_values = len(full_windows) == len(changed_windows) and all(
            np.array_equal(left, right) for left, right in zip(full_windows, changed_windows)
        )
        if full_windows and same_meta and same_values:
            passed += 1

    if tested == 0 or passed != tested:
        raise RuntimeError(f"数据层因果审计失败或无有效样本: passed={passed}, tested={tested}")
    cross_midnight_passed = _cross_midnight_contract_audit(
        window_size=window_size,
        slot_minutes=slot_minutes,
        max_forward_fill_slots=max_forward_fill_slots,
        max_gap_multiplier=max_gap_multiplier,
    )
    return {
        "scope": "preprocessing_windows_all_channels",
        "tested_device_days": tested,
        "passed_device_days": passed,
        "all_passed": True,
        "cross_midnight_contract_passed": cross_midnight_passed,
    }


def _artifact_records(temp_dir: Path, final_dir: Path, filenames: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    return {
        filename: {
            "path": _to_project_relative(final_dir / filename),
            "sha256": _file_sha256(temp_dir / filename),
            "bytes": int((temp_dir / filename).stat().st_size),
        }
        for filename in filenames
    }


def build_causal_windows(
    *,
    snapshot_dir: str,
    output_root: Optional[str] = None,
    window_size: int = DEFAULT_WINDOW_SIZE,
    stride: int = DEFAULT_STRIDE,
    slot_minutes: int = DEFAULT_SLOT_MINUTES,
    min_measured_ratio: float = DEFAULT_MIN_MEASURED_RATIO,
    max_forward_fill_slots: int = DEFAULT_MAX_FORWARD_FILL,
    max_gap_multiplier: int = DEFAULT_MAX_GAP_MULTIPLIER,
    seed: int = 42,
) -> Dict[str, Any]:
    """从不可变快照构建版本化、设备隔离、跨午夜的因果窗口数据集。"""
    _validate_parameters(
        window_size=window_size,
        stride=stride,
        slot_minutes=slot_minutes,
        min_measured_ratio=min_measured_ratio,
        max_forward_fill_slots=max_forward_fill_slots,
        max_gap_multiplier=max_gap_multiplier,
    )
    snapshot_dir = _normalise_relative_arg(snapshot_dir, "snapshot_dir")
    if output_root is not None:
        output_root = _normalise_relative_arg(output_root, "output_root")
    snapshot_path = _resolve_relative(snapshot_dir, "snapshot_dir")
    if not snapshot_path.is_dir():
        raise FileNotFoundError(f"快照目录不存在: {snapshot_dir}")
    manifest = _verify_snapshot(snapshot_path)
    if int(manifest["context_length"]) < window_size:
        raise ValueError(
            f"快照只固化 {manifest['context_length']} 槽上下文，不能构建 W={window_size} 窗口"
        )
    if int(manifest["slot_minutes"]) != slot_minutes:
        raise ValueError("窗口 slot_minutes 与快照契约不一致")

    index_df = pd.read_parquet(snapshot_path / "index.parquet")
    measurements_df = pd.read_parquet(snapshot_path / "measurements.parquet")
    labels_df = pd.read_parquet(snapshot_path / "point_labels.parquet")
    for frame in [index_df, measurements_df, labels_df]:
        for column in _DEVICE_COLUMNS:
            frame[column] = frame[column].astype(str)
    for column in ["date", "target_start", "target_end", "context_start"]:
        index_df[column] = pd.to_datetime(index_df[column])
    measurements_df["time"] = pd.to_datetime(measurements_df["time"])
    if not labels_df.empty:
        labels_df["time"] = pd.to_datetime(labels_df["time"])
        unexpected_sources = sorted(set(labels_df["source"].astype(str)) - PHASE0_POINT_SOURCES)
        if unexpected_sources:
            raise ValueError(f"快照包含未准入点标签来源: {unexpected_sources}")

    split_index = _deterministic_device_split(index_df, seed=seed)
    all_x: List[np.ndarray] = []
    all_y: List[np.ndarray] = []
    all_meta: List[Dict[str, Any]] = []
    rejected_device_days = 0

    for row in split_index.itertuples(index=False):
        target_start = pd.Timestamp(row.target_start)
        target_end = pd.Timestamp(row.target_end)
        interval_start = target_start - pd.Timedelta(minutes=(window_size - 1) * slot_minutes)
        measurement_mask = (
            (measurements_df["site_id"] == row.site_id)
            & (measurements_df["device_id"] == row.device_id)
            & (measurements_df["branch_id"] == row.branch_id)
            & (measurements_df["time"] >= interval_start)
            & (measurements_df["time"] < target_end)
        )
        device_rows = measurements_df.loc[measurement_mask]
        if device_rows.empty:
            rejected_device_days += 1
            continue
        aligned = _align_causal_grid(
            device_rows,
            start=interval_start,
            end=target_end,
            slot_minutes=slot_minutes,
            max_forward_fill_slots=max_forward_fill_slots,
        )
        if labels_df.empty:
            day_labels: Optional[pd.DataFrame] = None
        else:
            label_mask = (
                (labels_df["site_id"] == row.site_id)
                & (labels_df["device_id"] == row.device_id)
                & (labels_df["branch_id"] == row.branch_id)
                & (labels_df["time"] >= target_start)
                & (labels_df["time"] < target_end)
            )
            day_labels = labels_df.loc[label_mask]

        windows, targets, metadata = _extract_target_windows(
            aligned,
            labels=day_labels,
            target_start=target_start,
            target_end=target_end,
            window_size=window_size,
            stride=stride,
            slot_minutes=slot_minutes,
            min_measured_ratio=min_measured_ratio,
            max_gap_multiplier=max_gap_multiplier,
            require_label=True,
        )
        if not windows:
            rejected_device_days += 1
            continue
        for x, y, meta in zip(windows, targets, metadata):
            meta.update(
                {
                    "index_id": row.index_id,
                    "site_id": row.site_id,
                    "device_id": row.device_id,
                    "branch_id": row.branch_id,
                    "date": pd.Timestamp(row.date).date().isoformat(),
                    "split": row.split,
                }
            )
            all_x.append(x)
            all_y.append(y)
            all_meta.append(meta)

    if not all_x:
        raise ValueError("因果门控和逐点标签过滤后没有可训练窗口")
    x_array = np.stack(all_x).astype(np.float32)
    y_array = np.stack(all_y).astype(np.int16)
    meta_df = pd.DataFrame(all_meta)
    if x_array.shape[:2] != y_array.shape or x_array.shape[2] != len(CHANNELS):
        raise AssertionError(f"窗口张量契约错误: X={x_array.shape}, Y={y_array.shape}")

    audit = _causal_audit(
        measurements_df=measurements_df,
        index_df=split_index,
        window_size=window_size,
        stride=stride,
        slot_minutes=slot_minutes,
        min_measured_ratio=min_measured_ratio,
        max_forward_fill_slots=max_forward_fill_slots,
        max_gap_multiplier=max_gap_multiplier,
    )

    dataset_root = _resolve_relative(output_root, "output_root") if output_root else _DEFAULT_DATASET_ROOT
    dataset_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"point-w{window_size}-tmp-", dir=str(dataset_root)))
    try:
        npz_name = f"windows_w{window_size}.npz"
        meta_name = f"window_meta_w{window_size}.parquet"
        split_name = "split_manifest.parquet"
        np.savez_compressed(temp_dir / npz_name, X=x_array, Y=y_array, channels=np.asarray(CHANNELS))
        meta_df.to_parquet(temp_dir / meta_name, index=False)
        split_index.to_parquet(temp_dir / split_name, index=False)

        pre_artifact_hashes = {
            name: _file_sha256(temp_dir / name) for name in [npz_name, meta_name, split_name]
        }
        content_digest = hashlib.sha256(
            json.dumps(
                {
                    "snapshot": manifest["snapshot_version"],
                    "window_size": window_size,
                    "stride": stride,
                    "slot_minutes": slot_minutes,
                    "min_measured_ratio": min_measured_ratio,
                    "max_forward_fill_slots": max_forward_fill_slots,
                    "max_gap_multiplier": max_gap_multiplier,
                    "seed": seed,
                    "artifacts": pre_artifact_hashes,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        dataset_version = f"point-w{window_size}-{timestamp}-{content_digest[:8]}"
        final_dir = dataset_root / dataset_version
        if final_dir.exists():
            raise FileExistsError(f"衍生数据集已存在，拒绝覆盖: {_to_project_relative(final_dir)}")

        artifact_records = _artifact_records(
            temp_dir,
            final_dir,
            [npz_name, meta_name, split_name],
        )
        split_counts = {key: int(value) for key, value in meta_df["split"].value_counts().to_dict().items()}
        cross_midnight_windows = int(
            (
                pd.to_datetime(meta_df["start_time"]).dt.date
                < pd.to_datetime(meta_df["target_time"]).dt.date
            ).sum()
        )
        device_split_counts = {
            key: int(value)
            for key, value in split_index.drop_duplicates(_DEVICE_COLUMNS)["split"].value_counts().to_dict().items()
        }
        report = {
            "dataset_version": dataset_version,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "source_snapshot": snapshot_dir,
            "source_snapshot_version": manifest["snapshot_version"],
            "window_size": int(window_size),
            "stride": int(stride),
            "slot_minutes": int(slot_minutes),
            "min_measured_ratio": float(min_measured_ratio),
            "max_forward_fill_slots": int(max_forward_fill_slots),
            "max_gap_multiplier": int(max_gap_multiplier),
            "missing_value_policy": {
                "mode": "past_only_forward_fill_then_zero",
                "max_forward_fill_slots": int(max_forward_fill_slots),
                "remaining_fill_value": 0.0,
                "measurement_mask_channel": "is_measured",
                "time_since_channel": "time_since_measured",
                "uses_future_values": False,
            },
            "seed": int(seed),
            "channels": CHANNELS,
            "ignore_label": IGNORE_LABEL,
            "window_count": int(len(meta_df)),
            "labeled_point_count": int(np.sum(y_array != IGNORE_LABEL)),
            "split_counts": split_counts,
            "device_split_counts": device_split_counts,
            "rejected_device_days": int(rejected_device_days),
            "cross_midnight_supervised_windows": cross_midnight_windows,
            "causal_audit": audit,
            "artifacts": artifact_records,
        }
        (temp_dir / "build_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temp_dir.rename(final_dir)
    except BaseException:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    relative_dir = _to_project_relative(final_dir)
    logger.info("点路径因果窗口数据集已发布: %s", relative_dir)
    return {
        "dataset_dir": relative_dir,
        "output_file": f"{relative_dir}/{npz_name}",
        "window_count": int(len(meta_df)),
        "split_counts": split_counts,
        "build_report": report,
    }
# @AI_GENERATED: end
