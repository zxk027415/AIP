// @AI_GENERATED
/**
 * accuracy-operations.ts — 精度运营前端类型定义
 *
 * 与后端 `backend-service/services/accuracy_operations/models.py` 的
 * Pydantic 模型一一对应。JSON 字段名保持 snake_case（与后端 JSON 序列化一致），
 * TypeScript 接口名使用 PascalCase。
 *
 * 相关 spec：`.kiro/specs/accuracy-operations/`
 *   - Requirements 12.1, 12.2, 12.3
 *   - Task 12.1 前端类型定义
 */

// ===========================================================================
// 枚举 / 字面量联合类型
// ===========================================================================

/** 模型形态：production=生产 / shadow=影子 */
export type ModelForm = 'production' | 'shadow';

/** 退化趋势：sudden=骤升 / gradual=渐升 / stable=持续高位 */
export type DegradationTrend = 'sudden' | 'gradual' | 'stable';

/** 告警严重级别：warning=警告 / critical=严重 */
export type AlertSeverity = 'warning' | 'critical';

/** 告警生命周期状态 */
export type AlertStatus = 'open' | 'rca_running' | 'recovering' | 'observing' | 'closed';

/** RCA 触发方式：scheduled=定时 / alert=告警驱动 / manual=手动 */
export type RCATriggerType = 'scheduled' | 'alert' | 'manual';

/** RCA 报告执行状态 */
export type RCAStatus = 'running' | 'succeeded' | 'failed' | 'timeout';

/**
 * 恢复通道（本轮仅支持通道A和观察，通道B已移除）
 * shadow_switch=通道A影子切换 / observe=观察等待
 */
export type RecoveryChannel = 'shadow_switch' | 'observe';

/** 恢复决策执行状态 */
export type DecisionStatus = 'pending' | 'executing' | 'succeeded' | 'failed' | 'rolled_back';

/** 可执行建议类型 */
export type InsightType =
  | 'feature_engineering'
  | 'data_sourcing'
  | 'model_retraining_signal'
  | 'observation'
  | 'hyperparameter_hint';

/** 可执行建议优先级 */
export type InsightPriority = 'high' | 'medium' | 'low';

/** 预测误差偏差方向：over_forecast=高估 / under_forecast=低估 / balanced=均衡 */
export type ErrorBias = 'over_forecast' | 'under_forecast' | 'balanced';

// ===========================================================================
// 嵌入子类型
// ===========================================================================

/**
 * WorstWindow — 误差最差时间窗口
 * 记录误差最高的前 5 个时间窗口，含起止时间与该窗口 MAPE 值。
 */
export interface WorstWindow {
  /** start_time — 异常窗口起始时间 ISO8601 */
  start_time: string;
  /** end_time — 异常窗口结束时间 ISO8601 */
  end_time: string;
  /** mape — 该窗口 MAPE 值 */
  mape: number;
  /** description — 窗口描述（可选） */
  description: string;
}

/**
 * FeatureDriftDetail — 单个特征漂移详情
 * 记录检测到漂移的特征名称、漂移幅度和方向。
 */
export interface FeatureDriftDetail {
  /** feature_name — 漂移特征名 */
  feature_name: string;
  /** drift_magnitude — 漂移幅度（相对值或统计量） */
  drift_magnitude: number;
  /** drift_direction — 漂移方向描述（可选） */
  drift_direction: string;
}

/**
 * ErrorProfile — 误差画像
 * 包含预测误差的多维度统计分析，帮助定位误差集中的时段和模式。
 */
export interface ErrorProfile {
  /** mape_by_hour — 24小时分组平均MAPE，key="0"~"23" */
  mape_by_hour: Record<string, number>;
  /** mape_by_weekday — 7天分组平均MAPE，key="0"(Mon)~"6"(Sun) */
  mape_by_weekday: Record<string, number>;
  /** worst_windows — MAPE 最高的前 5 个时间窗口 */
  worst_windows: WorstWindow[];
  /** error_bias — 预测偏差方向 */
  error_bias: ErrorBias;
  /** peak_valley_error_ratio — 峰时段误差 vs 谷时段误差比值（null 表示未计算） */
  peak_valley_error_ratio: number | null;
}

