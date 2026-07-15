# @AI_GENERATED
"""
services/deployment/models.py — 部署槽位数据模型

对应设计文档 `.kiro/specs/algorithm-deployment-refactor/design.md` 中的
"Data Models" 章节，使用 Pydantic v2 BaseModel 定义：

  - PrelaunchMeta   — 预上线专属元数据（观察期、毕业容差、当前 MAPE 等）
  - ModelVersion    — 模型版本信息（workflow_id + 状态 + 精度评分等，可选带 PrelaunchMeta）
  - DeploymentSlot  — 部署槽位（1 production + N shadow + M prelaunch）
  - SwitchEvent     — 切换事件日志条目（append-only，不可篡改）

Slot（槽位）复用系统已有概念：与 `version_registry`、`candidate_pool`、
`prediction_result`、`accuracy_metric` 等表的 `slot` 列对齐，默认值 `"default"`。

字段命名迁移（本次改造）：
  - `evaluation_window_days` → `switch_observation_days`
    原字段名歧义（跟精度评估无关，实际是"shadow 连续多少天优于生产才切换"），
    使用 `AliasChoices` 兼容旧数据；序列化只输出新字段名。

新增关键字段（跟 AutoResearch train_days 对齐）：
  - `training_window_days` — 训练窗口天数，跟 AutoResearch evaluation_contract.train_days 语义一致
  - `max_shadow_slots`     — 影子池上限（锦标赛，比谁最好）
  - `max_prelaunch_slots`  — 预上线池上限（独立闸门，只要不劣于生产）

Shadow vs Prelaunch 语义区分：
  - Shadow：多个 shadow 排序取第一，需连续 `switch_observation_days` 天优于生产才建议切换
  - Prelaunch：每个独立跟生产比，MAPE ≤ production*(1 + tolerance) 且期满 → 毕业到 shadow

注意：本模块故意不使用 ``from __future__ import annotations``，避免
Pydantic v2 在类字段包含 Optional[ModelVersion] 等前向引用时需要显式
调用 ``model_rebuild()`` 才能实例化。项目中其他 Pydantic 模块
（如 services/workflow_agent/event_bus.py）也遵循同样约定。
"""
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, Field


# ---------------------------------------------------------------------------
# PrelaunchMeta — 预上线专属元数据
# ---------------------------------------------------------------------------

class PrelaunchMeta(BaseModel):
    """
    预上线专属元数据 —— 挂在 `ModelVersion.prelaunch_meta` 上，
    仅当 `status="prelaunch"` 时非空。

    预上线（Prelaunch）跟 Shadow 的语义差异：
      - Shadow：跟其他 shadow 及生产**竞争**，锦标赛取最好
      - Prelaunch：**只跟生产独立比较**，MAPE ≤ production*(1 + tolerance)
        且观察期满则毕业为 shadow

    多个 Prelaunch 并存无冲突（它们不互相比较，只跟生产比）。
    毕业后进入 shadow 池，由锦标赛机制决定谁上生产。

    字段说明：
      - candidate_id                  — 来源候选 ID（复验通过入池）
      - started_at                    — 观察开始时间 ISO 8601 字符串
      - observation_days              — 观察期天数，[1, 90]，默认 7
      - graduate_tolerance_pct        — 毕业容差（相对百分比），[0, 50]，默认 5
                                        允许 prelaunch MAPE 比生产高不超过此百分比仍毕业
      - evaluated_cycles              — 已评估天数（累计）
      - baseline_mape_at_entry        — 入池时的生产 MAPE 快照（可选）
      - current_rolling_mape          — 当前预上线滚动 MAPE（每日回填后更新）
      - production_rolling_mape       — 当前生产滚动 MAPE（每日回填后同步）
      - source_run_id                 — 来源 AutoResearch run ID（可选，审计）
      - note                          — 人工备注（可选）
    """

    candidate_id: str
    started_at: str
    observation_days: int = Field(default=7, ge=1, le=90)
    graduate_tolerance_pct: float = Field(default=5.0, ge=0.0, le=50.0)
    evaluated_cycles: int = 0
    baseline_mape_at_entry: Optional[float] = None
    current_rolling_mape: Optional[float] = None
    production_rolling_mape: Optional[float] = None
    source_run_id: Optional[str] = None
    note: str = ""


# ---------------------------------------------------------------------------
# ModelVersion — 模型版本信息
# ---------------------------------------------------------------------------

class ModelVersion(BaseModel):
    """
    模型版本信息。

    描述某一个 workflow（工作流模板）在部署槽位中的运行状态与精度评分。
    同一个 workflow_id + version_tag 组合在系统内唯一。

    字段说明：
      - workflow_id             — 关联的工作流 ID（后端 EnhancedWorkflow.id）
      - version_tag             — 版本标签，人类可读，如 "v2.1"
      - status                  — 状态："production" | "shadow" | "prelaunch" | "retired"
      - deployed_at             — 部署/注册时间 ISO 8601 字符串
      - accuracy_score          — 最新精度评分（可选，None 表示尚未评估）
      - consecutive_better_days — 连续优于当前 production 的天数（切换资格判定用，
                                  仅 status="shadow" 有意义）
      - prelaunch_meta          — 预上线专属元数据（可选，仅 status="prelaunch" 时非空）
      - source_run_id           — 来源实验 run ID（可选，供审计溯源）
      - source_candidate_id     — 来源候选 ID（可选，供审计溯源）
    """

    workflow_id: str
    version_tag: str
    status: str
    deployed_at: str
    accuracy_score: Optional[float] = None
    # @AI_GENERATED: 发布基线用于 7 天滚动退化预警，指标值均为百分比
    baseline_mape: Optional[float] = None
    baseline_wmape: Optional[float] = None
    # @AI_GENERATED: end
    consecutive_better_days: int = 0
    prelaunch_meta: Optional[PrelaunchMeta] = None
    source_run_id: Optional[str] = None
    source_candidate_id: Optional[str] = None


