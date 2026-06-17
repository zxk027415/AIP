// @AI_GENERATED: Kiro v1.0
/**
 * 算法模板 API 服务
 * 包含工作流模板和 Skill 的 API 调用
 */
import axios from 'axios';

const API_BASE = '/api';

// ============ 工作流模板 API ============

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  scenario_id: string;
  scenario_name: string;
  category: string;
  status: string;
  version: string;
  author: string;
  created_at: string;
  updated_at: string;
  published_at?: string;
  node_count: number;
  edge_count: number;
  usage_count: number;
  star_count: number;
  tags: string[];
  is_starred: boolean;
}

export interface WorkflowTemplateStats {
  total: number;
  published: number;
  testing: number;
  developing: number;
  draft: number;
}

export interface CreateWorkflowTemplateRequest {
  name: string;
  description: string;
  scenario_id: string;
  scenario_name: string;
  category: string;
  tags?: string[];
}

// @AI_GENERATED: Kiro v1.0
export interface UpdateWorkflowTemplateRequest {
  name?: string;
  description?: string;
  scenario_id?: string;
  scenario_name?: string;
  category?: string;
  status?: string;
  version?: string;
  tags?: string[];
}
// @AI_GENERATED: end

export const workflowTemplateApi = {
  /**
   * 获取工作流模板列表
   */
  async listTemplates(status?: string, category?: string): Promise<{
    total: number;
    templates: WorkflowTemplate[];
    stats: WorkflowTemplateStats;
  }> {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (category) params.append('category', category);
    const response = await axios.get(`${API_BASE}/workflow-templates/list?${params}`);
    return response.data;
  },

  /**
   * 获取单个模板详情
   */
  async getTemplate(templateId: string): Promise<WorkflowTemplate> {
    const response = await axios.get(`${API_BASE}/workflow-templates/${templateId}`);
    return response.data;
  },

  /**
   * 创建新模板
   */
  async createTemplate(request: CreateWorkflowTemplateRequest) {
    const response = await axios.post(`${API_BASE}/workflow-templates/create`, request);
    return response.data;
  },

  /**
   * 切换收藏状态
   */
  async toggleStar(templateId: string) {
    const response = await axios.put(`${API_BASE}/workflow-templates/${templateId}/star`);
    return response.data;
  },

  /**
   * 删除模板
   */
  async deleteTemplate(templateId: string) {
    const response = await axios.delete(`${API_BASE}/workflow-templates/${templateId}`);
    return response.data;
  },

  // @AI_GENERATED: Kiro v1.0
  /**
   * 更新模板
   */
  async updateTemplate(templateId: string, request: UpdateWorkflowTemplateRequest) {
    const response = await axios.put(`${API_BASE}/workflow-templates/${templateId}`, request);
    return response.data;
  },
  // @AI_GENERATED: end
};

// ============ Skill API (重新导出) ============

export { templateSkillApi, type PackagedSkill, type SkillPackageRequest } from './templateSkillApi';
// @AI_GENERATED: end
