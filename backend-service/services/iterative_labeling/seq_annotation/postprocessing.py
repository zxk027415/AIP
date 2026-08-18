# -*- coding: utf-8 -*-
# @AI_GENERATED
"""序列标注预测后处理：统一实验评估与生产推理的点级清理口径。"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Tuple

import numpy as np


DEFAULT_NORMAL_LABEL = 0
DEFAULT_FAULT_WINDOW_HOURS = (7, 17)
DEFAULT_MIN_FAULT_SEGMENT_POINTS = 3


def _strict_json_boolean(value: Any, field_name: str) -> bool:
    """只接受 JSON boolean，避免 ``bool("false")`` 意外开启生产策略。"""
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} 必须为 JSON boolean")
    return value


def build_postprocessing_contract(
    *,
    enabled: bool = True,
    fault_window_hours: Sequence[int] = DEFAULT_FAULT_WINDOW_HOURS,
    min_fault_segment_points: int = DEFAULT_MIN_FAULT_SEGMENT_POINTS,
) -> Dict[str, Any]:
    """构造并校验可持久化的正式后处理契约。"""
    normalized_enabled = _strict_json_boolean(enabled, "enabled")
    if isinstance(fault_window_hours, (str, bytes)):
        raise ValueError("fault_window_hours 必须为二元素数组")
    try:
        if len(fault_window_hours) != 2:
            raise ValueError("fault_window_hours 必须包含开始和结束小时")
        start_hour, end_hour = (
            int(fault_window_hours[0]),
            int(fault_window_hours[1]),
        )
    except (TypeError, ValueError, IndexError, OverflowError) as exc:
        raise ValueError("fault_window_hours 必须为有效的二元素整数数组") from exc
    if not 0 <= start_hour < end_hour <= 24:
        raise ValueError("fault_window_hours 必须满足 0 <= start < end <= 24")
    try:
        min_points = int(min_fault_segment_points)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("min_fault_segment_points 必须为整数") from exc
    if min_points < 1:
        raise ValueError("min_fault_segment_points 必须大于等于 1")
    return {
        "enabled": normalized_enabled,
        "normal_label": DEFAULT_NORMAL_LABEL,
        "force_normal_outside_fault_window": True,
        "fault_window_hours": [start_hour, end_hour],
        "min_fault_segment_points": min_points,
        "short_run_policy": "same_neighbors_else_normal",
    }


def normalize_postprocessing_contract(
    raw_contract: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    """读取模型工件契约；旧工件缺字段时禁用，以保持历史输出不变。"""
    if raw_contract is None:
        return build_postprocessing_contract(enabled=False)
    if not isinstance(raw_contract, Mapping):
        raise ValueError("postprocessing 必须为对象")
    raw = dict(raw_contract)
    if not raw:
        return build_postprocessing_contract(enabled=False)
    contract = build_postprocessing_contract(
        enabled=_strict_json_boolean(raw.get("enabled", False), "enabled"),
        fault_window_hours=raw.get(
            "fault_window_hours", DEFAULT_FAULT_WINDOW_HOURS
        ),
        min_fault_segment_points=raw.get(
            "min_fault_segment_points",
            DEFAULT_MIN_FAULT_SEGMENT_POINTS,
        ),
    )
    try:
        normal_label = int(raw.get("normal_label", DEFAULT_NORMAL_LABEL))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("normal_label 必须为整数") from exc
    if normal_label != DEFAULT_NORMAL_LABEL:
        raise ValueError("当前后处理仅支持业务正常标签 0")
    policy = str(
        raw.get("short_run_policy", "same_neighbors_else_normal")
    ).strip()
    if policy != "same_neighbors_else_normal":
        raise ValueError(f"不支持的短段后处理策略: {policy}")
    contract["normal_label"] = normal_label
    contract["force_normal_outside_fault_window"] = _strict_json_boolean(
        raw.get("force_normal_outside_fault_window", True),
        "force_normal_outside_fault_window",
    )
    contract["short_run_policy"] = policy
    return contract


def postprocess_point_predictions(
    predictions: Sequence[int] | np.ndarray,
    contract: Mapping[str, Any] | None,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """按正式契约清理逐点业务标签，并返回可审计的修改统计。

    规则顺序：先把物理白天窗口外强制设为正常，再清理少于阈值的短 run。
    短 run 左右标签一致时并入邻段；否则短故障段回退为正常。该规则既能去除
    单点故障毛刺，也能填平同一故障段内部极短的正常/异类裂缝。
    """
    normalized = normalize_postprocessing_contract(contract)
    raw = np.asarray(predictions, dtype=np.int64)
    if raw.ndim != 1:
        raise ValueError("predictions 必须是一维逐点标签")
    result = raw.copy()
    if not normalized["enabled"] or len(result) == 0:
        return result, {
            "enabled": bool(normalized["enabled"]),
            "changed_points": 0,
            "forced_normal_points": 0,
            "smoothed_short_run_points": 0,
            "contract": normalized,
        }

    forced_normal_points = 0
    if normalized["force_normal_outside_fault_window"]:
        if len(result) % 24 != 0:
            raise ValueError("启用小时窗口后处理时，序列长度必须能被 24 整除")
        slots_per_hour = len(result) // 24
        start_hour, end_hour = normalized["fault_window_hours"]
        fault_start = int(start_hour) * slots_per_hour
        fault_end = int(end_hour) * slots_per_hour
        outside = np.ones(len(result), dtype=bool)
        outside[fault_start:fault_end] = False
        changed = outside & (result != normalized["normal_label"])
        forced_normal_points = int(changed.sum())
        result[outside] = normalized["normal_label"]

    min_points = int(normalized["min_fault_segment_points"])
    smoothed_points = 0
    if min_points > 1:
        # 第一阶段先填平「左右同标签」之间的短裂缝。例如故障 4 中间夹两个
        # 正常点时，应先合并成完整故障段，不能把两侧短故障先误删。
        bridged = result.copy()
        for start, end, label in _runs(result):
            if end - start >= min_points:
                continue
            left = int(result[start - 1]) if start > 0 else None
            right = int(result[end]) if end < len(result) else None
            if (
                left is not None
                and right is not None
                and left == right
                and left != normalized["normal_label"]
                and left != label
            ):
                bridged[start:end] = left
                smoothed_points += end - start
        result = bridged

        # 第二阶段在合并后的 run 上删除仍然短于阈值的故障毛刺；短正常段只在
        # 第一阶段左右故障同类时才会被填充，不会无依据地扩张故障范围。
        cleaned = result.copy()
        for start, end, label in _runs(result):
            if (
                end - start < min_points
                and label != normalized["normal_label"]
            ):
                cleaned[start:end] = normalized["normal_label"]
                smoothed_points += end - start
        result = cleaned

    return result, {
        "enabled": True,
        "changed_points": int(np.count_nonzero(result != raw)),
        "forced_normal_points": forced_normal_points,
        "smoothed_short_run_points": int(smoothed_points),
        "contract": normalized,
    }


def _runs(values: np.ndarray) -> list[tuple[int, int, int]]:
    """返回半开区间 ``[start, end)`` 的连续同标签 run。"""
    if len(values) == 0:
        return []
    runs: list[tuple[int, int, int]] = []
    start = 0
    current = int(values[0])
    for index in range(1, len(values) + 1):
        if index < len(values) and int(values[index]) == current:
            continue
        runs.append((start, index, current))
        if index < len(values):
            start = index
            current = int(values[index])
    return runs
# @AI_GENERATED: end
