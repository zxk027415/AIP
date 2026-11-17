/**
 * 快速回测：请求在模块内发起，离开编辑器页面不会 abort（仅用户点击「停止」时中止）。
 */
import { message } from 'antd';
import i18n from '../i18n';
import type { BacktestPipelineResult } from '../types/pipeline';
import { usePipelineExecutionStore } from '../stores/pipelineExecutionStore';
import { useAlgorithmAgentStore } from '../stores/algorithmAgentStore';
import { useWorkflowRunNavStore } from '../stores/workflowRunNavStore';

let pollTimer: ReturnType<typeof setInterval> | null = null;
let currentRunId: string | null = null;
let currentWorkflowId: string | null = null;
let currentExecutionId: string | null = null;

function ts() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false });
}

function mapApiToResult(workflowId: string, result: Record<string, unknown>): BacktestPipelineResult {
  if ((result as any).mode === 'tuning_batch') {
    return {
      executionId: workflowId,
      totalDuration: 0,
      totalDays: 0,
      successDays: 0,
      skippedDays: 0,
      failedDays: 0,
      dailyResults: [],
      mode: 'tuning_batch',
      rankedCandidates: Array.isArray((result as any).ranked_candidates) ? ((result as any).ranked_candidates as any[]) : [],
      bestRecommendation: (result as any).best_recommendation || null,
    };
  }
  const daily = (result.daily_results as unknown[]) || [];
  return {
    executionId: workflowId,
    totalDuration: (result.total_duration as number) || 0,
    totalDays: (result.total_days as number) || 0,
    successDays: (result.success_days as number) || 0,
    skippedDays: (result.skipped_days as number) || 0,
    failedDays: (result.failed_days as number) || 0,
    dailyResults: daily.map((d: any) => ({
      date: d.date,
      status: d.status,
      durationSeconds: d.duration,
      pointCount: d.point_count || (d.y_pred ? d.y_pred.length : 0),
      forecastValues: d.y_pred || [],
      actualValues: d.y_true || [],
      reason: d.error,
    })),
    metrics: (result as any).avg_metrics
      ? {
          avgSmape: (result as any).avg_metrics.avg_smape,
          avgMae: (result as any).avg_metrics.avg_mae,
          avgRmse: (result as any).avg_metrics.avg_rmse,
          dailySmape: daily
            .filter((d: any) => d.metrics?.smape != null)
            .map((d: any) => ({ date: d.date, value: d.metrics.smape })),
          dailyMae: daily
            .filter((d: any) => d.metrics?.mae != null)
            .map((d: any) => ({ date: d.date, value: d.metrics.mae })),
          dailyRmse: daily
            .filter((d: any) => d.metrics?.rmse != null)
            .map((d: any) => ({ date: d.date, value: d.metrics.rmse })),
        }
      : undefined,
    artifactPaths: Array.isArray((result as any).artifact_paths) ? ((result as any).artifact_paths as string[]) : [],
    artifactUrls: Array.isArray((result as any).artifact_urls) ? ((result as any).artifact_urls as string[]) : [],
    outputDir: (result as any).output_dir || undefined,
    mode: (result as any).mode || 'backtest',
  };
}

function stopBacktestPollingTimer() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

export function stopQuickBacktest() {
  const wfId = currentWorkflowId;
  const execId = currentExecutionId;
  stopBacktestPollingTimer();
  if (wfId && execId) {
    fetch(`/api/workflows/enhanced/${wfId}/backtest-cancel/${execId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }).catch(() => {});
  }
  if (wfId) {
    fetch(`/api/workflows/enhanced/${wfId}/backtest/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }).catch(() => {});
  }
  const hadRun = currentRunId !== null;
  currentRunId = null;
  currentWorkflowId = null;
  currentExecutionId = null;
  usePipelineExecutionStore.setState((s) => ({
    quickBacktestLoading: false,
    isExecuting: false,
    executionStatus: 'failed',
    backtestProgress: null,
    logs: [
      ...s.logs,
      { timestamp: ts(), message: '✗ 回测已手动中止', type: 'error' },
    ],
  }));
  useWorkflowRunNavStore.getState().clearActiveRun();
  if (hadRun) {
    message.warning(i18n.t('backtest.backtestAborted'));
  }
}

