# @AI_GENERATED
"""TSC 网格化构建：每设备-天 → 一条 288×3 (value/i_cal/is_measured) 样本 + 窗口级单标签。

设计要点（严格核查后确定）：
  * 输入表示复用 ``seq_annotation.grid_align.align_day_to_grid``：同一套 288 槽时钟网格、
    夜间填 0、白天仅用实测锚点线性插值、覆盖率门控与 ``is_measured`` 掩码。训练与推理
    共用同一函数与 ``grid_contract``，从根上杜绝 train/serve skew。
  * 标签走 TSC 自己的「整日 gold 标签 majority + purity」口径（``all_labeled_combined``
    这类数据集本就是整日单标签），**不使用**点路径的逐点/夜间清零标签——否则夜间 0 与
    白天正常点会在多数投票里淹没白天故障段，把故障日误判为正常。
  * **不套用** 点路径的 ``min_std`` 白天平线过滤：组串开路/短路等真实故障恰恰表现为
    白天近零平线，套用会把故障类样本删掉。
  * 掩码通道不参与 z-score（``preprocess_grid_X`` 只归一化前两测量通道），否则 0/1 语义被毁。

与旧 ``SlidingWindowSampler`` 的差异：旧口径要求「连续 288 行 run」，把夜间/白天有缺口的
设备日整批丢弃（实测约丢 78% 设备日）；网格化按覆盖率证据保留边界日，一天产出一条样本，
标签为整日窗口标签，恰好对应 TSC「设备日」审核单元。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from services.iterative_labeling.seq_annotation.grid_align import (
    MASK_CHANNEL,
    MAX_DAYTIME_GAP_SLOTS,
    MIN_DAYTIME_OCCUPANCY,
    MIN_OCCUPIED_SLOTS,
    REQUIRE_ALL_HOURS_COVERED,
    SLOTS_PER_DAY,
    align_day_to_grid,
    grid_contract,
)

logger = logging.getLogger(__name__)

#: 测量通道顺序（前两通道），第三通道为派生掩码。
MEASURE_CHANNELS: Tuple[str, str] = ("value", "i_cal")
#: TSC 网格样本最终通道顺序。
TSC_GRID_CHANNELS: List[str] = [*MEASURE_CHANNELS, MASK_CHANNEL]
#: 默认序列主键（唯一标识一条物理时序）。
DEFAULT_SERIES_KEYS: Tuple[str, str, str] = ("site_id", "device_id", "branch_id")
#: 默认窗口纯度门槛：众数占比低于此值的设备日视为混合日并丢弃。
DEFAULT_PURITY_THRESHOLD = 0.7


def aggregate_day_label(
    labels: Any, purity_threshold: float = DEFAULT_PURITY_THRESHOLD
) -> Optional[Tuple[int, float]]:
    """把整日逐点标签聚合成单一窗口标签。

    取众数为窗口标签，众数占比为纯度；纯度不足或全部缺失返回 ``None``（丢弃该设备日）。
    仅统计真实存在的标签（NaN 视为未标注，不计入分母），与旧 ``SlidingWindowSampler``
    的 majority 口径一致。
    """
    arr = pd.to_numeric(pd.Series(labels), errors="coerce").to_numpy(dtype="float64")
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return None
    unique, counts = np.unique(valid.astype(np.int64), return_counts=True)
    idx = int(counts.argmax())
    label = int(unique[idx])
    purity = float(counts[idx] / valid.size)
    if purity < float(purity_threshold):
        return None
    return label, purity


def preprocess_grid_X(
    X: np.ndarray,
    *,
    mask_channel_index: int = 2,
    method: str = "per_sample_zscore",
) -> np.ndarray:
    """Mask-aware 预处理：只对测量通道做 per-sample 归一化，掩码通道原样保留。

    与旧 ``data_loader.preprocess_X`` 的差别：旧版对整条样本（含掩码）一起求 mean/std，
    会把 0/1 掩码破坏。这里只在测量通道上算统计量并归一化，掩码通道保持 0/1。
    网格对齐已保证测量通道无 NaN；仍保留 NaN 兜底以防上游异常。
    """
    if X.ndim != 3:
        raise ValueError(f"preprocess_grid_X 需要 [n,T,C]，收到 {X.shape}")
    out = X.astype(np.float32).copy()
    n_channels = out.shape[2]
    measure_idx = [c for c in range(n_channels) if c != mask_channel_index]
    for i in range(out.shape[0]):
        block = out[i][:, measure_idx]
        if np.isnan(block).any():
            for local, ch in enumerate(measure_idx):
                col = out[i][:, ch]
                nans = np.isnan(col)
                if nans.all():
                    out[i][:, ch] = 0.0
                elif nans.any():
                    valid_idx = np.flatnonzero(~nans)
                    out[i][:, ch] = np.interp(np.arange(col.shape[0]), valid_idx, col[valid_idx])
            block = out[i][:, measure_idx]
        if method == "none":
            continue
        if method == "per_sample_zscore":
            mean = float(block.mean())
            std = float(block.std())
            if std > 1e-8:
                for ch in measure_idx:
                    out[i][:, ch] = (out[i][:, ch] - mean) / std
            else:
                for ch in measure_idx:
                    out[i][:, ch] = 0.0
        elif method == "per_sample_minmax":
            vmin = float(block.min())
            vmax = float(block.max())
            rng = vmax - vmin
            for ch in measure_idx:
                out[i][:, ch] = (out[i][:, ch] - vmin) / rng if rng > 1e-8 else 0.0
        else:
            raise ValueError(f"未知预处理方法: {method}")
    return out


def build_tsc_grid_dataset(
    data: pd.DataFrame,
    *,
    purity_threshold: float = DEFAULT_PURITY_THRESHOLD,
    series_keys: Sequence[str] = DEFAULT_SERIES_KEYS,
    min_occupied_slots: int = MIN_OCCUPIED_SLOTS,
    min_daytime_occupancy: float = MIN_DAYTIME_OCCUPANCY,
    max_daytime_gap_slots: int = MAX_DAYTIME_GAP_SLOTS,
    require_all_hours_covered: bool = REQUIRE_ALL_HOURS_COVERED,
) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict[str, Any]]:
    """把带整日标签的时序表按设备-天网格化为 TSC 训练样本。

    Parameters
    ----------
    data:
        至少含 ``time``、``label`` 与 ``value``/``i_cal`` 及 ``series_keys`` 列。
    purity_threshold:
        设备日众数标签占比下限，低于则丢弃该日。

    Returns
    -------
    (X, y, meta, stats)
        ``X`` 形状 ``[N, 288, 3]``（value/i_cal/is_measured，未做归一化）；
        ``y`` 形状 ``[N]`` 窗口级标签；``meta`` 每条样本的设备/日期/覆盖率审计字段；
        ``stats`` 含保留数、拒绝原因分布、类别分布、grid_contract。
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("build_tsc_grid_dataset 输入必须是 DataFrame")
    keys = [str(k) for k in series_keys if k in data.columns]
    if not keys:
        raise ValueError(f"数据缺少序列主键列，series_keys={list(series_keys)}，实际={list(data.columns)}")
    required = ["time", "label", *MEASURE_CHANNELS]
    missing = [c for c in required if c not in data.columns]
    if missing:
        raise ValueError(f"TSC 网格构建缺少必需列: {missing}")

    df = data.copy()
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    if df["time"].isna().any():
        raise ValueError(f"存在 {int(df['time'].isna().sum())} 条无效 time")
    df["_date"] = df["time"].dt.date

    all_X: List[np.ndarray] = []
    all_y: List[int] = []
    metas: List[Dict[str, Any]] = []
    skip_reasons: Dict[str, int] = defaultdict(int)
    devices_seen: set = set()
    group_cols = [*keys, "_date"]

    for key_vals, grp in df.groupby(group_cols, sort=False):
        series_id = "|".join(str(v) for v in key_vals[:-1])
        g = grp.sort_values("time")
        values = np.stack(
            [
                g[MEASURE_CHANNELS[0]].to_numpy(dtype=np.float64),
                g[MEASURE_CHANNELS[1]].to_numpy(dtype=np.float64),
            ],
            axis=-1,
        )
        aligned = align_day_to_grid(
            g["time"],
            values,
            labels=None,
            min_occupied_slots=int(min_occupied_slots),
            min_daytime_occupancy=float(min_daytime_occupancy),
            max_daytime_gap_slots=int(max_daytime_gap_slots),
            require_all_hours_covered=bool(require_all_hours_covered),
        )
        if not aligned.ok:
            skip_reasons[str(aligned.reason or "unknown")] += 1
            continue
        agg = aggregate_day_label(g["label"], purity_threshold=purity_threshold)
        if agg is None:
            skip_reasons["impure_or_unlabeled_day"] += 1
            continue
        label, purity = agg
        x = np.concatenate(
            [aligned.values, aligned.measured_mask[:, np.newaxis]], axis=-1
        ).astype(np.float32)
        if x.shape != (SLOTS_PER_DAY, len(TSC_GRID_CHANNELS)):
            raise ValueError(f"网格样本形状异常: {x.shape}")
        all_X.append(x)
        all_y.append(int(label))
        device_id = str(key_vals[keys.index("device_id")]) if "device_id" in keys else series_id
        devices_seen.add(device_id)
        day_start = pd.Timestamp(key_vals[-1])
        metas.append(
            {
                "series_id": series_id,
                "device_id": device_id,
                "date": str(key_vals[-1]),
                "t_start": day_start.isoformat(),
                "t_end": (day_start + pd.Timedelta(days=1)).isoformat(),
                "label": int(label),
                "purity": round(float(purity), 4),
                "occupied_slots": int(aligned.occupied_slots),
                "daytime_occupancy": round(float(aligned.daytime_occupancy), 4),
                "hours_covered": int(aligned.hours_covered),
                "longest_daytime_gap": int(aligned.longest_daytime_gap),
                "is_full_day": bool(aligned.is_full_day),
            }
        )

    contract = grid_contract(
        min_occupied_slots=int(min_occupied_slots),
        min_daytime_occupancy=float(min_daytime_occupancy),
        max_daytime_gap_slots=int(max_daytime_gap_slots),
        require_all_hours_covered=bool(require_all_hours_covered),
    )
    if not all_X:
        empty = np.empty((0, SLOTS_PER_DAY, len(TSC_GRID_CHANNELS)), dtype=np.float32)
        stats = {
            "n_samples": 0,
            "devices_processed": 0,
            "class_distribution": {},
            "skip_reasons": dict(sorted(skip_reasons.items())),
            "channels": list(TSC_GRID_CHANNELS),
            "grid_contract": contract,
            "purity_threshold": float(purity_threshold),
        }
        return empty, np.empty(0, dtype=np.int64), pd.DataFrame(columns=list(metas[0].keys()) if metas else None), stats

    X = np.stack(all_X, axis=0)
    y = np.asarray(all_y, dtype=np.int64)
    meta = pd.DataFrame(metas)
    unique, counts = np.unique(y, return_counts=True)
    stats = {
        "n_samples": int(len(y)),
        "devices_processed": int(len(devices_seen)),
        "class_distribution": {int(k): int(v) for k, v in zip(unique, counts)},
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "channels": list(TSC_GRID_CHANNELS),
        "grid_contract": contract,
        "purity_threshold": float(purity_threshold),
        "series_keys": list(keys),
    }
    logger.info(
        "TSC 网格构建完成: %d 样本 / %d 设备 / %d 类；拒绝原因=%s",
        stats["n_samples"], stats["devices_processed"], len(unique), stats["skip_reasons"],
    )
    return X, y, meta, stats
# @AI_GENERATED: end
