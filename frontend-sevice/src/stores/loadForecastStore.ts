// @AI_GENERATED
/**
 * 负荷预测训练 zustand 状态管理 Store
 *
 * 管理场景列表、训练参数、训练状态轮询、日志生成、回测和训练历史。
 */
import { create } from 'zustand';
import i18n from '../i18n';
import { loadForecastApi } from '../services/loadForecastApi';
import type {
  ScenarioConfig,
  TrainingParams,
  TaskStatus,
  TrainingStepInfo,
  TrainingStepName,
  LogEntry,
  TrainingResult,
  BacktestResult,
  TrainingRecord,
  TaskStatusResponse,
} from '../types/load-forecast';
import { TRAINING_STEPS } from '../types/load-forecast';

function stepLabel(name: TrainingStepName): string {
  return i18n.t(`loadForecast.steps.${name}`);
}

function taskTypeLabel(code: string): string {
  const k = `loadForecast.taskTypes.${code}`;
  const translated = i18n.t(k);
  return translated === k ? code : translated;
}

// ===== 纯函数工具：日志生成 =====

/** 获取当前时间戳字符串 HH:MM:SS */
export function formatTimestamp(date: Date = new Date()): string {
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

/** 生成步骤开始日志 */
export function createStartLog(stepLabel: string, timestamp?: string): LogEntry {
  return {
    timestamp: timestamp ?? formatTimestamp(),
    message: i18n.t('loadForecast.store.stepStart', { label: stepLabel }),
    type: 'start',
  };
}

/** 生成步骤完成日志 */
export function createSuccessLog(stepLabel: string, duration: number, timestamp?: string): LogEntry {
  return {
    timestamp: timestamp ?? formatTimestamp(),
    message: i18n.t('loadForecast.store.stepDone', { label: stepLabel, duration: duration.toFixed(2) }),
    type: 'success',
  };
}

/** 生成步骤失败日志 */
export function createErrorLog(stepLabel: string, errorMessage: string, timestamp?: string): LogEntry {
  return {
    timestamp: timestamp ?? formatTimestamp(),
    message: i18n.t('loadForecast.store.stepError', { label: stepLabel, message: errorMessage }),
    type: 'error',
  };
}

/** 生成训练配置摘要日志 */
export function createConfigSummaryLog(params: TrainingParams, timestamp?: string): LogEntry {
  const scenario = taskTypeLabel(params.task_type);
  return {
    timestamp: timestamp ?? formatTimestamp(),
    message: i18n.t('loadForecast.store.configSummary', {
      scenario,
      csv: params.csv_path,
      horizon: params.forecast_horizon,
      granularity: params.time_granularity,
    }),
    type: 'config',
  };
}

// ===== 纯函数工具：步骤状态映射 =====

/** 根据 API 响应映射步骤状态 */
export function mapStepsFromResponse(response: TaskStatusResponse): TrainingStepInfo[] {
  return TRAINING_STEPS.map((step) => {
    const label = stepLabel(step.name);
    if (response.completed_steps.includes(step.name)) {
      return {
        name: step.name,
        label,
        status: 'completed' as const,
        duration: response.step_durations[step.name],
      };
    }
    if (response.current_step === step.name) {
      return {
        name: step.name,
        label,
        status: 'running' as const,
      };
    }
    if (response.error_step === step.name) {
      return {
        name: step.name,
        label,
        status: 'error' as const,
      };
    }
    return {
      name: step.name,
      label,
      status: 'waiting' as const,
    };
  });
}

// ===== Store 接口 =====

interface LoadForecastStore {
  // 场景
  scenarios: ScenarioConfig[];
  scenariosLoading: boolean;
  scenariosError: string | null;
  selectedTaskType: string | null;
  fetchScenarios: () => Promise<void>;
  selectScenario: (taskType: string) => void;

  // 训练
  trainingParams: Partial<TrainingParams>;
  trainingStatus: TaskStatus;
  currentTaskId: string | null;
  steps: TrainingStepInfo[];
  logs: LogEntry[];
  trainingResult: TrainingResult | null;
  isTraining: boolean;
  startTraining: (params: TrainingParams) => Promise<void>;
  pollStatus: () => void;
  stopPolling: () => void;

  // 轮询内部状态
  _pollingTimer: ReturnType<typeof setInterval> | null;
  _pollFailCount: number;
  _pollWarningShown: boolean;

  // 回测
  backtestResult: BacktestResult | null;
  backtestLoading: boolean;
  startBacktest: (params: Partial<TrainingParams>) => Promise<void>;

  // 历史
  trainingHistory: TrainingRecord[];
  loadHistoryParams: (record: TrainingRecord) => void;

  // 重置
  resetTraining: () => void;
}

// ===== 初始步骤状态 =====

function getInitialSteps(): TrainingStepInfo[] {
  return TRAINING_STEPS.map((step) => ({
    name: step.name,
    label: stepLabel(step.name),
    status: 'waiting' as const,
  }));
}

// ===== Store 实现 =====

export const useLoadForecastStore = create<LoadForecastStore>((set, get) => ({
  // ---------- 场景 ----------
  scenarios: [],
  scenariosLoading: false,
  scenariosError: null,
  selectedTaskType: null,

  fetchScenarios: async () => {
    set({ scenariosLoading: true, scenariosError: null });
    try {
      const data = await loadForecastApi.getScenarios();
      set({ scenarios: data.scenarios, scenariosLoading: false });
    } catch (error: any) {
      const msg =
        error.response?.data?.detail ||
        error.message ||
        i18n.t('loadForecast.store.fetchScenariosFailed');
      set({ scenariosError: msg, scenariosLoading: false });
    }
  },

  selectScenario: (taskType: string) => {
    const { scenarios } = get();
    const scenario = scenarios.find((s) => s.task_type === taskType);
    const recommendedConfig: Partial<TrainingParams> = {
      task_type: taskType,
    };
    if (scenario) {
      // 根据场景推荐配置填充默认值
      if (scenario.forecast_horizon_range && scenario.forecast_horizon_range.length > 0) {
        recommendedConfig.forecast_horizon = scenario.forecast_horizon_range[0];
      }
    }
    set({
      selectedTaskType: taskType,
      trainingParams: recommendedConfig,
    });
  },

  // ---------- 训练 ----------
  trainingParams: {},
  trainingStatus: 'idle',
  currentTaskId: null,
  steps: getInitialSteps(),
  logs: [],
  trainingResult: null,
  isTraining: false,

  startTraining: async (params: TrainingParams) => {
    const { stopPolling } = get();
    stopPolling();

    // 重置训练状态
    set({
      trainingStatus: 'pending',
      isTraining: true,
      currentTaskId: null,
      steps: getInitialSteps(),
      logs: [createConfigSummaryLog(params)],
      trainingResult: null,
      trainingParams: params,
      backtestResult: null,
      _pollFailCount: 0,
      _pollWarningShown: false,
    });

    try {
      const response = await loadForecastApi.startTraining(params);
      set({ currentTaskId: response.task_id, trainingStatus: 'running' });

      // 如果后端同步返回了成功结果（短训练场景）
      if (response.status === 'success') {
        const result: TrainingResult = {
          task_id: response.task_id,
          model_id: response.model_id || '',
          total_duration: response.duration_seconds || 0,
          step_durations: {},
          task_type: params.task_type,
          created_at: new Date().toISOString(),
        };

        // 获取最终状态以填充步骤耗时
        try {
          const statusResp = await loadForecastApi.getTaskStatus(response.task_id);
          result.step_durations = statusResp.step_durations;
          const finalSteps = mapStepsFromResponse(statusResp);
          // 生成所有步骤的完成日志
          const completionLogs: LogEntry[] = [];
          for (const step of finalSteps) {
            if (step.status === 'completed' && step.duration != null) {
              completionLogs.push(createSuccessLog(stepLabel(step.name), step.duration));
            }
          }
          set((state) => ({
            steps: finalSteps,
            logs: [...state.logs, ...completionLogs],
          }));
        } catch {
          // 状态查询失败不影响结果展示
        }

        set((state) => ({
          trainingStatus: 'success',
          isTraining: false,
          trainingResult: result,
          trainingHistory: [
            ...state.trainingHistory,
            {
              task_id: result.task_id,
              task_type: params.task_type,
              status: 'success' as TaskStatus,
              model_id: result.model_id,
              total_duration: result.total_duration,
              params,
              created_at: result.created_at,
            },
          ],
        }));
        return;
      }

      // 异步训练：启动轮询
      get().pollStatus();
    } catch (error: any) {
      const errorMsg =
        error.response?.data?.error_message ||
        error.response?.data?.detail ||
        error.message ||
        i18n.t('loadForecast.store.trainStartFailed');
      set((state) => ({
        trainingStatus: 'failed',
        isTraining: false,
        logs: [
          ...state.logs,
          createErrorLog(i18n.t('loadForecast.store.launchStep'), errorMsg),
        ],
      }));
    }
  },

  // ---------- 轮询 ----------
  _pollingTimer: null,
  _pollFailCount: 0,
  _pollWarningShown: false,

  pollStatus: () => {
    const { stopPolling, currentTaskId } = get();
    if (!currentTaskId) return;

    stopPolling();

    // 记录上一次已知的步骤状态，用于检测变更并生成日志
    let previousCompletedSteps: string[] = [];
    let previousCurrentStep: string | null = null;

    const timer = setInterval(async () => {
      const state = get();
      if (!state.currentTaskId) {
        state.stopPolling();
        return;
      }

      try {
        const statusResp = await loadForecastApi.getTaskStatus(state.currentTaskId);

        // 重置失败计数
        set({ _pollFailCount: 0, _pollWarningShown: false });

        const newSteps = mapStepsFromResponse(statusResp);

        // @AI_GENERATED
        // 使用后端返回的日志（如果有）
        const backendLogs: LogEntry[] = (statusResp as any).logs || [];
        if (backendLogs.length > 0) {
          const configLog = get().logs.find((l) => l.type === 'config');
          const mergedLogs = configLog ? [configLog, ...backendLogs] : backendLogs;
          set({ steps: newSteps, logs: mergedLogs });
        } else {
          const newLogs: LogEntry[] = [];
          // 检测新开始的步骤
          if (statusResp.current_step && statusResp.current_step !== previousCurrentStep) {
            const stepDef = TRAINING_STEPS.find((s) => s.name === statusResp.current_step);
            if (stepDef) {
              newLogs.push(createStartLog(stepLabel(stepDef.name)));
            }
          }
          // 检测新完成的步骤
          for (const stepName of statusResp.completed_steps) {
            if (!previousCompletedSteps.includes(stepName)) {
              const stepDef = TRAINING_STEPS.find((s) => s.name === stepName);
              const duration = statusResp.step_durations[stepName] ?? 0;
              if (stepDef) {
                newLogs.push(createSuccessLog(stepLabel(stepDef.name), duration));
              }
            }
          }
          if (newLogs.length > 0) {
            set((prev) => ({
              steps: newSteps,
              logs: [...prev.logs, ...newLogs],
            }));
          } else {
            set({ steps: newSteps });
          }
        }
        // @AI_GENERATED: end

        previousCompletedSteps = [...statusResp.completed_steps];
        previousCurrentStep = statusResp.current_step;

        // 训练成功
        if (statusResp.status === 'success') {
          state.stopPolling();
          const result: TrainingResult = {
            task_id: statusResp.task_id,
            model_id: statusResp.result?.model_id || '',
            total_duration: statusResp.total_duration,
            step_durations: statusResp.step_durations,
            task_type: statusResp.task_type,
            created_at: statusResp.created_at,
          };
          set((prev) => ({
            trainingStatus: 'success',
            isTraining: false,
            trainingResult: result,
            trainingHistory: [
              ...prev.trainingHistory,
              {
                task_id: result.task_id,
                task_type: result.task_type,
                status: 'success' as TaskStatus,
                model_id: result.model_id,
                total_duration: result.total_duration,
                params: prev.trainingParams as Partial<TrainingParams>,
                created_at: result.created_at,
              },
            ],
          }));
          return;
        }

        // 训练失败
        if (statusResp.status === 'failed') {
          state.stopPolling();
          set((prev) => ({
            trainingStatus: 'failed',
            isTraining: false,
            trainingHistory: [
              ...prev.trainingHistory,
              {
                task_id: statusResp.task_id,
                task_type: statusResp.task_type,
                status: 'failed' as TaskStatus,
                total_duration: statusResp.total_duration,
                params: prev.trainingParams as Partial<TrainingParams>,
                created_at: statusResp.created_at,
              },
            ],
          }));
          return;
        }

        // 正常更新（步骤和日志已在上面的 backendLogs 分支中更新）
      } catch {
        // 轮询容错
        const failCount = get()._pollFailCount + 1;
        set({ _pollFailCount: failCount });

        if (failCount >= 10) {
          // 连续 10 次失败：停止轮询
          get().stopPolling();
          set((prev) => ({
            isTraining: false,
            logs: [
              ...prev.logs,
              {
                timestamp: formatTimestamp(),
                message: i18n.t('loadForecast.store.pollStopped'),
                type: 'error' as const,
              },
            ],
          }));
        } else if (failCount >= 3 && !get()._pollWarningShown) {
          // 连续 3 次失败：展示警告
          set((prev) => ({
            _pollWarningShown: true,
            logs: [
              ...prev.logs,
              {
                timestamp: formatTimestamp(),
                message: i18n.t('loadForecast.store.pollRetry'),
                type: 'info' as const,
              },
            ],
          }));
        }
        // 单次失败：静默重试（不做任何处理）
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

  // ---------- 回测 ----------
  backtestResult: null,
  backtestLoading: false,

  startBacktest: async (backtestOverrides: Partial<TrainingParams>) => {
    const { trainingParams } = get();
    set({ backtestLoading: true, backtestResult: null });

    // 合并训练参数和回测覆盖参数
    const params = {
      task_type: trainingParams.task_type || '',
      csv_path: trainingParams.csv_path || '',
      parent_id: trainingParams.parent_id || '',
      child_id: trainingParams.child_id || '',
      forecast_horizon: trainingParams.forecast_horizon || 1,
      time_granularity: trainingParams.time_granularity || '15min',
      separate_modeling: trainingParams.separate_modeling || 'true',
      forecast_start_time: trainingParams.forecast_start_time || '00:15',
      start_date: (backtestOverrides as any).start_date || '',
      end_date: (backtestOverrides as any).end_date || '',
      // 继承可选参数
      ...(trainingParams.table_name && { table_name: trainingParams.table_name }),
      ...(trainingParams.parent_field && { parent_field: trainingParams.parent_field }),
      ...(trainingParams.child_field && { child_field: trainingParams.child_field }),
      ...(trainingParams.time_field && { time_field: trainingParams.time_field }),
      ...(trainingParams.load_field && { load_field: trainingParams.load_field }),
      ...(trainingParams.time_zone && { time_zone: trainingParams.time_zone }),
      ...(trainingParams.other_cols && { other_cols: trainingParams.other_cols }),
      ...(trainingParams.specify_model && { specify_model: trainingParams.specify_model }),
    };

    try {
      const response = await loadForecastApi.startBacktest(params);
      // @AI_GENERATED
      // 回测现在是异步的，需要轮询等待结果
      const btTaskId = (response as any).task_id;
      if (!btTaskId) {
        // 兼容同步返回的情况
        set({ backtestResult: response as any, backtestLoading: false });
        return;
      }
      // 轮询回测状态
      const pollBacktest = setInterval(async () => {
        try {
          const status = await loadForecastApi.getTaskStatus(btTaskId);
          if (status.status === 'success') {
            clearInterval(pollBacktest);
            set({ backtestResult: status.result as any, backtestLoading: false });
          } else if (status.status === 'failed') {
            clearInterval(pollBacktest);
            set((prev) => ({
              backtestLoading: false,
              logs: [
                ...prev.logs,
                {
                  timestamp: formatTimestamp(),
                  message: i18n.t('loadForecast.store.backtestFail', {
                    message: status.error_message || i18n.t('loadForecastTraining.unknownError'),
                  }),
                  type: 'error' as const,
                },
              ],
            }));
          }
        } catch {
          // 静默重试
        }
      }, 3000);
      // @AI_GENERATED: end
    } catch (error: any) {
      const errorMsg =
        error.response?.data?.error_message ||
        error.response?.data?.detail ||
        error.message ||
        i18n.t('loadForecast.store.backtestStartFailed');
      set((prev) => ({
        backtestLoading: false,
        logs: [
          ...prev.logs,
          {
            timestamp: formatTimestamp(),
            message: i18n.t('loadForecast.store.backtestFail', { message: errorMsg }),
            type: 'error' as const,
          },
        ],
      }));
    }
  },

  // ---------- 历史 ----------
  trainingHistory: [],

  loadHistoryParams: (record: TrainingRecord) => {
    set({
      trainingParams: { ...record.params },
      selectedTaskType: record.task_type,
    });
  },

  // ---------- 重置 ----------
  resetTraining: () => {
    const { stopPolling } = get();
    stopPolling();
    set({
      trainingStatus: 'idle',
      currentTaskId: null,
      steps: getInitialSteps(),
      logs: [],
      trainingResult: null,
      isTraining: false,
      backtestResult: null,
      backtestLoading: false,
      _pollFailCount: 0,
      _pollWarningShown: false,
    });
  },
}));
// @AI_GENERATED: end
