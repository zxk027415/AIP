// @AI_GENERATED
/**
 * 光伏故障诊断解决方案适配器（本规格唯一实现的适配器样例）。
 *
 * 设计依据：design.md §11.5——诊断路径 pv_day / pv_point / pv_tsc，六阶段生命周期，
 * 审核 / 累计 / canonical 打标均包含。solution_id 采用 'pv_fault'。
 */

import type { SolutionCapabilityAdapter } from './solutionCapabilityAdapter';

export const PV_FAULT_SOLUTION_ID = 'pv_fault';

export const pvFaultAdapter: SolutionCapabilityAdapter = {
  solutionId: PV_FAULT_SOLUTION_ID,
  displayName: '光伏故障诊断',
  pathsLabel: '诊断路径',
  paths: [
    { slot: 'pv_day', label: '天路径', description: '设备日 RF；当前生产日检测使用 quickval predict 图。' },
    { slot: 'pv_point', label: '点路径', description: '真实事件点 replay TCN；SeqDailyStrategy 直连 predictor。' },
    { slot: 'pv_tsc', label: 'TSC 路径', description: '设备日 MultiRocket 时序分类；288×3 时钟网格多窗口投票。' },
  ],
  lifecycleStages: [
    { key: 'data', label: '数据与兼容性', routeSegment: 'data' },
    { key: 'workflow', label: '工作流与运行', routeSegment: 'workflows' },
    { key: 'governance', label: '模型与治理', routeSegment: 'models' },
    { key: 'operations', label: '检测与回放', routeSegment: 'operations' },
    { key: 'review', label: '审核与精度', routeSegment: 'reviews' },
    { key: 'cumulative', label: '累计训练集', routeSegment: 'cumulative' },
  ],
  capabilities: {
    review: true,
    cumulative: true,
    canonicalLabeling: true,
  },
};

// @AI_GENERATED: end
