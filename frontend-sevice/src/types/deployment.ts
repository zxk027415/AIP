// @AI_GENERATED: Kiro v1.0
/**
 * 算法部署上线系统类型定义
 */

export type DeploymentTaskStatus = 'draft' | 'deploying' | 'running' | 'stopped' | 'failed' | 'rollback';
export type ServiceHealth = 'healthy' | 'warning' | 'unhealthy' | 'stopped';
export type ReleaseStrategyType = 'full' | 'canary' | 'blue-green';
export type SourceType = 'template' | 'workflow';
export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertStatus = 'triggered' | 'recovered';
export type CompareOperator = 'gt' | 'lt' | 'gte' | 'lte';

export interface DeployConfig {
  cpu: string;
  memory: string;
  gpu: string;
  replicas: number;
  endpoint: string;
  timeout_ms: number;
  env_vars: Record<string, string>;
}

export interface ReleaseStrategy {
  type: ReleaseStrategyType;
  canary_percent: number;
  auto_promote: boolean;
  promote_after_minutes: number;
}

export interface DeploymentTask {
  id: string;
  name: string;
  description: string;
  scenario: string;
  source_type: SourceType;
  source_id: string;
  source_name: string;
  backtest_task_id?: string | null;
  backtest_rank?: number | null;
  deploy_config: DeployConfig;
  release_strategy: ReleaseStrategy;
  status: DeploymentTaskStatus;
  created_at: string;
  updated_at: string;
}

export interface ServiceReplicas {
  desired: number;
  running: number;
  ready: number;
}

export interface ServiceVersion {
  version: string;
  published_at: string;
  status: 'active' | 'inactive';
}

export interface DeployedService {
  id: string;
  task_id: string;
  name: string;
  endpoint: string;
  version: string;
  replicas: ServiceReplicas;
  health: ServiceHealth;
  qps: number;
  avg_latency_ms: number;
  error_rate: number;
  uptime: string;
  created_at: string;
  versions: ServiceVersion[];
}

export interface ServiceMetricPoint {
  timestamp: string;
  qps: number;
  latency_p50: number;
  latency_p90: number;
  latency_p95: number;
  latency_p99: number;
  error_rate: number;
  cpu_usage: number;
  memory_usage: number;
  gpu_usage: number;
}

export interface AlertRule {
  id: string;
  service_id: string;
  metric_name: string;
  operator: CompareOperator;
  threshold: number;
  severity: AlertSeverity;
  enabled: boolean;
}

export interface AlertHistoryItem {
  id: string;
  rule_id: string;
  service_id: string;
  metric_name: string;
  triggered_value: number;
  severity: AlertSeverity;
  status: AlertStatus;
  triggered_at: string;
  recovered_at: string | null;
}

export interface AccessLog {
  timestamp: string;
  request_id: string;
  input_summary: string;
  output_summary: string;
  latency_ms: number;
  status_code: number;
}

export interface DeploymentStats {
  total_deployments: number;
  running_services: number;
  stopped_services: number;
  avg_health_score: number;
}

// 状态颜色映射
export const TASK_STATUS_CONFIG: Record<DeploymentTaskStatus, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  deploying: { color: 'processing', label: '部署中' },
  running: { color: 'success', label: '运行中' },
  stopped: { color: 'default', label: '已停止' },
  failed: { color: 'error', label: '失败' },
  rollback: { color: 'warning', label: '已回滚' },
};

export const HEALTH_CONFIG: Record<ServiceHealth, { color: string; label: string }> = {
  healthy: { color: '#52c41a', label: '健康' },
  warning: { color: '#faad14', label: '警告' },
  unhealthy: { color: '#ff4d4f', label: '异常' },
  stopped: { color: '#d9d9d9', label: '已停止' },
};

export const SEVERITY_CONFIG: Record<AlertSeverity, { color: string; label: string }> = {
  info: { color: 'blue', label: '信息' },
  warning: { color: 'orange', label: '警告' },
  critical: { color: 'red', label: '严重' },
};

export const RELEASE_STRATEGY_LABELS: Record<ReleaseStrategyType, string> = {
  full: '全量发布',
  canary: '灰度发布',
  'blue-green': '蓝绿部署',
};
// @AI_GENERATED: end