# ---------------------------------------------------------------------------
# DeploymentSlot — 部署槽位
# ---------------------------------------------------------------------------

class DeploymentSlot(BaseModel):
    """
    部署槽位（Deployment Slot）— 管理 1 个 production + N 个 shadow + M 个 prelaunch。

    Slot 是系统已有的多环境/多产品线分区概念，本模型复用该基础设施，
    与 version_registry、candidate_pool、prediction_result、accuracy_metric
    等表的 `slot` 列天然对齐。

    模型池结构：
      - production_model     — 唯一生产模型（可选，None 表示尚未上线）
      - shadow_models        — 影子池（锦标赛，比谁最好），按精度评分降序
      - prelaunch_models     — 预上线池（独立闸门，每个跟生产独立比），按入池时间升序

    资源上限：
      - max_shadow_slots     — 影子池上限，默认 3；限制每日 cron 里跑几个 shadow
      - max_prelaunch_slots  — 预上线池上限，默认 2；限制并行观察多少个 prelaunch

    决策参数：
      - auto_switch_enabled     — 是否启用自动切换（Shadow → Production）
      - switch_observation_days — 切换观察天数：shadow 连续多少天优于生产才建议切换
                                  【重命名自旧字段 evaluation_window_days，兼容读取】
      - cooldown_hours          — 切换后冷却期（小时），冷却期内不允许再切
      - threshold_mape          — 精度阈值（低于此值触发回滚，可选）

    训练参数（本次新增，跟 AutoResearch evaluation_contract.train_days 对齐）：
      - training_window_days    — 训练窗口天数，每天训练用最近 N 天历史数据
                                  默认 30，范围 [7, 730]

    元数据：
      - slot        — 槽位名称（分区键），如 "load_forecast"、"default"
      - updated_at  — 最后更新时间 ISO 8601 字符串

    向后兼容说明：
      - 旧 slots.json 中的 `evaluation_window_days` 字段会自动映射到
        `switch_observation_days`（通过 Pydantic AliasChoices 实现）
      - 序列化（model_dump）只输出新字段名 `switch_observation_days`
    """

    slot: str
    production_model: Optional[ModelVersion] = None
    shadow_models: List[ModelVersion] = Field(default_factory=list)
    prelaunch_models: List[ModelVersion] = Field(default_factory=list)

    # 资源上限
    max_shadow_slots: int = Field(default=3, ge=1, le=10)
    max_prelaunch_slots: int = Field(default=2, ge=1, le=5)

    # 决策参数
    auto_switch_enabled: bool = False
    switch_observation_days: int = Field(
        default=7,
        ge=1,
        le=30,
        validation_alias=AliasChoices("switch_observation_days", "evaluation_window_days"),
        description=(
            "切换观察天数：shadow 连续多少天优于生产才建议切换。"
            "跟训练窗口无关。旧字段名 evaluation_window_days 兼容读取。"
        ),
    )
    cooldown_hours: int = Field(default=48, ge=0)
    threshold_mape: Optional[float] = None

    # 训练参数（新增）
    training_window_days: int = Field(
        default=30,
        ge=7,
        le=730,
        description=(
            "训练窗口天数：每天训练用最近 N 天历史数据。"
            "跟 AutoResearch evaluation_contract.train_days 语义一致。"
            "Promote 时不自动改，需人工在算法部署页面调整。"
        ),
    )

    updated_at: str


# ---------------------------------------------------------------------------
# SwitchEvent — 切换事件日志条目
# ---------------------------------------------------------------------------

class SwitchEvent(BaseModel):
    """
    切换事件日志条目（append-only，不可篡改）。

    每次将 shadow 模型提升为 production 或执行回滚时都会追加一条记录，
    存储在 `data/deployment/switch_log.json` 中，作为审计真源。

    字段说明：
      - event_id           — 事件唯一 ID
      - slot               — 槽位（复用已有 slot 概念）
      - trigger_type       — 触发类型："auto"（自动切换）| "manual"（人工切换）
      - switch_time        — 切换时间 ISO 8601 字符串
      - from_workflow_id   — 原 production 的 workflow_id
      - from_version_tag   — 原 production 的版本标签
      - to_workflow_id     — 新 production 的 workflow_id
      - to_version_tag     — 新 production 的版本标签
      - pre_switch_mape    — 切换前的 MAPE 精度（可选）
      - post_switch_mape   — 切换后的 MAPE 精度（可选，后置评估时补写）
      - reason             — 切换原因备注（可选，人类可读）
      - rollback_of        — 若为回滚事件，指向被回滚的 event_id（可选）
    """

    event_id: str
    slot: str
    trigger_type: str
    switch_time: str
    from_workflow_id: str
    from_version_tag: str
    to_workflow_id: str
    to_version_tag: str
    pre_switch_mape: Optional[float] = None
    post_switch_mape: Optional[float] = None
    reason: str = ""
    rollback_of: Optional[str] = None
# @AI_GENERATED: end
