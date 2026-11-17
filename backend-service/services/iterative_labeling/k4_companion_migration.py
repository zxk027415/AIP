# @AI_GENERATED
# -*- coding: utf-8 -*-
"""把历史 K4 伴生 human_day 改写成点路径来源 point_rest_normal。

判定只看操作账本字段，禁止猜测：
- human_day + parent_op_id + rest_of_day_policy=normal + label_id=0 → point_rest_normal
- human_day + 无 parent + 完整自然日 → 保留真正天裁决
- 其余 human_day → 失败明细，不自动改写
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from services.iterative_labeling.point_label_service import (
    K4_COMPANION_SOURCE,
    NORMAL_LABEL_ID,
)

_KEEP_DAY = "human_day"
_AMBIGUOUS = "ambiguous"


def classify_human_day_op(op: Mapping[str, Any]) -> str:
    """把一条现有 human_day 操作分到点路径伴生、真正天裁决或无法判定。"""
    if str(op.get("source") or "") != "human_day":
        raise ValueError("classify_human_day_op 只接受 source=human_day")
    parent_op_id = op.get("parent_op_id")
    policy = str(op.get("rest_of_day_policy") or "")
    label_id = op.get("label_id")
    if parent_op_id and policy == "normal" and label_id == NORMAL_LABEL_ID:
        return K4_COMPANION_SOURCE
    if parent_op_id:
        return _AMBIGUOUS
    if _is_full_natural_day(op.get("t_start"), op.get("t_end")):
        return _KEEP_DAY
    return _AMBIGUOUS


def _is_full_natural_day(t_start: Any, t_end: Any) -> bool:
    if t_start is None or t_end is None:
        return False
    start = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return t_start == start and t_end == start + timedelta(days=1)


def plan_k4_companion_source_rewrite(
    ops: Iterable[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """对一组 label_ops 生成改写计划，不写库。"""
    migrate: List[Dict[str, Any]] = []
    keep_day: List[Dict[str, Any]] = []
    ambiguous: List[Dict[str, Any]] = []
    for op in ops:
        if str(op.get("source") or "") != "human_day":
            continue
        target = classify_human_day_op(op)
        record = {
            "op_id": op.get("op_id"),
            "parent_op_id": op.get("parent_op_id"),
            "status": op.get("status"),
            "from_source": "human_day",
            "to_source": target if target != _AMBIGUOUS else None,
            "reason": target,
        }
        if target == K4_COMPANION_SOURCE:
            migrate.append(record)
        elif target == _KEEP_DAY:
            keep_day.append(record)
        else:
            ambiguous.append(record)
    return {
        "migrate_to_point_rest_normal": migrate,
        "keep_human_day": keep_day,
        "ambiguous": ambiguous,
    }


def apply_k4_companion_source_rewrite(
    ops: Iterable[MutableMapping[str, Any]],
    points: Iterable[MutableMapping[str, Any]],
) -> Dict[str, int]:
    """在内存结构上改写操作和物化点的 source；用于单测，不连库。"""
    plan = plan_k4_companion_source_rewrite(ops)
    if plan["ambiguous"]:
        raise ValueError(
            f"存在 {len(plan['ambiguous'])} 条无法判定的 human_day，拒绝自动改写"
        )
    migrate_ids = {item["op_id"] for item in plan["migrate_to_point_rest_normal"]}
    op_count = 0
    for op in ops:
        if op.get("op_id") in migrate_ids:
            op["source"] = K4_COMPANION_SOURCE
            op_count += 1
    point_count = 0
    for point in points:
        if point.get("op_id") in migrate_ids:
            point["source"] = K4_COMPANION_SOURCE
            point_count += 1
    return {"ops_rewritten": op_count, "points_rewritten": point_count}
# @AI_GENERATED: end
