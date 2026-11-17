# @AI_GENERATED
"""
api/deployment.py — 算法部署槽位管理 HTTP 层

本模块把 `services.deployment` 中的槽位/切换/回滚逻辑暴露为 REST 端点，
供前端 "算法部署页面 → 模型管理 Tab" 使用。

对应 spec：
  - `.kiro/specs/algorithm-deployment-refactor/design.md`
    → "Components and Interfaces → 1. 部署槽位管理 API"
  - `.kiro/specs/algorithm-deployment-refactor/tasks.md` → Task 6.1
  - Requirements 3.1 / 3.2 / 3.3 / 3.4 / 5.1 / 5.2 / 5.3 / 5.5

端点一览（相对 prefix `/api/deployment`）：
  GET  /slots                            — 列出所有槽位及其 production/shadow 模型
  GET  /slots/{slot}/versions            — 获取版本历史（production + shadow + retired）
  POST /slots/{slot}/switch              — 执行切换（shadow → production）
  POST /slots/{slot}/rollback            — 回滚到前一 production 版本
  GET  /slots/{slot}/switch-log          — 获取切换日志（按 slot 过滤，按追加顺序）
  GET  /slots/{slot}/config              — 获取自动切换配置
  PUT  /slots/{slot}/config              — 局部更新自动切换配置

字段命名约定（"英文 key — 中文含义"）：
  - `slot`                       — 槽位名称（分区键，复用 version_registry / candidate_pool 等表的 slot 列）
  - `workflow_id`                — 工作流/模板唯一标识（EnhancedWorkflow.id）
  - `version_tag`                — 版本标签（人类可读，如 "v2.1"）
  - `deployed_at`                — 模型注册/部署时间（ISO 8601）
  - `accuracy_score`             — 最新精度评分（当前项目内 MAPE，越低越好）
  - `latest_mape`                — GET /slots 返回的 production 展示字段，语义等同于 accuracy_score
  - `consecutive_better_days`    — 影子模型连续优于生产的天数（切换资格判定，仅 shadow 有意义）
  - `auto_switch_enabled`        — 是否启用自动切换（false 时仅 UI 高亮，不自动 promote）
  - `switch_observation_days`    — 切换观察天数：shadow 连续多少天优于生产才建议切换
                                   【重命名自旧字段 evaluation_window_days，兼容读取；响应体中保留旧字段名作为 deprecated alias】
  - `cooldown_hours`             — 切换后冷却期（小时），冷却期内不允许再次切换（force=True 可绕过）
  - `threshold_mape`             — 精度阈值（低于此值触发回滚，可选）
  - `training_window_days`       — 训练窗口天数：每天训练用最近 N 天历史数据（跟 AutoResearch train_days 语义一致）
  - `max_shadow_slots`           — 影子池上限，默认 3（限制每日 cron 里跑几个 shadow）
  - `max_prelaunch_slots`        — 预上线池上限，默认 2（并行观察数量）
  - `prelaunch_models`           — 预上线模型列表（每个独立跟生产比，达标 + 期满则毕业为 shadow）
  - `prelaunch_meta`             — 预上线专属元数据（挂在单个 ModelVersion 上）

错误映射（对应 design.md "Error Handling → 模型切换错误处理"）：
  code                       -> HTTP
  ----                          ----
  slot_not_found             -> 404
  target_not_found           -> 404
  invalid_state_transition   -> 400
  cooldown_active            -> 409
  no_previous_version        -> 400
  no_current_production      -> 400
  pv_fault_registry_read_only -> 409
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.deployment import (
    DeploymentSlot,
    DeploymentSlotStore,
    ModelVersion,
    SwitchDecisionEngine,
    SwitchDecisionError,
    SwitchEventLog,
    PvFaultRegistryReadOnlyError,
)

# ---------------------------------------------------------------------------
# Router + 单例依赖
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/deployment", tags=["deployment"])

# Store/Log 每次调用都会读文件，安全地在进程内单例共享
_slot_store = DeploymentSlotStore()
_event_log = SwitchEventLog()
_engine = SwitchDecisionEngine(slot_store=_slot_store, event_log=_event_log)


# ---------------------------------------------------------------------------
# 请求体 Schema
# ---------------------------------------------------------------------------

class SwitchRequest(BaseModel):
    """
    POST /slots/{slot}/switch 请求体。

    字段：
      - target_workflow_id — 必填，要提升为 production 的影子模型 workflow_id
      - trigger_type       — 触发类型 "manual" | "auto"，默认 "manual"
      - reason             — 切换原因备注（人类可读，可选）
      - pre_switch_mape    — 切换前精度覆盖值（可选，未提供则取 production.accuracy_score）
      - force              — 手动 UI 可传 True 绕过冷却期检查（默认 False）
    """

    target_workflow_id: str = Field(..., description="要提升为 production 的影子模型 workflow_id")
    # @AI_GENERATED: 同一 workflow 的多版本必须携带 version_tag 才能精确切换
    target_version_tag: Optional[str] = Field(None, description="目标影子模型的 version_tag；同 workflow 多版本时必填")
    # @AI_GENERATED: end
    trigger_type: str = Field("manual", description="触发类型：'manual' | 'auto'")
    reason: str = Field("", description="切换原因备注")
    pre_switch_mape: Optional[float] = Field(None, description="切换前精度覆盖值")
    force: bool = Field(False, description="是否绕过冷却期检查（人工操作）")


class RollbackRequest(BaseModel):
    """
    POST /slots/{slot}/rollback 请求体。

    字段：
      - reason — 回滚原因备注（可选，默认 "manual_rollback"）
    """

    reason: str = Field("manual_rollback", description="回滚原因备注")


class SlotConfigUpdate(BaseModel):
    """
    PUT /slots/{slot}/config 请求体 —— 局部更新，仅设置传入的非 None 字段。

    字段（均可选，None 表示不修改）：
      - auto_switch_enabled        — 是否启用自动切换（Shadow → Production）
      - switch_observation_days    — 切换观察天数（旧字段名 evaluation_window_days 兼容读取）
      - evaluation_window_days     — 已废弃，旧字段名兼容，值将映射到 switch_observation_days
      - cooldown_hours             — 切换后冷却期（小时）
      - threshold_mape             — 精度阈值（低于此值触发回滚）
      - training_window_days       — 训练窗口天数（每天训练用最近 N 天历史数据）
      - max_shadow_slots           — 影子池上限（锦标赛并行数量）
      - max_prelaunch_slots        — 预上线池上限（安全闸门并行数量）
    """

    auto_switch_enabled: Optional[bool] = None
    switch_observation_days: Optional[int] = Field(default=None, ge=1, le=30)
    # 旧字段名兼容：如果客户端传 evaluation_window_days，会被读入并在 apply 时映射到新字段
    evaluation_window_days: Optional[int] = Field(default=None, ge=1, le=30, deprecated=True)
    cooldown_hours: Optional[int] = Field(default=None, ge=0)
    threshold_mape: Optional[float] = None
    training_window_days: Optional[int] = Field(default=None, ge=7, le=730)
    max_shadow_slots: Optional[int] = Field(default=None, ge=1, le=10)
    max_prelaunch_slots: Optional[int] = Field(default=None, ge=1, le=5)


# ---------------------------------------------------------------------------
# 内部工具：模型对象 -> 前端友好视图
# ---------------------------------------------------------------------------

def _production_view(model: Optional[ModelVersion]) -> Optional[Dict[str, Any]]:
    """
    序列化 production_model 到前端展示格式。

    与 design.md 的示例对齐：包含 `latest_mape`（语义等同 accuracy_score）。
    None 时返回 None（前端展示"当前无生产模型"占位）。
    """
    if model is None:
        return None
    patch = getattr(model, "experiment_patch", None) or None
    patch_fp = None
    if patch:
        try:
            from services.deployment.experiment_patch import experiment_patch_fingerprint

            patch_fp = experiment_patch_fingerprint(patch)
        except Exception:
            patch_fp = "unknown"
    return {
        "workflow_id": model.workflow_id,
        "version_tag": model.version_tag,
        "status": model.status,
        "deployed_at": model.deployed_at,
        # design.md 中 production 字段名为 latest_mape
        "latest_mape": model.accuracy_score,
        # 保留原字段名便于前端复用
        "accuracy_score": model.accuracy_score,
        "consecutive_better_days": model.consecutive_better_days,
        "source_run_id": model.source_run_id,
        "source_candidate_id": model.source_candidate_id,
        "has_experiment_patch": bool(patch),
        "experiment_patch_fingerprint": patch_fp,
    }


def _shadow_view(model: ModelVersion) -> Dict[str, Any]:
    """
    序列化 shadow_model 到前端展示格式。

    同时暴露 `accuracy_score` 和 `latest_mape`，两者含义相同 —— 便于前端
    在 shadow / production 卡片间共用渲染逻辑。
    """
    patch = getattr(model, "experiment_patch", None) or None
    patch_fp = None
    if patch:
        try:
            from services.deployment.experiment_patch import experiment_patch_fingerprint

            patch_fp = experiment_patch_fingerprint(patch)
        except Exception:
            patch_fp = "unknown"
    return {
        "workflow_id": model.workflow_id,
        "version_tag": model.version_tag,
        "status": model.status,
        "deployed_at": model.deployed_at,
        "accuracy_score": model.accuracy_score,
        "latest_mape": model.accuracy_score,
        "consecutive_better_days": model.consecutive_better_days,
        "source_run_id": model.source_run_id,
        "source_candidate_id": model.source_candidate_id,
        "has_experiment_patch": bool(patch),
        "experiment_patch_fingerprint": patch_fp,
    }


def _prelaunch_view(model: ModelVersion) -> Dict[str, Any]:
    """
    序列化 prelaunch_model 到前端展示格式。

    Prelaunch 语义：每个独立跟生产比较，MAPE ≤ production*(1 + tolerance)
    且观察期满则毕业为 shadow。返回体额外包含 `prelaunch_meta` 展示观察进度。
    """
    meta = model.prelaunch_meta
    patch = getattr(model, "experiment_patch", None) or None
    patch_fp = None
    if patch:
        try:
            from services.deployment.experiment_patch import experiment_patch_fingerprint

            patch_fp = experiment_patch_fingerprint(patch)
        except Exception:
            patch_fp = "unknown"
    return {
        "workflow_id": model.workflow_id,
        "version_tag": model.version_tag,
        "status": model.status,
        "deployed_at": model.deployed_at,
        "accuracy_score": model.accuracy_score,
        "latest_mape": model.accuracy_score,
        "source_run_id": model.source_run_id,
        "source_candidate_id": model.source_candidate_id,
        "has_experiment_patch": bool(patch),
        "experiment_patch_fingerprint": patch_fp,
        # 预上线专属字段（meta 为 None 时前端展示为占位）
        "prelaunch_meta": meta.model_dump() if meta is not None else None,
    }


def _slot_view(slot: DeploymentSlot) -> Dict[str, Any]:
    """
    序列化 DeploymentSlot 到前端展示格式。

    - shadow_models 只包含 status='shadow' 的条目（retired 通过 /versions 端点单独返回）
    - shadow_models 已由 store 按 accuracy_score 降序（Requirement 3.4 / Property 3）
    - prelaunch_models 只包含 status='prelaunch' 的条目
    - 响应体同时暴露 `switch_observation_days`（新字段名）和 `evaluation_window_days`
      （已废弃 alias，值相同），便于前端在改名期间兼容
    """
    active_shadows = [m for m in slot.shadow_models if m.status == "shadow"]
    active_prelaunches = [m for m in slot.prelaunch_models if m.status == "prelaunch"]
    return {
        "slot": slot.slot,
        "production_model": _production_view(slot.production_model),
        "shadow_models": [_shadow_view(m) for m in active_shadows],
        "prelaunch_models": [_prelaunch_view(m) for m in active_prelaunches],
        # 决策参数
        "auto_switch_enabled": slot.auto_switch_enabled,
        "switch_observation_days": slot.switch_observation_days,
        # 兼容旧字段名（已废弃，前端应改用 switch_observation_days）
        "evaluation_window_days": slot.switch_observation_days,
        "cooldown_hours": slot.cooldown_hours,
        "threshold_mape": slot.threshold_mape,
        # 训练参数
        "training_window_days": slot.training_window_days,
        # 资源上限
        "max_shadow_slots": slot.max_shadow_slots,
        "max_prelaunch_slots": slot.max_prelaunch_slots,
        "updated_at": slot.updated_at,
    }


# ---------------------------------------------------------------------------
# 错误翻译：SwitchDecisionError.code -> HTTPException
# ---------------------------------------------------------------------------

_ERROR_CODE_TO_HTTP: Dict[str, int] = {
    "slot_not_found": 404,
    "target_not_found": 404,
    "invalid_state_transition": 400,
    "cooldown_active": 409,
    "no_previous_version": 400,
    "no_current_production": 400,
    "pv_fault_registry_read_only": 409,
}


def _raise_from_decision_error(exc: SwitchDecisionError) -> None:
    """将 SwitchDecisionError 翻译为 HTTPException 并抛出。"""
    status = _ERROR_CODE_TO_HTTP.get(exc.code, 400)
    raise HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    )


# @AI_GENERATED: pv_fault 通用部署写入口统一翻译
def _persist_slot(slot_obj: DeploymentSlot) -> None:
    try:
        _slot_store.upsert(slot_obj)
    except PvFaultRegistryReadOnlyError as exc:
        _raise_from_decision_error(SwitchDecisionError(code=exc.code, message=exc.message))
# @AI_GENERATED: end


def _require_slot(slot: str) -> DeploymentSlot:
    """
    获取指定 slot，不存在时抛 404 slot_not_found。

    用于 versions / config 端点前置校验（switch/rollback 在 engine 内自校验）。
    """
    slot_obj = _slot_store.get(slot)
    if slot_obj is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "slot_not_found", "message": f"槽位不存在：slot={slot!r}"},
        )
    return slot_obj


# ---------------------------------------------------------------------------
# 端点实现
# ---------------------------------------------------------------------------

@router.get("/slots")
def list_slots(slot: Optional[str] = Query(default=None, description="仅返回指定 slot")) -> Dict[str, Any]:
    """
    列出所有部署槽位及各自的 production / shadow 模型。

    可选 query `slot` 只返回单个槽位视图（G3 最小 slot UI）。
    """
    slots = _slot_store.load_all()
    if slot:
        item = slots.get(slot)
        if item is None:
            raise HTTPException(status_code=404, detail=f"slot_not_found: {slot}")
        return {"slot": slot, "view": _slot_view(item)}
    return {"slots": {name: _slot_view(s) for name, s in slots.items()}}


@router.get("/slots/{slot}/versions")
def list_versions(slot: str) -> Dict[str, Any]:
    """
    获取某槽位的版本历史列表（production + shadow + retired）。

    每一条记录会额外附带 `role` 字段，方便前端渲染状态标签：
      - role='production' — 当前生产模型
      - role='shadow'     — 在测的影子模型
      - role='retired'    — 历史退役模型（可能来自切换降级或回滚降级）
    """
    slot_obj = _require_slot(slot)
    versions: List[Dict[str, Any]] = []
    if slot_obj.production_model is not None:
        versions.append({**_production_view(slot_obj.production_model), "role": "production"})
    for m in slot_obj.shadow_models:
        # status 里可能是 'shadow' 或 'retired'，直接透传作为 role
        versions.append({**_shadow_view(m), "role": m.status})
    return {"slot": slot, "versions": versions}


@router.post("/slots/{slot}/switch")
def switch_model(slot: str, req: SwitchRequest) -> Dict[str, Any]:
    """
    执行切换：将目标 shadow 提升为 production，原 production 降级为 retired，
    并追加 SwitchEvent。

    错误映射：
      - 目标不存在（slot 或 target_workflow_id）→ 404
      - 目标非 shadow / trigger_type 非法 → 400
      - 冷却期内（force=false）→ 409
    """
    try:
        event = _engine.execute_switch(
            slot=slot,
            target_workflow_id=req.target_workflow_id,
            trigger_type=req.trigger_type,
            reason=req.reason,
            pre_switch_mape=req.pre_switch_mape,
            force=req.force,
            target_version_tag=req.target_version_tag,
        )
    except SwitchDecisionError as exc:
        _raise_from_decision_error(exc)

    return {"event": event.model_dump()}


@router.post("/slots/{slot}/rollback")
def rollback_model(slot: str, req: RollbackRequest) -> Dict[str, Any]:
    """
    回滚到前一 production 版本。

    错误映射：
      - slot 不存在 → 404
      - 无历史事件 / 前版本已被清理 → 400 no_previous_version
      - 当前无 production → 400 no_current_production
    """
    try:
        event = _engine.execute_rollback(slot=slot, reason=req.reason)
    except SwitchDecisionError as exc:
        _raise_from_decision_error(exc)

    return {"event": event.model_dump()}


@router.get("/slots/{slot}/switch-log")
def get_switch_log(slot: str) -> Dict[str, Any]:
    """
    获取某槽位的切换事件日志。

    - 按追加顺序返回（最早在前）
    - append-only：日志条目一旦写入永不修改
    - slot 不存在时不抛 404 —— 返回空列表（因为日志本身独立于槽位快照，
      即便槽位被删除，历史事件仍具审计价值）
    """
    events = _event_log.list_by_slot(slot)
    return {"slot": slot, "events": [e.model_dump() for e in events]}


def _config_view(slot_obj: DeploymentSlot) -> Dict[str, Any]:
    """
    序列化 slot 配置到前端展示格式（GET/PUT /config 共用）。

    返回体同时提供 `switch_observation_days`（新字段名）和 `evaluation_window_days`
    （已废弃 alias，值相同），前端过渡期两个都能读到。
    """
    return {
        "slot": slot_obj.slot,
        "auto_switch_enabled": slot_obj.auto_switch_enabled,
        # 切换资格判定
        "switch_observation_days": slot_obj.switch_observation_days,
        # 兼容旧字段名（已废弃）
        "evaluation_window_days": slot_obj.switch_observation_days,
        "cooldown_hours": slot_obj.cooldown_hours,
        "threshold_mape": slot_obj.threshold_mape,
        # 训练参数
        "training_window_days": slot_obj.training_window_days,
        # 资源上限
        "max_shadow_slots": slot_obj.max_shadow_slots,
        "max_prelaunch_slots": slot_obj.max_prelaunch_slots,
        "updated_at": slot_obj.updated_at,
    }


@router.get("/slots/{slot}/config")
def get_slot_config(slot: str) -> Dict[str, Any]:
    """获取槽位配置（切换参数 + 训练参数 + 资源上限）。slot 不存在时返回 404。"""
    slot_obj = _require_slot(slot)
    return _config_view(slot_obj)


@router.put("/slots/{slot}/config")
def update_slot_config(slot: str, cfg: SlotConfigUpdate) -> Dict[str, Any]:
    """
    局部更新槽位配置 —— 仅设置传入的非 None 字段。

    支持字段：
      - auto_switch_enabled       — 是否启用自动切换
      - switch_observation_days   — 切换观察天数（新名字）
      - evaluation_window_days    — 已废弃 alias，若传入将映射到 switch_observation_days
      - cooldown_hours            — 切换冷却时长（小时）
      - threshold_mape            — 精度阈值
      - training_window_days      — 训练窗口天数
      - max_shadow_slots          — 影子池上限
      - max_prelaunch_slots       — 预上线池上限

    slot 不存在时返回 404。写入后返回最新配置。
    """
    slot_obj = _require_slot(slot)

    if cfg.auto_switch_enabled is not None:
        slot_obj.auto_switch_enabled = cfg.auto_switch_enabled

    # 优先取新字段名 switch_observation_days，未传时再看旧字段名 evaluation_window_days
    # 两个都传时，新字段名优先（一致性以新为准）
    if cfg.switch_observation_days is not None:
        slot_obj.switch_observation_days = cfg.switch_observation_days
    elif cfg.evaluation_window_days is not None:
        slot_obj.switch_observation_days = cfg.evaluation_window_days

    if cfg.cooldown_hours is not None:
        slot_obj.cooldown_hours = cfg.cooldown_hours
    if cfg.threshold_mape is not None:
        slot_obj.threshold_mape = cfg.threshold_mape

    if cfg.training_window_days is not None:
        slot_obj.training_window_days = cfg.training_window_days
    if cfg.max_shadow_slots is not None:
        slot_obj.max_shadow_slots = cfg.max_shadow_slots
    if cfg.max_prelaunch_slots is not None:
        slot_obj.max_prelaunch_slots = cfg.max_prelaunch_slots

    slot_obj.updated_at = datetime.now().isoformat()

    _persist_slot(slot_obj)

    return _config_view(slot_obj)


# ---------------------------------------------------------------------------
# 预上线池 API（/slots/{slot}/prelaunches）
# ---------------------------------------------------------------------------

# @AI_GENERATED: 阶段 2 — prelaunch API

class PrelaunchEnterBody(BaseModel):
    """
    POST /slots/{slot}/prelaunches 请求体 —— 将一个候选加入预上线观察池。

    字段说明（英文 — 中文）：
      - candidate_id            — 来源候选 ID（复验通过的候选，用于溯源）
      - workflow_id             — 要观察的工作流模板 ID
      - version_tag             — 版本标签（人类可读，可选，默认由 candidate_id 前缀生成）
      - observation_days        — 观察期天数，[1, 90]，默认 7
      - graduate_tolerance_pct  — 毕业容差百分比，[0, 50]，默认 5
      - source_run_id           — 来源 AutoResearch run ID（可选，审计）
      - note                    — 人工备注（可选）
    """

    candidate_id: str = Field(..., description="candidate_id — 来源候选 ID")
    workflow_id: str = Field(..., description="workflow_id — 要观察的工作流模板 ID")
    version_tag: Optional[str] = Field(
        default=None,
        description="version_tag — 版本标签（留空则用 prelaunch-{candidate_id[:12]}）",
    )
    observation_days: int = Field(
        default=7, ge=1, le=90,
        description="observation_days — 观察期天数",
    )
    graduate_tolerance_pct: float = Field(
        default=5.0, ge=0.0, le=50.0,
        description="graduate_tolerance_pct — 毕业容差百分比",
    )
    source_run_id: Optional[str] = Field(
        default=None,
        description="source_run_id — 来源 AutoResearch run ID（可选）",
    )
    note: str = Field(default="", description="note — 人工备注")
    # @AI_GENERATED: 真实携带 AR 实验补丁（结构/参数/节点），日滚预测前 apply
    experiment_patch: Optional[Dict[str, Any]] = Field(
        default=None,
        description="experiment_patch — AutoResearch 实验补丁；缺省则按 candidate_id 从候选池回填",
    )
    # @AI_GENERATED: end


def _prelaunch_model_view(model: ModelVersion) -> Dict[str, Any]:
    """序列化单条 prelaunch 模型到 API 响应格式（含完整 prelaunch_meta）。"""
    meta = model.prelaunch_meta
    patch = getattr(model, "experiment_patch", None) or None
    patch_fp = None
    if patch:
        try:
            from services.deployment.experiment_patch import experiment_patch_fingerprint

            patch_fp = experiment_patch_fingerprint(patch)
        except Exception:
            patch_fp = "unknown"
    return {
        "workflow_id": model.workflow_id,
        "version_tag": model.version_tag,
        "status": model.status,
        "deployed_at": model.deployed_at,
        "accuracy_score": model.accuracy_score,
        "source_run_id": model.source_run_id,
        "source_candidate_id": model.source_candidate_id,
        "has_experiment_patch": bool(patch),
        "experiment_patch_fingerprint": patch_fp,
        "prelaunch_meta": meta.model_dump() if meta is not None else None,
    }


@router.get("/slots/{slot}/prelaunches")
def list_prelaunches(
    slot: str,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    获取指定槽位的预上线模型列表。

    用途：前端「算法部署 → 预上线 Tab」首屏加载；精度运营侧历史查询。

    Query params:
      - status（可选）— 按状态过滤：prelaunch | graduated | failed | cancelled
                        不传则返回全部（含历史 retired 条目）

    返回体：
      - slot          — 槽位名称
      - prelaunches   — 预上线模型列表（按 started_at 降序，最新在前）
      - active_count  — 当前 status=prelaunch 的数量
    """
    slot_obj = _require_slot(slot)
    all_items = slot_obj.prelaunch_models

    if status:
        # "graduated" 和 "failed" 对应 status=retired，需要额外从 shadow_models 里捞历史
        if status in ("graduated", "failed"):
            all_items = [
                m for m in slot_obj.shadow_models
                if m.status == "retired" and m.prelaunch_meta is not None
            ]
        else:
            all_items = [m for m in all_items if m.status == status]

    # 按 started_at 降序（最新在前）
    def _started_at_key(m: ModelVersion) -> str:
        return m.prelaunch_meta.started_at if m.prelaunch_meta else ""

    sorted_items = sorted(all_items, key=_started_at_key, reverse=True)
    active_count = sum(1 for m in slot_obj.prelaunch_models if m.status == "prelaunch")

    return {
        "slot": slot,
        "prelaunches": [_prelaunch_model_view(m) for m in sorted_items],
        "active_count": active_count,
    }


