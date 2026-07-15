# @AI_GENERATED
"""
accuracy_operations/models.py — 精度运营 Pydantic 数据模型

包含：
  - ID 生成辅助函数（gen_alert_id / gen_rca_id / gen_decision_id）
  - 枚举（ModelForm / DegradationTrend / AlertSeverity / AlertStatus /
           RCATriggerType / RCAStatus / RecoveryChannel / DecisionStatus /
           InsightType / InsightPriority / ErrorBias）
  - 嵌入模型（WorstWindow / FeatureDriftDetail）
  - 核心实体（ErrorProfile / DataQualityDiagnosis / ActionableInsight /
               AccuracyAlert / RCAReport / RecoveryDecision）

注意：
  - 使用 Pydantic v1 风格（class Config: use_enum_values = True）
  - 所有 Optional 字段均从 typing 导入
  - 时间戳字段使用 now_iso() 作为默认工厂
  - RecoveryChannel 仅含 shadow_switch 和 observe（通道B 已从本轮范围移除）
"""
from __future__ import annotations

import secrets
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from services.precision_ops.utils import now_iso


# ---------------------------------------------------------------------------
# ID 生成辅助函数
# ---------------------------------------------------------------------------

def gen_alert_id() -> str:
    """生成精度告警 ID，格式 alert-{8hex}"""
    return "alert-" + secrets.token_hex(4)


def gen_rca_id() -> str:
    """生成根因分析报告 ID，格式 rca-{8hex}"""
    return "rca-" + secrets.token_hex(4)


def gen_decision_id() -> str:
    """生成恢复决策 ID，格式 rec-{8hex}"""
    return "rec-" + secrets.token_hex(4)


# ---------------------------------------------------------------------------
# 枚举定义
# ---------------------------------------------------------------------------

class ModelForm(str, Enum):
    """模型形态：生产 / 影子（prelaunch/AutoResearch 不触发告警）"""
    production = "production"
    shadow = "shadow"


class DegradationTrend(str, Enum):
    """退化趋势：sudden=骤升 / gradual=渐升 / stable=持续高位"""
    sudden = "sudden"
    gradual = "gradual"
    stable = "stable"


class AlertSeverity(str, Enum):
    """告警严重级别"""
    warning = "warning"
    critical = "critical"


class AlertStatus(str, Enum):
    """告警生命周期状态"""
    open = "open"
    rca_running = "rca_running"
    recovering = "recovering"
    observing = "observing"
    closed = "closed"


class RCATriggerType(str, Enum):
    """RCA 触发方式"""
    scheduled = "scheduled"
    alert = "alert"
    manual = "manual"


class RCAStatus(str, Enum):
    """RCA 报告执行状态"""
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    timeout = "timeout"


class RecoveryChannel(str, Enum):
    """恢复通道（本轮仅支持通道A 和观察，通道B 已移除）

    - shadow_switch：通道A，复用已有 switch_engine 执行影子切换
    - observe：观察通道，等 AutoResearch 自然产出更好影子或人工介入
    """
    shadow_switch = "shadow_switch"
    observe = "observe"


class DecisionStatus(str, Enum):
    """恢复决策执行状态"""
    pending = "pending"
    executing = "executing"
    succeeded = "succeeded"
    failed = "failed"
    rolled_back = "rolled_back"


class InsightType(str, Enum):
    """可执行建议类型"""
    feature_engineering = "feature_engineering"
    data_sourcing = "data_sourcing"
    model_retraining_signal = "model_retraining_signal"
    observation = "observation"
    hyperparameter_hint = "hyperparameter_hint"


class InsightPriority(str, Enum):
    """可执行建议优先级"""
    high = "high"
    medium = "medium"
    low = "low"


class ErrorBias(str, Enum):
    """预测误差偏差方向"""
    over_forecast = "over_forecast"
    under_forecast = "under_forecast"
    balanced = "balanced"


# ---------------------------------------------------------------------------
# 嵌入子模型
# ---------------------------------------------------------------------------

class WorstWindow(BaseModel):
    """误差最差时间窗口（嵌入在 ErrorProfile 中）

    记录误差最高的前 5 个时间窗口，含起止时间与该窗口 MAPE 值。
    """

    start_time: str
    """异常窗口起始时间 ISO8601"""

    end_time: str
    """异常窗口结束时间 ISO8601"""

    mape: float
    """该窗口 MAPE 值"""

    description: str = ""
    """窗口描述（可选，默认空字符串）"""

    class Config:
        use_enum_values = True


class FeatureDriftDetail(BaseModel):
    """单个特征漂移详情（嵌入在 DataQualityDiagnosis 中）

    记录检测到漂移的特征名称、漂移幅度和方向。
    """

    feature_name: str
    """漂移特征名"""

    drift_magnitude: float
    """漂移幅度（相对值或统计量）"""

    drift_direction: str = ""
    """漂移方向描述（可选，默认空字符串）"""

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# 诊断子模型
# ---------------------------------------------------------------------------

