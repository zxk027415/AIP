// @AI_GENERATED
/**
 * 路由元数据表（单一真源）：标题、分组、面包屑父级、主干参数需求与缺上下文行为。
 *
 * 设计依据：design.md §33（用单一路由元数据表取代 MainLayout ~60 行 pathname 三元链，
 * 由它统一生成页头标题与面包屑，页面不再各自手搓）。
 *
 * 为保持现有页头标题**逐字不变**，本表条目沿用原 MainLayout 里使用的 i18n key（titleKey）
 * 或中文字面量（title）；未收录的路由由解析器返回 undefined，页头显示空（与原「未命中即空」一致）。
 */

import type { JourneyParamKey } from '../utils/journeyParams';

export type RouteMatch = 'exact' | 'prefix';

export interface RouteMeta {
  /** 路由路径（exact 精确匹配 / prefix 前缀匹配）。 */
  pattern: string;
  match: RouteMatch;
  /** 中文字面量标题（与 titleKey 二选一）。 */
  title?: string;
  /** i18n key（通过 t() 解析），保持与原页头一致。 */
  titleKey?: string;
  /** 所属菜单分组标签，用于面包屑首段。 */
  group?: string;
  /** 面包屑父级标签（不含当前页自身）。 */
  breadcrumb?: string[];
  /** 该页需要的主干参数（缺失走 missingContext）。 */
  requiredSpine?: JourneyParamKey[];
  /** 该页可选主干参数（收到即渲染，未消费也向下透传）。 */
  optionalSpine?: JourneyParamKey[];
  /** 缺必需上下文时的行为：显式空态 / 允许（自解析）。 */
  missingContext?: 'empty' | 'allow';
}

const GRP_INDUSTRY = '行业服务';
const GRP_ALGO = '算法开发';
const GRP_SYSTEM = '系统';

