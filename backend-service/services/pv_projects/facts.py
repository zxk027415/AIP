# @AI_GENERATED
"""数据集质量事实计算（数据集切片第 1 步）。

职责：从**真实的 CSV/TSV/Parquet 文件**算出覆盖事实，供 readiness 判定"这份数据能不能喂这条路径"。

为什么必须服务端算：
`backend-service/services/pv_projects/readiness.py::evaluate_path_readiness` 判定 `ready` 的唯一开关是
`facts.sufficient_coverage`；在本次改动前，`facts` 完全由客户端传入、后端从不计算，于是生产路径
**恒**停在 `experiment_only`——"质量检测"实际不存在。

红线：
- 不得凭行数推断连续日期覆盖（行数多 ≠ 日期连续）；
- 阈值必须是命名常量并随 facts 一起返回（可解释、可测、可调）；
- 读文件按映射列裁剪，不整读大文件的全部列；
- 文件缺列 / 映射不全一律 fail-closed，不产出"看起来凑合"的 facts。
"""

from __future__ import annotations

from typing import Any, Optional

from services.pv_projects.errors import ScopeError
from services.pv_projects.source_resolver import resolve_dataset_unit

#: 覆盖判定阈值（命名常量：随 facts 一起返回，使判定可解释、可测、可调）。
COVERAGE_THRESHOLDS: dict[str, float] = {
    "min_date_coverage_ratio": 0.6,
    "min_device_count": 2,
    "min_sampling_completeness": 0.8,
}

#: 必需映射字段（缺任一即无法判定覆盖）。
REQUIRED_MAPPING_FIELDS: tuple[str, ...] = ("time_col", "device_col", "value_col")


def _read_frame(path, *, ext: str, wanted: list[str]):
    """按需读列；缺列即 fail-closed。

    先读表头做校验再按列读，避免"大文件整读一遍才发现列名错"。
    """
    import pandas as pd

    if ext == ".parquet":
        df = pd.read_parquet(path)
        absent = [c for c in wanted if c not in df.columns]
        if absent:
            raise ScopeError(
                "mapping_column_missing",
                f"文件里没有这些映射列：{absent}。",
                next_action=f"文件实际列：{sorted(map(str, df.columns))[:20]}",
            )
        return df[wanted]

    sep = "\t" if ext == ".tsv" else ","
    head = pd.read_csv(path, sep=sep, nrows=0)
    cols = {str(c) for c in head.columns}
    absent = [c for c in wanted if c not in cols]
    if absent:
        raise ScopeError(
            "mapping_column_missing",
            f"文件里没有这些映射列：{absent}。",
            next_action=f"文件实际列：{sorted(cols)[:20]}",
        )
    return pd.read_csv(path, sep=sep, usecols=wanted)


