// @AI_GENERATED: Kiro v1.0
/**
 * Workflow Agent API 服务层
 */
import api from './api';
import type {
  ScenarioMatchRequest,
  ScenarioMatchResponse,
  AlgorithmComposeRequest,
  AlgorithmComposeResponse,
  WorkflowGenerateRequest,
  WorkflowGenerateResponse,
  WorkflowValidateRequest,
  WorkflowValidateResponse,
  DomainConstraintResponse,
  TemplateCreateRequest,
  TemplateSearchParams,
  TemplateManageResponse,
  BestPracticeResponse,
  BestPracticeContribute,
  CrossScenarioRequest,
  MigrationReport,
  SkillStatus,
  ChainResult,
} from '../types/workflow-agent';

const BASE = '/agent/workflow';

export const workflowAgentApi = {
  /** 行业场景匹配 */
  matchScenario: (req: ScenarioMatchRequest): Promise<ScenarioMatchResponse> =>
    api.post(`${BASE}/scenario-match`, req),

  /** 算法组合推荐 */
  composeAlgorithms: (req: AlgorithmComposeRequest): Promise<AlgorithmComposeResponse> =>
    api.post(`${BASE}/algorithm-compose`, req),

  /** 算法模板自动生成 */
  generateWorkflow: (req: WorkflowGenerateRequest): Promise<WorkflowGenerateResponse> =>
    api.post(`${BASE}/workflow-generate`, req),

  /** 算法模板合理性验证 */
  validateWorkflow: (req: WorkflowValidateRequest): Promise<WorkflowValidateResponse> =>
    api.post(`${BASE}/workflow-validate`, req),

  /** 查询业务约束 */
  queryConstraints: (scenarioId: string): Promise<DomainConstraintResponse> =>
    api.get(`${BASE}/domain-constraint`, { params: { scenario_id: scenarioId } }),

  /** 创建算法模板 */
  createTemplate: (req: TemplateCreateRequest): Promise<TemplateManageResponse> =>
    api.post(`${BASE}/template-manage/create`, req),

  /** 搜索算法模板 */
  searchTemplates: (req: TemplateSearchParams): Promise<TemplateManageResponse> =>
    api.post(`${BASE}/template-manage/search`, req),

  /** 查询最佳实践 */
  queryBestPractices: (scenarioId: string, limit?: number): Promise<BestPracticeResponse> =>
    api.get(`${BASE}/best-practice`, { params: { scenario_id: scenarioId, limit: limit ?? 10 } }),

  /** 贡献最佳实践 */
  contributeBestPractice: (req: BestPracticeContribute): Promise<BestPracticeResponse> =>
    api.post(`${BASE}/best-practice/contribute`, req),

  /** 跨场景迁移 */
  migrateScenario: (req: CrossScenarioRequest): Promise<MigrationReport> =>
    api.post(`${BASE}/cross-scenario`, req),

  /** 链式编排执行 */
  executeChain: (steps: { skill_name: string; input_data: Record<string, unknown> }[]): Promise<ChainResult> =>
    api.post(`${BASE}/chain`, steps),

  /** Skill 状态仪表盘 */
  getSkillsStatus: (): Promise<SkillStatus[]> =>
    api.get(`${BASE}/skills/status`),
};

export default workflowAgentApi;
// @AI_GENERATED: end
