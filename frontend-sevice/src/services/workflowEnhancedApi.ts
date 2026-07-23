/**
 * Enhanced Workflow API Service
 * 增强版算法模板 API 服务
 */

import api from './api';
import type { 
  EnhancedWorkflow, 
  EnhancedWorkflowNode, 
  EnhancedWorkflowEdge,
  EnhancedWorkflowSummary,
} from '../types/workflow-enhanced';
import type { FunctionDefinition, Category } from '../types/function';

export interface ParamField {
  key: string;
  label: string;
  type: string;
  hint: string;
  value: unknown;
  source: string;
  node_id?: string;
  function_id?: string;
  node_label?: string;
}

export interface NodeParamGroup {
  node_id: string;
  function_id: string;
  node_label: string;
  fields: ParamField[];
}

export interface WorkflowParamsSummary {
  workflow_id: string;
  workflow_name: string;
  global_config_params: ParamField[];
  node_params: NodeParamGroup[];
}

/**
 * AI算法库 API
 */
export const functionLibraryApi = {
  /**
   * 获取所有函数
   */
  getAllFunctions: async (): Promise<FunctionDefinition[]> => {
    return api.get('/functions/');
  },

  /**
   * 获取函数定义
   */
  getFunction: async (functionId: string): Promise<FunctionDefinition> => {
    return api.get(`/functions/${functionId}`);
  },

  /**
   * 搜索函数
   */
  searchFunctions: async (query?: string, category?: string): Promise<FunctionDefinition[]> => {
    const params = new URLSearchParams();
    if (query) params.append('q', query);
    if (category) params.append('category', category);
    return api.get(`/functions/search/?${params.toString()}`);
  },

  /**
   * 获取分类下的函数
   */
  getFunctionsByCategory: async (categoryId: string): Promise<FunctionDefinition[]> => {
    return api.get(`/functions/category/${categoryId}`);
  },

  /**
   * 获取所有分类
   */
  getCategories: async (): Promise<Category[]> => {
    return api.get('/functions/categories/');
  },

  /**
   * 获取分类信息
   */
  getCategory: async (categoryId: string): Promise<Category> => {
    return api.get(`/functions/categories/${categoryId}`);
  },
};

/**
 * 增强版算法模板 API
 */
export const enhancedWorkflowApi = {
  /**
   * 保存算法模板
   */
  saveWorkflow: async (workflow: {
    name: string;
    description?: string;
    nodes: EnhancedWorkflowNode[];
    edges: EnhancedWorkflowEdge[];
  }): Promise<EnhancedWorkflow> => {
    return api.post('/workflows/enhanced', workflow);
  },

  /**
   * 更新算法模板
   */
  updateWorkflow: async (
    id: string,
    workflow: {
      name?: string;
      description?: string;
      nodes?: EnhancedWorkflowNode[];
      edges?: EnhancedWorkflowEdge[];
    }
  ): Promise<EnhancedWorkflow> => {
    return api.put(`/workflows/enhanced/${id}`, workflow);
  },

  // @AI_GENERATED
  /**
   * 保存已有算法模板（"编辑已有"模式，递增 version、写入 parent_version_id）
   *
   * 后端路由：POST /api/workflows/enhanced/{workflow_id}/save
   * - `workflow_id` — 已有工作流的唯一 ID（同一 workflow_id 内版本递增）
   * - 请求体承载最新的 name/nodes/edges/description
   * - 响应中的 `version` 已由后端 +1，`parent_version_id` 指向前一版本
   */
  saveExistingWorkflow: async (
    id: string,
    workflow: {
      name?: string;
      description?: string;
      nodes?: EnhancedWorkflowNode[];
      edges?: EnhancedWorkflowEdge[];
    }
  ): Promise<EnhancedWorkflow> => {
    return api.post(`/workflows/enhanced/${id}/save`, workflow);
  },
  // @AI_GENERATED: end

  /**
   * 克隆模板为新版本（version +1，新 id，继承 scenario_id/version_group_id）
   */
  cloneWorkflow: async (id: string): Promise<EnhancedWorkflow> => {
    return api.post(`/workflows/enhanced/${id}/clone`);
  },

  // @AI_GENERATED
  /**
   * 从模板创建独立工作流 —— 统一新建入口（spec: algorithm-deployment-refactor, task 7.1/11.1）
   *
   * 后端行为：
   * - 深拷贝源模板 nodes/edges/metadata/scenario_id
   * - 分配全新 workflow_id + 独立 version_group_id
   * - version=1, parent_version_id=null, source_template_id=<template.id>
   * - name 必须与模板不同，否则返回 400 {detail:{code:"name_conflict"}}
   * - template_id 不存在返回 404
   *
   * @param payload
   *   - template_id — 源模板 workflow_id（必填）
   *   - name — 新工作流名称（必填，且必须与源模板名称不同）
   * @returns 新创建的 EnhancedWorkflow（含全新 id / version_group_id / version=1）
   */
  createFromTemplate: async (payload: {
    template_id: string;
    name: string;
  }): Promise<EnhancedWorkflow> => {
    return api.post('/workflows/enhanced/create-from-template', payload);
  },
  // @AI_GENERATED: end

  /**
   * 加载算法模板
   */
  loadWorkflow: async (id: string): Promise<EnhancedWorkflow> => {
    return api.get(`/workflows/enhanced/${id}`);
  },

  /**
   * 列出所有算法模板
   */
  listWorkflows: async (): Promise<EnhancedWorkflow[]> => {
    return api.get('/workflows/enhanced');
  },

  /**
   * 列出算法模板摘要（轻量）
   */
  listWorkflowSummaries: async (): Promise<EnhancedWorkflowSummary[]> => {
    return api.get('/workflows/enhanced/summaries');
  },

  /**
   * 删除算法模板
   */
  deleteWorkflow: async (id: string): Promise<void> => {
    return api.delete(`/workflows/enhanced/${id}`);
  },

  /**
   * 执行算法模板
   */
  executeWorkflow: async (
    id: string,
    inputs?: Record<string, any>
  ): Promise<{
    success: boolean;
    nodeResults: Record<string, any>;
    error?: string;
    executionTime: number;
  }> => {
    return api.post(`/workflows/enhanced/${id}/execute`, { inputs });
  },

  /**
   * 验证算法模板
   */
  validateWorkflow: async (workflow: {
    nodes: EnhancedWorkflowNode[];
    edges: EnhancedWorkflowEdge[];
  }): Promise<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  }> => {
    return api.post('/workflows/enhanced/validate', workflow);
  },
};