/**
 * DataQualityDiagnosis — 数据质量诊断
 * 记录数据缺失率、异常值率、特征漂移和数据时效滞后等诊断信息。
 */
export interface DataQualityDiagnosis {
  /** missing_rate — 缺失率，范围 0.0~1.0 */
  missing_rate: number;
  /** outlier_rate — 异常值率，范围 0.0~1.0 */
  outlier_rate: number;
  /** feature_drift_detected — 是否检测到特征漂移 */
  feature_drift_detected: boolean;
  /** feature_drift_details — 漂移特征列表 */
  feature_drift_details: FeatureDriftDetail[];
  /** data_freshness_lag_hours — 数据时效滞后小时数 */
  data_freshness_lag_hours: number;
}

/**
 * ActionableInsight — 可执行建议
 * 每条建议包含类型、优先级、具体建议和支撑依据。
 */
export interface ActionableInsight {
  /** insight_type — 建议类型 */
  insight_type: InsightType;
  /** priority — 优先级 */
  priority: InsightPriority;
  /** description — 具体建议文本（中文） */
  description: string;
  /** supporting_evidence — 支撑数据依据列表 */
  supporting_evidence: string[];
}

/**
 * RecoveryEvidence — 恢复证据
 * 关闭告警时必须携带，type ∈ {passed, manual_close}。
 */
export interface RecoveryEvidence {
  /** type — 关闭类型：passed=自动恢复通过 / manual_close=人工关闭 */
  type: 'passed' | 'manual_close';
  /** ref — 关联引用（如 switch_event_id 或操作人），可选 */
  ref?: string;
  /** at — 关闭时间 ISO8601，可选 */
  at?: string;
}

// ===========================================================================
// 核心实体
// ===========================================================================

/**
 * AccuracyAlert — 精度告警实体
 *
 * 仅由 production 或 shadow 形态的精度退化触发。
 * 生命周期：open → rca_running → recovering/observing → closed。
 */
export interface AccuracyAlert {
  /** alert_id — 告警唯一 ID，格式 alert-{8hex} */
  alert_id: string;
  /** slot — 槽位名称（精度运营的分区键） */
  slot: string;
  /** model_form — 触发告警的形态（仅 production 或 shadow） */
  model_form: ModelForm;
  /** workflow_id — 退化版本的工作流/模板 ID */
  workflow_id: string;
  /** version_tag — 退化版本的版本标签 */
  version_tag: string;
  /** baseline_mape — 注册时的基线 MAPE（AR 参考，实验告警请优先看 baseline_metric） */
  baseline_mape: number;
  /** current_rolling_mape — 当前滚动 MAPE */
  current_rolling_mape: number;
  /** metric_name — 退化比较指标名 */
  metric_name?: string;
  /** baseline_metric — 实验/线上实际比较基线（百分比），有值时 UI 优先展示 */
  baseline_metric?: number | null;
  /** current_metric — 实验/线上当前指标（百分比），有值时 UI 优先展示 */
  current_metric?: number | null;
  /** degradation_pct — 退化百分比 */
  degradation_pct: number;
  /** degradation_trend — 退化趋势 */
  degradation_trend: DegradationTrend;
  /** severity — 严重级别 */
  severity: AlertSeverity;
  /** status — 告警当前状态 */
  status: AlertStatus;
  /** cooldown_until — 冷却截止时间 ISO8601（冷却期内不重复触发 RCA），null 表示无冷却 */
  cooldown_until: string | null;
  /** rca_report_id — 关联 RCA 报告 ID（RCA 产出后回填） */
  rca_report_id: string | null;
  /** recovery_decision_id — 关联恢复决策 ID（仲裁后回填） */
  recovery_decision_id: string | null;
  /** recovery_evidence — 恢复证据（关闭时必须非空） */
  recovery_evidence: RecoveryEvidence | null;
  /** created_at — 告警创建时间 ISO8601 */
  created_at: string;
  /** updated_at — 告警最近更新时间 ISO8601 */
  updated_at: string;
}

/**
 * RCAReport — 根因分析报告实体
 *
 * 记录针对某条精度告警的根因分析过程与结论，
 * 包含误差画像、数据质量诊断和可执行建议等诊断输出。
 */
