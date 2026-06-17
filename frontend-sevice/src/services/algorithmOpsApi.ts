// @AI_GENERATED: Kiro v1.0
/**
 * 算法运营 API 服务
 * 封装漂移监控、A/B测试、自动重训的所有API调用
 */
import api from './api';
import type {
  ModelDriftInfo,
  FeatureDriftDetail,
  AccuracyTrendPoint,
  RootCauseAnalysis,
  DriftMonitorStats,
  ABTestConfig,
  ABTestMetrics,
  ABTestStats,
  RetrainTask,
  RetrainStrategy,
  RetrainStats,
  PromptExecutionResult,
} from '../types/algorithm-ops';

// ============ 漂移监控 API ============

export const driftApi = {
  /** 获取漂移监控统计 */
  getStats: (): Promise<DriftMonitorStats> => api.get('/ops/drift/stats'),
  
  /** 获取所有模型漂移状态 */
  getModels: (params?: { scenario_id?: string; status?: string }): Promise<ModelDriftInfo[]> =>
    api.get('/ops/drift/models', { params }),
  
  /** 获取单个模型漂移详情 */
  getModelDrift: (modelId: string): Promise<ModelDriftInfo> =>
    api.get(`/ops/drift/models/${modelId}`),
  
  /** 获取特征漂移详情 */
  getFeatureDrift: (modelId: string): Promise<FeatureDriftDetail[]> =>
    api.get(`/ops/drift/models/${modelId}/features`),
  
  /** 获取精度趋势 */
  getAccuracyTrend: (modelId: string, days?: number): Promise<AccuracyTrendPoint[]> =>
    api.get(`/ops/drift/models/${modelId}/accuracy-trend`, { params: { days } }),
  
  /** 触发漂移检测 */
  triggerDetection: (modelId: string): Promise<{ success: boolean; message: string }> =>
    api.post(`/ops/drift/models/${modelId}/detect`),
  
  /** 获取根因分析 */
  getRootCauseAnalysis: (modelId: string): Promise<RootCauseAnalysis> =>
    api.get(`/ops/drift/models/${modelId}/root-cause`),
  
  /** 执行 AI Prompt */
  executePrompt: (prompt: string): Promise<PromptExecutionResult> =>
    api.post('/ops/drift/prompt', { prompt }),
};

// ============ A/B测试 API ============

export const abTestApi = {
  /** 获取A/B测试统计 */
  getStats: (): Promise<ABTestStats> => api.get('/ops/ab-test/stats'),
  
  /** 获取所有A/B测试 */
  getTests: (params?: { status?: string; scenario_id?: string }): Promise<ABTestConfig[]> =>
    api.get('/ops/ab-test/tests', { params }),
  
  /** 获取单个A/B测试详情 */
  getTest: (testId: string): Promise<ABTestConfig> =>
    api.get(`/ops/ab-test/tests/${testId}`),
  
  /** 创建A/B测试 */
  createTest: (config: Partial<ABTestConfig>): Promise<ABTestConfig> =>
    api.post('/ops/ab-test/tests', config),
  
  /** 更新A/B测试 */
  updateTest: (testId: string, config: Partial<ABTestConfig>): Promise<ABTestConfig> =>
    api.put(`/ops/ab-test/tests/${testId}`, config),
  
  /** 启动A/B测试 */
  startTest: (testId: string): Promise<{ success: boolean; message: string }> =>
    api.post(`/ops/ab-test/tests/${testId}/start`),
  
  /** 暂停A/B测试 */
  pauseTest: (testId: string): Promise<{ success: boolean; message: string }> =>
    api.post(`/ops/ab-test/tests/${testId}/pause`),
  
  /** 结束A/B测试 */
  endTest: (testId: string): Promise<{ success: boolean; message: string }> =>
    api.post(`/ops/ab-test/tests/${testId}/end`),
  
  /** 获取A/B测试指标对比 */
  getMetrics: (testId: string): Promise<ABTestMetrics> =>
    api.get(`/ops/ab-test/tests/${testId}/metrics`),
  
  /** 执行 AI Prompt */
  executePrompt: (prompt: string): Promise<PromptExecutionResult> =>
    api.post('/ops/ab-test/prompt', { prompt }),
};

// ============ 自动重训 API ============

export const retrainApi = {
  /** 获取重训统计 */
  getStats: (): Promise<RetrainStats> => api.get('/ops/retrain/stats'),
  
  /** 获取所有重训任务 */
  getTasks: (params?: { status?: string; scenario_id?: string }): Promise<RetrainTask[]> =>
    api.get('/ops/retrain/tasks', { params }),
  
  /** 获取单个重训任务详情 */
  getTask: (taskId: string): Promise<RetrainTask> =>
    api.get(`/ops/retrain/tasks/${taskId}`),
  
  /** 创建重训任务 */
  createTask: (config: Partial<RetrainTask>): Promise<RetrainTask> =>
    api.post('/ops/retrain/tasks', config),
  
  /** 取消重训任务 */
  cancelTask: (taskId: string): Promise<{ success: boolean; message: string }> =>
    api.post(`/ops/retrain/tasks/${taskId}/cancel`),
  
  /** 获取重训策略列表 */
  getStrategies: (): Promise<RetrainStrategy[]> =>
    api.get('/ops/retrain/strategies'),
  
  /** 更新重训策略 */
  updateStrategy: (strategyId: string, config: Partial<RetrainStrategy>): Promise<RetrainStrategy> =>
    api.put(`/ops/retrain/strategies/${strategyId}`, config),
  
  /** 执行 AI Prompt */
  executePrompt: (prompt: string): Promise<PromptExecutionResult> =>
    api.post('/ops/retrain/prompt', { prompt }),
};

// ============ 统一 Prompt API ============

// @AI_GENERATED: Kiro v1.0
/** Prompt 执行请求参数 */
export interface PromptExecuteRequest {
  prompt: string;
  context?: Record<string, any>;
  model_id?: string;
  scenario_id?: string;
  time_range?: string;
  enabled_skills?: string[];
}

/** Prompt 执行响应 */
export interface PromptExecuteResponse {
  response: string;
  type: string;
  data: Record<string, any>;
  actions?: Array<{
    label: string;
    action: string;
    [key: string]: any;
  }>;
}

export const opsPromptApi = {
  /** 执行跨页面 Prompt */
  execute: (prompt: string): Promise<PromptExecutionResult> =>
    api.post('/ops/prompt', { prompt }),
  
  /** 执行 AI Prompt（统一入口） */
  executePrompt: (request: PromptExecuteRequest): Promise<PromptExecuteResponse> =>
    api.post('/algorithm-ops/prompt/execute', request),
};
// @AI_GENERATED: end