@router.post("/slots/{slot}/prelaunches")
def enter_prelaunch(slot: str, body: PrelaunchEnterBody) -> Dict[str, Any]:
    """
    将候选加入预上线观察池。

    前置检查：
      - slot 存在
      - 当前 active prelaunch 数量 < slot.max_prelaunch_slots
      - 同一 workflow_id 不重复入池（status=prelaunch 时）

    入池后：
      - 创建 ModelVersion（status="prelaunch"）+ PrelaunchMeta
      - 写入 slot.prelaunch_models
      - 下一次 lf_daily_rolling cron 会把它纳入训练+预测

    错误映射：
      - slot 不存在 → 404
      - 超出 max_prelaunch_slots 上限 → 409 prelaunch_quota_exceeded
      - 同 workflow_id 已在观察 → 409 already_in_prelaunch
    """
    slot_obj = _require_slot(slot)

    # 检查配额
    active = [m for m in slot_obj.prelaunch_models if m.status == "prelaunch"]
    if len(active) >= slot_obj.max_prelaunch_slots:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "prelaunch_quota_exceeded",
                "message": (
                    f"预上线池已满（{len(active)}/{slot_obj.max_prelaunch_slots}），"
                    "请等现有预上线观察结束后再入池"
                ),
            },
        )

    version_tag = body.version_tag or f"prelaunch-{body.candidate_id[:12]}"

    # 同一 workflow 可带不同 AR patch / version_tag 入池；仅同 version_tag 视为重复
    dup = next(
        (
            m for m in active
            if m.workflow_id == body.workflow_id and m.version_tag == version_tag
        ),
        None,
    )
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "already_in_prelaunch",
                "message": (
                    f"workflow_id={body.workflow_id!r} version_tag={version_tag!r} "
                    "已在预上线观察中，不可重复入池"
                ),
            },
        )

    # 创建 PrelaunchMeta + ModelVersion
    from services.deployment.models import PrelaunchMeta
    from services.deployment.experiment_patch import (
        load_experiment_patch_from_candidate_id,
        normalize_experiment_patch,
    )

    now_iso = datetime.now().isoformat()
    baseline_mape: Optional[float] = None
    if slot_obj.production_model is not None:
        baseline_mape = slot_obj.production_model.accuracy_score

    experiment_patch = normalize_experiment_patch(body.experiment_patch)
    if not experiment_patch:
        experiment_patch = load_experiment_patch_from_candidate_id(body.candidate_id) or None

    meta = PrelaunchMeta(
        candidate_id=body.candidate_id,
        started_at=now_iso,
        observation_days=body.observation_days,
        graduate_tolerance_pct=body.graduate_tolerance_pct,
        baseline_mape_at_entry=baseline_mape,
        source_run_id=body.source_run_id,
        note=body.note,
    )
    new_model = ModelVersion(
        workflow_id=body.workflow_id,
        version_tag=version_tag,
        status="prelaunch",
        deployed_at=now_iso,
        prelaunch_meta=meta,
        source_candidate_id=body.candidate_id,
        source_run_id=body.source_run_id,
        experiment_patch=experiment_patch or None,
    )
    slot_obj.prelaunch_models.append(new_model)
    slot_obj.updated_at = now_iso
    _persist_slot(slot_obj)

    return {
        "success": True,
        "item": _prelaunch_model_view(new_model),
        "active_count": len([m for m in slot_obj.prelaunch_models if m.status == "prelaunch"]),
    }


