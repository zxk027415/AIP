// @AI_GENERATED
/**
 * PV 双路径 API 客户端：只读查询与有副作用写入分离。
 */
import api from './api';
import type {
  LedgerPage,
  ModelingPathsState,
  PathSwitchEvent,
  PromotionEvent,
  SetModelingPathsBody,
  ShadowReport,
} from '../types/pvDualPath';

export const pvDualPathApi = {
  getModelingPaths: (slot = 'pv_fault'): Promise<ModelingPathsState> =>
    api.get('/iterative-labeling/cumulative-training/modeling-paths', { params: { slot } }),

  setModelingPaths: (body: SetModelingPathsBody): Promise<Record<string, unknown>> =>
    api.put('/iterative-labeling/cumulative-training/modeling-paths', body, {
      params: { slot: body.slot || 'pv_fault' },
    }),

  promoteWithinPath: (
    modelingPath: string,
    body: {
      candidate_id: string;
      set_as_production: boolean;
      production_slot?: string;
      operator?: string;
      reason?: string;
    },
  ): Promise<Record<string, unknown>> =>
    api.post(
      `/iterative-labeling/cumulative-training/modeling-paths/${modelingPath}/promote`,
      body,
    ),

  getLedger: (params: Record<string, string | number | undefined> = {}): Promise<LedgerPage> =>
    api.get('/scheduler/pv-dual-path/ledger', { params }),

  getEpochs: (params: Record<string, string | number | undefined> = {}) =>
    api.get('/scheduler/pv-dual-path/activation-epochs', { params }),

  previewActivation: (body: Record<string, unknown>) =>
    api.post('/scheduler/pv-dual-path/activation-preview', body),

  runShadowCompare: (body: {
    slot?: string;
    start_date: string;
    end_date: string;
    device_scope?: Array<Record<string, string>>;
  }) => api.post('/scheduler/pv-dual-path/shadow-compare', body),

  getShadowCompare: (comparisonId: string, slot = 'pv_fault'): Promise<ShadowReport> =>
    api.get(`/scheduler/pv-dual-path/shadow-compare/${comparisonId}`, { params: { slot } }),

  getPromotionEvents: (params: Record<string, string | number | undefined> = {}): Promise<{
    total: number;
    items: PromotionEvent[];
  }> => api.get('/iterative-labeling/cumulative-training/promotion-events', { params }),

  getPathSwitchEvents: (params: Record<string, string | number | undefined> = {}): Promise<{
    total: number;
    items: PathSwitchEvent[];
  }> => api.get('/iterative-labeling/cumulative-training/path-switch-events', { params }),

  getBackfill: (taskId: string) => api.get(`/scheduler/pv-dual-path/backfill/${taskId}`),

  retryBackfill: (taskId: string) =>
    api.post(`/scheduler/pv-dual-path/backfill/${taskId}/retry`),

  cancelReleaseBackfill: (
    taskId: string,
    body: { confirm: boolean; operator: string; reason: string },
  ) => api.post(`/scheduler/pv-dual-path/backfill/${taskId}/cancel-release`, body),
};
// @AI_GENERATED: end
