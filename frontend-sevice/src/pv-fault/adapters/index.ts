// @AI_GENERATED
/**
 * 适配器注册入口。导入本模块即注册光伏故障适配器（本规格唯一实现的适配器）。
 * 后续接入新领域只需在此追加一次注册，不改工作台壳。
 */

import { registerSolutionAdapter } from './solutionCapabilityAdapter';
import { pvFaultAdapter } from './pvFaultAdapter';

registerSolutionAdapter(pvFaultAdapter);

export {
  getSolutionAdapter,
  listSolutionAdapters,
  registerSolutionAdapter,
} from './solutionCapabilityAdapter';
export type {
  SolutionCapabilityAdapter,
  SolutionPathDef,
  LifecycleStageDef,
  SolutionCapabilities,
} from './solutionCapabilityAdapter';
export { pvFaultAdapter, PV_FAULT_SOLUTION_ID } from './pvFaultAdapter';

// @AI_GENERATED: end
