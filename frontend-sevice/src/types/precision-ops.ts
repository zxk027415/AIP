/**
 * Precision Ops Types
 * 精度运营相关类型定义
 */

// 版本注册条目
export interface VersionEntry {
  workflow_id: string;
  version_tag: string;
  source_run_id: string | null;
  source_candidate_id: string | null;
  registered_at: string;
  status: 'production' | 'shadow' | 'retired';
  slot: string;
  baseline_mape: number | null;
}

// 滚动精度指标
export interface RollingMetrics {
  rolling_mape: number;
  rolling_mae: number;
  valid_cycle_count: number;
  total_cycle_count: number;
  last_evaluated_at: string;
  status: 'active' | 'insufficient_data';
}

// 排行榜条目
export interface LeaderboardEntry extends RollingMetrics {
  workflow_id: string;
}

// 切换事件
export interface SwitchEvent {
  event_id: string;
  timestamp: string;
  slot: string;
  trigger_type: 'automatic' | 'manual' | 'rollback';
  source_workflow_id: string;
  target_workflow_id: string;
  source_rolling_mape: number;
  target_rolling_mape: number;
  decision_reason: string;
}

// 槽位配置
export interface SlotConfig {
  slot: string;
  evaluation_window_days: number;
  degradation_threshold_pct: number;
  switch_margin_pct: number;
  cooldown_hours: number;
  min_valid_cycles: number;
  shadow_timeout_seconds: number;
  production_timeout_seconds: number;
  max_shadow_versions: number;
  rollback_window_hours: number;
  auto_switch_enabled: boolean;
  prediction_retention_days: number;
  min_eval_points: number;
  post_switch_observation_points: number;
  eval_window_points: number;
}

// 生产登记条目
export interface ProductionRegistryEntry {
  workflow_id: string;
  version_tag: string;
  updated_at: string;
  source_event_id: string;
}

// 切换日志查询结果
export interface SwitchLogQueryResult {
  total: number;
  page: number;
  page_size: number;
  events: SwitchEvent[];
}

// 预上线项
export interface PrelaunchItem {
  id: string;
  candidate_id: string;
  workflow_id: string;
  version_tag: string;
  slot: string;
  status: 'observing' | 'graduated' | 'failed' | 'cancelled';
  started_at: string;
  observation_days: number;
  graduate_tolerance_pct: number;
  source_run_id: string | null;
  baseline_mape_at_entry: number | null;
  current_rolling_mape: number | null;
  production_rolling_mape: number | null;
  evaluated_cycles: number;
  graduated_at: string | null;
  failed_at: string | null;
  cancelled_at: string | null;
  graduate_reason?: string;
  fail_reason?: string;
  cancel_reason?: string;
  note: string;
}

// 预上线入队请求
export interface PrelaunchEnqueueRequest {
  candidate_id: string;
  workflow_id: string;
  version_tag?: string;
  source_run_id?: string;
  observation_days?: number;
  graduate_tolerance_pct?: number;
  note?: string;
}

// 预上线队列查询结果
export interface PrelaunchQueueResult {
  slot: string;
  queue: PrelaunchItem[];
  total: number;
}
