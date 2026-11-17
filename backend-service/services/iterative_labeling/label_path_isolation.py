# @AI_GENERATED
# -*- coding: utf-8 -*-
"""天/点标签路径隔离：历史分类、来源规范化和迁移作用域对账。

旧表 ``label_ops`` 只作为迁移输入和回滚窗口保留。来源缺失、路径字段冲突、
非完整自然日天操作均进入 ``ambiguous``，禁止按时间范围猜测业务路径。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from services.iterative_labeling.k4_companion_migration import classify_human_day_op
from services.iterative_labeling.point_label_service import (
    DAY_PATH_LABEL_SOURCES,
    LEGACY_DAY_LABEL_SOURCES,
    LEGACY_POINT_LABEL_SOURCES,
    POINT_PATH_LABEL_SOURCES,
)

PATH_POINT = "point"
PATH_DAY = "day"
PATH_AMBIGUOUS = "ambiguous"

POINT_OP_SOURCES = frozenset(POINT_PATH_LABEL_SOURCES | LEGACY_POINT_LABEL_SOURCES)
DAY_OP_SOURCES = frozenset(DAY_PATH_LABEL_SOURCES | LEGACY_DAY_LABEL_SOURCES)
SOURCE_NORMALIZATION = {
    "cluster": "cluster_point",
    "pseudo": "pseudo_point",
    "parquet_day_label": "day_import",
}


def classify_op_path(source_or_op: Union[str, Mapping[str, Any]]) -> str:
    """判断历史操作属于 point/day/ambiguous；完整记录可识别历史 K4 伴生。"""
    if isinstance(source_or_op, Mapping):
        path, _, _ = _classify_record(source_or_op)
        return path
    value = str(source_or_op or "").strip()
    if value in POINT_OP_SOURCES:
        return PATH_POINT
    if value in DAY_OP_SOURCES:
        return PATH_DAY
    return PATH_AMBIGUOUS


def _classify_record(op: Mapping[str, Any]) -> Tuple[str, str, Optional[str]]:
    source = str(op.get("source") or "").strip()
    if not source:
        return PATH_AMBIGUOUS, "missing_source", None

    if source == "human_day":
        target = classify_human_day_op(op)
        if target == "point_rest_normal":
            return PATH_POINT, "historical_k4_companion", target
        if target == "human_day":
            return PATH_DAY, "explicit_full_day", target
        return PATH_AMBIGUOUS, "human_day_parent_or_boundary_conflict", None

    if source in DAY_OP_SOURCES:
        if op.get("parent_op_id"):
            return PATH_AMBIGUOUS, "day_source_has_parent_op", None
        return PATH_DAY, "day_source", SOURCE_NORMALIZATION.get(source, source)

    if source in POINT_OP_SOURCES:
        normalized = SOURCE_NORMALIZATION.get(source, source)
        if normalized == "point_rest_normal" and not op.get("parent_op_id"):
            return PATH_AMBIGUOUS, "point_rest_normal_missing_parent", None
        return PATH_POINT, "point_source", normalized

    return PATH_AMBIGUOUS, "unknown_source", None


def business_date_of_op(op: Mapping[str, Any]) -> Optional[date]:
    """返回完整自然日操作的业务日；边界不完整时返回 None。"""
    t_start = op.get("t_start")
    t_end = op.get("t_end")
    if not isinstance(t_start, datetime) or not isinstance(t_end, datetime):
        return None
    start = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
    if t_start != start or t_end != start + timedelta(days=1):
        return None
    return start.date()


def plan_legacy_ops_by_path(ops: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """把旧 ``label_ops`` 规范化拆分；歧义记录只进入失败明细。"""
    point_ops: List[Dict[str, Any]] = []
    day_ops: List[Dict[str, Any]] = []
    ambiguous: List[Dict[str, Any]] = []
    for op in ops:
        path, reason, normalized_source = _classify_record(op)
        record = dict(op)
        if path == PATH_POINT:
            record["source"] = normalized_source
            point_ops.append(record)
            continue
        if path == PATH_DAY:
            biz = business_date_of_op(op)
            if biz is None:
                ambiguous.append({
                    "op_id": op.get("op_id"),
                    "source": op.get("source"),
                    "reason": "day_op_not_full_natural_day",
                })
                continue
            record["source"] = normalized_source
            record["business_date"] = biz
            day_ops.append(record)
            continue
        ambiguous.append({
            "op_id": op.get("op_id"),
            "source": op.get("source"),
            "reason": reason,
            "parent_op_id": op.get("parent_op_id"),
        })
    return {"point_ops": point_ops, "day_ops": day_ops, "ambiguous": ambiguous}


def materialize_day_labels(day_ops: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """从 active 天操作生成每个设备日唯一 winner。"""
    winners: Dict[Tuple[str, str, str, date], Mapping[str, Any]] = {}
    for op in day_ops:
        if str(op.get("status") or "active") != "active":
            continue
        biz = op.get("business_date") or business_date_of_op(op)
        if biz is None:
            continue
        key = (str(op["site_id"]), str(op["device_id"]), str(op["branch_id"]), biz)
        current = winners.get(key)
        if current is None or _op_rank(op) > _op_rank(current):
            winners[key] = op
    rows: List[Dict[str, Any]] = []
    for (site_id, device_id, branch_id, biz), op in sorted(winners.items()):
        rows.append({
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "business_date": biz,
            "label_id": op.get("label_id"),
            "source": op.get("source"),
            "op_id": op.get("op_id"),
            "reviewer": op.get("reviewer"),
            "label_space_version": op.get("label_space_version"),
        })
    return rows


def _op_rank(op: Mapping[str, Any]) -> Tuple[int, Any, str]:
    return (
        int(op.get("priority") or 0),
        op.get("created_at") or datetime.min,
        str(op.get("op_id") or ""),
    )


def _op_signature(op: Mapping[str, Any], *, include_business_date: bool) -> Tuple[Any, ...]:
    values: List[Any] = [
        str(op.get("source") or ""),
        str(op.get("status") or "active"),
        op.get("t_start"),
        op.get("t_end"),
        op.get("label_id"),
        int(op.get("priority") or 0),
        str(op.get("parent_op_id") or ""),
        str(op.get("rest_of_day_policy") or ""),
    ]
    if include_business_date:
        values.append(str(op.get("business_date") or ""))
    return tuple(values)


def _changed_ops(
    expected: Mapping[str, Mapping[str, Any]],
    actual: Mapping[str, Mapping[str, Any]],
    *,
    include_business_date: bool,
) -> List[Dict[str, Any]]:
    changed: List[Dict[str, Any]] = []
    for op_id in sorted(set(expected) & set(actual)):
        expected_signature = _op_signature(expected[op_id], include_business_date=include_business_date)
        actual_signature = _op_signature(actual[op_id], include_business_date=include_business_date)
        if expected_signature != actual_signature:
            changed.append({
                "op_id": op_id,
                "expected": [str(value) for value in expected_signature],
                "actual": [str(value) for value in actual_signature],
            })
    return changed[:20]


def compare_path_ledgers(
    *,
    legacy_ops: Sequence[Mapping[str, Any]],
    point_ops: Sequence[Mapping[str, Any]],
    day_ops: Sequence[Mapping[str, Any]],
    day_labels: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """按迁移 op_id 作用域对账来源、状态、边界、优先级、父子关系和天 winner。

    新表中切换后产生的合法生产记录不属于本次迁移作用域，只计入
    ``unscoped_*`` 统计，不作为迁移失败。
    """
    plan = plan_legacy_ops_by_path(legacy_ops)
    expected_point = {str(op["op_id"]): op for op in plan["point_ops"]}
    expected_day = {str(op["op_id"]): op for op in plan["day_ops"]}
    actual_point = {str(op["op_id"]): op for op in point_ops}
    actual_day = {str(op["op_id"]): op for op in day_ops}

    expected_day_labels = materialize_day_labels(plan["day_ops"])
    expected_day_keys = {
        (
            str(row["site_id"]), str(row["device_id"]), str(row["branch_id"]),
            str(row["business_date"]), str(row["op_id"]), row.get("label_id"),
            str(row.get("source") or ""),
        )
        for row in expected_day_labels
    }
    scoped_day_ids = set(expected_day)
    actual_day_keys = {
        (
            str(row["site_id"]), str(row["device_id"]), str(row["branch_id"]),
            str(row["business_date"]), str(row["op_id"]), row.get("label_id"),
            str(row.get("source") or ""),
        )
        for row in day_labels
        if str(row.get("op_id") or "") in scoped_day_ids
    }

    mismatches = {
        "point_ops_missing": sorted(set(expected_point) - set(actual_point)),
        "point_ops_changed": _changed_ops(expected_point, actual_point, include_business_date=False),
        "day_ops_missing": sorted(set(expected_day) - set(actual_day)),
        "day_ops_changed": _changed_ops(expected_day, actual_day, include_business_date=True),
        "day_labels_missing": sorted(expected_day_keys - actual_day_keys, key=str)[:20],
        "day_labels_changed_or_extra": sorted(actual_day_keys - expected_day_keys, key=str)[:20],
        "ambiguous": plan["ambiguous"],
    }
    passed = all(not value for value in mismatches.values())
    return {
        "passed": passed,
        "legacy_ops": len(legacy_ops),
        "expected_point_ops": len(expected_point),
        "actual_point_ops_in_scope": len(set(expected_point) & set(actual_point)),
        "unscoped_point_ops": len(set(actual_point) - set(expected_point)),
        "expected_day_ops": len(expected_day),
        "actual_day_ops_in_scope": len(set(expected_day) & set(actual_day)),
        "unscoped_day_ops": len(set(actual_day) - set(expected_day)),
        "expected_day_labels": len(expected_day_labels),
        "actual_day_labels_in_scope": len(actual_day_keys),
        "mismatches": mismatches,
    }
# @AI_GENERATED: end