class ErrorProfile(BaseModel):
    """误差画像（嵌入在 RCAReport 中）

    包含预测误差的多维度统计分析，帮助算法工程师定位误差集中的时段和模式。
    """

    mape_by_hour: Dict[str, float] = Field(default_factory=dict)
    """24小时分组平均MAPE，key="0"~"23"（0=午夜）"""

    mape_by_weekday: Dict[str, float] = Field(default_factory=dict)
    """7天分组平均MAPE，key="0"(Mon)~"6"(Sun)"""

    worst_windows: List[WorstWindow] = Field(default_factory=list)
    """MAPE 最高的前 5 个时间窗口"""

    error_bias: ErrorBias = ErrorBias.balanced
    """预测偏差方向（over_forecast=高估 / under_forecast=低估 / balanced=均衡）"""

    peak_valley_error_ratio: Optional[float] = None
    """峰时段误差 vs 谷时段误差比值（None 表示未计算）"""

    class Config:
        use_enum_values = True


class DataQualityDiagnosis(BaseModel):
    """数据质量诊断（嵌入在 RCAReport 中）

    记录数据缺失率、异常值率、特征漂移和数据时效滞后等诊断信息。
    """

    missing_rate: float = 0.0
    """缺失率，范围 0.0~1.0"""

    outlier_rate: float = 0.0
    """异常值率，范围 0.0~1.0"""

    feature_drift_detected: bool = False
    """是否检测到特征漂移"""

    feature_drift_details: List[FeatureDriftDetail] = Field(default_factory=list)
    """漂移特征列表（feature_drift_detected=True 时应有具体条目）"""

    data_freshness_lag_hours: float = 0.0
    """数据时效滞后小时数（用于诊断数据延迟问题）"""

    class Config:
        use_enum_values = True


class ActionableInsight(BaseModel):
    """可执行建议（嵌入在 RCAReport.actionable_insights 中）

    每条建议包含类型、优先级、具体中文描述和数据支撑依据，
    帮助算法工程师即使不重训也能从报告中获取有价值的改善方向。
    """

    insight_type: InsightType
    """建议类型（feature_engineering/data_sourcing/model_retraining_signal/observation/hyperparameter_hint）"""

    priority: InsightPriority
    """优先级（high/medium/low）"""

    description: str
    """具体建议文本（中文）"""

    supporting_evidence: List[str] = Field(default_factory=list)
    """支撑数据依据列表（字符串，引用误差画像或诊断数据中的具体指标）"""

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# 核心实体
# ---------------------------------------------------------------------------

class AccuracyAlert(BaseModel):
    """精度告警实体

    仅由 production 或 shadow 形态的精度退化触发。
    生命周期：open → rca_running → recovering/observing → closed。
    关闭时 recovery_evidence 必须非空。

    存储路径：data/precision_ops/{slot}/accuracy_ops/alerts/{alert_id}.json
    """

    alert_id: str = Field(default_factory=gen_alert_id)
    """告警唯一 ID，格式 alert-{8hex}"""

    slot: str
    """槽位名称（精度运营的分区键，如 default）"""

    model_form: ModelForm
    """触发告警的形态（仅 production 或 shadow）"""

    workflow_id: str
    """退化版本的 workflow_id（来自 version_registry）"""

    version_tag: str
    """退化版本的 version_tag（来自 version_registry）"""

    baseline_mape: float
    """注册时的基线 MAPE（来自 version_registry.baseline_mape）"""

    current_rolling_mape: float
    """当前滚动 MAPE（来自 accuracy_tracker，兼容旧展示）"""

    # @AI_GENERATED: 实际告警可优先使用 WMAPE，保留 MAPE 字段兼容历史告警和前端
    metric_name: str = "mape"
    """本次退化比较使用的指标：wmape 优先，缺失时为 mape。"""

    baseline_metric: Optional[float] = None
    """本次实际比较使用的发布基线指标（百分比）。"""

    current_metric: Optional[float] = None
    """本次实际比较使用的 7 天滚动指标（百分比）。"""
    # @AI_GENERATED: end

    degradation_pct: float
    """退化百分比，公式：(current_rolling_mape - baseline_mape) / baseline_mape * 100"""

    degradation_trend: DegradationTrend
    """退化趋势（sudden=骤升 / gradual=渐升 / stable=持续高位）"""

    severity: AlertSeverity
    """严重级别（warning / critical，按 degradation_pct 分级）"""

    status: AlertStatus = AlertStatus.open
    """告警当前状态"""

    cooldown_until: Optional[str] = None
    """冷却截止时间 ISO8601（冷却期内不重复触发 RCA）"""

    rca_report_id: Optional[str] = None
    """关联 RCA 报告 ID（RCA 产出后回填）"""

    recovery_decision_id: Optional[str] = None
    """关联恢复决策 ID（仲裁后回填）"""

    recovery_evidence: Optional[Dict[str, Any]] = None
    """恢复证据，关闭时必须包含 {type: "passed"|"manual_close", ref: ..., at: ...}"""

    created_at: str = Field(default_factory=now_iso)
    """告警创建时间 ISO8601"""

    updated_at: str = Field(default_factory=now_iso)
    """告警最近更新时间 ISO8601"""

    class Config:
        use_enum_values = True


