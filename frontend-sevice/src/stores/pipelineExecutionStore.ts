// @AI_GENERATED
/**
 * 流水线执行 zustand 状态管理 Store
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { pipelineApi } from '../services/workflowEnhancedApi';
import { useAlgorithmAgentStore } from './algorithmAgentStore';
import { td } from '../utils/dataTranslation';
import type {
  ExecutionStatus,
  NodeExecutionStatus,
  PipelineLogEntry,
  WorkflowGlobalConfig,
  TrainingPipelineResult,
  PredictionPipelineResult,
  BacktestPipelineResult,
  BacktestProgressState,
  ExecutionRecord,
} from '../types/pipeline';

function formatTimestamp(date: Date = new Date()): string {
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

interface PipelineExecutionStore {
  executionId: string | null;
  executionStatus: ExecutionStatus;
  nodeStatuses: Record<string, NodeExecutionStatus>;
  /** 本次流水线画布节点数，用于进度 = 已返回 nodeResults 条目数 / 计划数（API 不含当前运行中节点） */
  pipelinePlannedNodeCount: number | null;
  logs: PipelineLogEntry[];
  isExecuting: boolean;
  globalConfig: WorkflowGlobalConfig;
  trainingResult: TrainingPipelineResult | null;
  predictionResult: PredictionPipelineResult | null;
  backtestResult: BacktestPipelineResult | null;
  backtestProgress: BacktestProgressState | null;
  /** 训练面板「快速回测」HTTP 请求进行中（离开编辑器也不断） */
  quickBacktestLoading: boolean;
  /** 快速回测「天数」选择，离开页面仍保留 */
  quickBacktestDays: number;
  setQuickBacktestDays: (days: number) => void;
  executionHistory: ExecutionRecord[];
  /** 流水线在后台完成时，供编辑器页拉取并打开结果抽屉 */
  pendingResultDrawer: { success: boolean; payload: unknown } | null;
  _pollingTimer: ReturnType<typeof setInterval> | null;
  _workflowId: string | null;

  executePipeline: (workflowId: string, plannedNodeCount?: number | null) => Promise<void>;
  executePreflightCheck: (workflowId: string) => Promise<any>;
  pollExecutionStatus: () => void;
  stopPolling: () => void;
  startBacktest: (workflowId: string, params: { start_date: string; end_date: string }) => Promise<void>;
  updateGlobalConfig: (config: Partial<WorkflowGlobalConfig>) => void;
  exportResults: (format: 'csv') => void;
  loadHistoryConfig: (record: ExecutionRecord) => void;
  reset: () => void;
}

const DEFAULT_GLOBAL_CONFIG: WorkflowGlobalConfig = {
  time_zone: 'Asia/Shanghai',
  operate_status: 'training',
  run_mode: 'training',
  nowtime: '',
  // @AI_GENERATED
  task_type: 'D',
  backtest_start_date: '',
  backtest_end_date: '',
  backtest_train_days: 30,
  backtest_daily_horizon: 96,
  backtest_generate_artifacts: true,
  backtest_output_dir: '',
  backtest_apply_window_filter: true,
  backtest_mask_target_values: true,
  backtest_mode: 'rolling_retrain',
  backtest_model_ref: '',
  use_reference_rolling_engine: false,
  strict_alignment_mode: false,
  tuning_objective: 'avg_smape',
  tuning_trials: 20,
  tuning_model_family: 'xgboost',
  tuning_model_params: {},
  // @AI_GENERATED: end
};

