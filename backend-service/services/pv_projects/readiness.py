# @AI_GENERATED
"""三路径 readiness 评估器（PathReadinessEvaluator）。

设计依据：design.md §13 第 6 步、§25（readiness 合同）；requirements.md R13.13–R13.21、
R13.23–R13.27、R14.7–R14.9、R14.14–R14.15、R14.23–R14.25。

读取不可变数据版本与其画像，为三条诊断路径分别输出：
status / facts / blockers / allowed_run_modes / primary_blocker（后端选定）/ next_action。
每条路径独立评估，不给项目一个模糊总分；ready 不等于生产 / 候选 / Promote 资格；
readiness 现算现取（不缓存），并回显 profile 摘要供前端判定过期（profile / 合同变化即视为过期）。
"""

from __future__ import annotations

from typing import Any, Optional

from services.pv_projects.errors import ScopeError
from services.pv_projects.scope import PRODUCT_SLOTS, ScopeContext
from services.pv_projects.stores import dataset_profiles, dataset_versions

#: 三路径共同必需的字段映射。
REQUIRED_MAPPING_FIELDS = ("time_col", "device_col", "value_col")

_ALLOWED_RUN_MODES: dict[str, list[str]] = {
    "needs_mapping": [],
    "needs_labels": ["experiment"],
    "insufficient_data": ["experiment"],
    "experiment_only": ["experiment"],
    "unsupported": [],
    "ready": ["experiment", "validation"],
}

_NEXT_ACTION: dict[str, str] = {
    "needs_mapping": "补齐字段映射（时间 / 设备 / 实测值）",
    "needs_labels": "发起打标（TSC 可走 canonical 模型辅助打标）",
    "insufficient_data": "补充数据覆盖（日期 / 设备 / 类别 / 采样）",
    "experiment_only": "创建实验工作流（生产资格待覆盖事实确认）",
    "unsupported": "更换数据或诊断路径",
    "ready": "创建工作流并运行",
}


def _mapping_gaps(mapping: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_MAPPING_FIELDS if not str(mapping.get(field) or "").strip()]


def _is_empty_dataset(facts: dict[str, Any]) -> bool:
    """facts **已由服务端算出**且显示没有可用数据（区别于「根本没算过」）。

    只认 `facts_source == "computed_from_file"` 的 facts：客户端传入的空 dict 或占位 facts
    不应被判成 insufficient_data —— 那会把「没检测」误报成「数据不足」，掩盖真正的原因。
    """
    if not facts or str(facts.get("facts_source") or "") != "computed_from_file":
        return False
    return int(facts.get("row_count") or 0) == 0 or int(facts.get("device_count") or 0) == 0


def _label_status_for_slot(slot: str, granularity: str) -> tuple[Optional[str], list[dict[str, Any]]]:
    """按路径判断标签就绪状态；返回 (阻断态 或 None 表示已具备标签或允许无标签实验, blockers)。"""
    blockers: list[dict[str, Any]] = []
    if slot == "pv_point":
        if granularity in ("point", "interval"):
            return None, blockers
        if granularity == "device_day":
            blockers.append(
                {
                    "reason_code": "device_day_label_not_point_truth",
                    "severity": "blocking",
                    "current_value": "device_day",
                    "required_value": "point/interval labels",
                }
            )
            return "needs_labels", blockers
        # 无标签：允许无标签因果 Sandbox replay（experiment_only），不是 needs_labels 阻断。
        return "experiment_only", blockers
    if slot == "pv_tsc":
        if granularity in ("device_day", "point", "interval"):
            return None, blockers
        blockers.append(
            {
                "reason_code": "needs_labels_canonical_available",
                "severity": "blocking",
                "current_value": "none",
                "required_value": "labels（可走 canonical 模型辅助打标）",
            }
        )
        return "needs_labels", blockers
    # pv_day（设备日监督）
    if granularity in ("device_day", "point", "interval"):
        return None, blockers
    blockers.append(
        {
            "reason_code": "needs_device_day_labels",
            "severity": "blocking",
            "current_value": "none",
            "required_value": "device-day labels",
        }
    )
    return "needs_labels", blockers


