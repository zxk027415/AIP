// @AI_GENERATED: Kiro v1.0
/**
 * 算法回测系统 API 服务
 */
import type {
  BacktestTask,
  BacktestRun,
  BacktestResult,
  BacktestStats,
  BacktestMetricsConfig,
  BacktestDatasetRef,
  BacktestAlgorithmRef,
  ResourceQuota,
  ScheduledTask,
  TaskScheduleConfig,
  ScheduleOptimizationResult,
} from '../types/backtest';

const API_BASE = '/api/backtest';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const backtestApi = {
  // Task CRUD
  listTasks: (params?: {
    scenario?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.scenario) sp.set('scenario', params.scenario);
    if (params?.status) sp.set('status', params.status);
    if (params?.page) sp.set('page', String(params.page));
    if (params?.page_size) sp.set('page_size', String(params.page_size));
    return request<{ total: number; items: BacktestTask[] }>(`${API_BASE}/tasks?${sp}`);
  },

  getTask: (id: string) => request<BacktestTask>(`${API_BASE}/tasks/${id}`),

  createTask: (data: {
    name: string;
    description: string;
    scenario_id: string;
    datasets: BacktestDatasetRef[];
    algorithms: BacktestAlgorithmRef[];
    metrics_config: BacktestMetricsConfig;
  }) => request<BacktestTask>(`${API_BASE}/tasks`, { method: 'POST', body: JSON.stringify(data) }),

  deleteTask: (id: string) => request<{ success: boolean }>(`${API_BASE}/tasks/${id}`, { method: 'DELETE' }),

  cloneTask: (id: string) => request<BacktestTask>(`${API_BASE}/tasks/${id}/clone`, { method: 'POST' }),

  // Execution
  executeTask: (id: string) => request<{ success: boolean }>(`${API_BASE}/tasks/${id}/execute`, { method: 'POST' }),

  pauseTask: (id: string) => request<{ success: boolean }>(`${API_BASE}/tasks/${id}/pause`, { method: 'PUT' }),

  cancelTask: (id: string) => request<{ success: boolean }>(`${API_BASE}/tasks/${id}/cancel`, { method: 'PUT' }),

  // Runs
  listRuns: (taskId: string) => request<{ runs: BacktestRun[] }>(`${API_BASE}/tasks/${taskId}/runs`),

  getRun: (taskId: string, runId: string) => request<BacktestRun>(`${API_BASE}/tasks/${taskId}/runs/${runId}`),

  retryRun: (taskId: string, runId: string) =>
    request<{ success: boolean }>(`${API_BASE}/tasks/${taskId}/runs/${runId}/retry`, { method: 'POST' }),

  // Results
  getResults: (taskId: string) => request<BacktestResult>(`${API_BASE}/tasks/${taskId}/results`),

  exportResults: (taskId: string, format: 'csv' = 'csv') => {
    window.open(`${API_BASE}/tasks/${taskId}/results/export?format=${format}`, '_blank');
  },

  // Stats
  getStats: () => request<BacktestStats>(`${API_BASE}/stats`),

  // @AI_GENERATED: Kiro v1.0
  // 智能调度 API
  getResourceQuota: () => request<ResourceQuota>(`${API_BASE}/schedule/quota`),

  updateResourceQuota: (data: Partial<ResourceQuota>) =>
    request<ResourceQuota>(`${API_BASE}/schedule/quota`, { method: 'PUT', body: JSON.stringify(data) }),

  getScheduleQueue: () => request<{
    queue: ScheduledTask[];
    total_tasks: number;
    running_tasks: number;
    queued_tasks: number;
    optimization: ScheduleOptimizationResult;
  }>(`${API_BASE}/schedule/queue`),

  addTaskToSchedule: (taskId: string, config: Partial<TaskScheduleConfig>) =>
    request<{ success: boolean; scheduled_task: ScheduledTask; optimization: ScheduleOptimizationResult }>(
      `${API_BASE}/schedule/tasks/${taskId}`,
      { method: 'POST', body: JSON.stringify(config) }
    ),

  updateTaskSchedule: (taskId: string, config: Partial<TaskScheduleConfig>) =>
    request<{ success: boolean; scheduled_task: ScheduledTask; optimization: ScheduleOptimizationResult }>(
      `${API_BASE}/schedule/tasks/${taskId}`,
      { method: 'PUT', body: JSON.stringify(config) }
    ),

  removeTaskFromSchedule: (taskId: string) =>
    request<{ success: boolean }>(`${API_BASE}/schedule/tasks/${taskId}`, { method: 'DELETE' }),

  optimizeSchedule: () =>
    request<ScheduleOptimizationResult>(`${API_BASE}/schedule/optimize`, { method: 'POST' }),

  startScheduledTask: (taskId: string) =>
    request<{ success: boolean; task: ScheduledTask }>(`${API_BASE}/schedule/tasks/${taskId}/start`, { method: 'POST' }),

  completeScheduledTask: (taskId: string) =>
    request<{ success: boolean }>(`${API_BASE}/schedule/tasks/${taskId}/complete`, { method: 'POST' }),
  // @AI_GENERATED: end
};
