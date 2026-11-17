// @AI_GENERATED: Kiro v1.0
/**
 * Algorithm Agent 类型定义
 * 算法全生命周期管理 Agent
 */

// ============ 通用类型 ============

export type AgentPhase = 'research' | 'release' | 'operation';
export type MessageRole = 'user' | 'assistant' | 'system';
export type SkillStatus = 'idle' | 'running' | 'success' | 'error';
export type ModelType = 'Linear' | 'Ridge' | 'MLP' | 'LSTM' | 'XGBoost' | 'LightGBM';

// @AI_GENERATED: Kiro v1.0
// Agent 类型定义
export type AgentType = 'curator' | 'sandbox' | 'onboarding' | 'operation';

export interface AgentTypeConfig {
  id: AgentType;
  name: string;
  englishName: string;
  description: string;
  icon: string;
  color: string;
  gradient: string;
  capabilities: string[];
  quickCommands: { label: string; prompt: string }[];
  systemPrompt: string;
}
// @AI_GENERATED: end

// ============ 对话消息 ============

/** 运营 Agent（多轮工具调用）思考轨迹，与后端 thinking_trace 对齐 */
export interface OperationThinkingStep {
  round: number;
  /** 流式进度行（连接大模型、第 N 轮推理等） */
  status?: 'progress';
  message?: string;
  assistant?: string | null;
  tools?: Array<{
    name: string;
    arguments: Record<string, unknown>;
    result_preview: string;
  }>;
}

export interface OperationObservability {
  preloading?: {
    workflow_id?: string | null;
    /** 后端：user_message | explicit_context | preselected_template | last_executed_run | template_path | auto_* */
    workflow_id_source?: string | null;
    template_found?: boolean;
    template_source?: string | null;
    template_path?: string | null;
    template_error?: string | null;
    node_count?: number;
    edge_count?: number;
    operator_ids?: string[];
    operator_param_keys?: Record<string, string[]>;
    backtest_loaded?: boolean;
    training_loaded?: boolean;
  };
  routing?: {
    rule_scores?: Record<string, number>;
    llm_scores?: Record<string, number>;
    final_scores?: Record<string, number>;
    ranked?: Array<[string, number]>;
    selected_targets?: string[];
    execution_plan?: string[];
    confirmation_needed?: boolean;
    llm_reason?: string | null;
  };
  execution?: {
    plan?: string[];
    stages?: Array<{
      agent: string;
      status: 'success' | 'failed';
      summary?: string;
      result_keys?: string[];
      details?: Record<string, unknown>;
    }>;
  };
}

export interface AgentMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  skill?: string;
  skillResult?: SkillExecutionResult;
  attachments?: MessageAttachment[];
  llm_used?: boolean;  // 是否由 LLM 生成
  /** 仅运营 Agent：模型输出的「思考过程」正文（来自后端解析的 agent_thinking 段，非工具日志） */
  reasoningContent?: string;
  /** 旧版：工具/轮次轨迹，不再默认展示，仅兼容历史 */
  thinkingTrace?: OperationThinkingStep[];
  /** 运营 Agent 阶段可观测数据（预读取/路由/执行） */
  operationObservability?: OperationObservability;
}

export interface MessageAttachment {
  type: 'chart' | 'table' | 'code' | 'workflow' | 'model';
  title: string;
  data: unknown;
}

// ============ Skill 执行 ============

export interface SkillExecutionResult {
  skill_name: string;
  status: SkillStatus;
  output?: unknown;
  error?: string;
  duration_ms: number;
  artifacts?: SkillArtifact[];
}

export interface SkillArtifact {
  type: 'model' | 'report' | 'chart' | 'data';
  name: string;
  url?: string;
  preview?: unknown;
}

// ============ 算法推荐 ============

export interface AlgorithmRecommendRequest {
  description: string;
  data_characteristics?: DataCharacteristics;
  business_objective?: string;
}

export interface DataCharacteristics {
  data_type: 'timeseries' | 'tabular' | 'image' | 'text';
  row_count?: number;
  feature_count?: number;
  missing_rate?: number;
  has_label?: boolean;
}

export interface AlgorithmRecommendation {
  algorithm_id: string;
  algorithm_name: string;
  category: string;
  score: number;
  rationale: string;
  source: 'basic_module' | 'industry_template';
  parameters?: Record<string, unknown>;
}

export interface AlgorithmRecommendResponse {
  recommendations: AlgorithmRecommendation[];
  data_analysis?: DataAnalysisResult;
  processing_time_ms: number;
}

export interface DataAnalysisResult {
  detected_type: string;
  statistics: Record<string, unknown>;
  suggestions: string[];
}

// ============ 参数配置 ============

export interface ParamConfigRequest {
  algorithm_id: string;
  data_characteristics?: DataCharacteristics;
  preset?: 'quick' | 'standard' | 'high_accuracy';
}

export interface ParameterSpec {
  name: string;
  type: 'int' | 'float' | 'string' | 'bool' | 'select';
  default: unknown;
  min?: number;
  max?: number;
  options?: string[];
  description: string;
  impact: string;
}

export interface ParamConfigResponse {
  algorithm_id: string;
  parameters: ParameterSpec[];
  recommended_config: Record<string, unknown>;
  presets: Record<string, Record<string, unknown>>;
}

// ============ 训练流水线 ============

