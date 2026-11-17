# @AI_GENERATED
"""项目工作流创建 + 数据绑定 + 执行前 preflight。

设计依据：`design.md` D-RUN-01；`requirements.md` R2.1–R2.4、R7.1、R7.6、R13.15–R13.19、R14.7–R14.8。

要点：
- 项目工作流是"项目内的工作流版本"，与全局共享模板（enhanced workflows）**分离**：
  从 canonical 模板 / 复制项目工作流 / 空白创建；把 `dataset_version_id` 绑定到 load 节点；
  保存为项目工作流版本，**绝不覆盖共享模板**。
- `run_preflight` 返回 `blocked` / `warning` / `passed`，逐项给出 scope、必填字段与表示、
  标签粒度、样本/日期/设备/类别覆盖、端口与节点契约、评测合同、资源估计、是否仅允许 `experiment`。
- 检查项带 `governance_impact`：`none` 为信息性提示（不影响 overall），
  `downgrade` 为治理降级（把 `experiment_only` 置真）。
  **这是 P0-3 的修复点**：修复前任何 warning 都会把 `overall` 压成 warning、
  使 `experiment_only` 恒真，于是 preflight 永远无法 `passed`。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects import stores
from services.pv_projects.errors import ScopeError
from services.pv_projects.readiness import evaluate_path_readiness
from services.pv_projects.scope import ScopeContext

CREATE_MODES = ("template", "copy", "blank")

#: 工作流用途（design §3 三类工作流）。
#: - training：训练工作流，**每路径可有 N 个**，消费冻结快照 → 产模型工件。
#: - labeling：打标工作流，每路径 1 个 canonical，消费未标注数据 + 辅助模型 → 产标签提案。
#: - detection：检测工作流，每路径 1 个**共用**，消费 registry 指针模型 → 产检测批次。
WORKFLOW_KINDS = ("training", "labeling", "detection")
DEFAULT_WORKFLOW_KIND = "training"

#: 现阶段不允许在项目内自建检测工作流：生产检测链路保持共用且只读
#: （pv_day 复用 quickval predict、pv_tsc 走 tsc_predict、pv_point 直连 predictor）。
#: 若将来允许自定义，必须同步引入"检测工作流也须正式复验才能上岗"的治理规则。
UNCREATABLE_WORKFLOW_KINDS = ("detection",)

#: 每路径 canonical 唯一的用途（labeling）：同 scope 只允许一个，避免"哪一个是规范打标"歧义。
CANONICAL_UNIQUE_KINDS = ("labeling",)

#: 各路径的冻结快照类型（须与 cumulative._SNAPSHOT_TYPE_BY_SLOT 一致）。
#: 训练工作流绑定的快照类型必须与其所属路径匹配，否则视为跨路径复用 → 阻断。
EXPECTED_SNAPSHOT_TYPE_BY_SLOT: dict[str, str] = {
    "pv_day": "device_day_curve_set",
    "pv_point": "whole_day_point_box",
    "pv_tsc": "tsc_288x3_grid",
}

#: 各路径的预测单元与所需真值粒度（路径契约的可校验部分）。
PATH_CONTRACT_BY_SLOT: dict[str, dict[str, Any]] = {
    "pv_day": {"output_unit": "device_day", "truth_granularity": ("device_day", "point", "interval")},
    "pv_point": {"output_unit": "point_interval", "truth_granularity": ("point", "interval")},
    "pv_tsc": {"output_unit": "device_day_288x3", "truth_granularity": ("device_day", "point", "interval")},
}

#: run_mode 与 workflow_kind 的合同（P0-1 第 5 条）。
#: `run_mode` 必须落在其**持久化工作流**用途允许的集合内；否则客户端可用
#: labeling 工作流以 `run_mode=training` 执行，凭空取得治理资格。
#: 注意 `runner.RUN_MODES` 是实际可传值域（无 `production`），本表是其子集约束。
RUN_MODE_CONTRACT_BY_KIND: dict[str, tuple[str, ...]] = {
    "training": ("experiment", "training"),
    "labeling": ("experiment", "validation"),
    "detection": ("prediction",),
}


def assert_run_mode_allowed(workflow_kind: str, run_mode: str) -> None:
    """校验 `run_mode` 与工作流用途一致；不一致 fail-closed 抛 `ScopeError`。"""
    allowed = RUN_MODE_CONTRACT_BY_KIND.get(str(workflow_kind or ""))
    if allowed is None:
        raise ScopeError(
            "unknown_workflow_kind",
            f"未知工作流用途：{workflow_kind!r}；允许 {list(RUN_MODE_CONTRACT_BY_KIND)}。",
            next_action="检查项目工作流的 workflow_kind 字段",
        )
    if str(run_mode or "") not in allowed:
        raise ScopeError(
            "run_mode_workflow_kind_mismatch",
            f"run_mode={run_mode!r} 与工作流用途 {workflow_kind!r} 不符；"
            f"该用途允许 {list(allowed)}。",
            next_action=f"改用 {list(allowed)} 之一，或换一个用途匹配的项目工作流",
        )


#: preflight 单项检查状态
CHECK_PASSED = "passed"
CHECK_WARNING = "warning"
CHECK_BLOCKED = "blocked"

#: 检查项的治理影响分级。
GOVERNANCE_IMPACT_NONE = "none"
GOVERNANCE_IMPACT_DOWNGRADE = "downgrade"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# 项目工作流创建（三模式）
# ---------------------------------------------------------------------------

def _load_template_graph(template_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """读取 `data/workflows_enhanced/<id>.json` 的 nodes / edges（canonical 模板图）。

    路径解析复用 `api.workflows_enhanced.get_workflow_path`，避免两处各写一遍目录约定；
    lazy import 防止 services → api 的模块级循环依赖。
    """
    import json
    import os

    from api.workflows_enhanced import get_workflow_path  # noqa: PLC0415

    path = get_workflow_path(template_id)
    if not os.path.exists(path):
        raise ValueError(f"模板不存在：{template_id!r}（期望 {path}）")
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return list(payload.get("nodes") or []), list(payload.get("edges") or [])


def list_templates_for_slot(slot: str) -> dict[str, Any]:
    """列出某条诊断路径下**可复用**的 canonical 模板。

    命名约定：模板 id 以 `workflow-<slot 连字符形>` 开头（`pv_tsc` → `workflow-pv-tsc-…`）；
    这样前端「从模板创建」时只看到本路径的模板，不会把 pv_day 的图建到 pv_tsc 上。
    """
    import json
    import os

    from api.workflows_enhanced import get_workflow_path  # noqa: PLC0415

    prefix = f"workflow-{str(slot or '').strip().replace('_', '-')}"
    wf_dir = os.path.dirname(get_workflow_path("_"))
    templates: list[dict[str, Any]] = []
    if os.path.isdir(wf_dir):
        for name in sorted(os.listdir(wf_dir)):
            if not name.endswith(".json") or not name.startswith(prefix):
                continue
            try:
                with open(os.path.join(wf_dir, name), encoding="utf-8") as fh:
                    payload = json.load(fh)
            except Exception:  # noqa: BLE001 — 单个模板坏掉不该让整个列表失败
                continue
            stem = name[: -len(".json")]
            templates.append(
                {
                    "template_id": str(payload.get("id") or stem),
                    "name": str(payload.get("name") or stem),
                    "description": str(payload.get("description") or ""),
                    "node_count": len(payload.get("nodes") or []),
                }
            )
    return {"slot": slot, "templates": templates, "total": len(templates)}


def create_project_workflow(
    scope: ScopeContext,
    *,
    mode: str,
    name: str,
    source_template_id: Optional[str] = None,
    source_project_workflow_id: Optional[str] = None,
    dataset_version_id: Optional[str] = None,
    source_snapshot_id: Optional[str] = None,
    workflow_kind: Optional[str] = None,
    nodes: Optional[list[dict[str, Any]]] = None,
    edges: Optional[list[dict[str, Any]]] = None,
    load_node_id: Optional[str] = None,
) -> dict[str, Any]:
    """创建一条项目工作流版本；绑定数据版本（load 节点）与训练输入快照。

    - `mode='template'`：来自 canonical 模板（记录 source_template_id + 主干归属）。
    - `mode='copy'`：复制既有项目工作流（version+1，继承 version_group_id）。
    - `mode='blank'`：空白画布（仍要求归属由上层保证）。
    - `workflow_kind`：training（可 N 个）/ labeling（**每路径 canonical 唯一**）/ detection（**不可自建**）。
      传 `None` 表示"未显式指定"：copy 模式继承来源工作流用途，其余模式回落 `training`。
    - `source_snapshot_id`：训练工作流的真实输入是**冻结快照**；必须同 scope 存在，
      且快照类型与本路径匹配（跨路径复用快照直接拒绝）。
    绝不写回 / 覆盖共享模板；仅写 scoped 项目工作流存储。

    解析顺序（P1-4 修复）：先解析来源（copy）→ 再定 kind → 再定快照 → 最后校验。
    修复前 kind 与快照在校验之后才被 copy 分支继承，导致"copy labeling 变 training"
    且被继承的快照逃过类型校验。
    """
    scope.assert_writable()
    slot = scope.require_slot()
    m = str(mode or "").strip()
    if m not in CREATE_MODES:
        raise ValueError(f"未知创建模式：{mode!r}（应为 {CREATE_MODES}）")

    # 1) 解析来源工作流（copy 模式）——必须先于 kind / 快照解析。
    src: Optional[dict[str, Any]] = None
    if m == "copy":
        if not source_project_workflow_id:
            raise ValueError("copy 模式需要 source_project_workflow_id")
        src = stores.project_workflows.find(scope, source_project_workflow_id)
        if src is None:
            raise ValueError(f"来源项目工作流不存在：{source_project_workflow_id}")

    # 2) 定用途：显式指定 > 继承来源 > 默认。
    explicit_kind = str(workflow_kind).strip() if workflow_kind is not None else ""
    if explicit_kind:
        kind = explicit_kind
    elif src is not None and src.get("workflow_kind"):
        kind = str(src.get("workflow_kind"))
    else:
        kind = DEFAULT_WORKFLOW_KIND
    if kind not in WORKFLOW_KINDS:
        raise ValueError(f"未知工作流用途：{workflow_kind!r}（应为 {WORKFLOW_KINDS}）")
    if kind in UNCREATABLE_WORKFLOW_KINDS:
        raise ValueError(
            f"不允许在项目内自建 {kind} 工作流：生产检测链路保持共用且只读"
            "（pv_day 复用 quickval predict、pv_tsc 走 tsc_predict、pv_point 直连 predictor）"
        )

    # 2b) canonical 唯一：每路径只允许一个 labeling 工作流。
    if kind in CANONICAL_UNIQUE_KINDS:
        existing = [
            w for w in stores.project_workflows.list(scope)
            if str(w.get("workflow_kind") or "") == kind
        ]
        # copy 自身来源不算重复（版本递增属于同一 canonical 的迭代）。
        src_id = str(src.get("project_workflow_id")) if src else ""
        others = [w for w in existing if str(w.get("project_workflow_id")) != src_id]
        if others:
            raise ValueError(
                f"当前项目 / 路径已存在 {kind} 工作流："
                f"{[w.get('project_workflow_id') for w in others]}；"
                f"{kind} 每路径 canonical 唯一，请复制既有版本而不是新建。"
            )

    # 3) 定快照：显式指定 > 继承来源。
    bound_snapshot: Optional[str] = str(source_snapshot_id).strip() if source_snapshot_id else None
    if not bound_snapshot and src is not None and src.get("bound_snapshot_id"):
        bound_snapshot = str(src.get("bound_snapshot_id"))

    snapshot_type: Optional[str] = None
    if bound_snapshot:
        snap = stores.snapshots.find(scope, bound_snapshot)
        if snap is None:
            raise ValueError(f"当前项目 / 路径下找不到冻结快照：{bound_snapshot}")
        snapshot_type = str(snap.get("snapshot_type") or "")
        expected = EXPECTED_SNAPSHOT_TYPE_BY_SLOT.get(slot)
        if expected and snapshot_type and snapshot_type != expected:
            raise ValueError(
                f"快照类型与路径不匹配：快照 {snapshot_type!r} vs 路径 {slot} 期望 {expected!r}；"
                "禁止跨路径复用冻结快照"
            )

    # 4) 版本 / 血缘 / 图。
    version = 1
    version_group_id = _new_id("pwfg")
    parent_id: Optional[str] = None
    graph_nodes = list(nodes or [])
    graph_edges = list(edges or [])

    # 1b) template 模式：真正把 canonical 模板的图装进来。
    # 此前只把 source_template_id 记进记录、**不加载 nodes/edges**，于是「从模板创建」产出空图
    # —— 界面上能看到工作流，但它没有任何可执行节点。这是「复用已有工作流」的核心缺口。
    template_id = str(source_template_id).strip() if source_template_id else ""
    if m == "template" and template_id and not graph_nodes:
        graph_nodes, graph_edges = _load_template_graph(template_id)

    if src is not None:
        version = int(src.get("version") or 1) + 1
        version_group_id = str(src.get("version_group_id") or version_group_id)
        parent_id = str(src.get("project_workflow_id"))
        source_template_id = src.get("source_template_id")
        if not graph_nodes:
            graph_nodes = list(src.get("nodes") or [])
            graph_edges = list(src.get("edges") or [])

    # 绑定 dataset_version_id 到 load 节点（load_csv / load_labeled_dataset）。
    bound_version = str(dataset_version_id).strip() if dataset_version_id else None
    if bound_version:
        graph_nodes = _bind_dataset_version(graph_nodes, bound_version, load_node_id)

    record = {
        "project_workflow_id": _new_id("pwf"),
        "version": version,
        "version_group_id": version_group_id,
        "parent_project_workflow_id": parent_id,
        "name": str(name or "").strip() or "未命名项目工作流",
        "create_mode": m,
        "workflow_kind": kind,
        "source_template_id": source_template_id,
        "bound_dataset_version_id": bound_version,
        # 训练输入 = 冻结快照（血缘链关键一环：workflow → snapshot → 台账 → 审核 → 数据版本）
        "bound_snapshot_id": bound_snapshot,
        "bound_snapshot_type": snapshot_type,
        "nodes": graph_nodes,
        "edges": graph_edges,
        "created_at": _now_iso(),
        # 溯源标记：明确这是项目内版本，不是共享模板
        "is_project_workflow": True,
        "overwrites_shared_template": False,
    }
    return stores.project_workflows.append(scope, record)


def _bind_dataset_version(
    nodes: list[dict[str, Any]],
    dataset_version_id: str,
    load_node_id: Optional[str],
) -> list[dict[str, Any]]:
    """把 dataset_version_id 写入 load 节点的 config（不修改其他节点）。"""
    bound: list[dict[str, Any]] = []
    for node in nodes:
        n = dict(node)
        data = dict(n.get("data") or {})
        config = dict(data.get("config") or {})
        fid = config.get("functionId")
        is_load = fid in ("load_csv", "load_labeled_dataset")
        if (load_node_id and n.get("id") == load_node_id) or (load_node_id is None and is_load):
            config["dataset_version_id"] = dataset_version_id
            data["config"] = config
            n["data"] = data
        bound.append(n)
    return bound


def list_project_workflows(scope: ScopeContext) -> list[dict[str, Any]]:
    return stores.project_workflows.list(scope)


def get_project_workflow(scope: ScopeContext, project_workflow_id: str) -> Optional[dict[str, Any]]:
    return stores.project_workflows.find(scope, project_workflow_id)


# ---------------------------------------------------------------------------
# 执行前 preflight
# ---------------------------------------------------------------------------

def _check(
    key: str,
    label: str,
    status: str,
    detail: str,
    *,
    governance_impact: str = GOVERNANCE_IMPACT_NONE,
    **extra: Any,
) -> dict[str, Any]:
    """构造一个检查项。

    `governance_impact`：
    - `none`（默认）：信息性提示，**不影响** `overall`，不降级治理资格。
    - `downgrade`：治理降级，使 `experiment_only=True` 并把 `overall` 压为 warning。
    """
    item = {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "governance_impact": governance_impact,
    }
    item.update({k: v for k, v in extra.items() if v is not None})
    return item


def run_preflight(
    scope: ScopeContext,
    *,
    project_workflow_id: str,
    dataset_version_id: Optional[str] = None,
) -> dict[str, Any]:
    """执行前预检：返回 blocked/warning/passed + 逐项检查 + 是否仅允许 experiment。

    读取项目工作流、绑定的数据版本与画像，复用三路径 readiness 评估覆盖度。
    fail-closed：项目工作流 / 数据版本 / 画像缺失 → blocked。
    """
    slot = scope.require_slot()
    checks: list[dict[str, Any]] = []

    pwf = stores.project_workflows.find(scope, project_workflow_id)
    if pwf is None:
        return _preflight_result(
            scope, project_workflow_id, None,
            [_check("project_workflow", "项目工作流", CHECK_BLOCKED,
                    f"项目工作流不存在：{project_workflow_id}")],
            experiment_only=True,
        )

    version_id = str(dataset_version_id or pwf.get("bound_dataset_version_id") or "").strip()
    if not version_id:
        checks.append(_check("data_binding", "数据版本绑定", CHECK_BLOCKED,
                             "未绑定 dataset_version_id，无法预检数据契约",
                             next_action="在 load 节点绑定一个不可变数据版本"))
        return _preflight_result(scope, project_workflow_id, None, checks, experiment_only=True)

    version = stores.dataset_versions.find(scope, version_id)
    if version is None:
        checks.append(_check("data_version", "数据版本", CHECK_BLOCKED,
                             f"数据版本不存在：{version_id}"))
        return _preflight_result(scope, project_workflow_id, version_id, checks, experiment_only=True)

    profile_id = str(version.get("dataset_profile_id") or "").strip()
    profile = stores.dataset_profiles.find(scope, profile_id) if profile_id else None
    if profile is None:
        checks.append(_check("dataset_profile", "字段映射 / 画像", CHECK_BLOCKED,
                             "数据版本缺少可解析的画像 / 字段映射"))
        return _preflight_result(scope, project_workflow_id, version_id, checks, experiment_only=True)

    # scope 回显
    checks.append(_check("scope", "作用域", CHECK_PASSED,
                         f"project={scope.project_id} slot={slot} version={version_id}"))

    # 必填字段与表示（来自 mapping）
    mapping = dict(profile.get("mapping") or {})
    required = ("time_col", "device_col", "value_col")
    missing = [f for f in required if not mapping.get(f)]
    if missing:
        checks.append(_check("required_fields", "必填字段与表示", CHECK_BLOCKED,
                             f"缺少必填字段映射：{', '.join(missing)}",
                             current_value=sorted(mapping.keys()), required_value=list(required)))
    else:
        checks.append(_check("required_fields", "必填字段与表示", CHECK_PASSED,
                             "time/device/value 映射齐备"))

    # readiness：标签粒度 + 覆盖 + 是否仅 experiment
    readiness = evaluate_path_readiness(scope, version=version, profile=profile, slot=slot)
    status = readiness.get("status")
    allowed_modes = list(readiness.get("allowed_run_modes") or [])
    experiment_only = "validation" not in allowed_modes and "production" not in allowed_modes

    # 标签粒度
    if status == "needs_labels":
        checks.append(_check("label_granularity", "标签粒度", CHECK_WARNING,
                             readiness.get("primary_blocker") or "标签不满足该路径监督口径",
                             governance_impact=GOVERNANCE_IMPACT_DOWNGRADE,
                             next_action=readiness.get("next_action")))
    elif status == "unsupported":
        checks.append(_check("label_granularity", "标签粒度", CHECK_BLOCKED,
                             readiness.get("primary_blocker") or "该路径不支持当前数据"))
    else:
        checks.append(_check("label_granularity", "标签粒度", CHECK_PASSED,
                             f"readiness={status}"))

    # 覆盖度：readiness.facts 是**事实列表**（非字典）；覆盖未确认时 readiness 会给
    # coverage_facts_unconfirmed 阻断项，据此诚实降级为 warning。
    facts_list = readiness.get("facts") or []
    coverage_unconfirmed = any(
        isinstance(b, dict) and b.get("reason_code") == "coverage_facts_unconfirmed"
        for b in (readiness.get("blockers") or [])
    )
    if coverage_unconfirmed or not facts_list:
        checks.append(_check("coverage", "样本/日期/设备/类别覆盖", CHECK_WARNING,
                             "画像未计算覆盖度事实；仅能作为实验级信号",
                             governance_impact=GOVERNANCE_IMPACT_DOWNGRADE,
                             next_action="补充画像 facts 后再评估验证 / 生产资格"))
    else:
        checks.append(_check("coverage", "样本/日期/设备/类别覆盖", CHECK_PASSED,
                             f"覆盖度事实可用（{len(facts_list)} 项）"))

    # 端口 / 节点契约
    node_count = len(pwf.get("nodes") or [])
    has_load = any(
        (n.get("data") or {}).get("config", {}).get("functionId") in ("load_csv", "load_labeled_dataset")
        for n in (pwf.get("nodes") or [])
    )
    if node_count == 0:
        checks.append(_check("node_contract", "端口与节点契约", CHECK_BLOCKED,
                             "空画布，无可执行节点"))
    elif not has_load:
        checks.append(_check("node_contract", "端口与节点契约", CHECK_WARNING,
                             "未发现 load 节点，数据绑定可能未生效",
                             governance_impact=GOVERNANCE_IMPACT_DOWNGRADE,
                             next_action="在画布中加入 load_csv / load_labeled_dataset 节点"))
    else:
        checks.append(_check("node_contract", "端口与节点契约", CHECK_PASSED,
                             f"节点数={node_count}，含 load 节点"))

    # 路径契约硬校验（让"属于哪条路径"成为可校验事实，而非创建时的声明）
    kind = str(pwf.get("workflow_kind") or DEFAULT_WORKFLOW_KIND)
    contract = PATH_CONTRACT_BY_SLOT.get(slot, {})
    expected_snapshot_type = EXPECTED_SNAPSHOT_TYPE_BY_SLOT.get(slot)
    granularity = str((profile.get("label_policy") or {}).get("granularity") or "").strip()
    allowed_granularity = tuple(contract.get("truth_granularity") or ())

    if kind in UNCREATABLE_WORKFLOW_KINDS:
        checks.append(_check("path_contract", "路径契约", CHECK_BLOCKED,
                             f"{kind} 工作流不可在项目内执行：生产检测链路共用且只读"))
    elif granularity and allowed_granularity and granularity not in allowed_granularity:
        # 例：设备日标签不能作为 pv_point 的逐点真值
        checks.append(_check("path_contract", "路径契约", CHECK_BLOCKED,
                             f"标签粒度 {granularity!r} 不满足路径 {slot} 的真值口径",
                             current_value=granularity,
                             required_value=list(allowed_granularity),
                             next_action="改用符合该路径粒度的标签，或切换诊断路径"))
    else:
        checks.append(_check("path_contract", "路径契约", CHECK_PASSED,
                             f"用途={kind}，预测单元={contract.get('output_unit')}，"
                             f"期望快照类型={expected_snapshot_type}"))

    # 训练输入：可治理训练必须绑定冻结快照（血缘链要求 source_snapshot_id）
    bound_snapshot = str(pwf.get("bound_snapshot_id") or "").strip()
    if kind == "training":
        if not bound_snapshot:
            checks.append(_check("training_input", "训练输入（冻结快照）", CHECK_WARNING,
                                 "训练工作流未绑定冻结快照：可做实验，但产出无法成为可治理候选",
                                 governance_impact=GOVERNANCE_IMPACT_DOWNGRADE,
                                 required_value="source_snapshot_id",
                                 next_action="先在累计阶段冻结快照，再绑定到该训练工作流"))
        else:
            snap = stores.snapshots.find(scope, bound_snapshot)
            if snap is None:
                checks.append(_check("training_input", "训练输入（冻结快照）", CHECK_BLOCKED,
                                     f"绑定的冻结快照在当前 scope 不存在：{bound_snapshot}"))
            elif expected_snapshot_type and str(snap.get("snapshot_type") or "") != expected_snapshot_type:
                checks.append(_check("training_input", "训练输入（冻结快照）", CHECK_BLOCKED,
                                     f"快照类型 {snap.get('snapshot_type')!r} 与路径 {slot} 期望 "
                                     f"{expected_snapshot_type!r} 不匹配（禁止跨路径复用快照）"))
            else:
                checks.append(_check("training_input", "训练输入（冻结快照）", CHECK_PASSED,
                                     f"已绑定快照 {bound_snapshot}"
                                     f"（纳入事件 {snap.get('included_count')} 条，可与同快照的其他工作流公平比较）"))

    # 评测合同（存在于 profile.label_policy / 或默认按路径）
    checks.append(_check("evaluation_contract", "评测合同", CHECK_PASSED,
                         f"按诊断路径 {slot} 使用固定评测口径（尺子不随被测对象变化）"))

    # 资源估计（启发式，非真实测量，诚实标注）——**信息性**，不降级治理资格。
    checks.append(_check("resource_estimate", "资源估计", CHECK_WARNING,
                         "资源估计为启发式占位（未接入真实排队 / 资源探测）",
                         governance_impact=GOVERNANCE_IMPACT_NONE,
                         current_value={"nodes": node_count}))

    return _preflight_result(scope, project_workflow_id, version_id, checks, experiment_only=experiment_only)


def _preflight_result(
    scope: ScopeContext,
    project_workflow_id: str,
    dataset_version_id: Optional[str],
    checks: list[dict[str, Any]],
    *,
    experiment_only: bool,
) -> dict[str, Any]:
    """归并逐项检查为总体结论。

    分级规则（P0-3 修复点）：
    - 任一 `blocked` → `overall=blocked`。
    - 任一 `warning` 且 `governance_impact=downgrade` → `overall=warning` 且 `experiment_only=True`。
    - 只有信息性 warning（`governance_impact=none`）时 → `overall=passed`，**不**降级。
    """
    statuses = {c["status"] for c in checks}
    downgrades = [
        c for c in checks
        if c["status"] == CHECK_WARNING and c.get("governance_impact") == GOVERNANCE_IMPACT_DOWNGRADE
    ]
    informational = [
        c for c in checks
        if c["status"] == CHECK_WARNING and c.get("governance_impact") != GOVERNANCE_IMPACT_DOWNGRADE
    ]

    if CHECK_BLOCKED in statuses:
        overall = CHECK_BLOCKED
    elif downgrades:
        overall = CHECK_WARNING
    else:
        overall = CHECK_PASSED

    return {
        **scope.echo(),
        "project_workflow_id": project_workflow_id,
        "dataset_version_id": dataset_version_id,
        "overall": overall,
        "checks": checks,
        # 信息性提示单独成列，前端据此显示"提示"而非"警告"，且不参与治理判定。
        "informational_notes": [
            {"key": c["key"], "label": c["label"], "detail": c["detail"]} for c in informational
        ],
        # 治理降级原因（可解释：为什么只能做实验）。
        "downgrade_reasons": [
            {"key": c["key"], "label": c["label"], "detail": c["detail"]} for c in downgrades
        ],
        "experiment_only": bool(experiment_only) or bool(downgrades),
        "allowed_to_run": overall != CHECK_BLOCKED,
        "evaluated_at": _now_iso(),
    }

# @AI_GENERATED: end
