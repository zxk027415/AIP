// @AI_GENERATED
/**
 * 解决方案能力适配层（让项目工作台领域无关）。
 *
 * 设计依据：design.md §11.5——领域差异全部收敛到 SolutionCapabilityAdapter；壳只依赖本接口，
 * 不出现任何 `if (solution === 'pv_fault')` 式硬编码分支。新增领域 = 注册一个适配器，
 * 不改壳 / 路由骨架 / 上下文栏 / scope 规则。
 *
 * 本规格只交付光伏故障适配器；负荷预测等仅在此定义接口位置，不在此实现。
 */

/** 领域的一条诊断路径（slot）。 */
export interface SolutionPathDef {
  /** slot 值（URL / API 用），如 pv_day。 */
  slot: string;
  /** 展示词，如「天路径」。 */
  label: string;
  /** 一句路径说明。 */
  description: string;
}

/** 生命周期阶段定义。 */
export interface LifecycleStageDef {
  /** 稳定 key（分支用），如 data / workflow / governance。 */
  key: string;
  /** 展示名，如「数据与兼容性」。 */
  label: string;
  /** 路由段，如 data / workflows / models。 */
  routeSegment: string;
}

/** 领域可选能力开关。 */
export interface SolutionCapabilities {
  review: boolean;
  cumulative: boolean;
  canonicalLabeling: boolean;
}

/**
 * 按 solution_id 提供某业务领域在工作台内差异化配置的适配器。
 * 壳只消费本接口。readinessContract / stagePanels / stateVocabulary 为扩展点，
 * 本期只声明位置（可选），由各领域按需提供。
 */
export interface SolutionCapabilityAdapter {
  solutionId: string;
  /** 领域展示名，如「光伏故障诊断」。 */
  displayName: string;
  /** 诊断路径集合的展示词（design §11.5：UI 显示「诊断路径」）。 */
  pathsLabel: string;
  /** 该领域的诊断路径集合及展示词。 */
  paths: SolutionPathDef[];
  /** 生命周期阶段集合、顺序与标签。 */
  lifecycleStages: LifecycleStageDef[];
  /** 每条路径的 readiness 判定输入与结论枚举（§25）；由 readiness 任务（2.5）填充。 */
  readinessContract?: Record<string, unknown>;
  /** 每个阶段内嵌的现有面板 / 页面（§11.4 归属表）；由 wrap-first 任务（2.2）填充。 */
  stagePanels?: Record<string, unknown>;
  /** 该领域是否包含审核 / 累计训练集 / canonical 打标等可选阶段。 */
  capabilities: SolutionCapabilities;
  /** 领域特有状态文案键（在 §28.4 集中词汇之上扩展；可选）。 */
  stateVocabulary?: Record<string, string>;
}

const _registry = new Map<string, SolutionCapabilityAdapter>();

/** 注册一个解决方案适配器（重复注册以后者为准）。 */
export function registerSolutionAdapter(adapter: SolutionCapabilityAdapter): void {
  _registry.set(adapter.solutionId, adapter);
}

/** 按 solution_id 取适配器；未注册返回 null（壳据此显示「尚未接入工作台」）。 */
export function getSolutionAdapter(solutionId: string | undefined | null): SolutionCapabilityAdapter | null {
  const key = String(solutionId ?? '').trim();
  if (!key) return null;
  return _registry.get(key) ?? null;
}

/** 已注册的适配器列表（调试 / 列表用）。 */
export function listSolutionAdapters(): SolutionCapabilityAdapter[] {
  return Array.from(_registry.values());
}

// @AI_GENERATED: end
