// @AI_GENERATED
/**
 * 流水线执行相关 TypeScript 类型定义
 */

// ===== 工作流全局配置 =====
export interface WorkflowGlobalConfig {
  time_zone: string;
  operate_status: string;
  nowtime: string;
  // @AI_GENERATED
  task_type: string;
  run_mode?: 'training' | 'prediction' | 'backtest' | 'tuning' | string;
  backtest_start_date?: string;
  backtest_end_date?: string;
  backtest_train_days?: number;
  backtest_daily_horizon?: number;
  backtest_generate_artifacts?: boolean;
  backtest_output_dir?: string;
  backtest_apply_window_filter?: boolean;
  backtest_mask_target_values?: boolean;
  backtest_mode?: 'rolling_retrain' | 'inference_only' | string;
  backtest_model_ref?: string;
  use_reference_rolling_engine?: boolean;
  strict_alignment_mode?: boolean;
  tuning_objective?: string;
  tuning_trials?: number;
  tuning_candidates?: Array<{ name?: string; params?: Record<string, any> }>;
  tuning_model_family?: string;
  tuning_model_params?: Record<string, any>;
  // @AI_GENERATED: end
}

// ===== 算子配置 =====
export interface OperatorParameter {
  name: string;
  type: 'STRING' | 'NUMBER' | 'BOOLEAN' | 'ARRAY' | 'SELECT';
  label: string;
  description: string;
  default_value: any;
  required: boolean;
  group: 'basic' | 'advanced';
  options?: { label: string; value: any }[];
  min?: number;
  max?: number;
  step?: number;
}

// ===== 数据契约 =====
export interface DataContract {
  contractId: string;
  dataType: 'MATRIX' | 'ARRAY' | 'NUMBER' | 'OBJECT' | 'STRING';
  requiredColumns: string[];
  columnTypes: Record<string, string>;
  constraints: string[];
  description: string;
}

// ===== 流水线模板 =====
export interface PipelineTemplate {
  id: string;
  name: string;
  description: string;
  type: 'training' | 'prediction' | 'backtest' | 'tuning';
  nodes: PipelineTemplateNode[];
  edges: PipelineTemplateEdge[];
  dataContracts: Record<string, DataContract>;
  defaultGlobalConfig: WorkflowGlobalConfig;
}

export interface PipelineTemplateNode {
  operatorId: string;
  label: string;
  position: { x: number; y: number };
  defaultParams: Record<string, any>;
  advancedParams?: Record<string, any>;
  description?: string;
}

export interface PipelineTemplateEdge {
  sourceOperator: string;
  targetOperator: string;
  contractId: string;
}

// ===== 执行状态 =====
export type ExecutionStatus = 'idle' | 'pending' | 'running' | 'success' | 'failed';

export interface NodeExecutionStatus {
  nodeId: string;
  operatorId: string;
  label: string;
  status: 'waiting' | 'running' | 'completed' | 'failed';
  duration?: number;
  error?: string;
}

export interface PipelineLogEntry {
  timestamp: string;
  message: string;
  type: 'info' | 'start' | 'success' | 'error' | 'config' | 'separator';
  nodeId?: string;
}

export interface BacktestProgressState {
  currentDay: number;
  totalDays: number;
  currentDate: string;
}

// ===== 执行结果 =====
export interface NodeExecutionResult {
  nodeId: string;
  status: 'success' | 'failed';
  output: any;
  outputSummary: {
    dataType: string;
    rowCount?: number;
    columnNames?: string[];
    preview?: any[];
    arrayLength?: number;
    value?: number;
  };
  executionTime: number;
  error?: string;
}

// ===== 训练结果 =====
export interface TrainingPipelineResult {
  executionId: string;
  totalDuration: number;
  completedAt: string;
  templateName: string;
  modelId?: string;
  nodeDurations: Record<string, number>;
  metrics?: {
    smape?: number;
    mse?: number;
    rmse?: number;
    mae?: number;
    // 分类指标（光伏故障诊断）
    accuracy?: number;
    precision?: number;
    recall?: number;
    f1?: number;
    confusion_matrix?: {
      labels: string[];
      data: number[][];
    };
    classification_report?: string;
    feature_list?: string[];
  };
}

// ===== 推理结果 =====
export interface PredictionPipelineResult {
  executionId: string;
  totalDuration: number;
  completedAt: string;
  modelId: string;
  forecastTimestamps: string[];
  forecastValues: number[];
  nodeDurations: Record<string, number>;
  // 故障诊断预测结果
  faultPredictions?: Array<{
    site_id?: string;
    device_id?: string;
    branch_id?: number | string;
    time_window?: string;
    predictions?: number | string;
    [key: string]: any;
  }>;
  // 模型历史评估指标（来自训练时保存）
  metrics?: {
    accuracy?: number;
    precision?: number;
    recall?: number;
    f1?: number;
    confusion_matrix?: {
      labels: string[];
      data: number[][];
    };
    classification_report?: string;
  };
  // 故障设备时序曲线（单个设备某天的原始波形）
  faultTimeseries?: {
    device_id: string;
    branch_id?: string;
    time_window: string;
    fault_type: string;
    timestamps: string[];
    series: Record<string, number[]>;
  };
}

// ===== 回测结果 =====
export interface BacktestPipelineResult {
  executionId: string;
  totalDuration: number;
  totalDays: number;
  successDays: number;
  skippedDays: number;
  failedDays: number;
  dailyResults: BacktestDailyResult[];
  metrics?: {
    avgSmape: number;
    avgMae: number;
    avgRmse: number;
    dailySmape: { date: string; value: number }[];
    dailyMae: { date: string; value: number }[];
    dailyRmse: { date: string; value: number }[];
  };
  artifactPaths?: string[];
  artifactUrls?: string[];
  outputDir?: string;
  mode?: string;
  rankedCandidates?: Array<{
    rank?: number | null;
    name?: string;
    candidate_index?: number;
    status?: string;
    error?: string;
    candidate_score?: { score?: number; name?: string };
    avg_metrics?: Record<string, number>;
    summary?: Record<string, number>;
    applied_params?: Record<string, any>;
  }>;
  bestRecommendation?: any;
}

export interface BacktestDailyResult {
  date: string;
  status: 'success' | 'skipped' | 'failed';
  durationSeconds?: number;
  forecastTimestamps?: string[];
  forecastValues?: number[];
  actualValues?: number[];
  pointCount?: number;
  reason?: string;
}

// ===== 执行历史 =====
export interface ExecutionRecord {
  executionId: string;
  templateName: string;
  templateType: 'training' | 'prediction' | 'backtest' | 'tuning';
  status: ExecutionStatus;
  modelId?: string;
  totalDuration?: number;
  nodeConfigs: Record<string, any>;
  globalConfig: WorkflowGlobalConfig;
  createdAt: string;
}

// ===== 端口类型颜色映射 =====
export const PORT_TYPE_COLORS: Record<string, string> = {
  MATRIX: '#1890ff',
  ARRAY: '#52c41a',
  NUMBER: '#faad14',
  STRING: '#722ed1',
  OBJECT: '#eb2f96',
};
// @AI_GENERATED: end
