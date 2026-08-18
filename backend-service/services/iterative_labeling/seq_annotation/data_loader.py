# @AI_GENERATED
"""
序列标注数据加载器 — 从 parquet + point_labels 批量构建逐点标签训练集。

输出格式：
  X: ndarray [N, seq_len, n_channels]   —— N 个设备-天，每个 seq_len 点 × 通道数
  Y: ndarray [N, seq_len]               —— 每个点的标签（0=正常, 其余=故障类型）
  meta: DataFrame                       —— 每条序列的 site_id/device_id/branch_id/date

数据来源两部分：
  1. segment_boundary：有段边界的设备-天（同天内有 label=0 和 label≠0 的切换）
  2. whole_day_fault：整天故障的设备-天（补充各类故障的信号特征）
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

logger = logging.getLogger(__name__)

DAYLIGHT_START_HOUR = 7
DAYLIGHT_END_HOUR = 17
MIN_POINTS = 60

_PARQUET = Path(__file__).resolve().parents[3] / "datasets" / "pv_cumulative_labeled_merged.parquet"


def load_seq_annotation_dataset(
    min_points: int = MIN_POINTS,
    daylight_only: bool = True,
    pad_to: Optional[int] = None,
    include_whole_day_fault: bool = True,
    max_whole_day_per_label: int = 300,
) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict]:
    """
    批量加载序列标注数据集（快速路径：parquet + 一次性 SQL）。

    Parameters
    ----------
    include_whole_day_fault : bool
        是否加载"整天故障"天（Y 全填该 label）。
    max_whole_day_per_label : int
        每个 label 最多取多少个整天故障天。
    """
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from sqlalchemy import text

    adapter = DBAdapter(DBConfig())

    # ---- 批量读 point_labels ----
    logger.info("批量读 point_labels...")
    with adapter.get_sync_session() as s:
        boundary_rows = s.execute(text("""
            SELECT site_id, device_id, branch_id, DATE(time) as d
            FROM point_labels WHERE source = 'cluster'
            GROUP BY site_id, device_id, branch_id, DATE(time)
            HAVING SUM(label_id = 0) > 0 AND SUM(label_id != 0) > 0
        """)).fetchall()

        all_labels_rows = s.execute(text("""
            SELECT site_id, device_id, branch_id, time, label_id
            FROM point_labels WHERE label_id IS NOT NULL
        """)).fetchall()

    target_keys = set((r[0], r[1], str(r[2]), r[3]) for r in boundary_rows)
    logger.info("有段边界的设备-天: %d", len(target_keys))

    labels_df = pd.DataFrame(all_labels_rows, columns=["site_id", "device_id", "branch_id", "time", "label_id"])
    labels_df["time"] = pd.to_datetime(labels_df["time"])
    labels_df["branch_id"] = labels_df["branch_id"].astype(str)

    # ---- 批量读测量值（从 parquet，秒级） ----
    logger.info("读 parquet: %s", _PARQUET.name)
    raw_df = pd.read_parquet(_PARQUET, columns=["site_id", "device_id", "branch_id", "time", "value", "i_cal", "label"])
    raw_df["time"] = pd.to_datetime(raw_df["time"])
    raw_df["branch_id"] = raw_df["branch_id"].astype(str)

    # ---- 处理有段边界的设备-天 ----
    all_X: List[np.ndarray] = []
    all_Y: List[np.ndarray] = []
    all_meta: List[dict] = []
    skipped = 0

    for site_id, device_id, branch_id, date in target_keys:
        x, y, ok = _load_one_device_day(
            raw_df, labels_df, site_id, device_id, branch_id, date,
            daylight_only, min_points, use_point_labels=True,
        )
        if not ok:
            skipped += 1
            continue
        all_X.append(x)
        all_Y.append(y)
        all_meta.append({
            "site_id": site_id, "device_id": device_id, "branch_id": branch_id,
            "date": str(date), "n_points": len(y),
            "n_fault_points": int((y != 0).sum()),
            "fault_ratio": float((y != 0).mean()),
            "data_type": "segment_boundary",
        })

    logger.info("段边界数据: %d 条, 跳过 %d", len(all_X), skipped)

    # ---- 加载整天故障 ----
    n_whole = 0
    if include_whole_day_fault:
        logger.info("加载整天故障天...")
        # 找天级标签≠0 且整天标签一致的设备-天（用 raw_df 的 label 列——天级广播）
        day_grp = raw_df.groupby(["site_id", "device_id", "branch_id", raw_df["time"].dt.date])
        day_labels = day_grp["label"].agg(["min", "max", "count"]).reset_index()
        day_labels.columns = ["site_id", "device_id", "branch_id", "date", "lmin", "lmax", "cnt"]
        # 整天同一故障标签且非正常
        whole_day = day_labels[(day_labels["lmin"] == day_labels["lmax"]) & (day_labels["lmin"] != 0)]

        # 排除已在段边界列表里的
        whole_day["_key"] = list(zip(whole_day["site_id"], whole_day["device_id"],
                                     whole_day["branch_id"], whole_day["date"]))
        whole_day = whole_day[~whole_day["_key"].isin(target_keys)]

        # 按 label 分组采样
        label_buckets: Dict[int, pd.DataFrame] = {}
        for lbl, grp in whole_day.groupby("lmin"):
            sampled = grp.sample(n=min(len(grp), max_whole_day_per_label), random_state=42)
            label_buckets[int(lbl)] = sampled
            logger.info("  label=%d: %d 个整天故障天", int(lbl), len(sampled))

        for lbl, bucket in sorted(label_buckets.items()):
            for _, row in bucket.iterrows():
                x, y, ok = _load_one_device_day(
                    raw_df, None, row.site_id, row.device_id, row.branch_id, row.date,
                    daylight_only, min_points, use_point_labels=False, fill_label=lbl,
                )
                if not ok:
                    continue
                all_X.append(x)
                all_Y.append(y)
                all_meta.append({
                    "site_id": row.site_id, "device_id": row.device_id,
                    "branch_id": row.branch_id, "date": str(row.date),
                    "n_points": len(y), "n_fault_points": len(y),
                    "fault_ratio": 1.0, "data_type": "whole_day_fault",
                })
                n_whole += 1

        logger.info("整天故障天: %d 条", n_whole)

    if not all_X:
        raise ValueError("加载后无有效序列")

    meta_df = pd.DataFrame(all_meta)

    # ---- 对齐长度 ----
    lengths = [len(x) for x in all_X]
    seq_len = pad_to or min(lengths)

    X_out, Y_out = [], []
    for x, y in zip(all_X, all_Y):
        if len(x) >= seq_len:
            X_out.append(x[:seq_len])
            Y_out.append(y[:seq_len])
        else:
            pad_len = seq_len - len(x)
            X_out.append(np.pad(x, ((0, pad_len), (0, 0)), constant_values=0))
            Y_out.append(np.pad(y, (0, pad_len), constant_values=0))

    X = np.stack(X_out, axis=0)
    Y = np.stack(Y_out, axis=0)

    info = {
        "n_sequences": len(X),
        "seq_len": seq_len,
        "n_channels": 2,
        "n_segment_boundary": sum(1 for m in all_meta if m["data_type"] == "segment_boundary"),
        "n_whole_day_fault": n_whole,
        "skipped": skipped,
        "labels": sorted(int(v) for v in np.unique(Y)),
        "n_classes": len(np.unique(Y)),
        "class_distribution": {int(k): int(v) for k, v in zip(*np.unique(Y, return_counts=True))},
        "fault_point_ratio": float((Y != 0).mean()),
    }
    logger.info("数据集: %d 序列 (段边界 %d + 整天 %d), seq_len=%d, %d 类",
                info["n_sequences"], info["n_segment_boundary"], n_whole, seq_len, info["n_classes"])

    return X, Y, meta_df, info


def _load_one_device_day(
    raw_df: pd.DataFrame,
    labels_df: Optional[pd.DataFrame],
    site_id: str,
    device_id: str,
    branch_id,
    date,
    daylight_only: bool,
    min_points: int,
    use_point_labels: bool = True,
    fill_label: Optional[int] = None,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], bool]:
    """加载单个设备-天的 (X, Y)。失败返回 (None, None, False)。"""
    branch_id = str(branch_id)
    if daylight_only:
        t_start = pd.Timestamp(date).replace(hour=DAYLIGHT_START_HOUR)
        t_end = pd.Timestamp(date).replace(hour=DAYLIGHT_END_HOUR)
    else:
        t_start = pd.Timestamp(date)
        t_end = t_start + timedelta(days=1)

    mask = (
        (raw_df["site_id"] == site_id) &
        (raw_df["device_id"] == device_id) &
        (raw_df["branch_id"] == branch_id) &
        (raw_df["time"] >= t_start) &
        (raw_df["time"] < t_end)
    )
    mdf = raw_df[mask][["time", "value", "i_cal"]].sort_values("time").reset_index(drop=True)
    if len(mdf) < min_points:
        return None, None, False

    values = mdf["value"].to_numpy(dtype=np.float32)
    i_cal = mdf["i_cal"].to_numpy(dtype=np.float32)

    # NaN 插值
    for arr in (values, i_cal):
        nans = np.isnan(arr)
        if nans.any() and not nans.all():
            arr[nans] = np.interp(np.flatnonzero(nans), np.flatnonzero(~nans), arr[~nans])

    if use_point_labels and labels_df is not None:
        lmask = (
            (labels_df["site_id"] == site_id) &
            (labels_df["device_id"] == device_id) &
            (labels_df["branch_id"] == branch_id) &
            (labels_df["time"] >= t_start) &
            (labels_df["time"] < t_end)
        )
        pdf = labels_df[lmask][["time", "label_id"]].sort_values("time")
        merged = mdf[["time"]].merge(pdf, on="time", how="left")
        labels = merged["label_id"].fillna(0).to_numpy(dtype=np.int64)
    elif fill_label is not None:
        labels = np.full(len(mdf), fill_label, dtype=np.int64)
    else:
        labels = np.zeros(len(mdf), dtype=np.int64)

    x = np.stack([values, i_cal], axis=-1)
    return x, labels, True


def split_by_device(
    X: np.ndarray, Y: np.ndarray, meta: pd.DataFrame,
    test_ratio: float = 0.3, random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, pd.DataFrame, pd.DataFrame]:
    """按设备划分 train/test（同设备不跨集）。"""
    groups = meta["device_id"].values
    gss = GroupShuffleSplit(n_splits=1, test_size=test_ratio, random_state=random_state)
    tr_idx, te_idx = next(gss.split(X, Y[:, 0], groups=groups))
    return (
        X[tr_idx], Y[tr_idx], X[te_idx], Y[te_idx],
        meta.iloc[tr_idx].reset_index(drop=True),
        meta.iloc[te_idx].reset_index(drop=True),
    )
# @AI_GENERATED: end