def compute_dataset_facts(
    source_ref: str,
    *,
    mapping: dict[str, Any],
    label_policy: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """读真实文件并算出覆盖事实（字段约定见模块 docstring 与实现尾部返回体）。"""
    unit = resolve_dataset_unit(source_ref)
    shard_paths = list(unit["shard_paths"])
    shard_count = len(shard_paths)
    # 分片组要求同构；以首片扩展名代表整组（不一致会在 _read_frame 处暴露为缺列/解析错）。
    ext = shard_paths[0].suffix.lower()

    time_col = str(mapping.get("time_col") or "").strip()
    device_col = str(mapping.get("device_col") or "").strip()
    value_col = str(mapping.get("value_col") or "").strip()
    missing = [
        name
        for name, value in (
            ("time_col", time_col),
            ("device_col", device_col),
            ("value_col", value_col),
        )
        if not value
    ]
    if missing:
        raise ScopeError(
            "incomplete_mapping",
            f"缺少必填映射字段：{missing}。",
            next_action="补齐时间列 / 设备列 / 实测值列后再做质量检测",
        )

    label_col = str(mapping.get("label_col") or "").strip()
    wanted = [time_col, device_col, value_col] + ([label_col] if label_col else [])

    import pandas as pd

    # 分片组必须**全量聚合**：质量结论不能只看第一个分片（否则"3 个月的数据"会被
    # 当成"1 个月"来判覆盖）。
    frames = [_read_frame(p, ext=p.suffix.lower(), wanted=wanted) for p in shard_paths]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    ts = pd.to_datetime(df[time_col], errors="coerce")
    keep = ts.notna()
    df = df.loc[keep].copy()
    ts = ts.loc[keep]

    row_count = int(len(df))
    if row_count == 0:
        return _empty_facts(source_ref, ext, shard_count=shard_count, reason="no_parseable_timestamp")

    df["__date"] = ts.dt.date
    distinct_dates = int(df["__date"].nunique())
    time_min = pd.Timestamp(ts.min())
    time_max = pd.Timestamp(ts.max())
    date_span_days = int((time_max.normalize() - time_min.normalize()).days) + 1
    date_coverage_ratio = (
        round(distinct_dates / date_span_days, 4) if date_span_days > 0 else 0.0
    )

    device_count = int(df[device_col].nunique(dropna=True))

    # 采样间隔：只看**同一设备内**相邻时间差（跨设备边界的差不代表采样节奏）。
    ordered = df.sort_values([device_col, time_col])
    ordered_ts = pd.to_datetime(ordered[time_col], errors="coerce")
    diff_seconds = ordered_ts.diff().dt.total_seconds()
    same_device = ordered[device_col].eq(ordered[device_col].shift())
    positive = diff_seconds[(diff_seconds > 0) & same_device]
    sampling_interval_seconds = int(positive.median()) if len(positive) else 0

    # 采样完整率 = **设备日内的点数完整度**（度量"某天占用了没有、缺没缺采样"）。
    #
    # 刻意不用 `行数 / (设备数 × 离散日期数 × 每日期望点数)`：那个式子会把
    # "各设备在不同日期交错出现"误判成"每一天都残缺"——实测 `uploads/pv_train_small.csv`
    # 有 75 设备、57,385 行、5 分钟采样，按前者只有 0.166，而按设备日看基本是满的。
    # 设计意图是日占用完整率，故取每个 (设备, 日) 的点数比、截断到 1 后求均值。
    if sampling_interval_seconds > 0:
        expected_per_device_day = 86400.0 / sampling_interval_seconds
        per_device_day_points = df.groupby([device_col, "__date"]).size()
        ratios = (per_device_day_points / expected_per_device_day).clip(upper=1.0)
        sampling_completeness = round(float(ratios.mean()), 4) if len(ratios) else 0.0
    else:
        sampling_completeness = 0.0

    value_null_ratio = round(float(df[value_col].isna().mean()), 4)

    label_distribution: dict[str, int] = {}
    label_granularity_detected = "unknown"
    if label_col and label_col in df.columns:
        counts = df[label_col].value_counts(dropna=True)
        label_distribution = {str(k): int(v) for k, v in counts.items()}
        per_device_day = df.groupby([device_col, "__date"])[label_col].nunique(dropna=True)
        if len(per_device_day):
            # 同一 (设备, 日) 内标签唯一 → 设备日粒度；多于一个 → 点/区间粒度。
            label_granularity_detected = (
                "device_day" if int(per_device_day.max()) <= 1 else "point"
            )

    gaps: list[str] = []
    if date_coverage_ratio < COVERAGE_THRESHOLDS["min_date_coverage_ratio"]:
        gaps.append("date_coverage_ratio")
    if device_count < COVERAGE_THRESHOLDS["min_device_count"]:
        gaps.append("device_count")
    if sampling_completeness < COVERAGE_THRESHOLDS["min_sampling_completeness"]:
        gaps.append("sampling_completeness")

    return {
        "source_ref": source_ref,
        "source_extension": ext,
        "shard_count": shard_count,
        "facts_source": "computed_from_file",
        "row_count": row_count,
        "time_min": time_min.isoformat(),
        "time_max": time_max.isoformat(),
        "distinct_dates": distinct_dates,
        "date_span_days": date_span_days,
        "date_coverage_ratio": date_coverage_ratio,
        "device_count": device_count,
        "sampling_interval_seconds": sampling_interval_seconds,
        "sampling_completeness": sampling_completeness,
        "value_null_ratio": value_null_ratio,
        "label_distribution": label_distribution,
        "label_granularity_detected": label_granularity_detected,
        "declared_label_granularity": str(
            (label_policy or {}).get("granularity") or ""
        ).strip() or None,
        "sufficient_coverage": not gaps,
        "coverage_gaps": gaps,
        "coverage_thresholds": dict(COVERAGE_THRESHOLDS),
    }


def _empty_facts(source_ref: str, ext: str, *, shard_count: int = 0, reason: str) -> dict[str, Any]:
    """没有任何可解析时间戳时的诚实返回（不假装有数据）。"""
    return {
        "source_ref": source_ref,
        "source_extension": ext,
        "shard_count": shard_count,
        "facts_source": "computed_from_file",
        "row_count": 0,
        "time_min": None,
        "time_max": None,
        "distinct_dates": 0,
        "date_span_days": 0,
        "date_coverage_ratio": 0.0,
        "device_count": 0,
        "sampling_interval_seconds": 0,
        "sampling_completeness": 0.0,
        "value_null_ratio": 0.0,
        "label_distribution": {},
        "label_granularity_detected": "unknown",
        "declared_label_granularity": None,
        "sufficient_coverage": False,
        "coverage_gaps": [reason, "date_coverage_ratio", "device_count", "sampling_completeness"],
        "coverage_thresholds": dict(COVERAGE_THRESHOLDS),
    }


# @AI_GENERATED: end
