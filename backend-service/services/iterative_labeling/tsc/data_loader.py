# @AI_GENERATED
"""
数据加载与划分 — 批量滑窗切分 + 故障过采样 + 按设备划分 train/test。

职责:
  1. 从 parquet 文件加载原始时序 + 逐点标签
  2. 遍历所有设备，调用 SlidingWindowSampler 切分
  3. 对故障时段自动使用更小 stride（窗口重叠过采样）
  4. 按设备 ID 划分 train/test（保证同设备窗口不跨集，防泄漏）

设计文档: .kiro/specs/pv-fault-timeseries-diagnosis/design.md §三
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .sliding_window_sampler import SamplerConfig, SlidingWindowSampler

logger = logging.getLogger(__name__)


def _resolve_dataset_path(dataset_path: str) -> Path:
    """Resolve a runtime dataset reference without persisting an absolute path."""
    raw = str(dataset_path or "").strip()
    if not raw:
        raise ValueError("数据集路径不能为空")
    candidate = Path(raw)
    if candidate.is_absolute():
        candidates = [candidate]
    else:
        backend_dir = Path(__file__).resolve().parents[3]
        project_root = backend_dir.parent
        candidates = [project_root / candidate, backend_dir / candidate, Path.cwd() / candidate]
    for item in candidates:
        if item.exists():
            return item.resolve()
    raise FileNotFoundError(f"数据集文件不存在: {dataset_path}")


def load_parquet_dataset(
    dataset_path: str,
    columns: Optional[List[str]] = None,
    optional_columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """加载 CSV 或 Parquet 原始时序数据，并统一返回按设备、时间排序的 DataFrame。

    函数名为兼容既有调用保留；持久化路径仍必须是项目或 backend-service 相对路径。
    """
    path = _resolve_dataset_path(dataset_path)
    if path.is_dir():
        raise ValueError(
            f"原始表格读取器不能直接读取目录 {dataset_path!r}；"
            "TSC 冻结快照请使用 load_tsc_samples"
        )

    suffix = path.suffix.lower()
    optional = set(optional_columns or [])
    requested = list(columns or [])
    if suffix in {".parquet", ".pq"}:
        import pyarrow.parquet as pq

        available = set(pq.ParquetFile(path).schema.names)
        missing_required = [name for name in requested if name not in available and name not in optional]
        if missing_required:
            raise ValueError(f"数据集缺少必需列: {missing_required}")
        selected = [name for name in requested if name in available] or None
        df = pd.read_parquet(path, columns=selected)
    elif suffix in {".csv", ".txt"}:
        available = set(pd.read_csv(path, nrows=0).columns)
        missing_required = [name for name in requested if name not in available and name not in optional]
        if missing_required:
            raise ValueError(f"数据集缺少必需列: {missing_required}")
        selected = [name for name in requested if name in available] or None
        df = pd.read_csv(path, usecols=selected)
    else:
        raise ValueError(f"TSC 原始数据仅支持 CSV/Parquet，当前后缀: {suffix or '<none>'}")

    if "time" not in df.columns:
        raise ValueError("TSC 数据集缺少必需列 time")
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    if df["time"].isna().any():
        raise ValueError(f"TSC 数据集存在 {int(df['time'].isna().sum())} 条无效 time")
    sort_cols = [name for name in ("site_id", "device_id", "branch_id", "time") if name in df.columns]
    return df.sort_values(sort_cols or ["time"]).reset_index(drop=True)


def load_frozen_tsc_snapshot(
    dataset_path: str,
    sampler_config: Optional[SamplerConfig] = None,
) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict, bool]:
    """读取 ``dataset.npz + meta.csv + manifest.json`` 不可变 TSC 快照。"""
    resolved = _resolve_dataset_path(dataset_path)
    snapshot_dir = resolved if resolved.is_dir() else resolved.parent
    npz_path = snapshot_dir / "dataset.npz" if resolved.is_dir() else resolved
    if npz_path.name != "dataset.npz" or not npz_path.is_file():
        raise ValueError(f"无效 TSC 快照路径: {dataset_path}")
    meta_path = snapshot_dir / "meta.csv"
    if not meta_path.is_file():
        raise ValueError(f"TSC 快照缺少 meta.csv: {dataset_path}")

    manifest_path = snapshot_dir / "manifest.json"
    manifest: Dict = {}
    if manifest_path.is_file():
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with np.load(npz_path, allow_pickle=False) as payload:
        if "X" not in payload or "y" not in payload:
            raise ValueError("TSC 快照 dataset.npz 缺少 X/y")
        X = np.asarray(payload["X"], dtype=np.float32)
        y = np.asarray(payload["y"], dtype=np.int64)
    meta = pd.read_csv(meta_path)
    for column in ("t_start", "t_end"):
        if column in meta.columns:
            meta[column] = pd.to_datetime(meta[column], errors="coerce")
    if len(X) != len(y) or len(meta) != len(y):
        raise ValueError(
            f"TSC 快照样本数不一致: X={len(X)}, y={len(y)}, meta={len(meta)}"
        )
    missing_meta = [name for name in ("device_id", "t_start") if name not in meta.columns]
    if missing_meta:
        raise ValueError(f"TSC 快照 meta.csv 缺少 strict 评估字段: {missing_meta}")

    sample_strategy = dict(manifest.get("sample_strategy") or {})
    expected = sampler_config or SamplerConfig()
    if sample_strategy:
        stored_length = int(sample_strategy.get("window_length") or X.shape[1])
        stored_channels = list(sample_strategy.get("channels") or [])
        if stored_length != int(expected.window_length):
            raise ValueError(
                f"TSC 快照 window_length={stored_length} 与训练配置 {expected.window_length} 不一致"
            )
        if stored_channels and stored_channels != list(expected.channels):
            raise ValueError(
                f"TSC 快照 channels={stored_channels} 与训练配置 {list(expected.channels)} 不一致"
            )

    unique, counts = np.unique(y, return_counts=True)
    stats = dict(manifest.get("load_stats") or {})
    stats.update(
        {
            "n_samples": int(len(y)),
            "n_classes": int(len(unique)),
            "class_distribution": {int(k): int(v) for k, v in zip(unique, counts)},
            "snapshot_manifest": manifest,
            "snapshot_path": str(dataset_path).replace("\\", "/"),
        }
    )
    return X, y, meta, stats, bool(manifest.get("preprocessed", True))


def load_tsc_samples(
    dataset_path: str,
    sampler_config: Optional[SamplerConfig] = None,
    fault_oversample: bool = True,
    fault_stride_divisor: int = 6,
) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict, bool]:
    """统一加载原始 CSV/Parquet 或冻结 NPZ；末项表示 X 是否已预处理。"""
    resolved = _resolve_dataset_path(dataset_path)
    if resolved.is_dir() or resolved.suffix.lower() == ".npz":
        return load_frozen_tsc_snapshot(dataset_path, sampler_config=sampler_config)
    X, y, meta, stats = load_and_split_all_devices(
        dataset_path,
        sampler_config=sampler_config,
        fault_oversample=fault_oversample,
        fault_stride_divisor=fault_stride_divisor,
    )
    return X, y, meta, stats, False


def split_labeled_dataframe(
    data: pd.DataFrame,
    sampler_config: Optional[SamplerConfig] = None,
    fault_oversample: bool = True,
    fault_stride_divisor: int = 6,
) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict]:
    """把带逐点标签的内存表切成 TSC 窗口，并保留故障过采样去重语义。

    ``data`` 至少包含 ``time``、``label`` 与配置声明的通道列；序列主键
    会按 :class:`SamplerConfig` 中实际存在的列解析。输入表只读，返回的
    ``meta.sample_id`` 可用于冻结快照去重和 strict 重复窗口隔离。
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("TSC 切窗输入必须是 pandas DataFrame")

    cfg = sampler_config or SamplerConfig()
    required_cols = ["time", "label", *cfg.channels]
    missing = [name for name in required_cols if name not in data.columns]
    if missing:
        raise ValueError(f"TSC 数据缺少必需列: {missing}")

    df = data.copy()
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    if df["time"].isna().any():
        raise ValueError(f"TSC 数据存在 {int(df['time'].isna().sum())} 条无效 time")

    sampler = SlidingWindowSampler(cfg)
    # 按完整序列主键分组，避免把同一设备的多条支路交错混成一条时序
    keys = sampler.resolve_series_keys(df)

    all_X: List[np.ndarray] = []
    all_y: List[np.ndarray] = []
    all_meta: List[pd.DataFrame] = []
    series_processed = 0
    devices_seen = set()
    seen_sample_ids: set = set()  # 增量维护，避免每轮 pd.concat 造成 O(n^2)

    fault_sampler = None
    if fault_oversample:
        fault_stride = max(1, cfg.stride // fault_stride_divisor)
        if fault_stride < cfg.stride:
            fault_cfg = replace(cfg, stride=fault_stride)
            fault_sampler = SlidingWindowSampler(fault_cfg)

    def _device_of(key_vals, grp) -> str:
        if "device_id" in keys:
            return str(key_vals[keys.index("device_id")])
        if "device_id" in grp.columns:
            return str(grp["device_id"].iloc[0])
        return "|".join(str(v) for v in key_vals)

    def _accept(X_new, y_new, meta_new, series_id: str, device_id: str) -> None:
        """去重后累积；同时补齐 series_id / device_id 列。"""
        mask = ~meta_new["sample_id"].isin(seen_sample_ids)
        if not mask.any():
            return
        m = meta_new[mask].copy()
        m["series_id"] = series_id
        m["device_id"] = device_id
        seen_sample_ids.update(m["sample_id"].tolist())
        all_X.append(X_new[mask.values])
        all_y.append(y_new[mask.values])
        all_meta.append(m.reset_index(drop=True))

    for key_vals, grp in df.groupby(keys, sort=False):
        if not isinstance(key_vals, tuple):
            key_vals = (key_vals,)
        series_id = "|".join(str(v) for v in key_vals)
        device_id = _device_of(key_vals, grp)

        grp_sorted = grp.sort_values("time").reset_index(drop=True)
        if len(grp_sorted) < cfg.window_length:
            continue

        series_processed += 1
        devices_seen.add(device_id)
        point_labels = grp_sorted[["time", "label"]]

        X, y, meta = sampler.transform(grp_sorted, point_labels, device_id=series_id)
        if len(X) > 0:
            _accept(X, y, meta, series_id, device_id)

        # 故障过采样：仅对含故障标签的序列，用更小 stride 补切故障窗口
        if fault_sampler is not None and (grp_sorted["label"] != cfg.normal_label).any():
            X_f, y_f, meta_f = fault_sampler.transform(
                grp_sorted, point_labels, device_id=series_id
            )
            if len(y_f) > 0:
                fault_mask = y_f != cfg.normal_label
                if fault_mask.any():
                    _accept(
                        X_f[fault_mask], y_f[fault_mask],
                        meta_f[fault_mask].reset_index(drop=True),
                        series_id, device_id,
                    )

    if not all_X:
        n_ch = len(cfg.channels)
        return (
            np.empty((0, cfg.window_length, n_ch), dtype=np.float32),
            np.empty(0, dtype=np.int64),
            pd.DataFrame(columns=[
                "sample_id", "t_start", "t_end", "purity",
                "device_id", "series_id", "label_strategy",
            ]),
            {"n_samples": 0, "series_processed": 0, "devices_processed": 0},
        )

    X = np.concatenate(all_X, axis=0)
    y = np.concatenate(all_y, axis=0)
    meta = pd.concat(all_meta, ignore_index=True)

    # 统计
    unique, counts = np.unique(y, return_counts=True)
    class_dist = {int(k): int(v) for k, v in zip(unique, counts)}
    stats = {
        "n_samples": len(y),
        "n_classes": len(unique),
        "class_distribution": class_dist,
        "series_processed": series_processed,
        "devices_processed": len(devices_seen),
        "series_keys": keys,
        "window_length": cfg.window_length,
        "stride": cfg.stride,
        "fault_oversample": fault_oversample,
    }

    logger.info(
        "数据加载完成: %d 样本, %d 类, %d 条序列 (%d 设备), 序列主键=%s",
        stats["n_samples"], stats["n_classes"], stats["series_processed"],
        stats["devices_processed"], keys,
    )

    return X, y, meta, stats


def load_and_split_all_devices(
    dataset_path: str,
    sampler_config: Optional[SamplerConfig] = None,
    fault_oversample: bool = True,
    fault_stride_divisor: int = 6,
) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict]:
    """加载相对路径数据并委托内存切窗入口，保持历史调用兼容。"""
    cfg = sampler_config or SamplerConfig()
    key_cols = list(cfg.series_keys)
    required_cols = list(dict.fromkeys(["time", "label", *key_cols, *cfg.channels]))
    frame = load_parquet_dataset(
        dataset_path,
        columns=required_cols,
        optional_columns=key_cols,
    )
    return split_labeled_dataframe(
        frame,
        sampler_config=cfg,
        fault_oversample=fault_oversample,
        fault_stride_divisor=fault_stride_divisor,
    )