export function runQuickBacktest(params: {
  workflowId: string;
  returnHref: string;
  workflowName: string;
  templateType?: 'backtest' | 'tuning';
  startDate: string;
  endDate: string;
  trainDays?: number;
  dailyHorizon?: number;
  generateArtifacts?: boolean;
  outputDir?: string;
  applyWindowFilter?: boolean;
  maskTargetValues?: boolean;
  backtestMode?: string;
  modelRef?: string;
  useReferenceEngine?: boolean;
  strictAlignmentMode?: boolean;
  tuningCandidates?: Array<{ name?: string; params?: Record<string, any> }>;
}) {
  const {
    workflowId,
    returnHref,
    workflowName,
    templateType = 'backtest',
    startDate,
    endDate,
    trainDays,
    dailyHorizon,
    generateArtifacts,
    outputDir,
    applyWindowFilter,
    maskTargetValues,
    backtestMode,
    modelRef,
    useReferenceEngine,
    strictAlignmentMode,
    tuningCandidates,
  } = params;

  stopBacktestPollingTimer();
  const runId = `${workflowId}-${Date.now()}`;
  currentRunId = runId;
  currentWorkflowId = workflowId;
  currentExecutionId = null;
  useAlgorithmAgentStore.getState().updateContext({ last_executed_workflow_id: workflowId });

  useWorkflowRunNavStore.getState().setActiveRun(returnHref, workflowName, 'backtest', workflowId);
  useWorkflowRunNavStore.getState().setBacktestInFlight(true);
  usePipelineExecutionStore.setState((s) => ({
    quickBacktestLoading: true,
    isExecuting: true,
    executionStatus: 'running',
    logs: [
      ...s.logs,
      { timestamp: ts(), message: `▶ 开始回测: ${startDate} ~ ${endDate}`, type: 'start' },
    ],
    backtestProgress: { currentDay: 0, totalDays: 0, currentDate: '' },
  }));

  fetch(`/api/workflows/enhanced/${workflowId}/backtest-async`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      start_date: startDate,
      end_date: endDate,
      train_days: trainDays,
      daily_horizon: dailyHorizon,
      generate_artifacts: generateArtifacts,
      output_dir: outputDir,
      apply_window_filter: applyWindowFilter,
      mask_target_values: maskTargetValues,
      backtest_mode: backtestMode,
      model_ref: modelRef,
      use_reference_engine: useReferenceEngine,
      strict_alignment_mode: strictAlignmentMode,
      tuning_candidates: tuningCandidates,
    }),
  })
    .then((r) => r.json())
    .then((startResp) => {
      if (currentRunId !== runId) return;
      const executionId = String(startResp.execution_id || '');
      if (!executionId) {
        throw new Error('missing execution_id');
      }
      currentExecutionId = executionId;
      let lastLogSignature = '';
      const pollOnce = () => {
        if (currentRunId !== runId || !currentWorkflowId || !currentExecutionId) return;
        fetch(`/api/workflows/enhanced/${workflowId}/backtest-status/${executionId}`)
          .then((r) => r.json())
          .then((statusResp) => {
            if (currentRunId !== runId) return;
            const logs = Array.isArray(statusResp.logs) ? statusResp.logs : [];
            const progress = statusResp.backtest_progress || { currentDay: 0, totalDays: 0, currentDate: '' };
            const signature = `${logs.length}-${logs.length > 0 ? logs[logs.length - 1]?.timestamp || '' : ''}-${logs.length > 0 ? logs[logs.length - 1]?.message || '' : ''}`;
            usePipelineExecutionStore.setState((s) => ({
              logs: signature !== lastLogSignature && logs.length > 0
                ? logs.map((l: any) => ({
                    timestamp: l.timestamp || '',
                    message: l.message || '',
                    type: l.type || 'info',
                  }))
                : s.logs,
              backtestProgress: {
                currentDay: Number(progress.currentDay || 0),
                totalDays: Number(progress.totalDays || 0),
                currentDate: String(progress.currentDate || ''),
              },
            }));
            if (signature !== lastLogSignature) {
              lastLogSignature = signature;
            }

            if (statusResp.status === 'success' || statusResp.status === 'failed') {
              stopBacktestPollingTimer();
              currentRunId = null;
              currentWorkflowId = null;
              currentExecutionId = null;
              const finalResult = statusResp.backtest_result || {};
              const mapped = mapApiToResult(workflowId, finalResult);
              const cancelled = Boolean(finalResult.cancelled) || Boolean(statusResp.error && String(statusResp.error).includes('取消'));
              usePipelineExecutionStore.setState({
                quickBacktestLoading: false,
                isExecuting: false,
                executionStatus: cancelled ? 'failed' : 'success',
                backtestResult: mapped,
                backtestProgress: null,
                executionHistory: [
                  ...usePipelineExecutionStore.getState().executionHistory,
                  {
                    executionId: runId,
                    templateName: workflowName,
                    templateType,
                    status: cancelled ? 'failed' : 'success',
                    totalDuration: mapped.totalDuration,
                    nodeConfigs: {},
                    globalConfig: usePipelineExecutionStore.getState().globalConfig,
                    createdAt: new Date().toISOString(),
                  },
                ],
              });
              useWorkflowRunNavStore.getState().clearActiveRun();
              if (cancelled) {
                message.warning(i18n.t('backtest.backtestAborted'));
              } else if ((finalResult as any).mode === 'tuning_batch') {
                const best = (finalResult as any).best_recommendation;
                const bestName = best?.name || '-';
                const bestScore = best?.candidate_score?.score;
                message.success(`调优完成：最佳候选 ${bestName}${bestScore != null ? `（score=${bestScore}）` : ''}`);
              } else {
                message.success(
                  i18n.t('backtest.backtestComplete', {
                    success: finalResult.success_days ?? 0,
                    skipped: finalResult.skipped_days ?? 0,
                    failed: finalResult.failed_days ?? 0,
                  }),
                );
              }
            }
          })
          .catch(() => {
            // ignore transient poll errors
          });
      };
      pollOnce();
      pollTimer = setInterval(pollOnce, 1500);
    })
    .catch((err: Error) => {
      if (currentRunId !== runId) return;
      stopBacktestPollingTimer();
      currentRunId = null;
      currentWorkflowId = null;
      currentExecutionId = null;
      usePipelineExecutionStore.setState((s) => ({
        quickBacktestLoading: false,
        isExecuting: false,
        executionStatus: 'failed',
        backtestProgress: null,
        logs: [
          ...s.logs,
          { timestamp: ts(), message: `✗ 回测失败: ${err.message || 'unknown error'}`, type: 'error' },
        ],
      }));
      useWorkflowRunNavStore.getState().clearActiveRun();
      message.error(i18n.t('backtest.backtestFailed'));
    });
}