// @AI_GENERATED
/**
 * 流水线执行 API
 */
export const pipelineApi = {
  /** 异步执行流水线 */
  executeAsync: (workflowId: string, params?: any): Promise<{ execution_id: string }> =>
    api.post(`/workflows/enhanced/${workflowId}/execute-async`, params),

  /** 查询执行状态 */
  getExecutionStatus: (workflowId: string, executionId: string): Promise<any> =>
    api.get(`/workflows/enhanced/${workflowId}/execution-status/${executionId}`),

  /** 预检 */
  preflight: (workflowId: string): Promise<any> =>
    api.post(`/workflows/enhanced/${workflowId}/preflight`),

  /** 获取节点执行结果 */
  getNodeResult: (workflowId: string, executionId: string, nodeId: string): Promise<any> =>
    api.get(`/workflows/enhanced/${workflowId}/execution/${executionId}/node/${nodeId}`),

  /** 取消执行 */
  cancelExecution: (workflowId: string, executionId: string): Promise<any> =>
    api.post(`/workflows/enhanced/${workflowId}/cancel/${executionId}`),
};
// @AI_GENERATED: end

/** 克隆模板并覆盖 global_config 字段 */
export const cloneWorkflowApi = {
  clone: (
    workflowId: string,
    opts: {
      name_suffix?: string;
      description?: string;
      global_config_patch?: Record<string, unknown>;
      node_patches?: Array<{ node_id: string; config_patch: Record<string, unknown> }>;
    },
  ): Promise<{ id: string; name: string; cloned_from: string }> =>
    api.post(`/workflows/enhanced/${workflowId}/clone`, opts),

  getParamsSummary: (workflowId: string): Promise<WorkflowParamsSummary> =>
    api.get(`/workflows/enhanced/${workflowId}/params-summary`),
};

