// @AI_GENERATED: Kiro v1.0
/**
 * Workflow Agent 类型定义
 */

// ============ 通用 ============

export type UserRole = 'user' | 'engineer' | 'admin';
export type CombinationProfile = 'high-accuracy' | 'low-latency' | 'balanced';
export type FindingSeverity = 'error' | 'warning' | 'info';
export type FindingCategory = 'structural' | 'business' | 'parameter' | 'data_flow';
export type TemplateVisibility = 'private' | 'team' | 'public';

export interface UserConstraints {
  data_volume?: string;
  realtime_required?: boolean;
  accuracy_target?: number;
  max_latency_ms?: number;
}

// ============ scenario-match ============

export interface ScenarioMatchRequest {
  description: string;
  language?: string;
}

export interface ScenarioMatchResult {
  scenario_id: string;
  scenario_name: string;
  confidence_score: number;
  rationale: string;
  extracted_entities: Record<string, string>;
}

export interface ScenarioMatchResponse {
  matches: ScenarioMatchResult[];
  extracted_entities: Record<string, string>;
  processing_time_ms: number;
}

// ============ algorithm-compose ============

export interface AlgorithmRecommendation {
  algorithm_id: string;
  algorithm_name: string;
  source: string;
  confidence_score: number;
  rationale: string;
  parameters: Record<string, unknown>;
}

export interface AlgorithmLayer {
  layer_name: string;
  algorithms: AlgorithmRecommendation[];
}

export interface AlgorithmCombination {
  combination_id: string;
  profile: CombinationProfile;
  layers: AlgorithmLayer[];
  overall_confidence: number;
}

export interface AlgorithmComposeRequest {
  scenario_id: string;
  template_id?: string;
  constraints?: UserConstraints;
}

export interface AlgorithmComposeResponse {
  combinations: AlgorithmCombination[];
  scenario_id: string;
  processing_time_ms: number;
}

// ============ workflow-generate ============

export interface WorkflowGenerateRequest {
  combination: AlgorithmCombination;
  scenario_id: string;
  apply_domain_constraints?: boolean;
}

export interface WorkflowGenerateResponse {
  workflow: Record<string, unknown>;
  generation_summary: string;
  node_count: number;
  edge_count: number;
  processing_time_ms: number;
}

// ============ workflow-validate ============

export interface ValidationFinding {
  severity: FindingSeverity;
  category: FindingCategory;
  message: string;
  node_id?: string;
  fix_suggestion: string;
  auto_fixable: boolean;
}

export interface WorkflowValidateRequest {
  workflow: Record<string, unknown>;
  scenario_id?: string;
}

export interface WorkflowValidateResponse {
  structural_valid: boolean;
  structural_errors: Record<string, unknown>[];
  business_findings: ValidationFinding[];
  readiness_score: number;
  auto_fix_available: boolean;
}

// ============ domain-constraint ============

export interface DomainConstraintResponse {
  scenario_id: string;
  scenario_name: string;
  parameter_constraints: Record<string, unknown>;
  evaluation_metrics: string[];
  business_rules: { rule: string; severity: string; description?: string }[];
  processing_time_ms: number;
}

// ============ template-manage ============

export interface TemplateRecord {
  id: string;
  name: string;
  description?: string;
  scenario_id?: string;
  category?: string;
  tags: string[];
  visibility: TemplateVisibility;
  workflow_data: Record<string, unknown>;
  version: number;
  creator_id: number;
  load_count: number;
  fork_count: number;
  created_at: string;
  updated_at: string;
}

export interface TemplateCreateRequest {
  name: string;
  description?: string;
  scenario_id?: string;
  category?: string;
  tags?: string[];
  visibility?: TemplateVisibility;
  workflow_data: Record<string, unknown>;
}

export interface TemplateSearchParams {
  name?: string;
  scenario_id?: string;
  tags?: string[];
  creator_id?: number;
  visibility?: TemplateVisibility;
  page?: number;
  page_size?: number;
}

export interface TemplateManageResponse {
  action: string;
  template?: TemplateRecord;
  templates: TemplateRecord[];
  total: number;
  processing_time_ms: number;
}

// ============ best-practice ============

export interface BestPracticeItem {
  id: string;
  scenario_id: string;
  title: string;
  description?: string;
  algorithm_combination: Record<string, unknown>;
  key_parameters: Record<string, unknown>;
  achieved_metrics: Record<string, unknown>;
  applicability_notes?: string;
  is_system: boolean;
}

export interface BestPracticeResponse {
  scenario_id: string;
  practices: BestPracticeItem[];
  total: number;
  processing_time_ms: number;
}

export interface BestPracticeContribute {
  scenario_id: string;
  title: string;
  description?: string;
  algorithm_combination: Record<string, unknown>;
  key_parameters?: Record<string, unknown>;
  achieved_metrics?: Record<string, unknown>;
  applicability_notes?: string;
}

// ============ cross-scenario ============

export type CompatibilityCategory = 'compatible' | 'adaptable' | 'incompatible';

export interface CrossScenarioRequest {
  source_scenario_id: string;
  target_scenario_id: string;
  source_workflow: Record<string, unknown>;
}

export interface MigrationAlgorithmReport {
  algorithm_id: string;
  algorithm_name: string;
  category: CompatibilityCategory;
  reason: string;
  replacement_id?: string;
}

export interface MigrationReport {
  source_scenario_id: string;
  target_scenario_id: string;
  confidence_score: number;
  algorithm_reports: MigrationAlgorithmReport[];
  migrated_workflow?: Record<string, unknown>;
  changes_highlighted: string[];
  warnings: string[];
}

// ============ Skill 状态 ============

export interface SkillStatus {
  skill_name: string;
  available: boolean;
  recent_execution_count: number;
  avg_execution_time_ms: number;
  error_rate: number;
}

// ============ 链式编排 ============

export interface SkillResult {
  skill_name: string;
  status: string;
  output?: Record<string, unknown>;
  error?: string;
  execution_duration_ms: number;
}

export interface ChainResult {
  steps: SkillResult[];
  overall_status: string;
  total_duration_ms: number;
}
// @AI_GENERATED: end