@router.post("/slots/{slot}/prelaunches/{workflow_id}/cancel")
def cancel_prelaunch(
    slot: str,
    workflow_id: str,
    reason: str = "",
) -> Dict[str, Any]:
    """
    取消预上线观察（手动）。

    条目 status 改为 "retired"，prelaunch_meta.note 记录取消原因。
    下一次 cron 不再跑该 workflow。

    错误映射：
      - slot 不存在 → 404
      - 目标不存在或已不是 prelaunch → 400
    """
    slot_obj = _require_slot(slot)
    try:
        success = _slot_store.fail_prelaunch(
            slot,
            workflow_id,
            reason=reason or "manual_cancel",
        )
    except PvFaultRegistryReadOnlyError as exc:
        _raise_from_decision_error(SwitchDecisionError(code=exc.code, message=exc.message))
    if not success:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "prelaunch_not_found",
                "message": f"未找到 slot={slot!r} workflow_id={workflow_id!r} 的活跃预上线项",
            },
        )
    return {"success": True, "workflow_id": workflow_id, "status": "retired"}


@router.post("/slots/{slot}/prelaunches/{workflow_id}/graduate")
def graduate_prelaunch(
    slot: str,
    workflow_id: str,
) -> Dict[str, Any]:
    """
    手动毕业预上线模型（跳过观察期，强制提升为 shadow）。

    用于：观察期数据充分但时间未到、或紧急上线场景。
    条目从 prelaunch_models 移入 shadow_models，清空 prelaunch_meta，
    status="shadow"，下一次 cron 参与锦标赛。

    错误映射：
      - slot 不存在 → 404
      - 目标不存在或已不是 prelaunch → 400
    """
    slot_obj = _require_slot(slot)
    try:
        success = _slot_store.promote_prelaunch_to_shadow(slot, workflow_id)
    except PvFaultRegistryReadOnlyError as exc:
        _raise_from_decision_error(SwitchDecisionError(code=exc.code, message=exc.message))
    if not success:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "prelaunch_not_found",
                "message": f"未找到 slot={slot!r} workflow_id={workflow_id!r} 的活跃预上线项",
            },
        )
    # 返回更新后的 slot 状态（前端可直接刷新视图）
    slot_obj = _slot_store.get(slot)
    return {
        "success": True,
        "workflow_id": workflow_id,
        "status": "shadow",
        "slot": _slot_view(slot_obj) if slot_obj else None,
    }
# @AI_GENERATED: end
