# -*- coding: utf-8 -*-
"""
services/iterative_labeling/sample_builder.py — 样本构造纯函数

读同一设备三元组下按时间升序的测量行 + 逐点标签，按 ``split_mode`` 切样本。
纯函数：只读入参、不写 point_labels、不改 label_id。

对应 design.md 组件 4。需求：1.x, 7.x, 3.17
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from services.iterative_labeling.daylight_window import DaylightWindow, DaylightWindowResolver
from services.iterative_labeling.sample_id import make_sample_id

SAMPLING_INTERVAL_SECONDS = 300

VALID_SPLIT_MODES = frozenset({"by_day", "by_day_night"})


@dataclass(frozen=True)
class SampleStrategy:
    split_mode: str = "by_day"
    min_points: int = 12
    daylight_window_source: str = "empirical"
    daylight_window_lookback_months: int = 24
    daylight_windows: Dict[Tuple[str, int], DaylightWindow] = field(default_factory=dict)
    version: str = "sb-v1"


@dataclass(frozen=True)
class Sample:
    sample_id: str
    label_id: int
    period_role: str
    t_start: datetime
    t_end: datetime
    row_indices: Tuple[int, ...]
    label_source: str
    label_source_purity: float
    label_op_id: str


def _fixed_daylight_window() -> DaylightWindow:
    return DaylightWindow(
        daylight_start=dt_time(6, 0),
        daylight_end=dt_time(18, 0),
        source="fixed",
    )


def _resolve_window(
    strategy: SampleStrategy,
    site_id: str,
    month: int,
) -> DaylightWindow:
    key = (str(site_id), int(month))
    window = strategy.daylight_windows.get(key)
    if window is not None:
        return window
    if strategy.daylight_window_source == "fixed":
        return _fixed_daylight_window()
    return _fixed_daylight_window()


def _attach_day_night_flags(rows: pd.DataFrame, strategy: SampleStrategy) -> pd.DataFrame:
    df = rows.copy()
    times = pd.to_datetime(df["time"])
    df["_day"] = times.dt.normalize()
    is_night = []
    for ts, site in zip(times, df["site_id"].astype(str)):
        month = int(ts.month)
        window = _resolve_window(strategy, site, month)
        is_night.append(not window.contains(ts.time()))
    df["is_night"] = np.array(is_night, dtype=bool)
    return df


def _dominant_source(sources: Sequence[str], op_ids: Sequence[str]) -> Tuple[str, float, str]:
    counter = Counter(str(s) for s in sources if s)
    if not counter:
        return "unknown", 0.0, ""
    label_source, count = counter.most_common(1)[0]
    purity = float(count) / float(len(sources))
    # 主来源对应的 op_id：取该 source 下出现次数最多的 op_id
    paired = [(str(s), str(o)) for s, o in zip(sources, op_ids) if str(s) == label_source and o]
    op_counter = Counter(p[1] for p in paired)
    label_op_id = op_counter.most_common(1)[0][0] if op_counter else ""
    return label_source, purity, label_op_id


def build_samples(
    labeled_rows: pd.DataFrame,
    strategy: SampleStrategy,
    *,
    namespace: str = "smp",
) -> Tuple[List[Sample], List[Dict[str, Any]]]:
    """按策略切样本。返回 (样本列表, 丢弃原因列表)。"""
    if strategy.split_mode not in VALID_SPLIT_MODES:
        raise ValueError(f"不支持的 split_mode: {strategy.split_mode}")

    if labeled_rows.empty:
        return [], []

    required = {"time", "label_id", "source", "op_id", "site_id", "device_id", "branch_id"}
    missing = required - set(labeled_rows.columns)
    if missing:
        raise ValueError(f"labeled_rows 缺少列: {sorted(missing)}")

    df = labeled_rows.reset_index(drop=True).copy()
    df = df.sort_values("time").reset_index(drop=True)
    site_id = str(df["site_id"].iloc[0])
    device_id = str(df["device_id"].iloc[0])
    branch_id = str(df["branch_id"].iloc[0])

    if strategy.split_mode == "by_day_night":
        df = _attach_day_night_flags(df, strategy)
    else:
        times = pd.to_datetime(df["time"])
        df["_day"] = times.dt.normalize()
        df["is_night"] = False

    lab_chg = df["label_id"].ne(df["label_id"].shift())
    day_chg = df["_day"].ne(df["_day"].shift())
    dev_chg = df["site_id"].ne(df["site_id"].shift()) | df["device_id"].ne(df["device_id"].shift()) | df["branch_id"].ne(df["branch_id"].shift())
    dn_chg = df["is_night"].ne(df["is_night"].shift()) if strategy.split_mode == "by_day_night" else pd.Series(False, index=df.index)

    if strategy.split_mode == "by_day":
        start_mask = lab_chg | day_chg | dev_chg
    else:
        start_mask = lab_chg | day_chg | dn_chg | dev_chg
    start_mask.iloc[0] = True
    group_id = start_mask.cumsum()

    samples: List[Sample] = []
    discards: List[Dict[str, Any]] = []
    seq_by_role: Dict[str, int] = {}

    for gid, group in df.groupby(group_id, sort=True):
        indices = tuple(int(i) for i in group.index.tolist())
        label_vals = group["label_id"].tolist()
        if all(pd.isna(v) for v in label_vals):
            discards.append({
                "reason": "unknown_label",
                "group_id": int(gid),
                "point_count": len(group),
                "t_start": str(group["time"].iloc[0]),
                "t_end": str(group["time"].iloc[-1]),
            })
            continue

        non_null = [v for v in label_vals if pd.notna(v)]
        if len(set(non_null)) != 1:
            discards.append({
                "reason": "mixed_label_in_group",
                "group_id": int(gid),
                "point_count": len(group),
                "labels": sorted({int(v) for v in non_null}),
            })
            continue

        label_id = int(non_null[0])
        point_count = len(group)
        if point_count < strategy.min_points:
            discards.append({
                "reason": "min_points",
                "group_id": int(gid),
                "point_count": point_count,
                "min_points": strategy.min_points,
                "label_id": label_id,
            })
            continue

        if strategy.split_mode == "by_day_night":
            if bool(group["is_night"].all()):
                period_role = "night"
            elif bool((~group["is_night"]).all()):
                period_role = "daylight"
            else:
                period_role = "night" if bool(group["is_night"].iloc[0]) else "daylight"
        else:
            period_role = "whole"

        t_start = pd.to_datetime(group["time"].iloc[0]).to_pydatetime()
        t_end = pd.to_datetime(group["time"].iloc[-1]).to_pydatetime()
        label_source, purity, label_op_id = _dominant_source(
            group["source"].tolist(),
            group["op_id"].tolist(),
        )

        seq = seq_by_role.get(period_role, 0)
        seq_by_role[period_role] = seq + 1
        sample_id = make_sample_id(
            site_id, device_id, branch_id, t_start, period_role, seq, namespace=namespace,
        )
        samples.append(
            Sample(
                sample_id=sample_id,
                label_id=label_id,
                period_role=period_role,
                t_start=t_start,
                t_end=t_end,
                row_indices=indices,
                label_source=label_source,
                label_source_purity=purity,
                label_op_id=label_op_id,
            )
        )

    return samples, discards


def sample_covered_days(sample: Sample, rows: pd.DataFrame) -> List[datetime]:
    """样本覆盖的自然日列表（用于 group_key 连通块）。"""
    sub = rows.iloc[list(sample.row_indices)]
    days = pd.to_datetime(sub["time"]).dt.normalize().unique()
    return sorted(d.to_pydatetime() for d in days)


def compute_group_keys(
    samples: Sequence[Sample],
    rows: pd.DataFrame,
    site_id: str,
    device_id: str,
    branch_id: str,
) -> Dict[str, str]:
    """按自然日连通块为样本分配 group_key。"""
    if not samples:
        return {}

    n = len(samples)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    day_sets = [set(sample_covered_days(s, rows)) for s in samples]
    for i in range(n):
        for j in range(i + 1, n):
            if day_sets[i] & day_sets[j]:
                union(i, j)

    components: Dict[int, List[int]] = {}
    for i in range(n):
        root = find(i)
        components.setdefault(root, []).append(i)

    result: Dict[str, str] = {}
    ordered_roots = sorted(
        components.keys(),
        key=lambda r: min(samples[i].t_start for i in components[r]),
    )
    for blk_idx, root in enumerate(ordered_roots, start=1):
        gkey = f"{site_id}|{device_id}|{branch_id}|blk{blk_idx}"
        for i in components[root]:
            result[samples[i].sample_id] = gkey
    return result