export interface RCAReport {
  /** rca_report_id — 报告唯一 ID，格式 rca-{8hex} */
  rca_report_id: string;
  /** alert_id — 来源告警 ID */
  alert_id: string;
  /** trigger_type — 触发方式 */
  trigger_type: RCATriggerType;
  /** root_cause — 根因结论（如 data_gap / feature_broken / model_decay / external） */
  root_cause: string;
  /** confidence — 置信度，范围 0.0~1.0 */
  confidence: number;
  /** reasoning — 推理过程说明 */
  reasoning: string;
  /** supporting_evidence — 支撑证据列表 */
  supporting_evidence: string[];
  /** undetermined — 是否无法定论（true 时仲裁器走观察通道） */
  undetermined: boolean;
  /** error_profile — 误差画像（可选，operation_skill 产出） */
  error_profile: ErrorProfile | null;
  /** data_quality_diagnosis — 数据质量诊断（可选，operation_skill 产出） */
  data_quality_diagnosis: DataQualityDiagnosis | null;
  /** actionable_insights — 可执行建议列表（按 priority 排序展示） */
  actionable_insights: ActionableInsight[];
  /** artifacts_dir — artifacts 相对目录（相对 backend-service/） */
  artifacts_dir: string;
  /** status — 报告执行状态 */
  status: RCAStatus;
  /** created_at — 报告创建时间 ISO8601 */
  created_at: string;
}

/**
 * RecoveryDecision — 恢复决策实体
 *
 * 记录仲裁器基于 RCA 结论和影子池状态做出的恢复通道选择及执行状态。
 * 本轮仅支持 shadow_switch（通道A）和 observe（观察）两个通道。
 */
export interface RecoveryDecision {
  /** decision_id — 决策唯一 ID，格式 rec-{8hex} */
  decision_id: string;
  /** alert_id — 来源告警 ID */
  alert_id: string;
  /** rca_report_id — 引用的 RCA 报告 ID（必须对应已存在的 RCAReport） */
  rca_report_id: string;
  /** channel — 选定恢复通道（shadow_switch=通道A / observe=观察等待） */
  channel: RecoveryChannel;
  /** decision_reason — 决策理由 */
  decision_reason: string;
  /** confidence_gate_passed — 是否通过置信度门控 */
  confidence_gate_passed: boolean;
  /** switch_event_id — 通道A产出的切换事件 ID（执行后回填），null 表示未执行 */
  switch_event_id: string | null;
  /** sla_deadline — SLA 截止时间 ISO8601（shadow_switch=2h / observe=12h） */
  sla_deadline: string;
  /** rollback_of — 若此决策是回滚操作，指向被回滚的 decision_id */
  rollback_of: string | null;
  /** target_workflow_id — 通道 A 要提升的影子工作流 ID；观察通道时为 null。 */
  target_workflow_id?: string | null;
  /** target_version_tag — 通道 A 要提升的影子版本标签；观察通道时为 null。 */
  target_version_tag?: string | null;
  /** status — 决策执行状态 */
  status: DecisionStatus;
  /** created_at — 决策创建时间 ISO8601 */
  created_at: string;
  /** updated_at — 决策最近更新时间 ISO8601 */
  updated_at: string;
}

// ===========================================================================
// API 响应类型
// ===========================================================================

/**
 * DailyMapePoint — 单个业务日的 MAPE 快照
 */
export interface DailyMapePoint {
  business_day?: string | null;
  prediction_cycle_id?: string | null;
  daily_mape?: number | null;
  daily_wmape?: number | null;
  point_count?: number | null;
}

/**
 * MonitoringMetrics — 单个模型的精度监控指标
 * （对应后端 GET /monitoring/snapshot 返回的每条 metrics 对象）
 */
