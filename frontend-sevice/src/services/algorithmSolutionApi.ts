// @AI_GENERATED: Kiro v1.0
import api from './api';
import type {
  TemplateListResponse, TemplateStats,
  AccuracyRecord, AccuracyRankingItem, ApplicationStats, ApplicationItem,
} from '../types/algorithm-solution';

const API_PATH = '/algorithm-solutions';

// 获取模板列表
export async function fetchTemplates(params?: {
  scenario?: string; industry?: string; keyword?: string; page?: number; page_size?: number;
}): Promise<TemplateListResponse> {
  return api.get(API_PATH, { params });
}

// 获取统计信息
export async function fetchTemplateStats(): Promise<TemplateStats> {
  return api.get(`${API_PATH}/stats`);
}

// 获取精度历史
export async function fetchAccuracyHistory(templateId: string): Promise<{ template_id: string; records: AccuracyRecord[] }> {
  return api.get(`${API_PATH}/${templateId}/accuracy`);
}

// 添加精度记录
export async function addAccuracyRecord(templateId: string, body: Partial<AccuracyRecord>): Promise<AccuracyRecord> {
  return api.post(`${API_PATH}/${templateId}/accuracy`, body);
}

// 获取精度排名
export async function fetchAccuracyRanking(scenarioId?: string): Promise<{ ranking: AccuracyRankingItem[]; total: number }> {
  return api.get(`${API_PATH}/accuracy/ranking`, { params: { scenario_id: scenarioId } });
}

// 挂载算法模板到业务场景
export async function mountWorkflowToScenario(solutionId: string, scenarioId: string, workflowId: string): Promise<void> {
  return api.post(`${API_PATH}/${solutionId}/scenarios/${scenarioId}/mount`, { workflow_id: workflowId });
}

// 从业务场景卸载算法模板
export async function unmountWorkflowFromScenario(solutionId: string, scenarioId: string, workflowId: string): Promise<void> {
  return api.delete(`${API_PATH}/${solutionId}/scenarios/${scenarioId}/mount/${workflowId}`);
}

// 兼容旧API - 挂载到方案
export async function mountWorkflowToSolution(solutionId: string, workflowId: string): Promise<void> {
  return api.post(`${API_PATH}/${solutionId}/mount`, { workflow_id: workflowId });
}

// 兼容旧API - 从方案卸载
export async function unmountWorkflowFromSolution(solutionId: string, workflowId: string): Promise<void> {
  return api.delete(`${API_PATH}/${solutionId}/mount/${workflowId}`);
}

// 获取应用统计
export async function fetchApplicationStats(): Promise<ApplicationStats> {
  return api.get(`${API_PATH}/applications/stats`);
}

// 获取模板应用实例
export async function fetchTemplateApplications(templateId: string): Promise<{ template_id: string; applications: ApplicationItem[]; total: number }> {
  return api.get(`${API_PATH}/${templateId}/applications`);
}
// @AI_GENERATED: end
