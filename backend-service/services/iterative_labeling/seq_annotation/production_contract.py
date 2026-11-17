# -*- coding: utf-8 -*-
# @AI_GENERATED
"""最终序列模型的生产准入契约；训练登记、Promote 与调度加载共用。"""
from __future__ import annotations

from math import isclose
from typing import Any, Dict, Mapping


FINAL_MODEL_NAME = "bilstm_attn"
FINAL_CHANNELS = ("value", "i_cal", "is_measured")
FINAL_LOSS = "cross_entropy"
FINAL_SEGMENT_BOUNDARY_WEIGHT = 4.0
FINAL_FAULT_WINDOW_HOURS = (7, 17)
FINAL_MIN_FAULT_SEGMENT_POINTS = 3


def _mapping_field(
    value: Any,
    field_name: str,
    errors: list[str],
) -> Mapping[str, Any]:
    """安全读取 JSON object；损坏结构只形成契约差异，不泄漏 TypeError。"""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        errors.append(f"{field_name} 必须为对象")
        return {}
    return value


def _integer(value: Any) -> int | None:
    """将整数型契约值安全归一化；非法值交由调用方记录差异。"""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _require_true(value: Any, field_name: str, errors: list[str]) -> bool:
    """只接受真实 JSON boolean ``true``，拒绝 ``"false"`` 等真值字符串。"""
    if value is True:
        return True
    if value is not None and not isinstance(value, bool):
        errors.append(f"{field_name} 必须为 JSON boolean")
    errors.append(f"{field_name} 必须为 true")
    return False


def final_sequence_contract_errors(payload: Mapping[str, Any] | None) -> list[str]:
    """返回最终生产方案的契约差异；任意损坏 JSON 均安全失败。"""
    errors: list[str] = []
    if payload is None:
        contract: Mapping[str, Any] = {}
    elif isinstance(payload, Mapping):
        contract = payload
    else:
        return ["seq_annotation 生产契约必须为对象"]

    training = _mapping_field(
        contract.get("training_config"), "training_config", errors
    )
    weighting_source = contract.get("sequence_weighting")
    if weighting_source is None:
        weighting_source = training.get("sequence_weighting")
    weighting = _mapping_field(
        weighting_source, "sequence_weighting", errors
    )
    postprocessing = _mapping_field(
        contract.get("postprocessing"), "postprocessing", errors
    )
    grid_contract = _mapping_field(
        contract.get("grid_contract"), "grid_contract", errors
    )

    if str(contract.get("model_name") or "") != FINAL_MODEL_NAME:
        errors.append(f"model_name 必须为 {FINAL_MODEL_NAME}")
    channels = contract.get("channels")
    normalized_channels = (
        tuple(str(value) for value in channels)
        if isinstance(channels, (list, tuple))
        else ()
    )
    if normalized_channels != FINAL_CHANNELS:
        errors.append(f"channels 必须为 {list(FINAL_CHANNELS)}")
    if _integer(contract.get("seq_len")) != 288:
        errors.append("seq_len 必须为 288")
    _require_true(contract.get("trained_full_day"), "trained_full_day", errors)

    top_grid = contract.get("grid_aligned")
    nested_grid = grid_contract.get("grid_aligned")
    if top_grid is not None and not isinstance(top_grid, bool):
        errors.append("grid_aligned 必须为 JSON boolean")
    if nested_grid is not None and not isinstance(nested_grid, bool):
        errors.append("grid_contract.grid_aligned 必须为 JSON boolean")
    if top_grid is not True and nested_grid is not True:
        errors.append("grid_aligned 必须为 true")

    loss = str(contract.get("loss") or training.get("loss") or "")
    if loss != FINAL_LOSS:
        errors.append(f"loss 必须为 {FINAL_LOSS}")
    if str(weighting.get("field") or "") != "data_type":
        errors.append("sequence_weighting.field 必须为 data_type")
    if str(weighting.get("match") or "") != "segment_boundary":
        errors.append("sequence_weighting.match 必须为 segment_boundary")
    try:
        multiplier = float(weighting.get("multiplier"))
    except (TypeError, ValueError, OverflowError):
        multiplier = float("nan")
    if not isclose(multiplier, FINAL_SEGMENT_BOUNDARY_WEIGHT, rel_tol=0.0, abs_tol=1e-9):
        errors.append("segment_boundary multiplier 必须为 4.0")

    _require_true(
        postprocessing.get("enabled"), "postprocessing.enabled", errors
    )
    fault_window = postprocessing.get("fault_window_hours")
    normalized_window = (
        tuple(fault_window) if isinstance(fault_window, (list, tuple)) else ()
    )
    if normalized_window != FINAL_FAULT_WINDOW_HOURS:
        errors.append("postprocessing.fault_window_hours 必须为 [7, 17]")
    if (
        _integer(postprocessing.get("min_fault_segment_points"))
        != FINAL_MIN_FAULT_SEGMENT_POINTS
    ):
        errors.append("postprocessing.min_fault_segment_points 必须为 3")
    _require_true(
        postprocessing.get("force_normal_outside_fault_window"),
        "postprocessing.force_normal_outside_fault_window",
        errors,
    )
    if str(postprocessing.get("short_run_policy") or "") != "same_neighbors_else_normal":
        errors.append("postprocessing.short_run_policy 不符合最终方案")
    return errors


def assert_final_sequence_contract(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    """校验最终生产模型契约，不符合时阻止 Promote 或调度加载。"""
    errors = final_sequence_contract_errors(payload)
    if errors:
        raise ValueError("seq_annotation 最终生产契约不满足: " + "; ".join(errors))
    return dict(payload or {})
# @AI_GENERATED: end
