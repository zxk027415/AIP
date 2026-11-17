// @AI_GENERATED
/**
 * 负荷预测训练可视化界面类型定义
 */

// ===== 场景配置 =====
export interface ScenarioConfig {
  task_type: string;        // "DI" | "D" | "WI" | "W" | "MI" | "M"
  name: string;
  description: string;
  rounding_unit: string | null;
  default_retrain: boolean | null;
  forecast_horizon_range: number[] | null;
}

// ===== 训练参数 =====
export interface TrainingParams {
  task_type: string;
  csv_path: string;
  parent_id: string;
  child_id: string;
  forecast_horizon: number;
  time_granularity: string;
  separate_modeling: string;       // "true" | "false" (后端接收字符串)
  forecast_start_time: string;
  // 可选高级参数
  table_name?: string;
  parent_field?: string;
  child_field?: string;
  time_field?: string;
  load_field?: string;
  time_zone?: string;
  other_cols?: string[];
  specify_model?: string;
  nowtime?: string;
}

// ===== 任务状态 =====
export type TaskStatus = 'idle' | 'pending' | 'running' | 'success' | 'failed';

export type TrainingStepName = 'data_fetch' | 'anomaly_detection' | 'feature_engineering' | 'model_train';

export interface TrainingStepInfo {
  name: TrainingStepName;
  label: string;
  status: 'waiting' | 'running' | 'completed' | 'error';
  duration?: number;  // 秒
}

// ===== 日志条目 =====
export interface LogEntry {
  timestamp: string;     // "HH:MM:SS"
  message: string;
  type: 'info' | 'start' | 'success' | 'error' | 'config';
}

// ===== 训练结果 =====
export interface TrainingResult {
  task_id: string;
  model_id: string;
  total_duration: number;
  step_durations: Record<string, number>;
  task_type: string;
  created_at: string;
}

// ===== 回测参数 =====
export interface BacktestParams {
  task_type: string;
  csv_path: string;
  parent_id: string;
  child_id: string;
  forecast_horizon: number;
  time_granularity: string;
  separate_modeling: string;
  forecast_start_time: string;
  start_date: string;
  end_date: string;
  // 继承训练时的其他参数
  table_name?: string;
  parent_field?: string;
  child_field?: string;
  time_field?: string;
  load_field?: string;
  time_zone?: string;
  other_cols?: string[];
  specify_model?: string;
}

// ===== 回测结果 =====
export interface BacktestDailyResult {
  date: string;
  status: 'success' | 'skipped' | 'failed';
  duration_seconds?: number;
  forecast_timestamps?: string[];
  forecast_values?: number[];
  point_count?: number;
  reason?: string;
}

export interface BacktestResult {
  task_id: string;
  status: string;
  duration_seconds: number;
  total_days: number;
  success_days: number;
  skipped_days: number;
  failed_days: number;
  daily_results: BacktestDailyResult[];
}

// ===== 训练历史记录 =====
export interface TrainingRecord {
  task_id: string;
  task_type: string;
  status: TaskStatus;
  model_id?: string;
  total_duration?: number;
  params: Partial<TrainingParams>;
  created_at: string;
}

// ===== API 响应 =====
export interface ScenariosResponse {
  scenarios: ScenarioConfig[];
}

export interface TrainResponse {
  task_id: string;
  status: string;
  model_id?: string;
  duration_seconds?: number;
  steps_completed?: string[];
  metrics?: Record<string, any>;
}

export interface TaskStatusResponse {
  task_id: string;
  status: string;
  task_type: string;
  current_step: string | null;
  completed_steps: string[];
  step_durations: Record<string, number>;
  total_duration: number;
  error_message: string | null;
  error_step: string | null;
  created_at: string;
  updated_at: string;
  result: Record<string, any> | null;
}

// ===== 步骤常量（展示文案由 i18n loadForecast.steps.* 提供）=====
export const TRAINING_STEPS: { name: TrainingStepName }[] = [
  { name: 'data_fetch' },
  { name: 'anomaly_detection' },
  { name: 'feature_engineering' },
  { name: 'model_train' },
];

export const TASK_TYPE_CODES = ['DI', 'D', 'WI', 'W', 'MI', 'M'] as const;
// @AI_GENERATED: end
