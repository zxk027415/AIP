/**
 * LLM配置管理API客户端
 * 对接后端 /llm 路由,支持智谱GLM等多种大模型提供商配置
 */
import api from './api';

// ============ 类型定义 ============

/**
 * LLM提供商信息
 */
export interface LLMProvider {
  id: string;
  name: string;
  description: string;
  defaultApiBase: string;
  models: string[];
  requiresApiBase: boolean;
}

/**
 * LLM配置(camelCase格式,对应前端使用)
 */
export interface LLMConfig {
  id: string;
  credentialName: string;    // 凭据名称
  displayName: string;       // 模型显示名称
  provider: string;          // 提供商: openai, azure, anthropic, deepseek, qwen, zhipu, custom
  apiKey: string;            // API密钥(展示时已脱敏)
  apiBase: string;           // API端点URL
  model: string;             // 模型名称
  completionMode: 'chat' | 'completion';  // 补全模式
  contextLength: number;     // 上下文长度
  maxTokens: number;         // 最大token数
  temperature: number;       // 温度参数
  isDefault: boolean;        // 是否为默认配置
  isEnabled: boolean;        // 是否启用
  createdAt: string;         // 创建时间
  updatedAt: string;         // 更新时间
}

/**
 * 创建LLM配置的请求参数(snake_case格式,对应后端API)
 */
export interface LLMConfigCreateRequest {
  credential_name: string;
  display_name: string;
  provider: string;
  api_key: string;
  api_base: string;
  model: string;
  completion_mode?: 'chat' | 'completion';
  context_length?: number;
  max_tokens?: number;
  temperature?: number;
  is_default?: boolean;
  is_enabled?: boolean;
}

/**
 * 更新LLM配置的请求参数
 */
export interface LLMConfigUpdateRequest {
  credential_name?: string;
  display_name?: string;
  provider?: string;
  api_key?: string;
  api_base?: string;
  model?: string;
  completion_mode?: 'chat' | 'completion';
  context_length?: number;
  max_tokens?: number;
  temperature?: number;
  is_default?: boolean;
  is_enabled?: boolean;
}

/**
 * 测试LLM配置的请求参数
 */
export interface LLMTestRequest {
  config_id: string;
  prompt?: string;
}

/**
 * 测试LLM配置的响应
 */
export interface LLMTestResponse {
  success: boolean;
  error?: string;
  latencyMs: number;
  model: string;
  response?: string;
}

/**
 * 获取配置列表的响应
 */
export interface LLMConfigsResponse {
  configs: LLMConfig[];
  default_config_id: string | null;
}

// ============ API方法 ============

/**
 * LLM配置管理API
 */
export const llmConfigApi = {
  /**
   * 获取支持的LLM提供商列表
   */
  getProviders: (): Promise<LLMProvider[]> => {
    return api.get('/llm/providers');
  },

  /**
   * 获取所有LLM配置
   */
  getConfigs: (): Promise<LLMConfigsResponse> => {
    return api.get('/llm/configs');
  },

  /**
   * 获取单个配置详情
   */
  getConfig: (configId: string): Promise<LLMConfig> => {
    return api.get(`/llm/configs/${configId}`);
  },

  /**
   * 创建新的LLM配置
   */
  createConfig: (config: LLMConfigCreateRequest): Promise<LLMConfig> => {
    return api.post('/llm/configs', config);
  },

  /**
   * 更新LLM配置
   */
  updateConfig: (configId: string, config: LLMConfigUpdateRequest): Promise<LLMConfig> => {
    return api.put(`/llm/configs/${configId}`, config);
  },

  /**
   * 删除LLM配置
   */
  deleteConfig: (configId: string): Promise<{ status: string }> => {
    return api.delete(`/llm/configs/${configId}`);
  },

  /**
   * 测试LLM配置连接
   */
  testConfig: (request: LLMTestRequest): Promise<LLMTestResponse> => {
    return api.post('/llm/test', request);
  },

  /**
   * 获取默认配置
   */
  getDefaultConfig: (): Promise<LLMConfig | null> => {
    return api.get('/llm/default');
  },
};

/**
 * 智谱GLM配置预设
 * 基于环境变量GLM_*的配置
 */
export const GLM_PRESET = {
  provider: 'zhipu',
  defaultApiBase: 'https://open.bigmodel.cn/api/paas/v4',
  models: ['glm-5.1', 'glm-4-plus', 'glm-4', 'glm-4-flash'],
  defaultModel: 'glm-5.1',
  defaultContextLength: 64000,
  defaultMaxTokens: 64000,
  defaultTemperature: 0.7,
};

export default llmConfigApi;
