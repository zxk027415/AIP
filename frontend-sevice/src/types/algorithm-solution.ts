// @AI_GENERATED: Kiro v1.0
export interface TemplateWorkflow {
  profile: string;
  name: string;
  layers: Record<string, string[]>;
}

// 已挂载的算法模板
export interface MountedWorkflow {
  id: string;
  name: string;
  node_count: number;
  edge_count: number;
  mounted_at?: string;
}

// 业务场景
export interface BusinessScenario {
  id: string;
  name: string;
  description: string;
  mounted_workflows?: MountedWorkflow[];
}

export interface TemplateItem {
  id: string;
  name: string;
  scenario_id: string;
  display_category: string;
  description: string;
  business_scenarios?: BusinessScenario[];
  default_workflows?: TemplateWorkflow[];
  accuracy_status: string | null;
  accuracy_metrics: Record<string, number> | null;
  mounted_workflows?: MountedWorkflow[];
}

export interface TemplateListResponse {
  total: number;
  page: number;
  page_size: number;
  items: TemplateItem[];
}

// @AI_GENERATED: Kiro v1.0
export interface TemplateStats {
  total: number;
  scenario_count: number;
  by_scenario: {
    scenario_id: string;
    name: string;
    icon: string;
    count: number;
    industry_tags?: string[];
  }[];
}
// @AI_GENERATED: end

export interface AccuracyRecord {
  id: string;
  template_id: string;
  dataset_id: string;
  dataset_name: string;
  test_date: string;
  metrics: Record<string, number>;
  status: string;
  tester: string;
  notes: string;
}

export interface AccuracyRankingItem {
  template_id: string;
  template_name: string;
  scenario_id: string;
  metrics: Record<string, number>;
  status: string;
  test_date: string;
}

export interface ApplicationItem {
  workflow_id: string;
  workflow_name: string;
  created_at: string;
  node_count: number;
  edge_count: number;
}

export interface ApplicationStats {
  total_templates_used: number;
  total_workflows: number;
  usage: Record<string, { count: number; workflows: string[] }>;
}
// @AI_GENERATED: end
