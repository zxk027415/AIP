// @AI_GENERATED: Kiro v1.0
import api from './api';
import type { IndustryScenario, IndustryStats } from '../types/industry';

export interface IndustryTemplate {
  id: string;
  name: string;
  scenario_id: string;
  display_category: string;
  description: string;
  default_workflows: Array<{
    profile: string;
    name: string;
    layers: Record<string, string[]>;
  }>;
}

export const industryApi = {
  getScenarios: (): Promise<IndustryScenario[]> => api.get('/industry/scenarios'),
  getScenario: (id: string): Promise<IndustryScenario> => api.get(`/industry/scenarios/${id}`),
  getStats: (): Promise<IndustryStats> => api.get('/industry/stats'),
  getTemplates: (scenarioId?: string): Promise<IndustryTemplate[]> =>
    api.get('/industry/templates', { params: scenarioId ? { scenario_id: scenarioId } : {} }),
  getTemplate: (templateId: string): Promise<IndustryTemplate> =>
    api.get(`/industry/templates/${templateId}`),
};
// @AI_GENERATED: end
