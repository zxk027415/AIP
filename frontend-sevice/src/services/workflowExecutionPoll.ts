/**
 * 算法模板异步执行的全局轮询：离开编辑器页面不停止，仅通过 stop 或任务结束停止。
 */
import { message } from 'antd';
import i18n from '../i18n';
import { pipelineApi } from './workflowEnhancedApi';
import { useWorkflowEditorStore } from '../stores/workflowEditorStore';
import { usePipelineExecutionStore } from '../stores/pipelineExecutionStore';
import { useWorkflowRunNavStore } from '../stores/workflowRunNavStore';

let pollTimer: ReturnType<typeof setInterval> | null = null;
let timeoutTimer: ReturnType<typeof setTimeout> | null = null;

export function stopWorkflowExecutionPollAll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (timeoutTimer) {
    clearTimeout(timeoutTimer);
    timeoutTimer = null;
  }
}

export function isWorkflowExecutionPolling() {
  return pollTimer !== null;
}

async function pollOnce(workflowId: string, executionId: string) {
  try {
    const resp = await pipelineApi.getExecutionStatus(workflowId, executionId);
    const editorWfId = useWorkflowEditorStore.getState().workflowId;
    const canvasMatchesRun = editorWfId === workflowId;
    const nodesSnapshot = useWorkflowEditorStore.getState().nodes;

    const newLogs = (resp.logs || []).map((l: { timestamp?: string; message?: string; type?: string }) => ({
      timestamp: l.timestamp || '',
      message: l.message || '',
      type: l.type || 'info',
    }));

    const newStatuses: Record<string, any> = {};
    if (resp.nodeResults) {
      const nrMap = resp.nodeResults as Record<string, { status?: string; executionTime?: number; error?: string }>;
      for (const [nid, nr] of Object.entries(nrMap)) {
        const nodeObj = canvasMatchesRun ? nodesSnapshot.find((n) => n.id === nid) : undefined;
        const st = nr.status;
        const status =
          st === 'success' || st === 'skipped'
            ? 'completed'
            : st === 'failed'
              ? 'failed'
              : 'waiting';
        newStatuses[nid] = {
          nodeId: nid,
          operatorId: nodeObj?.data?.config?.functionId || '',
          label: nodeObj?.data?.label || nid,
          status,
          duration: nr.executionTime,
          error: nr.error,
        };
      }
    }

    if (resp.nodeResults && canvasMatchesRun) {
      const updatedNodes = nodesSnapshot.map((n) => {
        const nr = (resp.nodeResults as Record<string, { status?: string }>)[n.id];
        if (!nr) return n;
        let next: 'idle' | 'running' | 'success' | 'error' = n.data.status || 'idle';
        if (nr.status === 'success' || nr.status === 'skipped') next = 'success';
        else if (nr.status === 'failed') next = 'error';
        return { ...n, data: { ...n.data, status: next } };
      });
      useWorkflowEditorStore.getState().setNodes(updatedNodes);
    }

    usePipelineExecutionStore.setState((s) => ({
      logs: newLogs.length > 0 ? newLogs : s.logs,
      ...(resp.nodeResults !== undefined ? { nodeStatuses: newStatuses } : {}),
    }));

    if (resp.status === 'success' || resp.status === 'failed') {
      stopWorkflowExecutionPollAll();
      useWorkflowEditorStore.getState().setIsExecuting(false);
      useWorkflowRunNavStore.getState().clearActiveRun();

      const nameNow = useWorkflowEditorStore.getState().workflowName;
      const globalCfg = usePipelineExecutionStore.getState().globalConfig as any;
      const runMode = String(globalCfg?.run_mode || globalCfg?.operate_status || 'training').toLowerCase();
      const templateType =
        runMode === 'prediction' || runMode === 'predict'
          ? 'prediction'
          : runMode === 'backtest'
            ? 'backtest'
            : runMode === 'tuning'
              ? 'tuning'
              : 'training';
      // 如果后端返回了 fault_predictions，说明这是故障诊断预测，强制按预测模式展示
      const hasFaultPredictions = Array.isArray(resp.fault_predictions) && resp.fault_predictions.length > 0;
      const isPredictionMode = templateType === 'prediction' || hasFaultPredictions;
      const isBacktestMode = templateType === 'backtest';
      const isTuningMode = templateType === 'tuning';
      const drawerPayload = {
        ...resp,
        success: resp.status === 'success',
        executionTime: resp.executionTime || 0,
        nodeResults: resp.nodeResults || {},
      };

      const historyEntry = {
        executionId,
        templateName: nameNow,
        templateType: templateType as 'training' | 'prediction' | 'backtest' | 'tuning',
        status: resp.status,
        modelId: resp.model_id,
        totalDuration: resp.executionTime,
        nodeConfigs: {},
        globalConfig: usePipelineExecutionStore.getState().globalConfig,
        createdAt: new Date().toISOString(),
        resultPayload: drawerPayload,
      };

      if (resp.status === 'success') {
        const forecastValues = Array.isArray(resp.forecast_values)
          ? resp.forecast_values
          : (Array.isArray(resp.y_pred) ? resp.y_pred : []);
        const rawTimestamps = Array.isArray(resp.forecast_timestamps) ? resp.forecast_timestamps : [];
        const forecastTimestamps =
          rawTimestamps.length === forecastValues.length
            ? rawTimestamps
            : forecastValues.map((_: unknown, idx: number) => String(idx));
        const gcfg = usePipelineExecutionStore.getState().globalConfig || {};
        const nowtime = gcfg?.nowtime;
        const backtestDate = typeof nowtime === 'string' && nowtime.trim().length > 0
          ? nowtime.slice(0, 10)
          : (String(gcfg?.backtest_end_date || '').trim() || new Date().toISOString().slice(0, 10));

        usePipelineExecutionStore.setState({
          executionStatus: 'success',
          isExecuting: false,
          trainingResult:
            !isPredictionMode && !isBacktestMode && !isTuningMode && (resp.metrics || resp.model_id || resp.nodeDurations)
              ? ({
                  executionId,
                  totalDuration: resp.executionTime || 0,
                  completedAt: new Date().toISOString(),
                  templateName: nameNow,
                  modelId: resp.model_id,
                  nodeDurations: resp.nodeDurations || {},
                  metrics: resp.metrics,
                } as any)
              : null,
          predictionResult:
            isPredictionMode && (forecastValues.length > 0 || resp.fault_predictions)
              ? ({
                  executionId,
                  totalDuration: resp.executionTime || 0,
                  completedAt: new Date().toISOString(),
                  modelId: resp.model_id || '',
                  forecastTimestamps,
                  forecastValues,
                  nodeDurations: resp.nodeDurations || {},
                  faultPredictions: resp.fault_predictions || undefined,
                  metrics: resp.metrics || undefined,
                  faultTimeseries: resp.fault_timeseries || undefined,
                } as any)
              : null,
          backtestResult:
            isBacktestMode
              ? ({
                  executionId,
                  totalDuration: resp.executionTime || 0,
                  totalDays: 1,
                  successDays: resp.status === 'success' ? 1 : 0,
                  skippedDays: 0,
                  failedDays: resp.status === 'success' ? 0 : 1,
                  dailyResults: [
                    {
                      date: backtestDate,
                      status: resp.status === 'success' ? 'success' : 'failed',
                      durationSeconds: resp.executionTime || 0,
                      forecastTimestamps,
                      forecastValues,
                      actualValues: Array.isArray(resp.y_true) ? resp.y_true : [],
                      pointCount: forecastValues.length,
                      reason: resp.status === 'success' ? undefined : (resp.error || ''),
                    },
                  ],
                  metrics: {
                    avgSmape: Number(resp.metrics?.smape || 0),
                    avgMae: Number(resp.metrics?.mae || 0),
                    avgRmse: Number(resp.metrics?.rmse || 0),
                    dailySmape: [{ date: backtestDate, value: Number(resp.metrics?.smape || 0) }],
                    dailyMae: [{ date: backtestDate, value: Number(resp.metrics?.mae || 0) }],
                    dailyRmse: [{ date: backtestDate, value: Number(resp.metrics?.rmse || 0) }],
                  },
                } as any)
              : null,
          executionHistory: [...usePipelineExecutionStore.getState().executionHistory, historyEntry],
          pendingResultDrawer: { success: true, payload: drawerPayload },
        });
        message.success(
          i18n.t('workflow.pipelineSuccess', { time: (resp.executionTime || 0).toFixed(1) }),
        );
      } else {
        usePipelineExecutionStore.setState({
          executionStatus: 'failed',
          isExecuting: false,
          executionHistory: [...usePipelineExecutionStore.getState().executionHistory, historyEntry],
          pendingResultDrawer: { success: false, payload: drawerPayload },
        });
        message.error(i18n.t('workflow.pipelineFailed', { error: resp.error || '' }));
      }
    }
  } catch {
    /* 静默重试 */
  }
}

export function startWorkflowExecutionPoll(workflowId: string, executionId: string) {
  stopWorkflowExecutionPollAll();

  timeoutTimer = setTimeout(() => {
    const st = usePipelineExecutionStore.getState();
    if (st.executionStatus === 'running') {
      stopWorkflowExecutionPollAll();
      usePipelineExecutionStore.setState({ executionStatus: 'failed', isExecuting: false });
      useWorkflowEditorStore.getState().setIsExecuting(false);
      useWorkflowRunNavStore.getState().clearActiveRun();
      message.warning(i18n.t('workflow.executionTimeout'));
    }
  }, 300_000);

  pollTimer = setInterval(() => {
    void pollOnce(workflowId, executionId);
  }, 1500);
}