/** Baseline / Challenger 多窗回测比对与候选池 */
export const baselineCompareApi = {
  startCompareAsync: (body: Record<string, unknown>): Promise<{ comparison_id: string; status: string }> =>
    api.post('/workflows/enhanced/compare-backtest-batch-async', body),

  getCompareStatus: (comparisonId: string): Promise<Record<string, unknown>> =>
    api.get(`/workflows/enhanced/compare-backtest-status/${comparisonId}`),

  cancelCompare: (comparisonId: string): Promise<{ success: boolean; message?: string }> =>
    api.post(`/workflows/enhanced/compare-backtest-cancel/${comparisonId}`),

  listCandidatePool: (): Promise<{ candidates: unknown[]; total: number }> =>
    api.get('/workflows/enhanced/tuning-candidate-pool'),

  getCandidateDetail: (candidateId: string): Promise<{ candidate: Record<string, unknown> }> =>
    api.get(`/workflows/enhanced/tuning-candidate-pool/${candidateId}`),

  listVerificationQueue: (): Promise<{ items: Record<string, unknown>[]; total: number; active_item_id?: string }> =>
    api.get('/workflows/enhanced/candidate-verification-queue'),

  enqueueCandidateVerification: (
    candidateId: string,
    body?: {
      windows?: Array<Record<string, unknown>>;
      note?: string;
      auto_start?: boolean;
      aggregate_method?: string;
      score_margin?: number;
      min_windows_challenger_better?: number;
    },
  ): Promise<{ success: boolean; item: Record<string, unknown>; deduped?: boolean; start_result?: Record<string, unknown> }> =>
    api.post(`/workflows/enhanced/candidate-verification-queue/from-candidate/${candidateId}`, body ?? {}),

  startNextVerification: (body?: { force?: boolean }): Promise<Record<string, unknown>> =>
    api.post('/workflows/enhanced/candidate-verification-queue/start-next', body ?? {}),

  startVerification: (itemId: string, body?: {
    force?: boolean;
    windows?: Array<{ start_date: string; end_date: string }>;
    aggregate_method?: string;
    min_windows_challenger_better?: number;
    score_margin?: number;
  }): Promise<Record<string, unknown>> =>
    api.post(`/workflows/enhanced/candidate-verification-queue/${itemId}/start`, body ?? {}),

  cancelVerification: (itemId: string): Promise<{ success: boolean; item?: Record<string, unknown> }> =>
    api.post(`/workflows/enhanced/candidate-verification-queue/${itemId}/cancel`),

  listSearchRegistries: (): Promise<{ registries: { registry_id: string; description: string; layers_count: number; layers: string[] }[] }> =>
    api.get('/workflows/enhanced/list-search-registries'),

  listRunInsights: (): Promise<{ insights: Record<string, unknown>[]; total: number }> =>
    api.get('/workflows/enhanced/auto-research-insights'),

  promoteCandidate: (
    candidateId: string,
    body?: {
      note?: string;
      set_as_production?: boolean;
      production_slot?: string;
      force?: boolean;
      enter_prelaunch?: boolean;
      prelaunch_slot?: string;
    },
  ): Promise<{ success: boolean; candidate?: unknown; production_entry?: unknown; prelaunch_entry?: unknown }> =>
    api.post(`/workflows/enhanced/tuning-candidate-pool/${candidateId}/promote`, body ?? {}),

  deleteCandidate: (candidateId: string): Promise<{ success: boolean; deleted_id: string; remaining: number }> =>
    api.delete(`/workflows/enhanced/tuning-candidate-pool/${candidateId}`),

  clearCandidatePool: (): Promise<{ success: boolean; deleted_count: number }> =>
    api.delete('/workflows/enhanced/tuning-candidate-pool'),

  getProductionWorkflowRef: (): Promise<{ slots?: Record<string, unknown> }> =>
    api.get('/workflows/enhanced/production-workflow-ref'),

  putProductionWorkflowRef: (body: {
    workflow_id: string;
    slot?: string;
    note?: string;
  }): Promise<{ success: boolean; slot?: string; entry?: unknown }> =>
    api.put('/workflows/enhanced/production-workflow-ref', body),

  startAutoResearchAsync: (body: Record<string, unknown>): Promise<{ run_id: string; status: string }> =>
    api.post('/workflows/enhanced/auto-research-async', body),

  getAutoResearchStatus: (runId: string): Promise<Record<string, unknown>> =>
    api.get(`/workflows/enhanced/auto-research-status/${runId}`),

  listAutoResearchRuns: (limit = 10): Promise<{ runs: Record<string, unknown>[]; total: number }> =>
    api.get(`/workflows/enhanced/auto-research-runs?limit=${limit}`),

  listAutoResearchTrials: (runId: string, limit = 200): Promise<{ run_id: string; trials: Record<string, unknown>[]; total: number }> =>
    api.get(`/workflows/enhanced/auto-research-runs/${runId}/trials?limit=${limit}`),

  cancelAutoResearch: (runId: string): Promise<{ success: boolean; message?: string }> =>
    api.post(`/workflows/enhanced/auto-research-cancel/${runId}`),

  resumeAutoResearch: (runId: string, body?: { windows?: Record<string, unknown>[] }): Promise<Record<string, unknown>> =>
    api.post(`/workflows/enhanced/auto-research-resume/${runId}`, body ?? {}),

  getAutoResearchReport: (runId: string): Promise<Record<string, unknown>> =>
    api.get(`/workflows/enhanced/auto-research-report/${runId}`),

  generateAutoResearchProposal: (runId: string): Promise<Record<string, unknown>> =>
    api.post('/workflows/enhanced/auto-research/proposal/generate', { run_id: runId }),

  getAutoResearchProposal: (proposalId: string): Promise<Record<string, unknown>> =>
    api.get(`/workflows/enhanced/auto-research/proposal/${proposalId}`),

  applyAutoResearchProposal: (
    proposalId: string,
    body?: { reviewer?: string },
  ): Promise<Record<string, unknown>> =>
    api.post(`/workflows/enhanced/auto-research/proposal/${proposalId}/apply`, body ?? {}),

  rejectAutoResearchProposal: (
    proposalId: string,
    body?: { reviewer?: string; reason?: string },
  ): Promise<Record<string, unknown>> =>
    api.post(`/workflows/enhanced/auto-research/proposal/${proposalId}/reject`, body ?? {}),

  continueAutoResearch: (runId: string, body?: { reviewer?: string }): Promise<Record<string, unknown>> =>
    api.post(`/workflows/enhanced/auto-research-continue/${runId}`, body ?? {}),

  autoResearchSelfcheck: (runId: string): Promise<Record<string, unknown>> =>
    api.get(`/workflows/enhanced/auto-research-selfcheck/${runId}`),

  /** 函数库 ts_forecast ∩ *_forecast ∩ OperatorRouter 注册 */
  listModelOperatorsAvailable: (): Promise<Record<string, unknown>> =>
    api.get('/workflows/enhanced/model-operators-available'),

  listStructureProfiles: (): Promise<Record<string, unknown>> =>
    api.get('/workflows/enhanced/structure-profiles'),

  baselineWorkflowPrecheck: (body: {
    baseline_workflow_id: string;
    max_rows?: number;
  }): Promise<Record<string, unknown>> =>
    api.post('/workflows/enhanced/baseline-workflow-precheck', body),

  /** 槽位档案详情：各 slot 的 effective_candidates（已注册可选算子） */
  getStructureProfileDetail: (profileId: string): Promise<Record<string, unknown>> =>
    api.get(`/workflows/enhanced/structure-profile-detail/${encodeURIComponent(profileId)}`),

  /** Phase B：特征配方（feature_recipes.json） */
  listFeatureRecipes: (): Promise<{ recipes: Array<{ recipe_id: string; title: string; description: string }> }> =>
    api.get('/workflows/enhanced/feature-recipes'),
};