export interface MonitoringMetrics {
  /** workflow_id — 工作流/模板唯一 ID */
  workflow_id: string;
  /** version_tag — 版本标签 */
  version_tag: string;
  /** rolling_mape — 当前滚动 MAPE（null 表示尚未有足够数据） */
  rolling_mape: number | null;
  /** rolling_mae — 当前滚动 MAE（null 表示尚未有足够数据） */
  rolling_mae: number | null;
  /** valid_cycle_count — 有效评估周期数（null 表示尚未统计） */
  valid_cycle_count: number | null;
  /** baseline_mape — 部署登记时的 MAPE 基线，null 表示未登记。 */
  baseline_mape?: number | null;
  /** baseline_wmape — 部署登记时的 WMAPE 基线，null 时监控安全回退 MAPE。 */
  baseline_wmape?: number | null;
  /** rolling_wmape — 当前滚动 WMAPE，退化告警优先使用该指标。 */
  rolling_wmape?: number | null;
  /** rolling_mape_pooled — 7 天窗口内所有点 pooled MAPE（参考口径）。 */
  rolling_mape_pooled?: number | null;
  /** rolling_mape_method — 滚动 MAPE 聚合方式，如 daily_median。 */
  rolling_mape_method?: string | null;
  /** daily_mape_series — 按业务日的 MAPE 序列。 */
  daily_mape_series?: DailyMapePoint[];
  /** coverage_rate — 当前评估窗口中已回填真实值的覆盖率，范围 0~1。 */
  coverage_rate?: number | null;
  /** window_days — 滚动评估窗口天数。 */
  window_days?: number | null;
  /** status — 模型状态描述（null 表示状态未知） */
  status: string | null;
}

/**
 * MonitoringSnapshot — 精度监控快照
 * GET /monitoring/snapshot 返回体，包含生产和所有影子模型的当前指标。
 */
export interface MonitoringSnapshot {
  /** production — 当前生产模型指标（null 表示无生产模型） */
  production: MonitoringMetrics | null;
  /** shadows — 影子模型指标列表 */
  shadows: MonitoringMetrics[];
  /** prelaunches — 预上线模型指标列表 */
  prelaunches: MonitoringMetrics[];
  /** autoresearch_score — AutoResearch 得分（暂为 null，留待后续扩展） */
  autoresearch_score: null;
}

/**
 * LifecycleNode — 模型生命周期图节点
 * GET /models/lifecycle 返回的节点，代表一个模型版本及其当前形态。
 */
export interface LifecycleNode {
  /** workflow_id — 节点对应的工作流/模板 ID */
  workflow_id: string;
  /** version_tag — 版本标签 */
  version_tag: string;
  /** model_form — 模型当前形态（production/shadow/prelaunch/autoresearch） */
  model_form: string;
  /** status — 节点状态（active/retired/observing 等） */
  status: string;
}

/**
 * LifecycleEdge — 模型生命周期图边
 * 代表两个节点之间的状态迁移关系（如影子切换、晋升等）。
 */
export interface LifecycleEdge {
  /** source — 来源节点的 workflow_id */
  source: string;
  /** target — 目标节点的 workflow_id */
  target: string;
  /** transition_type — 迁移类型（如 shadow_switch / promote / rollback），可选 */
  transition_type?: string;
  /** timestamp — 迁移发生时间 ISO8601，可选 */
  timestamp?: string;
}

/**
 * OverviewResponse — 运营总览响应体
 * GET /overview 返回的总览信息，包含当前生产模型指标和告警统计。
 */
export interface OverviewResponse {
  /** slot — 槽位名称 */
  slot: string;
  /** production — 当前生产模型指标（null 表示无生产模型） */
  production: MonitoringMetrics | null;
  /** shadows — 影子模型指标列表 */
  shadows: MonitoringMetrics[];
  /** open_alert_count — 当前未关闭告警数量 */
  open_alert_count: number;
  /** active_recovery_count — 当前活跃恢复决策数量 */
  active_recovery_count: number;
}

/**
 * AlertsResponse — 告警列表响应体
 * GET /alerts 返回的分页告警列表。
 */
export interface AlertsResponse {
  /** alerts — 告警列表（最多 200 条） */
  alerts: AccuracyAlert[];
  /** total — 满足条件的告警总数 */
  total: number;
}

/**
 * LifecycleResponse — 模型生命周期视图响应体
 * GET /models/lifecycle 返回的有向图数据（节点 + 边）。
 */
export interface LifecycleResponse {
  /** nodes — 生命周期图节点列表 */
  nodes: LifecycleNode[];
  /** edges — 生命周期图边列表（状态迁移记录） */
  edges: LifecycleEdge[];
}
// @AI_GENERATED: end
