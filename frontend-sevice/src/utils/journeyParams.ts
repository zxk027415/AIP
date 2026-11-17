// @AI_GENERATED
/**
 * 平台旅程「上下文合同」：四层主干 query 参数的规范命名与读写。
 *
 * 设计依据：design.md §32（四层主干 scenario_id › solution_id › slot › project_id）、
 * §33.2（每次导航携带已解析主干；目标渲染收到的上下文；未消费参数向下透传）；
 * requirements.md R1.1–R1.5、R1.8、R1.9、R2.1、R2.3。
 *
 * 迁移策略（安全、向后兼容）：
 * - 规范写入名：scenario_id / solution_id / slot / project_id / workflow_id / dataset_version_id。
 * - 读取时兼容历史别名：scenario_id←scenario，solution_id←template，workflow_id←workflowId。
 *   这样存量深链接仍可解析，新链接统一输出规范名，无需一次性改所有旧链接。
 */

/** 规范 query 参数名（唯一真源）。 */
export const JOURNEY_PARAM = {
  scenarioId: 'scenario_id',
  solutionId: 'solution_id',
  slot: 'slot',
  projectId: 'project_id',
  workflowId: 'workflow_id',
  datasetVersionId: 'dataset_version_id',
} as const;

export type JourneyParamKey = keyof typeof JOURNEY_PARAM;

/** 每个规范名可接受的历史别名（第一个即规范名）。 */
const PARAM_ALIASES: Record<string, string[]> = {
  scenario_id: ['scenario_id', 'scenario'],
  solution_id: ['solution_id', 'template'],
  workflow_id: ['workflow_id', 'workflowId'],
  slot: ['slot'],
  project_id: ['project_id'],
  dataset_version_id: ['dataset_version_id'],
};

/** 已解析的旅程主干（camelCase 视图，便于 TS 使用）。 */
export interface JourneySpine {
  scenarioId?: string;
  solutionId?: string;
  slot?: string;
  projectId?: string;
  workflowId?: string;
  datasetVersionId?: string;
}

type SearchParamsLike = URLSearchParams | { get(name: string): string | null };

/** 按规范名读取参数，兼容历史别名；空串视为缺失。 */
export function readParam(searchParams: SearchParamsLike, canonical: string): string | undefined {
  const aliases = PARAM_ALIASES[canonical] ?? [canonical];
  for (const key of aliases) {
    const value = searchParams.get(key);
    if (value != null && value.trim() !== '') return value.trim();
  }
  return undefined;
}

/** 从 URLSearchParams 解析完整旅程主干（别名兼容）。 */
export function readSpine(searchParams: SearchParamsLike): JourneySpine {
  return {
    scenarioId: readParam(searchParams, JOURNEY_PARAM.scenarioId),
    solutionId: readParam(searchParams, JOURNEY_PARAM.solutionId),
    slot: readParam(searchParams, JOURNEY_PARAM.slot),
    projectId: readParam(searchParams, JOURNEY_PARAM.projectId),
    workflowId: readParam(searchParams, JOURNEY_PARAM.workflowId),
    datasetVersionId: readParam(searchParams, JOURNEY_PARAM.datasetVersionId),
  };
}

/** 把主干写入 URLSearchParams（仅输出规范名；空值跳过）。 */
export function applySpine(target: URLSearchParams, spine: JourneySpine): URLSearchParams {
  const set = (name: string, value?: string) => {
    if (value && value.trim() !== '') target.set(name, value.trim());
  };
  set(JOURNEY_PARAM.scenarioId, spine.scenarioId);
  set(JOURNEY_PARAM.solutionId, spine.solutionId);
  set(JOURNEY_PARAM.slot, spine.slot);
  set(JOURNEY_PARAM.projectId, spine.projectId);
  set(JOURNEY_PARAM.workflowId, spine.workflowId);
  set(JOURNEY_PARAM.datasetVersionId, spine.datasetVersionId);
  return target;
}

/** 构造带规范主干参数的 URL（extra 为附加规范参数）。 */
export function buildJourneyHref(
  path: string,
  spine: JourneySpine,
  extra?: Record<string, string | undefined>,
): string {
  const params = new URLSearchParams();
  applySpine(params, spine);
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      if (value && value.trim() !== '') params.set(key, value.trim());
    }
  }
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

/**
 * 兼容重定向拼接：把当前 location.search 透传到目标路径（§33.2 未消费参数向下透传）。
 * `search` 形如 `?a=1&b=2`（含前导 ?）或空串。
 */
export function appendSearch(to: string, search: string): string {
  const trimmed = (search || '').replace(/^\?/, '');
  if (!trimmed) return to;
  return `${to}${to.includes('?') ? '&' : '?'}${trimmed}`;
}

// @AI_GENERATED: end