def split_by_device(
    X: np.ndarray,
    y: np.ndarray,
    meta: pd.DataFrame,
    test_ratio: float = 0.2,
    random_state: int = 90,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, pd.DataFrame, pd.DataFrame]:
    """
    按设备 ID 划分 train/test（同设备窗口不跨集，防泄漏）。

    Parameters
    ----------
    X : ndarray [n_samples, window_length, n_channels]
    y : ndarray [n_samples]
    meta : DataFrame with 'device_id' column
    test_ratio : float
        测试集设备比例。
    random_state : int
        随机种子（与 RF 路线保持一致）。

    Returns
    -------
    X_train, y_train, X_test, y_test, meta_train, meta_test
    """
    groups = meta["device_id"].values

    splitter = GroupShuffleSplit(n_splits=1, test_size=test_ratio, random_state=random_state)
    train_idx, test_idx = next(splitter.split(X, y, groups=groups))

    X_train = X[train_idx]
    y_train = y[train_idx]
    X_test = X[test_idx]
    y_test = y[test_idx]
    meta_train = meta.iloc[train_idx].reset_index(drop=True)
    meta_test = meta.iloc[test_idx].reset_index(drop=True)

    # 验证：测试集设备不出现在训练集中
    train_devices = set(meta_train["device_id"].unique())
    test_devices = set(meta_test["device_id"].unique())
    leaked = train_devices & test_devices
    if leaked:
        logger.error("数据泄漏！%d 设备同时出现在 train 和 test: %s", len(leaked), list(leaked)[:5])
        raise RuntimeError(f"数据泄漏：{len(leaked)} 设备跨集")

    logger.info(
        "划分完成: train=%d 样本(%d 设备), test=%d 样本(%d 设备)",
        len(y_train), len(train_devices), len(y_test), len(test_devices),
    )

    return X_train, y_train, X_test, y_test, meta_train, meta_test


