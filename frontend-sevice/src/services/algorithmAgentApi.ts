// @AI_GENERATED: Kiro v1.0
/**
 * Algorithm Agent API 服务层
 * 算法全生命周期管理 Agent
 */
import api from './api';
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentSession,
  AlgorithmRecommendRequest,
  AlgorithmRecommendResponse,
  ParamConfigRequest,
  ParamConfigResponse,
  TrainingRequest,
  TrainingProgress,
  TrainingResult,
  ExperimentCompareRequest,
  ExperimentCompareResponse,
  DriftDetectRequest,
  DriftDetectResult,
  ABTestConfig,
  ABTestResult,
  RetrainConfig,
  RetrainResult,
  LLMStatus,
  OperationObservability,
} from '../types/algorithm-agent';

const BASE = '/agent/algorithm';

export const algorithmAgentApi = {
  // ============ 对话接口 ============
  
  /** 发送对话消息 */
  chat: (req: AgentChatRequest): Promise<AgentChatResponse> =>
    api.post(`${BASE}/chat`, req),

  // @AI_GENERATED: Kiro v1.0
  /** 流式对话消息 */
  chatStream: (
    req: AgentChatRequest,
    onChunk: (chunk: string) => void,
    onDone: (data: { llm_used: boolean; suggested_actions: any[]; operation_observability?: OperationObservability }) => void,
    onStart?: (sessionId: string) => void,
    onError?: (error: Error) => void,
    onReasoning?: (text: string) => void,
    onReasoningChunk?: (chunk: string) => void,
    onReasoningProgress?: (message: string) => void,
  ): AbortController => {
    const controller = new AbortController();
    
    fetch(`/api${BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const reader = response.body?.getReader();
        if (!reader) throw new Error('No reader');
        
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'start' && onStart) {
                  onStart(data.session_id);
                } else if (data.type === 'reasoning_progress' && onReasoningProgress && data.message) {
                  onReasoningProgress(String(data.message));
                } else if (data.type === 'reasoning_chunk' && onReasoningChunk) {
                  onReasoningChunk(String(data.content ?? ''));
                } else if (data.type === 'reasoning' && onReasoning) {
                  onReasoning(String(data.content ?? ''));
                } else if (data.type === 'chunk') {
                  onChunk(data.content);
                } else if (data.type === 'done') {
                  onDone({
                    llm_used: data.llm_used,
                    suggested_actions: data.suggested_actions,
                    operation_observability: data.operation_observability,
                  });
                }
              } catch {}
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError' && onError) {
          onError(err);
        }
      });
    
    return controller;
  },
  // @AI_GENERATED: end

  /** 获取会话列表 */
  getSessions: (): Promise<AgentSession[]> =>
    api.get(`${BASE}/sessions`),

  /** 获取会话详情 */
  getSession: (sessionId: string): Promise<AgentSession> =>
    api.get(`${BASE}/sessions/${sessionId}`),

  /** 删除会话 */
  deleteSession: (sessionId: string): Promise<void> =>
    api.delete(`${BASE}/sessions/${sessionId}`),

  // ============ 研发阶段 Skills ============

  /** 算法推荐 */
  recommendAlgorithm: (req: AlgorithmRecommendRequest): Promise<AlgorithmRecommendResponse> =>
    api.post(`${BASE}/skills/algorithm-recommend`, req),

  /** 参数配置 */
  configParams: (req: ParamConfigRequest): Promise<ParamConfigResponse> =>
    api.post(`${BASE}/skills/param-config`, req),

  /** 启动训练 */
  startTraining: (req: TrainingRequest): Promise<{ task_id: string }> =>
    api.post(`${BASE}/skills/training-pipeline/start`, req),

  /** 获取训练进度 */
  getTrainingProgress: (taskId: string): Promise<TrainingProgress> =>
    api.get(`${BASE}/skills/training-pipeline/${taskId}/progress`),

  /** 获取训练结果 */
  getTrainingResult: (taskId: string): Promise<TrainingResult> =>
    api.get(`${BASE}/skills/training-pipeline/${taskId}/result`),

  /** 实验对比 */
  compareExperiments: (req: ExperimentCompareRequest): Promise<ExperimentCompareResponse> =>
    api.post(`${BASE}/skills/experiment-compare`, req),

  // ============ 运营阶段 Skills ============

  /** 漂移检测 */
  detectDrift: (req: DriftDetectRequest): Promise<DriftDetectResult> =>
    api.post(`${BASE}/skills/drift-detect`, req),

  /** 创建 A/B 测试 */
  createABTest: (config: ABTestConfig): Promise<ABTestResult> =>
    api.post(`${BASE}/skills/ab-test/create`, config),

  /** 获取 A/B 测试结果 */
  getABTestResult: (testId: string): Promise<ABTestResult> =>
    api.get(`${BASE}/skills/ab-test/${testId}`),

  /** 配置自动重训 */
  configRetrain: (config: RetrainConfig): Promise<{ config_id: string }> =>
    api.post(`${BASE}/skills/retrain-trigger/config`, config),

  /** 触发重训 */
  triggerRetrain: (modelId: string, reason?: string): Promise<RetrainResult> =>
    api.post(`${BASE}/skills/retrain-trigger/execute`, { model_id: modelId, reason }),

  // ============ 快捷指令 ============

  /** 获取快捷指令列表 */
  getQuickCommands: (phase?: string): Promise<{ label: string; prompt: string }[]> =>
    api.get(`${BASE}/quick-commands`, { params: { phase } }),

  // @AI_GENERATED: Kiro v1.0
  /** 获取 LLM 服务状态 */
  getLLMStatus: (): Promise<LLMStatus> =>
    api.get(`${BASE}/llm-status`),
  // @AI_GENERATED: end
};

export default algorithmAgentApi;
// @AI_GENERATED: end