class RCAReport(BaseModel):
    """根因分析报告实体

    记录针对某条精度告警的根因分析过程与结论，
    包含误差画像、数据质量诊断和可执行建议等诊断输出。

    存储路径：data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}.json
    Artifacts：data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}/
    """

    rca_report_id: str = Field(default_factory=gen_rca_id)
    """报告唯一 ID，格式 rca-{8hex}"""

    alert_id: str
    """来源告警 ID（AccuracyAlert.alert_id）"""

    trigger_type: RCATriggerType
    """触发方式（scheduled=定时 / alert=告警驱动 / manual=手动）"""

    root_cause: str = ""
    """根因结论（来自 operation_skill，如 data_gap / feature_broken / model_decay / external）"""

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    """置信度，范围 0.0~1.0"""

    reasoning: str = ""
    """推理过程（来自 operation_skill 的文字说明）"""

    supporting_evidence: List[str] = Field(default_factory=list)
    """支撑证据列表（来自 operation_skill）"""

    undetermined: bool = False
    """是否无法定论（True 时仲裁器走观察+人工通道）"""

    error_profile: Optional[ErrorProfile] = None
    """误差画像（operation_skill 产出，含时段误差分布、异常窗口等）"""

    data_quality_diagnosis: Optional[DataQualityDiagnosis] = None
    """数据质量诊断（operation_skill 产出，含缺失率、特征漂移等）"""

    actionable_insights: List[ActionableInsight] = Field(default_factory=list)
    """可执行建议列表（operation_skill 产出，按 priority 排序展示）"""

    candidate_strategies: List[Any] = Field(default_factory=list)
    """候选恢复策略列表（来自 operation_skill，供仲裁器参考）"""

    recommended_strategy_id: Optional[str] = None
    """推荐策略 ID（operation_skill 推荐的最优策略）"""

    artifacts_dir: str = ""
    """artifacts 相对目录（相对 backend-service/，不允许绝对路径）"""

    status: RCAStatus = RCAStatus.running
    """报告执行状态"""

    created_at: str = Field(default_factory=now_iso)
    """报告创建时间 ISO8601"""

    class Config:
        use_enum_values = True


class RecoveryDecision(BaseModel):
    """恢复决策实体

    记录仲裁器基于 RCA 结论和影子池状态做出的恢复通道选择及执行状态。
    本轮仅支持 shadow_switch（通道A）和 observe（观察）两个通道。

    存储路径：data/precision_ops/{slot}/accuracy_ops/recovery/{decision_id}.json
    """

    decision_id: str = Field(default_factory=gen_decision_id)
    """决策唯一 ID，格式 rec-{8hex}"""

    alert_id: str
    """来源告警 ID（AccuracyAlert.alert_id）"""

    rca_report_id: str
    """引用的 RCA 报告 ID（必须对应已存在的 RCAReport）"""

    channel: RecoveryChannel
    """选定恢复通道（shadow_switch=通道A影子切换 / observe=观察等待）"""

    decision_reason: str
    """决策理由（说明为何选择该通道）"""

    confidence_gate_passed: bool
    """是否通过置信度门控（confidence >= 0.6 且 undetermined=False）"""

    switch_event_id: Optional[str] = None
    """通道A产出的切换事件 ID（来自部署切换引擎，执行后回填）"""

    # @AI_GENERATED: 精度运营只保存部署动作建议，部署服务是实际状态机与审计真源
    target_workflow_id: Optional[str] = None
    """推荐提升为 production 的影子 workflow_id。"""

    target_version_tag: Optional[str] = None
    """推荐目标的 version_tag，消除同 workflow 多版本歧义。"""
    # @AI_GENERATED: end

    sla_deadline: str
    """SLA 截止时间 ISO8601（shadow_switch=2h / observe=12h）"""

    rollback_of: Optional[str] = None
    """若此决策是回滚操作，指向被回滚的 decision_id"""

    status: DecisionStatus = DecisionStatus.pending
    """决策执行状态"""

    created_at: str = Field(default_factory=now_iso)
    """决策创建时间 ISO8601"""

    updated_at: str = Field(default_factory=now_iso)
    """决策最近更新时间 ISO8601"""

    class Config:
        use_enum_values = True
# @AI_GENERATED: end
