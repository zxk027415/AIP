// @AI_GENERATED: Kiro v1.0
/**
 * 大模型 API 配置类型定义
 */

export type LLMProvider = 'openai' | 'azure' | 'anthropic' | 'deepseek' | 'qwen' | 'zhipu' | 'custom';

export type CompletionMode = 'chat' | 'completion';

export interface LLMConfig {
  id: string;
  // 基本信息
  credentialName: string;      // 凭据名称
  displayName: string;         // 模型显示名称
  provider: LLMProvider;
  // API 配置
  apiKey: string;
  apiBase: string;             // API endpoint URL
  model: string;               // API endpoint 中的模型名称
  // 模型参数
  completionMode: CompletionMode;  // 对话/补全模式
  contextLength: number;       // 模型上下文长度
  maxTokens: number;           // 最大 token 上限
  temperature?: number;
  // 状态
  isDefault: boolean;
  isEnabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface LLMProviderInfo {
  id: LLMProvider;
  name: string;
  description: string;
  defaultApiBase: string;
  models: string[];
  requiresApiBase: boolean;
}

export interface LLMTestRequest {
  configId: string;
  prompt?: string;
}

export interface LLMTestResponse {
  success: boolean;
  latencyMs: number;
  response?: string;
  error?: string;
  model: string;
  tokensUsed?: number;
}

export interface LLMChatRequest {
  configId?: string;
  messages: { role: 'user' | 'assistant' | 'system'; content: string }[];
  temperature?: number;
  maxTokens?: number;
}

export interface LLMChatResponse {
  content: string;
  model: string;
  tokensUsed: number;
  latencyMs: number;
}
// @AI_GENERATED: end
