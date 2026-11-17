// @AI_GENERATED: pv-fault accuracy-ops shared data bundle
/**
 * usePvFaultAccuracyOpsBundle — 精度运营 pv_fault 页一次性并行拉取共享数据，
 * 避免 StoryRail / Evidence / PointLabelOps / Overview 各自重复请求。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  schedulerTaskApi,
  type PvMockFeedPreview,
  type PvPredictionCursorStatusResponse,
  type ScheduledTaskSummary,
} from '../services/deploymentApi';
import { cumulativeTrainingApi, pointLabelApi, trainingWorkspaceApi } from '../services/iterativeLabelingApi';

export interface PvFaultOpsBundle {
  overview: Record<string, unknown> | null;
  tasks: ScheduledTaskSummary[];
  feedPreview: PvMockFeedPreview | null;
  feedError: string | null;
  cumulativeState: Record<string, unknown> | null;
  cursorStatus: PvPredictionCursorStatusResponse | null;
  sourceCoverage: Record<string, unknown> | null;
  pendingQueue: Record<string, unknown> | null;
}

function mergeCumulativeIntoOverview(
  overview: Record<string, unknown> | null,
  cumulativeResp: Record<string, unknown> | null,
): Record<string, unknown> | null {
  if (!overview && !cumulativeResp) return null;
  const merged: Record<string, unknown> = overview ? { ...overview } : {};
  if (!cumulativeResp) return merged;

  if (!merged.cumulative_training) {
    const latestSnapshot = (cumulativeResp.latest_snapshot || {}) as Record<string, unknown>;
    const latestRetrain = (cumulativeResp.latest_retrain_request || {}) as Record<string, unknown>;
    merged.cumulative_training = {
      effective_labeled_unit_count: cumulativeResp.effective_labeled_unit_count,
      pending_change_count: cumulativeResp.pending_change_count,
      retrain_label_threshold: cumulativeResp.retrain_label_threshold,
      next_retrain_in: cumulativeResp.next_retrain_in,
      latest_snapshot_id: latestSnapshot.snapshot_id || latestSnapshot.id || null,
      latest_retrain_status: latestRetrain.status || null,
      latest_retrain_request_id: latestRetrain.request_id || null,
      latest_completed_model_ref: cumulativeResp.latest_completed_model_ref || null,
    };
  }
  if (!merged.model_ref) {
    merged.model_ref = cumulativeResp.latest_completed_model_ref || null;
  }
  return merged;
}

export function usePvFaultAccuracyOpsBundle(slot: string, refreshKey: number, enabled: boolean) {
  const [bundle, setBundle] = useState<PvFaultOpsBundle | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    let feedError: string | null = null;

    try {
      const [
        overviewResp,
        tasksResp,
        feedResp,
        cumulativeResp,
        cursorResp,
        coverageResp,
        queueResp,
      ] = await Promise.all([
        trainingWorkspaceApi.getSlotOverview(slot).catch(() => null),
        schedulerTaskApi.listScheduledTasks().catch(() => ({ tasks: [] as ScheduledTaskSummary[] })),
        schedulerTaskApi.getPvMockFeedStatus().catch((err: { response?: { data?: { detail?: string } }; message?: string }) => {
          const detail = err?.response?.data?.detail || err?.message || '喂数状态读取失败';
          feedError = typeof detail === 'string' ? detail : '喂数状态读取失败';
          return null;
        }),
        cumulativeTrainingApi.getState(slot).catch(() => null),
        schedulerTaskApi.getPvPredictionCursorStatus().catch(() => null),
        pointLabelApi.getSourceCoverage(slot).catch(() => null),
        pointLabelApi.getPendingQueue({ page: 1, pageSize: 20 }, slot).catch(() => null),
      ]);

      const overview = mergeCumulativeIntoOverview(
        overviewResp as Record<string, unknown> | null,
        cumulativeResp as Record<string, unknown> | null,
      );

      setBundle({
        overview,
        tasks: tasksResp?.tasks ?? [],
        feedPreview: feedResp?.preview ?? null,
        feedError,
        cumulativeState: cumulativeResp as Record<string, unknown> | null,
        cursorStatus: cursorResp,
        sourceCoverage: coverageResp as Record<string, unknown> | null,
        pendingQueue: queueResp as Record<string, unknown> | null,
      });
    } catch {
      setBundle(null);
    } finally {
      setLoading(false);
    }
  }, [enabled, slot]);

  useEffect(() => {
    if (!enabled) return;
    void load();
  }, [load, refreshKey, enabled]);

  return { bundle, loading, reload: load };
}
