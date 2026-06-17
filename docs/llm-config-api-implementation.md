# LLM配置API前端实现文档

## 概述

本文档说明了为AIP平台前端实现的LLM配置管理API客户端,支持智谱GLM等多种大模型提供商的配置管理。

## 实现文件

### 1. `/frontend-sevice/src/services/llmConfigApi.ts`

**职责:** LLM配置管理的TypeScript API客户端

**主要功能:**
- 获取支持的LLM提供商列表 (`getProviders`)
- 获取/创建/更新/删除LLM配置
- 测试LLM配置连接
- 获取默认配置

**核心类型定义:**

```typescript
// LLM提供商信息
export interface LLMProvider {
  id: string;
  name: string;
  description: string;
  defaultApiBase: string;
  models: string[];
  requiresApiBase: boolean;
}

// LLM配置(camelCase格式,前端使用)
export interface LLMConfig {
  id: string;
  credentialName: string;
  displayName: string;
  provider: string;
  apiKey: string;
  apiBase: string;
  model: string;
  completionMode: 'chat' | 'completion';
  contextLength: number;
  maxTokens: number;
  temperature: number;
  isDefault: boolean;
  isEnabled: boolean;
  createdAt: string;
  updatedAt: string;
}
```

**API方法:**

| 方法 | 路径 | 说明 |
|------|------|------|
| `getProviders()` | `GET /llm/providers` | 获取支持的LLM提供商列表 |
| `getConfigs()` | `GET /llm/configs` | 获取所有LLM配置 |
| `getConfig(id)` | `GET /llm/configs/{id}` | 获取单个配置详情 |
| `createConfig(config)` | `POST /llm/configs` | 创建新的LLM配置 |
| `updateConfig(id, config)` | `PUT /llm/configs/{id}` | 更新LLM配置 |
| `deleteConfig(id)` | `DELETE /llm/configs/{id}` | 删除LLM配置 |
| `testConfig(request)` | `POST /llm/test` | 测试LLM配置连接 |
| `getDefaultConfig()` | `GET /llm/default` | 获取默认配置 |

**智谱GLM预设:**

```typescript
export const GLM_PRESET = {
  provider: 'zhipu',
  defaultApiBase: 'https://open.bigmodel.cn/api/paas/v4',
  models: ['glm-5.1', 'glm-4-plus', 'glm-4', 'glm-4-flash'],
  defaultModel: 'glm-5.1',
  defaultContextLength: 64000,
  defaultMaxTokens: 64000,
  defaultTemperature: 0.7,
};
```

### 2. `/frontend-sevice/src/services/api.ts` (更新)

**变更:** 导出LLM配置API及相关类型

```typescript
// 导出 LLM 配置 API
export { llmConfigApi, GLM_PRESET } from './llmConfigApi';
export type {
  LLMProvider,
  LLMConfig,
  LLMConfigCreateRequest,
  LLMConfigUpdateRequest,
  LLMTestRequest,
  LLMTestResponse,
  LLMConfigsResponse,
} from './llmConfigApi';
```

### 3. `/frontend-sevice/src/pages/LLMConfigPage.tsx` (修复)

**变更:** 修复API导入方式

- 从 `import * as llmApi from '../services/llmConfigApi'` 改为 `import { llmConfigApi } from '../services/llmConfigApi'`
- 所有 `llmApi.xxx()` 调用改为 `llmConfigApi.xxx()`
- 修复 `testConfig` 调用参数格式

## 后端API对接

### 后端路由

后端API位于 `/backend-service/api/llm_config.py`,提供以下路由:

- `GET /llm/providers` - 获取提供商列表
- `GET /llm/configs` - 获取所有配置
- `GET /llm/configs/{config_id}` - 获取单个配置
- `POST /llm/configs` - 创建配置
- `PUT /llm/configs/{config_id}` - 更新配置
- `DELETE /llm/configs/{config_id}` - 删除配置
- `POST /llm/test` - 测试连接
- `GET /llm/default` - 获取默认配置

### 支持的提供商

| ID | 名称 | 说明 |
|---|---|---|
| `openai` | OpenAI | GPT系列模型 |
| `azure` | Azure OpenAI | 微软Azure托管的OpenAI服务 |
| `anthropic` | Anthropic | Claude系列模型 |
| `deepseek` | DeepSeek | 深度求索大模型 |
| `qwen` | 通义千问 | 阿里云通义千问 |
| `zhipu` | 智谱AI | 智谱GLM系列(含GLM-5.1) |
| `custom` | 自定义 | OpenAI兼容接口 |

## 使用示例

### 在React组件中使用

```typescript
import { llmConfigApi, GLM_PRESET } from '@/services/llmConfigApi';

// 获取所有配置
const { configs, default_config_id } = await llmConfigApi.getConfigs();

// 创建GLM配置
const glmConfig = await llmConfigApi.createConfig({
  credential_name: 'my-glm',
  display_name: 'GLM-5.1',
  provider: GLM_PRESET.provider,
  api_key: 'your-api-key',
  api_base: GLM_PRESET.defaultApiBase,
  model: GLM_PRESET.defaultModel,
  completion_mode: 'chat',
  context_length: GLM_PRESET.defaultContextLength,
  max_tokens: GLM_PRESET.defaultMaxTokens,
  temperature: GLM_PRESET.defaultTemperature,
  is_default: true,
  is_enabled: true,
});

// 测试连接
const testResult = await llmConfigApi.testConfig({
  config_id: glmConfig.id,
  prompt: '你好,请介绍一下你自己',
});

console.log(testResult.success ? '连接成功' : '连接失败');
```

## 环境变量配置

后端支持通过环境变量配置GLM:

```bash
# 在 backend-service/.env.local 或通过 scripts/load_glm_env.sh 设置
export GLM_ENABLE=true
export GLM_RESEARCH_QUESTIONS_ENABLE=true
export GLM_API_KEY="your-api-key"
export GLM_BASE_URL="https://open.bigmodel.cn/api/coding/paas/v4"
export GLM_MODEL="glm-5.1"
export GLM_TIMEOUT_S=120
```

## 验证清单

- [x] 前端API客户端创建 (`llmConfigApi.ts`)
- [x] API导出更新 (`api.ts`)
- [x] 页面导入修复 (`LLMConfigPage.tsx`)
- [x] TypeScript类型定义完整
- [x] 前端构建成功 (`npm run build`)
- [x] 后端语法验证通过 (`python -m py_compile`)
- [x] GLM预设配置提供
- [x] 文档完整

## 注意事项

1. **API Key安全:** 前端展示的API Key已脱敏(只显示前8位和后4位)
2. **字段命名:** 前端使用camelCase,后端使用snake_case,API客户端负责转换
3. **测试连接:** 测试功能会实际调用LLM API,请注意配额消耗
4. **默认配置:** 系统只允许一个配置被设为默认,设置新默认时会自动取消其他配置的默认状态
5. **Provider约束:** 不同provider的models列表和requiresApiBase要求不同,前端表单应根据选择的provider动态调整

## 后续改进建议

1. 添加配置验证规则(如API Base格式校验)
2. 支持批量导入/导出配置
3. 添加配置使用统计(调用次数、成功率等)
4. 支持配置分组管理
5. 添加配置变更历史记录
6. 优化测试连接的超时处理和重试机制

---

**实现日期:** 2026-06-15  
**实现人:** Kiro AI Agent  
**相关Issue:** LLM配置前端API实现
