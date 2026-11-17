// @AI_GENERATED: Kiro v1.0
/**
 * 算法模板 Skill 打包 API 服务
 */
import axios from 'axios';

const API_BASE = '/api/skills';

export interface TrainingConfig {
  enabled: boolean;
  min_samples: number;
  default_epochs: number;
  default_batch_size: number;
}

export interface ResourceConfig {
  cpu: string;
  memory: string;
  gpu: string;
  timeout_seconds: number;
}

export interface SkillPackageRequest {
  template_id: string;
  template_name: string;
  template_version: string;
  skill_name: string;
  skill_version: string;
  description?: string;
  training_config: TrainingConfig;
  resource_config: ResourceConfig;
}

export interface PackagedSkill {
  skill_id: string;
  skill_name: string;
  skill_version: string;
  description: string;
  source_template_id: string;
  source_template_name: string;
  source_template_version: string;
  training_config: TrainingConfig;
  resource_config: ResourceConfig;
  status: string;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export const templateSkillApi = {
  /**
   * 打包模板为 Skill
   */
  async packageTemplate(request: SkillPackageRequest) {
    const response = await axios.post(`${API_BASE}/package`, request);
    return response.data;
  },

  /**
   * 获取所有已打包的 Skills
   */
  async listSkills(): Promise<{ total: number; skills: PackagedSkill[] }> {
    const response = await axios.get(`${API_BASE}/list`);
    return response.data;
  },

  /**
   * 获取单个 Skill 详情
   */
  async getSkill(skillId: string): Promise<PackagedSkill> {
    const response = await axios.get(`${API_BASE}/${skillId}`);
    return response.data;
  },

  /**
   * 删除 Skill
   */
  async deleteSkill(skillId: string) {
    const response = await axios.delete(`${API_BASE}/${skillId}`);
    return response.data;
  },

  // @AI_GENERATED: Kiro v1.0
  /**
   * 更新 Skill
   */
  async updateSkill(skillId: string, request: UpdateSkillRequest) {
    const response = await axios.put(`${API_BASE}/${skillId}`, request);
    return response.data;
  },
  // @AI_GENERATED: end
};

// @AI_GENERATED: Kiro v1.0
export interface UpdateSkillRequest {
  skill_name?: string;
  skill_version?: string;
  description?: string;
  status?: string;
  training_config?: TrainingConfig;
  resource_config?: ResourceConfig;
}
// @AI_GENERATED: end
