# @AI_GENERATED
"""
序列标注数据集构建器 — 持久化 .npz 数据集，支持累计增长。

职责：
  1. 从 point_labels（段边界数据）+ parquet（测量值+天级标签）批量构建
  2. 组合三类数据源：segment_boundary / whole_day_fault / whole_day_normal
  3. 输出固定格式的 .npz + meta.parquet + build_config.json + build_report.json
  4. 每次构建产出不可变快照，通过 registry.json 管理版本

设计依据：与用户确认的累计训练数据集方案（2026-08-11）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from services.iterative_labeling.seq_annotation.grid_align import (
    DAYLIGHT_END_HOUR,
    DAYLIGHT_START_HOUR,
    MASK_CHANNEL,
    MAX_DAYTIME_GAP_SLOTS,
    MIN_DAYTIME_OCCUPANCY,
    MIN_OCCUPIED_SLOTS,
    SLOTS_PER_DAY,
    align_day_to_grid,
    daytime_slot_mask,
    grid_contract,
)

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[3]
_DATASETS_DIR = _BACKEND / "data" / "seq_annotation_datasets"
_PARQUET = _BACKEND / "datasets" / "pv_cumulative_labeled_merged.parquet"

SEQ_LEN = SLOTS_PER_DAY  # 全天 24h × 12 槽/h = 288 槽 @ 5min
#: 第 3 通道 is_measured 由网格对齐派生，标记该槽是实测还是补出。
CHANNELS = ["value", "i_cal", MASK_CHANNEL]
EXPLICIT_POINT_SOURCES = {"human_range", "cluster"}
IGNORE_LABEL = -1


def build_dataset(
    *,
    max_whole_day_per_label: int = 200,
    max_normal_days: int = 200,
    seq_len: int = SEQ_LEN,
    min_occupied_slots: int = MIN_OCCUPIED_SLOTS,
    min_daytime_occupancy: float = MIN_DAYTIME_OCCUPANCY,
    max_daytime_gap_slots: int = MAX_DAYTIME_GAP_SLOTS,
    min_points: Optional[int] = None,
    random_state: int = 42,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    构建持久化序列标注数据集（自然日 288 槽网格对齐）。

    Parameters
    ----------
    min_occupied_slots:
        288 槽里至少要有多少个**实测**槽才收该设备-天。默认 173（≈60%）。
        注意这与旧的 ``min_points`` 语义不同：旧参数卡的是原始行数，会把
        「夜间 10 分钟采样、物理完整」的自然日误杀掉。
    min_daytime_occupancy:
        白天时段实测占有率下限，默认 0.8。
    max_daytime_gap_slots:
        白天允许的最长连续空槽，默认 6 槽（30 分钟），超过则拒绝该天。
    min_points:
        已废弃，仅为兼容历史调用保留；传入时按 ``min_occupied_slots`` 解释并告警。

    Returns
    -------
    dict: {"version", "output_dir", "report"}
    """
    if min_points is not None:
        logger.warning(
            "min_points 已废弃（旧语义为原始行数门槛）；按 min_occupied_slots=%d 解释。"
            "请改用 min_occupied_slots。",
            int(min_points),
        )
        min_occupied_slots = int(min_points)
    if int(seq_len) != SLOTS_PER_DAY:
        raise ValueError(
            f"网格对齐后 seq_len 固定为 {SLOTS_PER_DAY}（自然日 5 分钟槽位），收到 {seq_len}"
        )
    # P2 修复：output_dir 必须在开始读数据库或写任何文件之前校验，否则几分钟的
    # 构建工作白跑之后才发现路径越界，还遗留半成品文件。
    if output_dir is not None:
        _out = Path(output_dir).resolve()
        try:
            _out.relative_to(_BACKEND)
        except ValueError as exc:
            raise ValueError(
                "output_dir 必须位于 backend-service 内部"
            ) from exc
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from sqlalchemy import text

    adapter = DBAdapter(DBConfig())
    rng = np.random.default_rng(random_state)

    # ---- 1. 读 point_labels ----
    logger.info("读取 point_labels...")
    with adapter.get_sync_session() as s:
        boundary_rows = s.execute(text("""
            SELECT site_id, device_id, branch_id, DATE(time) as d
            FROM point_labels
            WHERE source IN ('human_range', 'cluster') AND label_id IS NOT NULL
            GROUP BY site_id, device_id, branch_id, DATE(time)
            HAVING COUNT(*) > 0
        """)).fetchall()

        all_labels_rows = s.execute(text("""
            SELECT site_id, device_id, branch_id, time, label_id, source
            FROM point_labels WHERE label_id IS NOT NULL
        """)).fetchall()

        # label_snapshot_hash: 用于判断 point_labels 是否有变化
        hash_row = s.execute(text(
            "SELECT COUNT(*), MAX(updated_at) FROM label_ops WHERE status='active'"
        )).fetchone()
        label_hash_input = f"{hash_row[0]}|{hash_row[1]}"
        label_snapshot_hash = hashlib.sha256(label_hash_input.encode()).hexdigest()[:16]

    target_keys = set((r[0], r[1], str(r[2]), r[3]) for r in boundary_rows)
    logger.info("有段边界的设备-天: %d", len(target_keys))

    labels_df = pd.DataFrame(
        all_labels_rows,
        columns=["site_id", "device_id", "branch_id", "time", "label_id", "source"],
    )
    labels_df["time"] = pd.to_datetime(labels_df["time"])
    labels_df["branch_id"] = labels_df["branch_id"].astype(str)

    # ---- 2. 读 parquet 并建索引 ----
    logger.info("读取 parquet: %s", _PARQUET.name)
    raw_df = pd.read_parquet(_PARQUET, columns=["site_id", "device_id", "branch_id", "time", "value", "i_cal", "label"])
    raw_df["time"] = pd.to_datetime(raw_df["time"])
    raw_df["branch_id"] = raw_df["branch_id"].astype(str)
    raw_df["_date"] = raw_df["time"].dt.date
    raw_df["_hour"] = raw_df["time"].dt.hour

    # 全天 288 点均进入模型；07:00~17:00 仅用于限制低置信天级标签的故障广播。
    raw_scope = raw_df.copy()
    logger.info("全天数据: %d 行", len(raw_scope))

    # 建索引字典：(site,device,branch,date) -> DataFrame
    # 关键优化：groupby 一次 O(n)，替代 2000 次 × 100万行的布尔 mask
    logger.info("构建测量值索引...")
    measure_index: Dict[tuple, pd.DataFrame] = {
        k: g[["time", "value", "i_cal"]].sort_values("time").reset_index(drop=True)
        for k, g in raw_scope.groupby(["site_id", "device_id", "branch_id", "_date"], sort=False)
    }
    logger.info("索引完成: %d 个设备-天", len(measure_index))

    # 同样给标签建索引
    labels_df["_date"] = labels_df["time"].dt.date
    labels_df["_hour"] = labels_df["time"].dt.hour
    # Seq 只消费真实逐点来源；human_day/day_label 即使已物化到 point_labels，仍是纯天级
    # 事实的展开结果，必须在建索引前排除，禁止铺满 288 点。
    labels_scope = labels_df[
        labels_df["source"].isin(EXPLICIT_POINT_SOURCES)
    ].copy()
    label_index: Dict[tuple, pd.DataFrame] = {
        k: g[["time", "label_id", "source"]].sort_values("time").reset_index(drop=True)
        for k, g in labels_scope.groupby(["site_id", "device_id", "branch_id", "_date"], sort=False)
    }
    logger.info("标签索引: %d 个设备-天", len(label_index))

    # ---- 3. 构建三类数据 ----
    all_X: List[np.ndarray] = []
    all_Y: List[np.ndarray] = []
    all_meta: List[dict] = []
    stats = {"segment_boundary": 0, "whole_day_fault": 0, "whole_day_normal": 0, "skipped": 0}
    # 网格对齐的拒绝原因计数，写进 build_report 便于回溯「为什么某天没进训练集」。
    skip_reasons: Dict[str, int] = defaultdict(int)
    grid_kwargs = {
        "min_occupied_slots": int(min_occupied_slots),
        "min_daytime_occupancy": float(min_daytime_occupancy),
        "max_daytime_gap_slots": int(max_daytime_gap_slots),
    }

    # 3a. segment_boundary
    logger.info("处理段边界数据...")
    for key in target_keys:
        x, y, grid_meta, ok = _load_one_indexed(
            measure_index, label_index, *key, use_labels=True, **grid_kwargs
        )
        if not ok:
            stats["skipped"] += 1
            skip_reasons[str(grid_meta.get("reason") or "unknown")] += 1
            continue
        all_X.append(x)
        all_Y.append(y)
        all_meta.append(_meta_dict(*key, y, "segment_boundary", grid_meta))
        stats["segment_boundary"] += 1
    logger.info("段边界: %d 条 (跳过 %d)", stats["segment_boundary"], stats["skipped"])

    # 3b/3c. 纯天级 parquet 标签不进入 Seq 训练。
    # Legacy 仍可消费 parquet 的天级 label；Seq 只保留上面的显式逐点事实，绝不把一个
    # day label 广播为 288 个点。参数 max_whole_day_per_label/max_normal_days 仅为旧调用兼容。
    logger.info("跳过 parquet 纯天级故障/正常标签：Seq 仅消费显式逐点标签")

    if skip_reasons:
        logger.info("网格对齐拒绝原因: %s", dict(sorted(skip_reasons.items())))

    if not all_X:
        raise ValueError("构建后无有效序列")

    # ---- 4. 数据质量门控 ----
    logger.info("执行数据质量门控...")
    quality_stats = {
        "before_filter": len(all_X),
        "removed_low_std": 0,
        "removed_incomplete_day": 0,
        "removed_low_coverage": 0,
        "removed_duplicate": 0,
        "removed_label_inconsistent": 0,
        "after_filter": 0,
    }

    # 4a. min_std 过滤：白天平线（停机/卡死）无诊断价值。
    # 注意必须只统计**白天实测**槽：网格对齐后夜间被填成 0，若把夜间算进来，
    # 「白天恒定 + 夜间 0」也会有很大 std，从而让真正的白天平线天逃过过滤。
    MIN_STD_THRESHOLD = 0.1
    is_daytime_slot = daytime_slot_mask()
    keep_mask = []
    for x in all_X:
        measured = x[:, 2] > 0.5
        daytime_measured = measured & is_daytime_slot
        sample = x[daytime_measured, 0] if daytime_measured.any() else x[:, 0]
        val_std = float(np.nanstd(sample)) if sample.size else 0.0
        if not np.isfinite(val_std) or val_std < MIN_STD_THRESHOLD:
            quality_stats["removed_low_std"] += 1
            keep_mask.append(False)
        else:
            keep_mask.append(True)

    all_X = [all_X[i] for i in range(len(all_X)) if keep_mask[i]]
    all_Y = [all_Y[i] for i in range(len(all_Y)) if keep_mask[i]]
    all_meta = [all_meta[i] for i in range(len(all_meta)) if keep_mask[i]]
    logger.info("  min_std 过滤: 移除 %d 条（白天平线/停机天）", quality_stats["removed_low_std"])

    # 4b. 安全网：全天快照要求每个原始样本的 24 个小时都有至少一个实测槽。
    # 该门控已前移到 align_day_to_grid（reason=hours_not_fully_covered），推理侧读
    # 同一份契约执行同一条规则；这里保留一层结构性兜底，正常应恒为 0。
    full_day_keep = [bool(meta["is_full_day"]) for meta in all_meta]
    quality_stats["removed_incomplete_day"] = int(
        sum(not keep for keep in full_day_keep)
    )
    all_X = [all_X[i] for i in range(len(all_X)) if full_day_keep[i]]
    all_Y = [all_Y[i] for i in range(len(all_Y)) if full_day_keep[i]]
    all_meta = [all_meta[i] for i in range(len(all_meta)) if full_day_keep[i]]
    logger.info(
        "  全天小时覆盖兜底: 移除 %d 条（应为 0，网格阶段已拒绝）",
        quality_stats["removed_incomplete_day"],
    )

    # 4c. 覆盖率门控已前移到网格对齐（min_occupied_slots / min_daytime_occupancy /
    # max_daytime_gap_slots），这里只统计被拒绝的条数，避免与旧的
    # 「有效点数 / seq_len」判据重复——网格化后长度恒为 288，旧判据永远为真。
    quality_stats["removed_low_coverage"] = int(sum(skip_reasons.values()))
    quality_stats["skip_reasons"] = dict(sorted(skip_reasons.items()))
    logger.info(
        "  覆盖率门控（网格对齐阶段）: 拒绝 %d 个设备-天", quality_stats["removed_low_coverage"]
    )

    # 4d. segment_boundary 标签一致性：如果标签只有一种值（误分类），移到 whole_day
    for i in range(len(all_meta)):
        if all_meta[i]["data_type"] == "segment_boundary":
            unique_labels = set(int(v) for v in all_Y[i] if v >= 0)
            if len(unique_labels) < 2:
                all_meta[i]["data_type"] = "whole_day_fault"  # 降级
                quality_stats["removed_label_inconsistent"] += 1
    logger.info("  标签一致性降级: %d 条 segment_boundary → whole_day", quality_stats["removed_label_inconsistent"])

    # 4e. 字节级去重：相同 X 只保留第一条
    hashes_seen = set()
    keep_idx = []
    for i, x in enumerate(all_X):
        h = hashlib.sha256(x.tobytes()).digest()
        if h not in hashes_seen:
            hashes_seen.add(h)
            keep_idx.append(i)
        else:
            quality_stats["removed_duplicate"] += 1

    all_X = [all_X[i] for i in keep_idx]
    all_Y = [all_Y[i] for i in keep_idx]
    all_meta = [all_meta[i] for i in keep_idx]
    logger.info("  字节级去重: 移除 %d 条", quality_stats["removed_duplicate"])

    quality_stats["after_filter"] = len(all_X)
    logger.info("  门控后剩余: %d 条（移除 %d 条，%.1f%%）",
                quality_stats["after_filter"],
                quality_stats["before_filter"] - quality_stats["after_filter"],
                (1 - quality_stats["after_filter"] / quality_stats["before_filter"]) * 100)

    if not all_X:
        raise ValueError("质量门控后无有效序列")

    # ---- 5. 标记 tier + sample_weight ----
    for m in all_meta:
        dt = m["data_type"]
        if dt == "segment_boundary":
            m["tier"] = "gold"
            m["sample_weight"] = 1.0
        elif dt == "whole_day_fault" and m.get("fault_ratio", 0) < 1.0:
            # 有实际段边界的中置信数据（从段边界处理后降级的）
            m["tier"] = "silver"
            m["sample_weight"] = 0.8
        elif dt in ("whole_day_fault", "whole_day_normal"):
            m["tier"] = "bronze"
            m["sample_weight"] = 0.3
        else:
            m["tier"] = "bronze"
            m["sample_weight"] = 0.3
        m["is_augmented"] = False
        m["augment_method"] = "none"
        m["source_idx"] = -1

    # ---- 6. 数据增强（只对 gold + silver）----
    from services.iterative_labeling.seq_annotation.augmentation import augment_batch

    AUGMENT_MULTIPLIER_GOLD = 4    # gold ×4 增强
    AUGMENT_MULTIPLIER_SILVER = 2  # silver ×2 增强

    aug_X_all, aug_Y_all, aug_meta_all = [], [], []

    # 掩码通道不参与增强：scaling/magnitude_warp 是乘法，会把 1/0 变成 1.15/0，
    # 破坏 is_measured 的语义；jitter 则只对实测槽加噪。因此先拆出掩码，
    # 只增强测量通道，再把原掩码原样拼回去。
    for tier, multiplier in [("gold", AUGMENT_MULTIPLIER_GOLD), ("silver", AUGMENT_MULTIPLIER_SILVER)]:
        tier_indices = [i for i, m in enumerate(all_meta) if m["tier"] == tier]
        if not tier_indices or multiplier <= 0:
            continue
        tier_X = [all_X[i][:, :-1] for i in tier_indices]
        tier_masks = [all_X[i][:, -1] for i in tier_indices]
        tier_Y = [all_Y[i] for i in tier_indices]

        aug_X, aug_Y, aug_methods = augment_batch(
            tier_X, tier_Y, n_augments=multiplier, seed=random_state, masks=tier_masks,
        )
        for j, (xa, ya, method) in enumerate(zip(aug_X, aug_Y, aug_methods)):
            source_i = tier_indices[j // multiplier]
            orig = all_meta[source_i]
            aug_X_all.append(
                np.concatenate([xa, tier_masks[j // multiplier][:, np.newaxis]], axis=-1)
            )
            aug_Y_all.append(ya)
            aug_meta_all.append({
                **{k: orig[k] for k in ("site_id", "device_id", "branch_id", "date",
                                         "n_points", "is_full_day", "n_fault_points",
                                         "fault_ratio", "data_type", "occupied_slots",
                                         "daytime_occupancy", "hours_covered",
                                         "longest_daytime_gap")},
                "tier": tier,
                "sample_weight": orig["sample_weight"],
                "is_augmented": True,
                "augment_method": method,
                "source_idx": source_i,
            })

    n_augmented = len(aug_X_all)
    logger.info("数据增强: gold ×%d + silver ×%d → 新增 %d 条",
                AUGMENT_MULTIPLIER_GOLD, AUGMENT_MULTIPLIER_SILVER, n_augmented)

    # 合并原始 + 增强
    all_X.extend(aug_X_all)
    all_Y.extend(aug_Y_all)
    all_meta.extend(aug_meta_all)

    # ---- 7. 结构性校验 ----
    # 网格对齐已保证每条序列都是 288 槽，这里不再做截断/尾部补零（那正是时间轴
    # 错位的根源）。任何长度不符都说明上游逻辑被改坏了，直接失败而不是静默补齐。
    bad_shapes = {
        (int(x.shape[0]), int(x.shape[1]))
        for x in all_X
        if x.shape[0] != seq_len or x.shape[1] != len(CHANNELS)
    }
    if bad_shapes:
        raise ValueError(
            f"网格对齐后序列形状必须是 ({seq_len}, {len(CHANNELS)})，出现异常形状: {sorted(bad_shapes)}"
        )
    if any(len(y) != seq_len for y in all_Y):
        raise ValueError(f"网格对齐后标签长度必须是 {seq_len}")

    X = np.stack(all_X, axis=0).astype(np.float32)  # [N, 288, 3]
    Y = np.stack(all_Y, axis=0).astype(np.int64)    # [N, 288]
    meta_df = pd.DataFrame(all_meta)

    # ---- 6. 保存 ----
    version = f"snap-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    out_dir = output_dir or (_DATASETS_DIR / "snapshots" / version)
    out_dir.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(out_dir / "dataset.npz", X=X, Y=Y)
    meta_df.to_parquet(out_dir / "meta.parquet", index=False)

    labels_in_data = sorted(int(v) for v in np.unique(Y[Y >= 0]))
    class_dist = {int(k): int(v) for k, v in zip(*np.unique(Y[Y >= 0], return_counts=True))}

    contract = grid_contract(
        min_occupied_slots=int(min_occupied_slots),
        min_daytime_occupancy=float(min_daytime_occupancy),
        max_daytime_gap_slots=int(max_daytime_gap_slots),
    )
    build_config = {
        "version": version,
        "built_at": datetime.utcnow().isoformat(),
        "label_snapshot_hash": label_snapshot_hash,
        "seq_len": seq_len,
        "min_occupied_slots": int(min_occupied_slots),
        "min_daytime_occupancy": float(min_daytime_occupancy),
        "max_daytime_gap_slots": int(max_daytime_gap_slots),
        "channels": CHANNELS,
        "daylight_hours": [0, 24],
        "label_granularity_policy": "explicit_point_only",
        "excluded_day_label_sources": ["day_label", "human_day", "parquet_day_label"],
        "unlabeled_point_policy": "ignore_index_-1",
        "grid_contract": contract,
        "max_whole_day_per_label": max_whole_day_per_label,
        "max_normal_days": max_normal_days,
        "random_state": random_state,
    }
    (out_dir / "build_config.json").write_text(
        json.dumps(build_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # full_day_grid_validated 必须来自**真实覆盖证据**，不能用「长度是否等于 288」推导。
    # 网格化之后每条序列长度恒为 288，若沿用长度判据，这个标记会永远为真，
    # trainer 侧的全天门控就会形同虚设，半天数据也能冒充全天模型。
    # 这里的 is_full_day 由 grid_align 按「24 小时都有实测覆盖 + 实测槽数达标」给出，
    # 因此昼间窗口数据（例如只有 07~17 的 120 槽）会让该标记降为 False。
    original_meta = [m for m in all_meta if not m["is_augmented"]]
    full_day_grid_validated = bool(
        seq_len == SLOTS_PER_DAY
        and contract["grid_aligned"]
        and build_config["daylight_hours"] == [0, 24]
        and original_meta
        and all(bool(m["is_full_day"]) for m in original_meta)
    )
    report = {
        **build_config,
        "stats": stats,
        "quality_filter": quality_stats,
        "augmentation": {
            "n_augmented": n_augmented,
            "gold_multiplier": AUGMENT_MULTIPLIER_GOLD,
            "silver_multiplier": AUGMENT_MULTIPLIER_SILVER,
        },
        "grid_contract": {**contract, "full_day_grid_validated": full_day_grid_validated},
        "full_day_grid_validated": full_day_grid_validated,
        "n_full_day_original": int(sum(1 for m in original_meta if m["is_full_day"])),
        "n_sequences": len(X),
        "n_original": len(X) - n_augmented,
        "labels": labels_in_data,
        "n_classes": len(labels_in_data),
        "class_distribution": class_dist,
        "fault_point_ratio": float((Y[Y >= 0] != 0).mean()),
        "data_type_counts": meta_df["data_type"].value_counts().to_dict(),
    }
    (out_dir / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # ---- 6. 更新 registry ----
    _update_registry(version, out_dir, report)

    logger.info("数据集构建完成: %s (%d 序列, %d 类)", version, len(X), len(labels_in_data))
    return {
        "version": version,
        "output_dir": _to_backend_relative(out_dir),
        "report": report,
    }


def _load_one_indexed(
    measure_index: Dict[tuple, pd.DataFrame],
    label_index: Optional[Dict[tuple, pd.DataFrame]],
    site_id: str, device_id: str, branch_id, date,
    *,
    use_labels: bool = True,
    fill_label: Optional[int] = None,
    fault_daylight_only: bool = False,
    min_occupied_slots: int = MIN_OCCUPIED_SLOTS,
    min_daytime_occupancy: float = MIN_DAYTIME_OCCUPANCY,
    max_daytime_gap_slots: int = MAX_DAYTIME_GAP_SLOTS,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Dict[str, Any], bool]:
    """
    用预建索引加载单个设备-天，并对齐到 288 槽自然日网格。

    性能关键：原实现对 100 万行做 4 个布尔 mask × 2000 次循环 = 几十分钟；
    改成 groupby 建索引后单次查找是 dict lookup，整体 O(n) 一次。

    Returns
    -------
    (x, y, grid_meta, ok)
        ``x`` 形状 ``[288, 3]``，通道顺序为 ``value / i_cal / is_measured``；
        ``y`` 形状 ``[288]``；``grid_meta`` 含占有率等可审计字段，被拒绝时含
        ``reason``；``ok=False`` 表示该设备-天不满足网格覆盖门槛。
    """
    key = (site_id, device_id, str(branch_id), date)
    mdf = measure_index.get(key)
    if mdf is None or mdf.empty:
        return None, None, {"reason": "no_measurement"}, False

    values = np.stack(
        [
            mdf["value"].to_numpy(dtype=np.float64),
            mdf["i_cal"].to_numpy(dtype=np.float64),
        ],
        axis=-1,
    )

    # 逐点标签先在「测量行」空间上按来源裁决，再交给网格对齐外推到空槽，
    # 这样夜间弱标签清零的既有口径不受网格化影响。
    if use_labels and label_index is not None:
        pdf = label_index.get(key)
        if pdf is None:
            return None, None, {"reason": "no_point_label"}, False
        pdf = pdf[pdf["source"].isin(EXPLICIT_POINT_SOURCES)]
        if pdf.empty:
            return None, None, {"reason": "pure_day_label_not_allowed_for_seq"}, False
        merged = mdf[["time"]].merge(pdf, on="time", how="left")
        # 未被显式逐点事实覆盖的位置保持 IGNORE_LABEL，由 loss ignore_index=-1 忽略；
        # 不能把缺失点默认为正常，更不能用 human_day/day_label 铺满全天。
        labels = merged["label_id"].fillna(IGNORE_LABEL).to_numpy(dtype=np.int64)
    elif fill_label is not None:
        return None, None, {"reason": "pure_day_label_not_allowed_for_seq"}, False
    else:
        labels = np.full(len(mdf), IGNORE_LABEL, dtype=np.int64)

    aligned = align_day_to_grid(
        mdf["time"],
        values,
        labels,
        min_occupied_slots=min_occupied_slots,
        min_daytime_occupancy=min_daytime_occupancy,
        max_daytime_gap_slots=max_daytime_gap_slots,
        daylight_start_hour=DAYLIGHT_START_HOUR,
        daylight_end_hour=DAYLIGHT_END_HOUR,
    )
    if not aligned.ok:
        return None, None, {"reason": aligned.reason, **aligned.as_meta()}, False

    x = np.concatenate(
        [aligned.values, aligned.measured_mask[:, np.newaxis]], axis=-1
    ).astype(np.float32)
    return x, aligned.labels.astype(np.int64), aligned.as_meta(), True


def _meta_dict(
    site_id, device_id, branch_id, date,
    y: np.ndarray,
    data_type: str,
    grid_meta: Dict[str, Any],
) -> dict:
    """组装单条序列的 meta。

    ``n_points`` 现在是网格槽位数（恒为 288），真实测量点数看 ``occupied_slots``；
    ``is_full_day`` 来自网格对齐的覆盖证据，不再由长度推导。
    """
    return {
        "site_id": site_id, "device_id": device_id, "branch_id": str(branch_id),
        "date": str(date),
        "n_points": int(len(y)),
        "occupied_slots": int(grid_meta["occupied_slots"]),
        "daytime_occupancy": float(grid_meta["daytime_occupancy"]),
        "hours_covered": int(grid_meta["hours_covered"]),
        "longest_daytime_gap": int(grid_meta["longest_daytime_gap"]),
        "is_full_day": bool(grid_meta["is_full_day"]),
        "n_fault_points": int((y > 0).sum()),
        "fault_ratio": float((y > 0).mean()),
        "data_type": data_type,
    }


def _to_backend_relative(path: Path) -> str:
    """将持久化路径转换为 backend-service 相对路径。"""
    try:
        return path.resolve().relative_to(_BACKEND).as_posix()
    except ValueError as exc:
        raise ValueError("序列标注数据集必须保存在 backend-service 内") from exc


def _update_registry(version: str, out_dir: Path, report: dict) -> None:
    """更新 registry.json，记录当前版本。"""
    reg_path = _DATASETS_DIR / "registry.json"
    _DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    if reg_path.exists():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    else:
        reg = {"current_version": None, "versions": []}

    reg["current_version"] = version
    reg["versions"].append({
        "version": version,
        "path": _to_backend_relative(out_dir),
        "built_at": report["built_at"],
        "n_sequences": report["n_sequences"],
        "n_classes": report["n_classes"],
        "label_snapshot_hash": report["label_snapshot_hash"],
    })

    reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def load_current_dataset() -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict]:
    """加载当前版本数据集（从 npz，快速）。"""
    reg_path = _DATASETS_DIR / "registry.json"
    if not reg_path.exists():
        raise FileNotFoundError("没有已构建的数据集，请先运行 build_seq_annotation_dataset.py")

    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    version = reg["current_version"]
    snap_dir = _DATASETS_DIR / "snapshots" / version

    data = np.load(snap_dir / "dataset.npz")
    X, Y = data["X"], data["Y"]
    meta = pd.read_parquet(snap_dir / "meta.parquet")
    config = json.loads((snap_dir / "build_config.json").read_text(encoding="utf-8"))
    report = json.loads((snap_dir / "build_report.json").read_text(encoding="utf-8"))

    return X, Y, meta, report
# @AI_GENERATED: end