def preprocess_X(
    X: np.ndarray,
    method: str = "per_sample_zscore",
) -> np.ndarray:
    """
    对样本矩阵做归一化预处理。

    Parameters
    ----------
    X : ndarray [n_samples, window_length, n_channels]
    method : str
        'per_sample_zscore' — 每个样本独立 z-score 归一化
        'per_sample_minmax' — 每个样本独立 min-max 归一化到 [0, 1]
        'none' — 不做归一化

    Returns
    -------
    X_preprocessed : ndarray，同形状，NaN 已填充。
    """
    X = X.copy()

    # 先填充 NaN（线性插值在时序维度上）
    for i in range(X.shape[0]):
        for ch in range(X.shape[2]):
            series = X[i, :, ch]
            nans = np.isnan(series)
            if nans.any():
                if nans.all():
                    X[i, :, ch] = 0.0
                else:
                    # 线性插值
                    valid_idx = np.where(~nans)[0]
                    X[i, :, ch] = np.interp(
                        np.arange(len(series)), valid_idx, series[valid_idx]
                    )

    if method == "none":
        return X

    if method == "per_sample_zscore":
        for i in range(X.shape[0]):
            mean = X[i].mean()
            std = X[i].std()
            if std > 1e-8:
                X[i] = (X[i] - mean) / std
            else:
                X[i] = 0.0
        return X

    if method == "per_sample_minmax":
        for i in range(X.shape[0]):
            vmin = X[i].min()
            vmax = X[i].max()
            rng = vmax - vmin
            if rng > 1e-8:
                X[i] = (X[i] - vmin) / rng
            else:
                X[i] = 0.0
        return X

    logger.warning("未知预处理方法 %s，不做归一化", method)
    return X
# @AI_GENERATED: end