export const usePipelineExecutionStore = create<PipelineExecutionStore>()(
  persist(
    (set, get) => ({
  executionId: null,
  executionStatus: 'idle',
  nodeStatuses: {},
  pipelinePlannedNodeCount: null,
  logs: [],
  isExecuting: false,
  globalConfig: { ...DEFAULT_GLOBAL_CONFIG },
  trainingResult: null,
  predictionResult: null,
  backtestResult: null,
  backtestProgress: null,
  quickBacktestLoading: false,
  quickBacktestDays: 2,
  executionHistory: [],
  pendingResultDrawer: null,
  _pollingTimer: null,
  _workflowId: null,

  executePipeline: async (workflowId: string, plannedNodeCount?: number | null, liveNodes?: any[]) => {
    const { stopPolling, globalConfig } = get();
    stopPolling();
    set({
      executionStatus: 'pending',
      isExecuting: true,
      executionId: null,
      nodeStatuses: {},
      pipelinePlannedNodeCount:
        plannedNodeCount != null && plannedNodeCount > 0 ? plannedNodeCount : null,
      logs: [{
        timestamp: formatTimestamp(),
        message: `${td('流水线配置')}: ${td('时区')}=${globalConfig.time_zone}, ${td('状态')}=${globalConfig.operate_status}`,
        type: 'config',
      }],
      trainingResult: null,
      predictionResult: null,
      backtestResult: null,
      backtestProgress: null,
      quickBacktestLoading: false,
      _workflowId: workflowId,
    });
    try {
      const payload: any = { global_config: globalConfig };
      if (liveNodes) {
        payload.live_nodes = liveNodes;
      }
      const resp = await pipelineApi.executeAsync(workflowId, payload);
      set({ executionId: resp.execution_id, executionStatus: 'running' });
      useAlgorithmAgentStore.getState().updateContext({ last_executed_workflow_id: workflowId });
      get().pollExecutionStatus();
    } catch (error: any) {
      const msg = td(error.response?.data?.detail || error.message || '执行启动失败');
      set((s) => ({
        executionStatus: 'failed',
        isExecuting: false,
        logs: [...s.logs, { timestamp: formatTimestamp(), message: `✗ ${td('启动失败')}: ${msg}`, type: 'error' as const }],
      }));
    }
  },

  executePreflightCheck: async (workflowId: string) => {
    return pipelineApi.preflight(workflowId);
  },

  pollExecutionStatus: () => {
    const { stopPolling, executionId, _workflowId } = get();
    if (!executionId || !_workflowId) return;
    stopPolling();

    const timer = setInterval(async () => {
      const state = get();
      if (!state.executionId || !state._workflowId) {
        state.stopPolling();
        return;
      }
      try {
        const resp = await pipelineApi.getExecutionStatus(state._workflowId, state.executionId);
        const nodeStatuses: Record<string, NodeExecutionStatus> = {};
        if (resp.node_results) {
          for (const [nid, nr] of Object.entries(resp.node_results as Record<string, any>)) {
            nodeStatuses[nid] = {
              nodeId: nid,
              operatorId: nr.operator_id || '',
              label: nr.label || nid,
              status: nr.status === 'success' ? 'completed' : nr.status === 'failed' ? 'failed' : nr.status === 'running' ? 'running' : 'waiting',
              duration: nr.execution_time,
              error: nr.error,
            };
          }
        }
        const newLogs: PipelineLogEntry[] = (resp.logs || []).map((l: any) => ({
          timestamp: l.timestamp || '',
          message: l.message || '',
          type: l.type || 'info',
          nodeId: l.node_id,
        }));
        set({
          nodeStatuses,
          logs: newLogs.length > 0 ? newLogs : state.logs,
        });

        if (resp.status === 'success' || resp.status === 'failed') {
          state.stopPolling();
          const record: ExecutionRecord = {
            executionId: state.executionId!,
            templateName: td(resp.template_name || '流水线'),
            templateType: resp.template_type || 'training',
            status: resp.status as ExecutionStatus,
            modelId: resp.result?.model_id,
            totalDuration: resp.total_duration,
            nodeConfigs: {},
            globalConfig: state.globalConfig,
            createdAt: new Date().toISOString(),
          };

          const updates: Partial<PipelineExecutionStore> = {
            executionStatus: resp.status as ExecutionStatus,
            isExecuting: false,
            backtestProgress: null,
          };

          if (resp.result?.training) {
            (updates as any).trainingResult = resp.result.training;
          }
          if (resp.result?.prediction) {
            (updates as any).predictionResult = resp.result.prediction;
          }
          if (resp.result?.backtest) {
            (updates as any).backtestResult = resp.result.backtest;
          }

          set((s) => ({
            ...updates,
            executionHistory: [...s.executionHistory, record],
          } as any));
        }
      } catch {
        // silent retry
      }
    }, 2000);
    set({ _pollingTimer: timer });
  },

  stopPolling: () => {
    const { _pollingTimer } = get();
    if (_pollingTimer) {
      clearInterval(_pollingTimer);
      set({ _pollingTimer: null });
    }
  },

  startBacktest: async (workflowId: string, params) => {
    const { globalConfig } = get();
    const config = { ...globalConfig, run_mode: 'backtest', operate_status: 'backtest' };
    set({ globalConfig: config });
    await get().executePipeline(workflowId);
  },

  updateGlobalConfig: (config) => {
    set((s) => ({ globalConfig: { ...s.globalConfig, ...config } }));
  },

  exportResults: (format: 'csv') => {
    const { predictionResult, backtestResult } = get();
    let csvContent = '';
    if (predictionResult) {
      csvContent = 'timestamp,value\n' +
        predictionResult.forecastTimestamps.map((t, i) => `${t},${predictionResult.forecastValues[i]}`).join('\n');
    } else if (backtestResult) {
      csvContent = 'date,status,duration,point_count\n' +
        backtestResult.dailyResults.map((d) => `${d.date},${d.status},${d.durationSeconds || ''},${d.pointCount || ''}`).join('\n');
    }
    if (csvContent) {
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pipeline_result_${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }
  },

  loadHistoryConfig: (record: ExecutionRecord) => {
    set({ globalConfig: { ...record.globalConfig } });
  },

  setQuickBacktestDays: (days) => {
    const n = Number.isFinite(days) && days >= 1 ? Math.min(30, Math.floor(days)) : 2;
    set({ quickBacktestDays: n });
  },

  reset: () => {
    const { stopPolling } = get();
    stopPolling();
    set({
      executionId: null,
      executionStatus: 'idle',
      nodeStatuses: {},
      pipelinePlannedNodeCount: null,
      logs: [],
      isExecuting: false,
      trainingResult: null,
      predictionResult: null,
      backtestResult: null,
      backtestProgress: null,
      quickBacktestLoading: false,
      pendingResultDrawer: null,
      _workflowId: null,
    });
  },
}),
    {
      name: 'aip-execution-history',
      partialize: (state) => ({ executionHistory: state.executionHistory }),
    }
  )
);
// @AI_GENERATED: end
