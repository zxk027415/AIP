# -*- coding: utf-8 -*-
# @AI_GENERATED
"""自然日 5 分钟时钟网格对齐 — 训练侧与推理侧共用的唯一契约。

为什么需要这个模块
------------------
原实现按「行数」截断或尾部补零对齐长度，这在稀疏采样日会把时间轴挤乱：
电站 SCADA 白天每 5 分钟一采（12 点/h），夜间常常每 10 分钟一采（6 点/h），
所以一个物理完整的自然日经常只有约 220 行，而不是 288 行。尾部补零之后，
下标 144 在完整日是 12:00、在稀疏日却是 15:10，模型学到的位置语义不一致；
推理侧若用同样的尾部补零，还会和训练侧产生不同的错位，形成 train/serve skew。

本模块把一天固定铺成 ``00:00, 00:05, ..., 23:55`` 共 288 个槽位：
  * 有测量的槽位放真实值，并在 ``measured_mask`` 里标 1
  * 夜间空槽填 0（夜间功率/电流物理上就接近 0），mask 标 0
  * 白天短空槽用相邻**实测**点线性插值，mask 标 0
  * 白天连续空槽过长（默认 > 6 槽 = 30 分钟）直接拒绝该天，避免把停机/通讯
    中断插成一条斜线而被误认为故障爬升
  * 标签只在两侧实测标签一致时才外推，否则夜间归正常、白天置忽略

门槛口径参考 NREL Solar Data Tools 的清洗流水线（先对齐时间轴再按覆盖率过滤，
默认覆盖率下限 0.6），而不是要求原始行数刚好等于每天格点数。

被谁调用
--------
  * ``dataset_builder._load_one_indexed``：构建训练快照时对齐
  * ``predictor.SeqAnnotationPredictor.predict_device_day``：推理时对齐
两侧共用本模块，保证 ``grid_contract`` 一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd

SLOT_MINUTES = 5
SLOTS_PER_HOUR = 60 // SLOT_MINUTES  # 12
SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR  # 288

#: 掩码通道名。取值 1=该槽为实测，0=该槽由夜间填零或白天插值补出。
MASK_CHANNEL = "is_measured"

#: 白天时段仅用于「夜间填零 / 弱标签不得广播到夜间」的判定，不用于裁剪序列。
DAYLIGHT_START_HOUR = 7
DAYLIGHT_END_HOUR = 17

#: 硬门槛：288 槽里至少要有多少个实测槽。173/288 ≈ 60%，对齐 Solar Data Tools 默认。
MIN_OCCUPIED_SLOTS = 173
#: 软门槛：白天时段实测占有率下限，防止「夜间很满、白天大段缺」的坏天混入。
MIN_DAYTIME_OCCUPANCY = 0.8
#: 白天允许的最长连续空槽（6 槽 = 30 分钟），超过即拒绝该天。
MAX_DAYTIME_GAP_SLOTS = 6
#: 是否要求 24 个小时都至少有一个实测槽。全天口径必须为真：只看总占有率会放进
#: 「整小时通讯中断」的边缘日，训练侧剔除、推理侧接受就会形成 train/serve skew。
REQUIRE_ALL_HOURS_COVERED = True

IGNORE_LABEL = -1


@dataclass(frozen=True)
class GridAlignResult:
    """单个设备-天的网格对齐结果。

    ``values`` 不含掩码通道，掩码单独放在 ``measured_mask``，由调用方决定是否
    拼成第 3 通道，这样旧的 2 通道模型仍可复用同一套对齐逻辑。
    """

    ok: bool
    reason: Optional[str]
    values: Optional[np.ndarray]          # [288, n_channels] float32
    measured_mask: Optional[np.ndarray]   # [288] float32，1=实测 0=补出
    labels: Optional[np.ndarray]          # [288] int64，未传标签时为 None
    occupied_slots: int
    daytime_occupancy: float
    hours_covered: int
    longest_daytime_gap: int
    is_full_day: bool

    def as_meta(self) -> Dict[str, Any]:
        """展开成可写入 meta.parquet 的可审计字段。"""
        return {
            "occupied_slots": int(self.occupied_slots),
            "daytime_occupancy": round(float(self.daytime_occupancy), 4),
            "hours_covered": int(self.hours_covered),
            "longest_daytime_gap": int(self.longest_daytime_gap),
            "is_full_day": bool(self.is_full_day),
        }


def grid_timestamps(day: Any) -> pd.DatetimeIndex:
    """返回某一天的 288 个槽位时间戳（00:00 起，步长 5 分钟）。"""
    start = pd.Timestamp(day).normalize()
    return pd.date_range(start, periods=SLOTS_PER_DAY, freq=f"{SLOT_MINUTES}min")


def slot_of(times: Any) -> np.ndarray:
    """把时间戳映射到 [0, 288) 的槽位下标（按当天 00:00 起的 5 分钟向下取整）。"""
    ts = pd.to_datetime(pd.Series(np.asarray(times).ravel()), errors="coerce")
    minutes = ts.dt.hour.to_numpy(dtype="float64") * 60 + ts.dt.minute.to_numpy(dtype="float64")
    slots = np.floor_divide(minutes, SLOT_MINUTES)
    slots = np.where(np.isfinite(slots), slots, -1)
    return slots.astype(np.int64)


def daytime_slot_mask(
    daylight_start_hour: int = DAYLIGHT_START_HOUR,
    daylight_end_hour: int = DAYLIGHT_END_HOUR,
) -> np.ndarray:
    """返回 [288] 布尔数组，标记哪些槽位属于白天时段。"""
    slot_hour = np.arange(SLOTS_PER_DAY) // SLOTS_PER_HOUR
    return (slot_hour >= int(daylight_start_hour)) & (slot_hour < int(daylight_end_hour))


def split_mask_channel(channels: Sequence[str]) -> tuple[list[str], Optional[int]]:
    """把通道列表拆成（实测通道, 掩码通道下标）。

    掩码通道不是从数据源读来的列，而是对齐时派生出来的，所以调用方需要知道它在
    通道顺序里的位置，才能在归一化时跳过它、在推理时自行补齐。
    """
    measured = [str(name) for name in channels if str(name) != MASK_CHANNEL]
    try:
        mask_index = [str(name) for name in channels].index(MASK_CHANNEL)
    except ValueError:
        mask_index = None
    return measured, mask_index


def grid_contract(
    *,
    min_occupied_slots: int = MIN_OCCUPIED_SLOTS,
    min_daytime_occupancy: float = MIN_DAYTIME_OCCUPANCY,
    max_daytime_gap_slots: int = MAX_DAYTIME_GAP_SLOTS,
    require_all_hours_covered: bool = REQUIRE_ALL_HOURS_COVERED,
    daylight_start_hour: int = DAYLIGHT_START_HOUR,
    daylight_end_hour: int = DAYLIGHT_END_HOUR,
) -> Dict[str, Any]:
    """生成写入 build_config / 模型 metadata 的网格契约描述。

    训练侧把它落进快照与模型工件，推理侧读回来用同一组门槛，避免训练/推理漂移。
    """
    return {
        "grid_aligned": True,
        "slots_per_day": SLOTS_PER_DAY,
        "slot_minutes": SLOT_MINUTES,
        "mask_channel": MASK_CHANNEL,
        "night_fill": "zero",
        "daytime_gap_fill": "linear_interp_between_measured",
        "min_occupied_slots": int(min_occupied_slots),
        "min_daytime_occupancy": float(min_daytime_occupancy),
        "max_daytime_gap_slots": int(max_daytime_gap_slots),
        "require_all_hours_covered": bool(require_all_hours_covered),
        "weak_label_fault_hours": [int(daylight_start_hour), int(daylight_end_hour)],
        "label_gap_policy": "explicit point labels only; unlabeled slots stay ignore_index_-1",
    }


def align_day_to_grid(
    times: Any,
    values: np.ndarray,
    labels: Optional[np.ndarray] = None,
    *,
    min_occupied_slots: int = MIN_OCCUPIED_SLOTS,
    min_daytime_occupancy: float = MIN_DAYTIME_OCCUPANCY,
    max_daytime_gap_slots: int = MAX_DAYTIME_GAP_SLOTS,
    require_all_hours_covered: bool = REQUIRE_ALL_HOURS_COVERED,
    daylight_start_hour: int = DAYLIGHT_START_HOUR,
    daylight_end_hour: int = DAYLIGHT_END_HOUR,
) -> GridAlignResult:
    """把一个设备-天的不规则采样对齐到 288 槽自然日网格。

    Parameters
    ----------
    times:
        该设备-天的测量时间戳，长度与 ``values`` 行数一致，允许乱序与重复。
    values:
        ``[n_rows, n_channels]`` 测量值，通常是 ``[value, i_cal]``。
    labels:
        ``[n_rows]`` 逐点业务标签；``None`` 表示本次只对齐测量值。
        传入前应已完成「夜间弱标签清零」等来源裁决。

    Returns
    -------
    GridAlignResult
        ``ok=False`` 时 ``reason`` 说明拒绝原因，调用方应跳过该设备-天。
    """
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError(f"values 必须是 [n_rows, n_channels]，收到 {values.shape}")
    n_channels = values.shape[1]

    slots = slot_of(times)
    if slots.shape[0] != values.shape[0]:
        raise ValueError("times 与 values 行数不一致")
    if labels is not None:
        labels = np.asarray(labels, dtype=np.int64).ravel()
        if labels.shape[0] != values.shape[0]:
            raise ValueError("labels 与 values 行数不一致")

    grid_values = np.full((SLOTS_PER_DAY, n_channels), np.nan, dtype=np.float64)
    grid_labels = np.full(SLOTS_PER_DAY, IGNORE_LABEL, dtype=np.int64)
    measured = np.zeros(SLOTS_PER_DAY, dtype=bool)

    row_is_finite = np.isfinite(values).all(axis=1)
    in_range = (slots >= 0) & (slots < SLOTS_PER_DAY)
    # 同槽多行时后写的覆盖先写的，与既有 drop_duplicates(keep="last") 口径一致。
    for row in range(values.shape[0]):
        if not in_range[row]:
            continue
        slot = int(slots[row])
        if labels is not None:
            grid_labels[slot] = int(labels[row])
        if not row_is_finite[row]:
            # 行存在但测量值缺失：标签仍可用，测量值交给插补。
            continue
        grid_values[slot] = values[row]
        measured[slot] = True

    is_daytime = daytime_slot_mask(daylight_start_hour, daylight_end_hour)
    is_night = ~is_daytime
    occupied_slots = int(measured.sum())
    daytime_total = int(is_daytime.sum())
    daytime_occupancy = (
        float(measured[is_daytime].sum() / daytime_total) if daytime_total else 0.0
    )
    hours_covered = int(np.unique(np.arange(SLOTS_PER_DAY)[measured] // SLOTS_PER_HOUR).size)
    longest_daytime_gap = _longest_run(is_daytime & ~measured)
    is_full_day = bool(hours_covered == 24 and occupied_slots >= int(min_occupied_slots))

    def _reject(reason: str) -> GridAlignResult:
        return GridAlignResult(
            ok=False,
            reason=reason,
            values=None,
            measured_mask=None,
            labels=None,
            occupied_slots=occupied_slots,
            daytime_occupancy=daytime_occupancy,
            hours_covered=hours_covered,
            longest_daytime_gap=longest_daytime_gap,
            is_full_day=is_full_day,
        )

    if occupied_slots == 0:
        return _reject("no_measured_slot")
    if occupied_slots < int(min_occupied_slots):
        return _reject("occupancy_below_threshold")
    if daytime_occupancy < float(min_daytime_occupancy):
        return _reject("daytime_occupancy_below_threshold")
    if longest_daytime_gap > int(max_daytime_gap_slots):
        return _reject("daytime_gap_too_long")
    # 整小时无实测的天在训练侧本来就会被剔除；推理侧必须用同一条规则 fail closed，
    # 否则「缺一整个夜间小时但总占有率达标」的输入只有线上会被接受。
    if require_all_hours_covered and hours_covered < 24:
        return _reject("hours_not_fully_covered")

    filled = _fill_values(grid_values, measured, is_night)
    grid_labels = _fill_labels(grid_labels, is_night)

    return GridAlignResult(
        ok=True,
        reason=None,
        values=filled.astype(np.float32),
        measured_mask=measured.astype(np.float32),
        labels=grid_labels if labels is not None else None,
        occupied_slots=occupied_slots,
        daytime_occupancy=daytime_occupancy,
        hours_covered=hours_covered,
        longest_daytime_gap=longest_daytime_gap,
        is_full_day=is_full_day,
    )


def _longest_run(flags: np.ndarray) -> int:
    """返回布尔数组里最长的连续 True 段长度。"""
    longest = 0
    current = 0
    for flag in flags:
        if flag:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def _fill_values(
    grid_values: np.ndarray,
    measured: np.ndarray,
    is_night: np.ndarray,
) -> np.ndarray:
    """夜间空槽填 0，白天空槽用相邻实测点线性插值。

    插值只使用实测槽作为锚点，避免把夜间填出来的 0 当作插值端点，从而把 0 拖进
    白天。``np.interp`` 在两端会夹取最近实测值，等价于边界前向/后向填充。
    """
    slot_axis = np.arange(SLOTS_PER_DAY)
    measured_idx = np.flatnonzero(measured)
    filled = np.empty_like(grid_values)
    for channel in range(grid_values.shape[1]):
        column = grid_values[:, channel]
        interpolated = np.interp(slot_axis, measured_idx, column[measured_idx])
        merged = np.where(measured, column, interpolated)
        merged[is_night & ~measured] = 0.0
        filled[:, channel] = merged
    return filled


def _fill_labels(grid_labels: np.ndarray, _is_night: np.ndarray) -> np.ndarray:
    """只保留显式逐点标签；未标注槽位始终保持 ``IGNORE_LABEL``。

    测量值可为 288 点模型输入做插补，但监督标签不能由相邻点、夜间先验或天级裁决推断。
    这样可避免两个同标签点之间整段被误当成人工确认，也不会把纯天级事实广播到序列训练。
    """

    return grid_labels.copy()
# @AI_GENERATED: end
