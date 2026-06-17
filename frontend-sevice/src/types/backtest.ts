// @AI_GENERATED: Kiro v1.0
/**
 * 算法回测系统类型定义
 */

export type BacktestTaskStatus = 'pending' | 'running' | 'paused' | 'completed' | 'cancelled' | 'failed';
export type BacktestRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'timeout';
export type AlgorithmType = 'template' | 'workflow';

export interface BacktestDatasetRef {
  id: string;
  name: string;
}

export interface BacktestAlgorithmRef {
  type: AlgorithmType;
  id: string;
  name: string;
}

export interface BacktestMetricsConfig {
  primary_metric: string;
  metrics: string[];
  thresholds: Record<string, number>;
}

export interface BacktestTask {
  id: string;
  name: string;
  description: string;
  scenario_id: string;
  datasets: BacktestDatasetRef[];
  algorithms: BacktestAlgorithmRef[];
  metrics_config: BacktestMetricsConfig;
  status: BacktestTaskStatus;
  created_by: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
}

export interface BacktestRun {
  id: string;
  task_id: string;
  dataset_id: string;
  dataset_name: string;
  algorithm_type: AlgorithmType;
  algorithm_id: string;
  algorithm_name: string;
  status: BacktestRunStatus;
  started_at?: string;
  completed_at?: string;
  execution_time_ms?: number;
  result?: Record<string, number>;
  error_message?: string;
}

export interface BacktestResultMatrix {
  datasets: string[];
  algorithms: string[];
  dataset_names: Record<string, string>;
  algorithm_names: Record<string, string>;
  results: Record<string, Record<string, Record<string, number> & { rank?: number }>>;
}

export interface BacktestRanking {
  algorithm_id: string;
  algorithm_name: string;
  avg_value: number;
  rank: number;
}

export interface BacktestStatistics {
  [algorithmId: string]: {
    [metric: string]: { mean: number; std: number; min: number; max: number; median: number };
  };
}

export interface BacktestResult {
  task_id: string;
  matrix: BacktestResultMatrix;
  ranking: { overall: BacktestRanking[] };
  statistics: BacktestStatistics;
}

export interface BacktestStats {
  total_tasks: number;
  running_tasks: number;
  completed_tasks: number;
  avg_score: number;
}

export const TASK_STATUS_CONFIG: Record<BacktestTaskStatus, { label: string; color: string }> = {
  pending: { label: '待执行', color: 'default' },
  running: { label: '运行中', color: 'processing' },
  paused: { label: '已暂停', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
  cancelled: { label: '已取消', color: 'default' },
  failed: { label: '失败', color: 'error' },
};

export const RUN_STATUS_CONFIG: Record<BacktestRunStatus, { label: string; color: string }> = {
  pending: { label: '待执行', color: '#d9d9d9' },
  running: { label: '执行中', color: '#1890ff' },
  completed: { label: '成功', color: '#52c41a' },
  failed: { label: '失败', color: '#f5222d' },
  timeout: { label: '超时', color: '#faad14' },
};

export const METRIC_OPTIONS = [
  { value: 'rmse', label: 'RMSE' },
  { value: 'mae', label: 'MAE' },
  { value: 'r2', label: 'R²' },
  { value: 'mape', label: 'MAPE' },
  { value: 'f1', label: 'F1-Score' },
  { value: 'precision', label: 'Precision' },
  { value: 'recall', label: 'Recall' },
  { value: 'accuracy', label: 'Accuracy' },
];

export const SCENARIO_METRICS: Record<string, string[]> = {
  'renewable-energy': ['rmse', 'mae', 'r2', 'mape'],
  'industrial-manufacturing': ['f1', 'precision', 'recall', 'accuracy'],
  'grid-load-storage': ['rmse', 'mae', 'r2', 'mape'],
  'carbon-management': ['rmse', 'mae', 'r2'],
  'building-park': ['rmse', 'mae', 'r2', 'mape'],
  'port-transport': ['f1', 'precision', 'recall'],
  'general-industry': ['rmse', 'mae', 'r2'],
};

// @AI_GENERATED: Kiro v1.0
// 智能调度相关类型定义

export type SchedulePriority = 'critical' | 'high' | 'normal' | 'low';

export interface TaskScheduleConfig {
  priority: SchedulePriority;
  deadline?: string;  // ISO datetime
  estimated_duration_minutes: number;
  gpu_required: number;  // GPU 核心数
  cpu_required: number;  // CPU 核心数
  memory_required_gb: number;  // 内存 GB
  allow_preemption: boolean;  // 是否允许被抢占
  max_retry: number;
}

export interface ResourceQuota {
  gpu_total: number;
  gpu_available: number;
  gpu_reserved: number;
  cpu_total: number;
  cpu_available: number;
  cpu_reserved: number;
  memory_total_gb: number;
  memory_available_gb: number;
}

export interface ScheduledTask {
  task_id: string;
  task_name: string;
  task_type: 'workflow' | 'skill';
  schedule_config: TaskScheduleConfig;
  scheduled_start?: string;
  scheduled_end?: string;
  queue_position: number;
  status: 'queued' | 'scheduled' | 'running' | 'completed' | 'preempted';
  resource_allocation?: {
    gpu_allocated: number;
    cpu_allocated: number;
    memory_allocated_gb: number;
  };
}

export interface ScheduleOptimizationResult {
  optimized_order: ScheduledTask[];
  total_estimated_time_minutes: number;
  resource_utilization: {
    gpu_utilization: number;
    cpu_utilization: number;
    memory_utilization: number;
  };
  deadline_violations: Array<{
    task_id: string;
    task_name: string;
    deadline: string;
    estimated_completion: string;
    delay_minutes: number;
  }>;
  recommendations: string[];
}

export const PRIORITY_CONFIG: Record<SchedulePriority, { label: string; color: string; weight: number }> = {
  critical: { label: '紧急', color: '#f5222d', weight: 4 },
  high: { label: '高', color: '#fa8c16', weight: 3 },
  normal: { label: '普通', color: '#1890ff', weight: 2 },
  low: { label: '低', color: '#8c8c8c', weight: 1 },
};
// @AI_GENERATED: end