/** 路由元数据表。exact 优先于 prefix；prefix 取最长匹配。 */
export const ROUTE_METADATA: RouteMeta[] = [
  { pattern: '/home', match: 'exact', titleKey: 'header.home' },

  // 项目工作台（领域无关壳 + 光伏适配器）
  { pattern: '/projects', match: 'exact', title: '项目工作台' },
  { pattern: '/projects/', match: 'prefix', title: '项目工作台', optionalSpine: ['projectId', 'slot', 'datasetVersionId'] },

  // 行业服务
  { pattern: '/industry', match: 'exact', titleKey: 'header.industryAISolutions', group: GRP_INDUSTRY },
  { pattern: '/industry/', match: 'prefix', titleKey: 'header.scenarioDetails', group: GRP_INDUSTRY, breadcrumb: ['行业场景'], optionalSpine: ['scenarioId', 'solutionId'] },
  { pattern: '/algorithm-solutions', match: 'exact', titleKey: 'header.algorithmSolutions', group: GRP_INDUSTRY, optionalSpine: ['scenarioId', 'solutionId'] },
  { pattern: '/algorithm-solutions/accuracy', match: 'exact', titleKey: 'header.accuracyManagement', group: GRP_INDUSTRY },
  { pattern: '/algorithm-solutions/applications', match: 'exact', titleKey: 'header.applicationInstances', group: GRP_INDUSTRY },
  { pattern: '/data-sources', match: 'exact', titleKey: 'header.dataSourceManagement', group: GRP_INDUSTRY },
  { pattern: '/datasets', match: 'exact', titleKey: 'header.datasetManagement', group: GRP_INDUSTRY },
  { pattern: '/datasets/cumulative-training', match: 'exact', title: '累计训练数据集', group: GRP_INDUSTRY, optionalSpine: ['projectId', 'slot', 'datasetVersionId'] },

  // 算法开发
  { pattern: '/algorithm-dev/management', match: 'exact', title: '算法管理', group: GRP_ALGO, breadcrumb: ['算法开发'], optionalSpine: ['scenarioId', 'solutionId'] },
  { pattern: '/algorithm-dev/workflows', match: 'exact', title: '工作流编排', group: GRP_ALGO, breadcrumb: ['算法开发'] },
  { pattern: '/algorithm-dev/workflow-editor', match: 'prefix', title: '工作流编排', group: GRP_ALGO, breadcrumb: ['算法开发'], optionalSpine: ['scenarioId', 'solutionId', 'workflowId'] },
  { pattern: '/algorithm-dev/operators', match: 'exact', title: '基础算法库', group: GRP_ALGO, breadcrumb: ['算法开发'] },
  { pattern: '/algorithm-dev/autoresearch', match: 'exact', title: '自动化回测', group: GRP_ALGO, breadcrumb: ['算法开发'], optionalSpine: ['scenarioId', 'solutionId', 'workflowId'] },
  { pattern: '/algorithm-dev/deployment', match: 'exact', title: '算法部署', group: GRP_ALGO, breadcrumb: ['算法开发'], optionalSpine: ['slot', 'workflowId'] },
  // 注：/accuracy-operations、/algorithm-deployment 原页头链未收录（显示空标题，页面自带页头），
  // 此处不加标题以保持逐字一致；其上下文栏在后续页面改造（§18 / 任务 2.2）中提供。

  // 基础算法库 / 工作流（旧入口）
  { pattern: '/functions', match: 'exact', titleKey: 'header.basicAlgorithmLibrary' },
  { pattern: '/knowledge-graph', match: 'exact', titleKey: 'header.aiKnowledgeGraph' },
  { pattern: '/workflow/editor', match: 'prefix', titleKey: 'header.workflowEditor', optionalSpine: ['workflowId'] },
  { pattern: '/workflow/list', match: 'exact', titleKey: 'header.myWorkflows' },
  { pattern: '/workflow/baseline-compare', match: 'exact', titleKey: 'header.baselineCompare' },
  { pattern: '/workflow-agent', match: 'exact', titleKey: 'header.intelligentOrchestration' },
  { pattern: '/workflow-agent/history', match: 'exact', titleKey: 'header.orchestrationHistory' },

  // 回测
  { pattern: '/backtest', match: 'exact', titleKey: 'header.workflowBacktest' },
  { pattern: '/backtest/monitor', match: 'exact', titleKey: 'header.backtestMonitor' },
  { pattern: '/backtest/results', match: 'exact', titleKey: 'header.backtestResults' },
  { pattern: '/backtest/unified', match: 'exact', titleKey: 'header.backtestTasks' },
  { pattern: '/backtest/unified/monitor', match: 'exact', titleKey: 'header.backtestMonitor' },
  { pattern: '/backtest/unified/results', match: 'exact', titleKey: 'header.backtestResults' },

  // 部署 / 运维（旧入口）
  { pattern: '/deployment', match: 'exact', titleKey: 'header.deploymentTasks' },
  { pattern: '/deployment/services', match: 'exact', titleKey: 'header.serviceManagement' },
  { pattern: '/deployment/monitor', match: 'exact', titleKey: 'header.serviceMonitor' },
  { pattern: '/ops/drift', match: 'exact', titleKey: 'header.driftMonitor' },
  { pattern: '/ops/ab-test', match: 'exact', titleKey: 'header.abTest' },
  { pattern: '/ops/retrain', match: 'exact', titleKey: 'header.autoRetrain' },
  { pattern: '/precision-ops', match: 'exact', title: '精度运营' },
  { pattern: '/algorithm-agent', match: 'exact', titleKey: 'header.algorithmAgent' },
  { pattern: '/llm-config', match: 'exact', titleKey: 'header.llmConfig' },

  // 模板 / 技能
  { pattern: '/templates', match: 'exact', titleKey: 'header.templateLibrary' },
  { pattern: '/template-library', match: 'exact', titleKey: 'header.templateLibrary' },
  { pattern: '/skill-library', match: 'exact', titleKey: 'header.skills' },
  { pattern: '/skill-library/', match: 'prefix', titleKey: 'header.skillDetails' },
  { pattern: '/skill-test/tasks', match: 'exact', titleKey: 'header.skillTest' },
  { pattern: '/skill-test/training', match: 'exact', titleKey: 'header.skillTraining' },
  { pattern: '/skill-test/results', match: 'exact', titleKey: 'header.skillResults' },

  // 系统
  { pattern: '/system-status', match: 'exact', titleKey: 'header.systemStatus', group: GRP_SYSTEM },
  { pattern: '/architecture', match: 'exact', titleKey: 'header.devArchitecture', group: GRP_SYSTEM },
  { pattern: '/settings', match: 'exact', titleKey: 'header.systemConfig', group: GRP_SYSTEM },
  { pattern: '/algorithm-db-test', match: 'exact', titleKey: 'header.functionalTest' },
  { pattern: '/load-forecast/training', match: 'exact', titleKey: 'header.loadForecastTraining' },
  { pattern: '/profile', match: 'exact', titleKey: 'header.profile', group: GRP_SYSTEM },
];

/** 解析某路径的路由元数据：exact 优先，其次最长 prefix。 */
export function resolveRouteMeta(pathname: string): RouteMeta | undefined {
  const exact = ROUTE_METADATA.find((m) => m.match === 'exact' && m.pattern === pathname);
  if (exact) return exact;
  let best: RouteMeta | undefined;
  for (const meta of ROUTE_METADATA) {
    if (meta.match === 'prefix' && pathname.startsWith(meta.pattern)) {
      if (!best || meta.pattern.length > best.pattern.length) best = meta;
    }
  }
  return best;
}

/** 解析页头标题（保持与原 MainLayout 逐字一致；未命中返回空串）。 */
export function resolveRouteTitle(pathname: string, translate: (key: string) => string): string {
  const meta = resolveRouteMeta(pathname);
  if (!meta) return '';
  if (meta.title) return meta.title;
  if (meta.titleKey) return translate(meta.titleKey);
  return '';
}

// @AI_GENERATED: end