/** 数据集管理 API */
export const datasetApi = {
  /** 列出所有可用数据集文件 */
  listAvailable: (): Promise<{ success: boolean; data: DatasetFileInfo[] }> =>
    api.get('/workflows/enhanced/datasets/available'),

  /** 查看 workflow 当前使用的数据集 */
  getCurrentForWorkflow: (workflowId: string): Promise<{ success: boolean; data: DatasetNodeInfo[] }> =>
    api.get(`/workflows/enhanced/datasets/current-for-workflow/${workflowId}`),

  /** 切换 workflow 使用的数据集 */
  switchDataset: (body: { workflow_id: string; file_path: string; node_id?: string }): Promise<{ success: boolean; updated_nodes: string[]; new_file_path: string }> =>
    api.post('/workflows/enhanced/datasets/switch', body),

  /** 预览数据集 */
  preview: (pathOrId: string, rows?: number): Promise<{ success: boolean; data: DatasetPreview }> =>
    api.get(`/workflows/enhanced/datasets/${encodeURIComponent(pathOrId.replace(/\//g, '__'))}/preview${rows ? `?rows=${rows}` : ''}`),

  /** 已注册数据集列表 */
  listRegistered: (): Promise<{ success: boolean; data: RegisteredDataset[] }> =>
    api.get('/workflows/enhanced/datasets'),

  /** 注册数据集 */
  register: (body: { file_path: string; name?: string; dataset_id?: string }): Promise<{ success: boolean; data: RegisteredDataset }> =>
    api.post('/workflows/enhanced/datasets/register', body),

  /** 上传数据集文件 */
  upload: (file: File): Promise<{ file_id: string; filename: string; file_size: number; analysis: Record<string, unknown> }> => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/upload/file', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};

export interface DatasetFileInfo {
  file_name: string;
  file_path: string;
  source: 'datasets' | 'uploads';
  size_bytes: number;
  extension: string;
  columns?: string[];
  row_count_estimate?: number | null;
  registered?: boolean;
  upload_time?: string;
  file_id?: string;
}

export interface DatasetNodeInfo {
  node_id: string;
  label: string;
  file_path: string;
  timestamp_column: string;
  parent_id: string;
  child_id: string;
}

export interface DatasetPreview {
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
  date_range?: { start: string; end: string } | null;
  file_path: string;
}

export interface RegisteredDataset {
  dataset_id: string;
  file_path: string;
  name: string;
  registered_at: string;
}

export default {
  functionLibrary: functionLibraryApi,
  workflow: enhancedWorkflowApi,
  pipeline: pipelineApi,
  baselineCompare: baselineCompareApi,
  dataset: datasetApi,
};
