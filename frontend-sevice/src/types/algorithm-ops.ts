// @AI_GENERATED: Kiro v1.0
/**
 * 算法运营系统类型定义
 * 包含漂移监控、A/B测试、自动重训三个模块的类型
 */

// ============ 漂移监控类型 ============

/** 漂移状态枚举 */
export type DriftStatus = 'normal' | 'mild' | 'severe';

/** 漂移类型枚举 */
export type DriftType = 'data' | 'concept' | 'both';

/** 模型漂移信息 */
export interface ModelDriftInfo {
  model_id: string;
  model_name: string;
  scenario_id: string;
  scenario_name: string;
  status: DriftStatus;
  drift_type: DriftType;
  psi_score: number;
  accuracy_change: number;
  last_check_time: string;
  alert_triggered: boolean;
}

/** 特征漂移详情 */
export interface FeatureDriftDetail {
  feature_name: string;
  psi_value: number;
  ks_statistic: number;
  js_divergence: number;
  drift_status: DriftStatus;
  train_mean: number;
  train_std: number;
  prod_mean: number;
  prod_std: number;
}

/** 精度趋势数据点 */
export interface AccuracyTrendPoint {
  timestamp: string;
  rmse: number;
  mae: number;
  mape: number;
  r2: number;
}

/** 根因分析结果 */
export interface RootCauseAnalysis {
  model_id: string;
  analysis_time: string;
  contributing_factors: ContributingFactor[];
  recommendations: string[];
  ai_summary: string;
}

/** 贡献因子 */
export interface ContributingFactor {
  factor_name: string;
  factor_type: 'feature_drift' | 'data_quality' | 'concept_shift' | 'external';
  contribution_score: number;
  description: string;
}

/** 漂移监控统计 */
export interface DriftMonitorStats {
  total_models: number;
  normal_count: number;
  mild_drift_count: number;
  severe_drift_count: number;
  retrain_triggered: number;
}

// ============ A/B测试类型 ============

/** A/B测试状态 */
export type ABTestStatus = 'draft' | 'running' | 'paused' | 'completed' | 'cancelled';

/** A/B测试结果 */
export type ABTestResult = 'pending' | 'a_wins' | 'b_wins' | 'no_difference';

/** A/B测试配置 */
export interface ABTestConfig {
  test_id: string;
  test_name: string;
  model_a_id: string;
  model_a_name: string;
  model_b_id: string;
  model_b_name: string;
  traffic_split: number; // 0-100, A的流量百分比
  start_time: string;
  end_time?: string;
  status: ABTestStatus;
  result: ABTestResult;
  scenario_id: string;
  scenario_name: string;
}

/** A/B测试指标对比 */
export interface ABTestMetrics {
  test_id: string;
  model_a_metrics: ModelMetrics;
  model_b_metrics: ModelMetrics;
  statistical_significance: number;
  confidence_level: number;
  sample_size_a: number;
  sample_size_b: number;
}

/** 模型指标 */
export interface ModelMetrics {
  accuracy: number;
  latency_p50: number;
  latency_p99: number;
  error_rate: number;
  throughput: number;
}

/** A/B测试统计 */
export interface ABTestStats {
  total_tests: number;
  running_count: number;
  completed_count: number;
  a_wins_count: number;
  b_wins_count: number;
}

// ============ 自动重训类型 ============

/** 重训任务状态 */
export type RetrainStatus = 'queued' | 'training' | 'validating' | 'completed' | 'failed' | 'cancelled';

/** 重训类型 */
export type RetrainType = 'incremental' | 'full';

/** 重训触发原因 */
export type RetrainTrigger = 'drift_detected' | 'scheduled' | 'manual' | 'ab_test_result';

/** 重训任务 */
export interface RetrainTask {
  task_id: string;
  model_id: string;
  model_name: string;
  scenario_id: string;
  scenario_name: string;
  retrain_type: RetrainType;
  trigger: RetrainTrigger;
  status: RetrainStatus;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  progress: number;
  old_accuracy: number;
  new_accuracy?: number;
  improvement?: number;
}

/** 重训策略配置 */
export interface RetrainStrategy {
  strategy_id: string;
  model_id: string;
  model_name: string;
  enabled: boolean;
  drift_threshold: number;
  accuracy_drop_threshold: number;
  min_retrain_interval_hours: number;
  prefer_incremental: boolean;
  auto_deploy: boolean;
  require_ab_test: boolean;
}

/** 重训统计 */
export interface RetrainStats {
  total_tasks: number;
  queued_count: number;
  training_count: number;
  completed_count: number;
  failed_count: number;
  avg_improvement: number;
}

// ============ 通用类型 ============

/** AI Prompt 执行结果 */
export interface PromptExecutionResult {
  success: boolean;
  intent: string;
  skills_executed: string[];
  result_summary: string;
  detailed_results: any;
  execution_time_ms: number;
}

/** 快捷指令 */
export interface QuickCommand {
  label: string;
  prompt: string;
  icon?: string;
}

// ============ 状态配置 ============

/** 漂移状态颜色映射 */
export const DRIFT_STATUS_CONFIG: Record<DriftStatus, { color: string; text: string }> = {
  normal: { color: '#52c41a', text: '正常' },
  mild: { color: '#faad14', text: '轻度漂移' },
  severe: { color: '#f5222d', text: '严重漂移' },
};

/** A/B测试状态颜色映射 */
export const ABTEST_STATUS_CONFIG: Record<ABTestStatus, { color: string; text: string }> = {
  draft: { color: '#d9d9d9', text: '草稿' },
  running: { color: '#1890ff', text: '运行中' },
  paused: { color: '#faad14', text: '已暂停' },
  completed: { color: '#52c41a', text: '已完成' },
  cancelled: { color: '#ff4d4f', text: '已取消' },
};

/** 重训状态颜色映射 */
export const RETRAIN_STATUS_CONFIG: Record<RetrainStatus, { color: string; text: string }> = {
  queued: { color: '#d9d9d9', text: '排队中' },
  training: { color: '#1890ff', text: '训练中' },
  validating: { color: '#722ed1', text: '验证中' },
  completed: { color: '#52c41a', text: '已完成' },
  failed: { color: '#f5222d', text: '失败' },
  cancelled: { color: '#ff4d4f', text: '已取消' },
};
// @AI_GENERATED: end
