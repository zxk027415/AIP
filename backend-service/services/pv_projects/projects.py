# @AI_GENERATED
"""空项目生命周期服务：创建 / 列表 / 总览（按真实对象计算阶段）。

设计依据：design.md §12（项目列表与创建）、§14（三路径生命周期矩阵）、§22（阶段由真实对象计算，
不额外保存易漂移的“当前步骤”）；requirements.md R1.1–R1.12、R2.1–R2.13、R13.2–R13.4、R13.23–R13.24。

红线：
- 新建项目返回空生命周期，不继承任何 review / 累计 / candidate / registry / cursor / result 状态。
- “从现有项目复制”只复制结构（scenario_id / solution_id），不复制数据与业务状态。
- 项目列表跨领域；每个项目自带 scenario_id 与 solution_id。
- legacy 是只读兼容项目，不能被创建。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects.errors import ScopeError
from services.pv_projects.readiness import evaluate_path_readiness
from services.pv_projects.scope import PRODUCT_SLOTS, ScopeContext
from services.pv_projects.repositories import (
    read_projects_index,
    register_project_in_index,
    update_project_in_index,
)
from services.pv_projects.stores import (
    candidates,
    cumulative_events,
    dataset_profiles,
    dataset_versions,
    ensure_layout,
    executions,
    get_scoped_registry_store,
    reviews,
    snapshots,
    verifications,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_mount_slot(entry: dict[str, Any], mount_slot: Optional[str]) -> str:
    """从目录条目推导挂载路径：显式且适用 → 来源路径且适用 → 唯一适用，否则拒绝。"""
    from services.pv_projects import catalog as catalog_service

    explicit = str(mount_slot or "").strip()
    if explicit:
        # 创建项目**之前**先校验，避免先建出半个项目、随后挂载才失败。
        return catalog_service.assert_entry_mountable(entry, explicit)

    applicable = [
        slot
        for slot, info in (entry.get("applicable_paths") or {}).items()
        if slot in PRODUCT_SLOTS and isinstance(info, dict) and info.get("applicable") is True
    ]
    origin = str(entry.get("origin_slot") or "").strip()
    if origin in applicable:
        return origin
    if len(applicable) == 1:
        return applicable[0]
    raise ScopeError(
        "ambiguous_mount_slot",
        "该数据集没有唯一对应路径，创建时需要指定 mount_slot。",
        next_action="先看适用路径，再选择一条诊断路径",
    )


def create_project(
    *,
    project_name: str,
    owner: Optional[str] = None,
    scenario_id: Optional[str] = None,
    solution_id: Optional[str] = None,
    copy_from_project_id: Optional[str] = None,
    catalog_entry_id: Optional[str] = None,
    mount_slot: Optional[str] = None,
) -> dict[str, Any]:
    """创建项目并登记索引。

    copy_from_project_id 只复制结构（scenario_id / solution_id），不复制任何业务状态。
    catalog_entry_id 若提供：先校验目录条目再创建，创建后挂载（先数据集后路径）。
    """
    from services.pv_projects import catalog as catalog_service

    name = str(project_name or "").strip()
    if not name:
        raise ScopeError("missing_project_name", "缺少项目名称。", next_action="填写项目名称后重试")

    resolved_scenario = str(scenario_id or "").strip() or None
    resolved_solution = str(solution_id or "").strip() or None
    entry_id = str(catalog_entry_id or "").strip() or None
    entry: Optional[dict[str, Any]] = None
    resolved_slot: Optional[str] = None
    if entry_id:
        entry = catalog_service.get_catalog_entry(entry_id)
        if entry is None:
            raise ScopeError(
                "catalog_entry_not_found",
                f"目录里没有条目 {entry_id!r}。",
                next_action="先到数据集目录检测并发布，再创建项目",
            )
        resolved_slot = _resolve_mount_slot(entry, mount_slot)

    # 从现有项目复制结构（只拿 scenario_id / solution_id，绝不拿数据 / 状态）。
    if copy_from_project_id:
        source = get_project(copy_from_project_id)
        if source is None:
            raise ScopeError(
                "source_project_not_found",
                f"复制来源项目不存在：{copy_from_project_id!r}",
                next_action="选择一个已存在的项目作为结构来源",
            )
        resolved_scenario = resolved_scenario or source.get("scenario_id")
        resolved_solution = resolved_solution or source.get("solution_id")

    project_id = f"proj-{uuid.uuid4().hex[:12]}"
    record = register_project_in_index(
        project_id,
        scenario_id=resolved_scenario,
        solution_id=resolved_solution,
        project_name=name,
        owner=str(owner or "").strip() or None,
    )
    # 幂等建骨架目录（不写任何业务数据）。
    for slot in PRODUCT_SLOTS:
        ensure_layout(ScopeContext.create(project_id, slot))

    mounted = None
    if entry is not None and resolved_slot:
        mounted = catalog_service.mount_into_project(
            ScopeContext.create(project_id, resolved_slot),
            str(entry.get("entry_id") or entry_id),
        )
        try:
            set_enabled_slots(project_id, [resolved_slot])
            record = get_project(project_id) or record
        except ScopeError:
            pass

    empty = mounted is None
    return {
        **record,
        "empty_lifecycle": empty,
        "mounted": mounted,
        "mount_slot": resolved_slot,
        "next_action": {
            "action": "查看已挂载数据集与路径模板" if mounted else "接入第一个数据集",
            "href": f"/projects/{project_id}/overview",
        },
    }


_LEGACY_INDEX_ENTRY: dict[str, Any] = {
    "project_id": "legacy",
    "project_name": "历史兼容（只读）",
    "read_only": True,
    "source": "slot_only_compat",
    "note": "现有仅按 slot 分区的历史状态只读映射，不复制到新项目",
}


def list_projects(*, include_legacy: bool = True) -> list[dict[str, Any]]:
    """跨领域列出项目（始终把 legacy 表示为只读映射；GET 不写存储）。"""
    index = read_projects_index()
    projects = [p for p in index.get("projects", []) if isinstance(p, dict)]
    if not include_legacy:
        return [p for p in projects if str(p.get("project_id")) != "legacy"]
    # legacy 是隐式只读兼容项目：若索引未显式登记，合成一条（不修改存储）。
    if not any(str(p.get("project_id")) == "legacy" for p in projects):
        projects = [dict(_LEGACY_INDEX_ENTRY), *projects]
    return projects


def get_project(project_id: str) -> Optional[dict[str, Any]]:
    target = str(project_id or "").strip()
    for project in list_projects():
        if str(project.get("project_id")) == target:
            return project
    return None


# ---------------------------------------------------------------------------
# 生命周期阶段（由真实对象计算）
# ---------------------------------------------------------------------------

def _count_pending_reviews(items: list[dict[str, Any]]) -> int:
    return sum(1 for r in items if str(r.get("status") or "").lower() not in {"completed", "admitted"})


#: readiness 状态 → 数据阶段（仅在该路径尚无下游产物时决定阶段）。
_READINESS_STAGE: dict[str, tuple[str, str, str]] = {
    # status: (stage, 主动作, 目标路由段)
    "needs_mapping": ("DATA_NEEDS_MAPPING", "补齐字段映射", "data"),
    "needs_labels": ("DATA_NEEDS_LABELS", "发起打标", "data"),
    "insufficient_data": ("DATA_INSUFFICIENT", "补充数据覆盖", "data"),
    "unsupported": ("PATH_UNSUPPORTED", "更换数据或诊断路径", "data"),
    # 评估器抛异常：**fail-closed**——可用性未知，绝不回落 DATA_READY（P1-2）。
    "unavailable": ("DATA_READINESS_UNKNOWN", "重新评估数据可用性", "data"),
    "experiment_only": ("DATA_READY", "创建工作流并运行", "workflows"),
    "ready": ("DATA_READY", "创建工作流并运行", "workflows"),
}


#: 训练工作流上能产出"模型工件"的运行目的。
#: `prediction` / `replay` / `validation` 不产模型候选，不构成训练产物。
_TRAINING_PRODUCT_RUN_MODES: tuple[str, ...] = ("training", "experiment")


def _is_training_product(rec: dict[str, Any]) -> bool:
    """该 execution 是否构成"有业务意义的训练产物"（P1-3）。

    要求三条同时成立：
    1. `status == "success"`（failed / cancelled 不产结果）；
    2. `run_mode ∈ {training, experiment}`（prediction / replay / validation 不产模型候选）；
    3. 出自训练用途的工作流（记录无 `workflow_kind` 的历史记录免除本条，
       因为它们已被第 2 条约束住）。
    """
    if str(rec.get("status") or "") != "success":
        return False
    if str(rec.get("run_mode") or "") not in _TRAINING_PRODUCT_RUN_MODES:
        return False
    kind = str(rec.get("workflow_kind") or "")
    if kind:
        return kind == "training"
    return True


def _latest_version_readiness(scope: ScopeContext) -> Optional[dict[str, Any]]:
    """取最新已发布数据版本，评估**当前路径**的 readiness；缺画像返回 needs_mapping。

    数据版本是项目级共享的，但能否走某条路径由 readiness 逐路径判定 —— 这是总览阶段
    不能只看"有没有数据版本"的原因（design §11 差异 1）。
    """
    versions = dataset_versions.list(scope)
    if not versions:
        return None
    version = versions[-1]
    profile_id = str(version.get("dataset_profile_id") or "")
    profile = dataset_profiles.find(scope, profile_id) if profile_id else None
    if profile is None:
        return {
            "status": "needs_mapping",
            "primary_blocker": "profile_not_found",
            "next_action": "补齐字段映射与画像",
            "dataset_version_id": version.get("dataset_version_id"),
        }
    try:
        return evaluate_path_readiness(
            scope, version=version, profile=profile, slot=scope.require_slot()
        )
    except Exception as exc:  # noqa: BLE001 - 评估失败必须 **fail-closed**，不得回落 ready
        # 修复前这里 `return None`，调用方再把 None 当 "ready" → 项目明明有数据版本
        # 却给出 DATA_READY（fail-open），把画像 / 合同错误整个掩盖掉。
        return {
            "status": "unavailable",
            "primary_blocker": "readiness_evaluation_failed",
            "next_action": "检查画像 / 路径合同配置后重新评估",
            "dataset_version_id": version.get("dataset_version_id"),
            "error": f"{type(exc).__name__}: {exc}",
        }


def compute_slot_lifecycle(scope: ScopeContext) -> dict[str, Any]:
    """由 scoped 真实对象计算单条路径的阶段、证据摘要与唯一下一步。"""
    versions = dataset_versions.list(scope)
    execs = executions.list(scope)
    cands = candidates.list(scope)
    vers = verifications.list(scope)
    revs = reviews.list(scope)
    events = cumulative_events.list(scope)
    snaps = snapshots.list(scope)
    registry = get_scoped_registry_store().get(scope)

    passed_verifications = [v for v in vers if v.get("passed") is True]
    rolling_set = bool(registry.get("rolling_detect_model"))
    pending_reviews = _count_pending_reviews(revs)
    # 只有 governance_eligible=true 的候选才是"可治理（待复验）候选"；validation / experiment /
    # sandbox 来源的候选是"实验结果"，不能据其判定为治理阶段（与四层治理页口径一致）。
    governable_cands = [c for c in cands if c.get("governance_eligible") is True]
    experiment_cands = [c for c in cands if c.get("governance_eligible") is not True]
    # P1-3：只有"成功且出自训练用途"的执行才构成有业务意义的训练产物。
    # failed / cancelled / prediction / replay 执行不得推进阶段（否则会给出
    # "登记为可治理候选"这种无凭据的指引）。
    training_products = [e for e in execs if _is_training_product(e)]

    facts = {
        "dataset_versions": len(versions),
        "executions": len(execs),
        "candidates": len(governable_cands),
        "verifications_passed": len(passed_verifications),
        "rolling_model_set": rolling_set,
        "reviews_pending": pending_reviews,
        "snapshots": len(snaps),
        "cumulative_events": len(events),
    }

    # 阶段推导（design §22 线性主链的粗粒度投影；不覆盖各对象自身状态）。
    # 每个阶段附 stage_reason，明确“由哪条真实证据判定”，即证据化状态（非臆测/推断）。
    # 顺序：**下游产物优先**（走得最远的赢）；该路径尚无任何下游产物时，才由 readiness 决定数据阶段。
    # readiness 与 stage 是**两个独立问题**：
    #   - stage：这条路径走到哪了（由真实对象计算，下游产物优先）
    #   - readiness：**当前最新数据版本**能不能喂这条路径（始终有意义，即便已有下游产物 ——
    #     新发布的数据版本可能不再满足该路径口径，这个事实必须可见，不能被阶段掩盖）
    # 因此这里**始终计算** readiness；它只在"尚无下游产物"时参与决定 stage。
    readiness: Optional[dict[str, Any]] = _latest_version_readiness(scope) if versions else None

    if not versions:
        stage, action, href = "UNCONFIGURED", "接入数据", f"/projects/{scope.project_id}/data"
        reason = "无已发布数据版本（dataset_versions=0）"
    elif rolling_set:
        stage, action, href = "ROLLING_MODEL_SELECTED", "查看检测与回放", f"/projects/{scope.project_id}/operations"
        reason = "registry.rolling_detect_model 已设置（证据：滚动指针存在）"
    elif passed_verifications:
        stage, action, href = "VERIFIED", "设为下一轮检测模型", f"/projects/{scope.project_id}/models"
        reason = f"存在 {len(passed_verifications)} 条 passed=true 的正式复验"
    elif governable_cands:
        stage, action, href = "GOVERNANCE_CANDIDATE", "发起正式复验", f"/projects/{scope.project_id}/models"
        reason = f"存在 {len(governable_cands)} 个可治理候选，但无 passed 复验"
    elif snaps:
        # 已冻结快照优先于未完成审核：冻结是"已产出"的事实，审核积压是"待办"，
        # 已产出不应被待办覆盖（否则已冻结的路径会退回"完成审核"，丢失进度）。
        stage, action, href = "SNAPSHOT_READY", "基于快照创建训练工作流", f"/projects/{scope.project_id}/workflows"
        reason = f"已冻结 {len(snaps)} 个快照，可基于快照训练（仍需过候选治理）"
    elif pending_reviews > 0:
        stage, action, href = "REVIEW_PENDING", "完成审核", f"/projects/{scope.project_id}/reviews"
        reason = f"有 {pending_reviews} 个未完成审核会话"
    elif training_products:
        stage, action, href = "EXPERIMENT_RESULT", "登记为可治理候选", f"/projects/{scope.project_id}/models"
        _exp = f"，另有 {len(experiment_cands)} 个非可治理实验候选" if experiment_cands else ""
        reason = (
            f"已有 {len(training_products)} 次成功的训练执行，"
            f"但无可治理候选 / 复验 / 指针{_exp}"
        )
    else:
        # 尚无有业务意义的下游产物（失败执行、预测执行都不算）→ 由 readiness 决定数据阶段。
        # 有项目级数据版本 ≠ 这条路径可用：逐路径 readiness 说话（修正总览误判为“数据就绪”）。
        # 缺省值取 `unavailable`（fail-closed），不取 `ready`——评估缺失不应被读成"就绪"。
        r_status = str((readiness or {}).get("status") or "unavailable")
        stage, action, seg = _READINESS_STAGE.get(
            r_status, ("DATA_READINESS_UNKNOWN", "重新评估数据可用性", "data")
        )
        href = f"/projects/{scope.project_id}/{seg}"
        blocker = (readiness or {}).get("primary_blocker")
        if r_status in ("ready", "experiment_only"):
            reason = f"该路径 readiness={r_status}，可创建工作流（ready 不等于生产资格）"
        else:
            reason = f"该路径 readiness={r_status}" + (f"，首要阻断：{blocker}" if blocker else "")
        action = (readiness or {}).get("next_action") or action

    return {
        "project_id": scope.project_id,
        "slot": scope.slot,
        "stage": stage,
        "stage_reason": reason,
        # 该路径最新数据版本的 readiness 始终独立计算；有下游产物时也不被 stage 掩盖。
        "readiness_status": (readiness or {}).get("status"),
        "readiness_primary_blocker": (readiness or {}).get("primary_blocker"),
        "facts": facts,
        "primary_next_action": {"action": action, "href": href},
    }


def set_enabled_slots(project_id: str, slots: Optional[list[str]]) -> dict[str, Any]:
    """确认项目启用的诊断路径（intent）。

    设计约定：**在 readiness 出来之后确认**，避免盲选。传 None 表示撤销确认（回到未确认）。
    只校验取值合法性，不校验可行性 —— 可行性由 readiness 逐路径给出，两者在总览上叠加展示。
    """
    if slots is None:
        return update_project_in_index(project_id, enabled_slots=None)
    cleaned: list[str] = []
    for raw in slots:
        key = str(raw or "").strip()
        if key not in PRODUCT_SLOTS:
            raise ScopeError(
                "invalid_slot",
                f"启用路径含非法取值 {key!r}；允许 {list(PRODUCT_SLOTS)}",
                next_action="只提交 pv_day / pv_point / pv_tsc",
            )
        if key not in cleaned:
            cleaned.append(key)
    if not cleaned:
        raise ScopeError(
            "empty_enabled_slots",
            "启用路径不能为空列表；如需撤销确认请提交 null。",
        )
    return update_project_in_index(project_id, enabled_slots=cleaned)


def _workflow_brief(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_workflow_id": item.get("project_workflow_id"),
        "name": item.get("name"),
        "workflow_kind": item.get("workflow_kind"),
        "source_template_id": item.get("source_template_id"),
        "version": item.get("version"),
    }


def _path_templates() -> dict[str, list[dict[str, Any]]]:
    """按路径列出 canonical 模板，避免 overview 去 import workflows_enhanced。"""
    import json
    from pathlib import Path

    wf_dir = Path(__file__).resolve().parents[2] / "data" / "workflows_enhanced"
    out: dict[str, list[dict[str, Any]]] = {}
    for slot in PRODUCT_SLOTS:
        prefix = f"workflow-{slot.replace('_', '-')}"
        templates: list[dict[str, Any]] = []
        if wf_dir.is_dir():
            for path in sorted(wf_dir.glob(f"{prefix}*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                stem = path.stem
                templates.append(
                    {
                        "template_id": str(payload.get("id") or stem),
                        "name": str(payload.get("name") or stem),
                        "description": str(payload.get("description") or ""),
                        "node_count": len(payload.get("nodes") or []),
                    }
                )
        out[slot] = templates
    return out


def _mounted_datasets(
    project_id: str, templates: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """项目已挂载数据集 → 对应路径 → 该路径工作流 / 模板。"""
    from services.pv_projects import catalog as catalog_service
    from services.pv_projects import datasets as dataset_service
    from services.pv_projects import governance as governance_service
    from services.pv_projects import workflows as workflow_service

    scope0 = ScopeContext.create(project_id)
    assets = dataset_service.list_dataset_assets(scope0)
    catalog_by_id = {
        str(entry.get("entry_id") or ""): entry
        for entry in catalog_service.list_catalog()
        if isinstance(entry, dict)
    }
    catalog_by_ref = {
        str(entry.get("dataset_ref") or ""): entry
        for entry in catalog_by_id.values()
        if entry.get("dataset_ref")
    }
    rows: list[dict[str, Any]] = []
    for asset in assets:
        entry = catalog_by_id.get(str(asset.get("catalog_entry_id") or "")) or catalog_by_ref.get(
            str(asset.get("dataset_ref") or "")
        )
        origin = None
        applicable_slots: list[str] = []
        display_name = asset.get("file_name") or asset.get("dataset_ref")
        if entry:
            origin = str(entry.get("origin_slot") or "").strip() or None
            display_name = entry.get("display_name") or display_name
            applicable_slots = [
                slot
                for slot, info in (entry.get("applicable_paths") or {}).items()
                if slot in PRODUCT_SLOTS and isinstance(info, dict) and info.get("applicable")
            ]
        if not origin:
            origin = catalog_service.infer_origin_slot(str(asset.get("dataset_ref") or ""))
        # 已发布目录条目的 applicable_paths 是适用性真源；不能因为 origin_slot 相同
        # 就把明确不适用的普通数据重新塞回该路径。仅旧资产查不到目录条目时，才按引用
        # 推断 origin 作为兼容兜底。
        if entry is None and not applicable_slots and origin in PRODUCT_SLOTS:
            applicable_slots = [origin]
        model_inheritance = None
        if (
            entry
            and str(entry.get("origin") or "") == catalog_service.ORIGIN_PATH_CUMULATIVE
            and origin in PRODUCT_SLOTS
        ):
            model_inheritance = governance_service.ensure_inherited_baseline(
                ScopeContext.create(project_id, origin),
                entry=entry,
                asset=asset,
                link_basis="lazy_backfill_current_slot_model",
            )
        workflows_by_slot: dict[str, list[dict[str, Any]]] = {}
        for slot in applicable_slots or []:
            items = workflow_service.list_project_workflows(ScopeContext.create(project_id, slot))
            workflows_by_slot[slot] = [_workflow_brief(item) for item in items]
        rows.append(
            {
                "dataset_id": asset.get("dataset_id"),
                "dataset_ref": asset.get("dataset_ref"),
                "file_name": asset.get("file_name"),
                "source_kind": asset.get("source_kind"),
                "catalog_entry_id": asset.get("catalog_entry_id"),
                "display_name": display_name,
                "origin_slot": origin if origin in PRODUCT_SLOTS else None,
                "applicable_slots": applicable_slots,
                "workflows_by_slot": workflows_by_slot,
                "templates_by_slot": {slot: templates.get(slot) or [] for slot in applicable_slots},
                "model_inheritance": model_inheritance,
            }
        )
    return rows


def project_overview(project_id: str) -> dict[str, Any]:
    """项目总览：已挂载数据集优先，三条路径生命周期仍返回（平台页用，项目页不再当主视图）。

    始终返回三条路径（不隐藏），并回显 `enabled_slots` — 项目启用意图。
    """
    scope0 = ScopeContext.create(project_id)
    project = get_project(scope0.project_id)
    enabled = (project or {}).get("enabled_slots")
    templates = _path_templates()
    # 先组装挂载数据：这一步会为历史累计快照做幂等模型补链；随后再计算生命周期，
    # 同一响应里就能读到最新 registry，而不是必须刷新第二次。
    mounted_datasets = _mounted_datasets(scope0.project_id, templates)
    paths = [compute_slot_lifecycle(ScopeContext.create(scope0.project_id, slot)) for slot in PRODUCT_SLOTS]
    return {
        "project_id": scope0.project_id,
        "project_name": (project or {}).get("project_name"),
        "enabled_slots": enabled if isinstance(enabled, list) else None,
        "scenario_id": (project or {}).get("scenario_id"),
        "solution_id": (project or {}).get("solution_id"),
        "read_only": scope0.read_only,
        "paths": paths,
        "mounted_datasets": mounted_datasets,
        "path_templates": templates,
        "computed_at": _now_iso(),
    }


# @AI_GENERATED: end