export interface TrainingRequest {
  skill_id: string;
  model_type: ModelType;
  parameters?: Record<string, unknown>;
  data_config?: {
    train_ratio?: number;
    val_ratio?: number;
    test_ratio?: number;
  };
}

export interface TrainingProgress {
  stage: 'data_validation' | 'data_split' | 'training' | 'evaluation' | 'saving';
  progress: number;
  current_epoch?: number;
  total_epochs?: number;
  metrics?: Record<string, number>;
  logs?: string[];
}

export interface TrainingResult {
  task_id: string;
  status: 'success' | 'failed';
  model_path?: string;
  metrics: {
    train: Record<string, number>;
    val: Record<string, number>;
    test: Record<string, number>;
  };
  training_time_s: number;
  model_size_mb?: number;
}

// ============ 实验对比 ============

export interface ExperimentRecord {
  id: string;
  name: string;
  algorithm_id: string;
  parameters: Record<string, unknown>;
  metrics: Record<string, number>;
  created_at: string;
  tags?: string[];
}

export interface ExperimentCompareRequest {
  experiment_ids: string[];
  metrics?: string[];
}

export interface ExperimentCompareResponse {
  experiments: ExperimentRecord[];
  comparison_table: Record<string, Record<string, number>>;
  best_experiment_id: string;
  analysis: string;
}

// ============ 漂移检测 ============

export interface DriftDetectRequest {
  model_id: string;
  reference_data?: string;
  current_data?: string;
}

export interface DriftDetectResult {
  model_id: string;
  data_drift: {
    detected: boolean;
    psi_score: number;
    drifted_features: string[];
  };
  concept_drift: {
    detected: boolean;
    metric_degradation: number;
    trend: 'stable' | 'declining' | 'improving';
  };
  recommendation: string;
  alert_level: 'none' | 'warning' | 'critical';
}

// ============ A/B 测试 ============

export interface ABTestConfig {
  name: string;
  control_model_id: string;
  treatment_model_id: string;
  traffic_split: number; // 0-100, treatment percentage
  duration_hours: number;
  metrics: string[];
}

export interface ABTestResult {
  test_id: string;
  status: 'running' | 'completed' | 'stopped';
  control_metrics: Record<string, number>;
  treatment_metrics: Record<string, number>;
  p_value?: number;
  is_significant?: boolean;
  recommendation?: 'adopt' | 'reject' | 'extend';
  sample_size: { control: number; treatment: number };
}

// ============ 自动重训 ============

export interface RetrainTrigger {
  type: 'metric_threshold' | 'scheduled' | 'drift_alert' | 'manual';
  condition?: Record<string, unknown>;
}

export interface RetrainConfig {
  model_id: string;
  triggers: RetrainTrigger[];
  training_type: 'incremental' | 'full';
  data_range?: { start: string; end: string };
  auto_deploy: boolean;
}

export interface RetrainResult {
  task_id: string;
  trigger_reason: string;
  training_type: 'incremental' | 'full';
  old_metrics: Record<string, number>;
  new_metrics: Record<string, number>;
  improvement: Record<string, number>;
  deployed: boolean;
}

// ============ Agent 会话 ============

export interface AgentSession {
  id: string;
  title: string;
  phase: AgentPhase;
  messages: AgentMessage[];
  context: SessionContext;
  created_at: string;
  updated_at: string;
}

export interface SessionContext {
  selected_algorithm?: AlgorithmRecommendation;
  selected_skill?: string;
  current_model?: string;
  experiment_ids?: string[];
  active_ab_test?: string;
  agent_type?: AgentType;  // 当前使用的 Agent 类型
  language?: string; // 当前会话语言（zh-CN / en-US）
  /** 运营分析：本轮显式指定的模板 id（消息里写 workflow- 或传此字段优先） */
  workflow_id?: string;
  template_id?: string;
  /** 编辑器里最近一次启动流水线/回测的模板 id，用于「只说需要」时默认命中 */
  last_executed_workflow_id?: string;
  /** 可选：触发重训后是否自动执行一轮真实回测 */
  trigger_backtest_after_retrain?: boolean;
  /** 可选：触发调优后是否自动执行一轮真实回测 */
  trigger_backtest_after_tuning?: boolean;
  /** 可选：指定触发回测的时间范围 */
  backtest_start_date?: string;
  backtest_end_date?: string;
  // @AI_GENERATED: Kiro v1.0
  // 从策划 Agent 预选的模板信息
  preselected_template?: {
    id: string;
    type: 'workflow' | 'skill';
    name: string;
  };
  // @AI_GENERATED: end
}

// ============ Agent 请求/响应 ============

export interface AgentChatRequest {
  session_id?: string;
  message: string;
  context?: SessionContext;
  use_llm?: boolean;  // 是否使用 LLM，默认 true
}

export interface AgentChatResponse {
  session_id: string;
  message: AgentMessage;
  suggested_actions?: SuggestedAction[];
  context_update?: Partial<SessionContext>;
  llm_used?: boolean;  // 是否使用了 LLM
}

// @AI_GENERATED: Kiro v1.0
export interface LLMStatus {
  available: boolean;
  provider?: string;
  model?: string;
  message?: string;
  error?: string;
}
// @AI_GENERATED: end

export interface SuggestedAction {
  label: string;
  action: string;
  params?: Record<string, unknown>;
}
// @AI_GENERATED: end