def evaluate_path_readiness(
    scope: ScopeContext,
    *,
    version: dict[str, Any],
    profile: dict[str, Any],
    slot: str,
) -> dict[str, Any]:
    """评估单条路径的 readiness。"""
    mapping = profile.get("mapping") or {}
    label_policy = profile.get("label_policy") or {}
    facts = profile.get("facts") or {}
    granularity = str(label_policy.get("granularity") or "").strip()

    blockers: list[dict[str, Any]] = []
    gaps = _mapping_gaps(mapping)
    if gaps:
        status = "needs_mapping"
        blockers.append(
            {
                "reason_code": "missing_field_mapping",
                "severity": "blocking",
                "current_value": f"missing={gaps}",
                "required_value": "time_col / device_col / value_col",
            }
        )
    else:
        label_state, label_blockers = _label_status_for_slot(slot, granularity)
        blockers.extend(label_blockers)
        if label_state is not None:
            status = label_state
        elif _is_empty_dataset(facts):
            # facts 已算出且显示**没有可用数据** → 比 experiment_only 更早的阻断：
            # 该补数据，而不是去做实验。此前这条状态从不被赋值（死状态）。
            status = "insufficient_data"
            blockers.append(
                {
                    "reason_code": "no_usable_rows",
                    "severity": "blocking",
                    "current_value": f"rows={facts.get('row_count')} devices={facts.get('device_count')}",
                    "required_value": "至少 1 行可解析数据 + 至少 1 台设备",
                }
            )
        else:
            # 映射与标签具备：需覆盖事实确认才判 ready，否则诚实降级为 experiment_only。
            if bool(facts.get("sufficient_coverage")):
                status = "ready"
            else:
                status = "experiment_only"
                blockers.append(
                    {
                        "reason_code": "coverage_facts_unconfirmed",
                        "severity": "warning",
                        "current_value": "facts_missing",
                        "required_value": "日期 / 设备 / 类别 / 采样覆盖事实",
                    }
                )

    facts_list = (
        [{"fact": key, "value": value} for key, value in facts.items()]
        if facts
        else [
            {
                "fact": "coverage_facts",
                "value": "未计算",
                "impact": "无法确认生产级覆盖，暂按 experiment_only 处理",
                "fix": "补充画像覆盖事实（需真实数据解析）后可判定 ready",
            }
        ]
    )
    primary_blocker = blockers[0]["reason_code"] if blockers else None

    return {
        "project_id": scope.project_id,
        "slot": slot,
        "dataset_version_id": version.get("dataset_version_id"),
        "dataset_profile_id": profile.get("dataset_profile_id"),
        "status": status,
        "facts": facts_list,
        "blockers": blockers,
        "allowed_run_modes": list(_ALLOWED_RUN_MODES.get(status, [])),
        "primary_blocker": primary_blocker,
        "next_action": _NEXT_ACTION.get(status),
        # ready 不等于生产资格（红线）。
        "not_production_eligible_note": "ready 只表示当前路径输入与预检合同可用，不表示生产 / 候选 / Promote 资格。",
        # profile 摘要变化即视为 readiness 过期（前端据此标 STALE）。
        "computed_from_profile_digest": profile.get("mapping_digest"),
    }


def evaluate_all_paths(scope: ScopeContext, dataset_version_id: str) -> dict[str, Any]:
    """对一个不可变数据版本评估三条路径 readiness；回显 scope。"""
    version = dataset_versions.find(scope, dataset_version_id)
    if version is None:
        raise ScopeError(
            "dataset_version_not_found",
            f"当前项目下找不到数据版本 {dataset_version_id!r}。",
            next_action="先发布一个不可变数据版本",
            scope=scope.echo(),
        )
    profile_id = str(version.get("dataset_profile_id") or "")
    profile = dataset_profiles.find(scope, profile_id) if profile_id else None
    if profile is None:
        raise ScopeError(
            "profile_not_found",
            f"数据版本 {dataset_version_id!r} 关联的画像 {profile_id!r} 缺失。",
            scope=scope.echo(),
        )

    paths = [
        evaluate_path_readiness(scope, version=version, profile=profile, slot=slot)
        for slot in PRODUCT_SLOTS
    ]
    return {
        "project_id": scope.project_id,
        "dataset_version_id": dataset_version_id,
        "dataset_profile_id": profile_id,
        "paths": paths,
    }


# @AI_GENERATED: end
