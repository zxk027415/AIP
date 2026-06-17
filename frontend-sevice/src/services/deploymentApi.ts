// @AI_GENERATED: Kiro v1.0
/**
 * 算法部署上线系统 API 服务
 */
import type {
  DeploymentTask,
  DeployedService,
  ServiceMetricPoint,
  AlertRule,
  AlertHistoryItem,
  AccessLog,
  DeploymentStats,
  DeployConfig,
  ReleaseStrategy,
} from '../types/deployment';

const API_BASE = '/api/deployment';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const deploymentApi = {
  // Stats
  getStats: () => request<DeploymentStats>(`${API_BASE}/stats`),

  // Task CRUD
  listTasks: (params?: { scenario?: string; status?: string; source_type?: string; page?: number; page_size?: number }) => {
    const sp = new URLSearchParams();
    if (params?.scenario) sp.set('scenario', params.scenario);
    if (params?.status) sp.set('status', params.status);
    if (params?.source_type) sp.set('source_type', params.source_type);
    if (params?.page) sp.set('page', String(params.page));
    if (params?.page_size) sp.set('page_size', String(params.page_size));
    return request<{ total: number; items: DeploymentTask[] }>(`${API_BASE}/tasks?${sp}`);
  },
  getTask: (id: string) => request<DeploymentTask>(`${API_BASE}/tasks/${id}`),
  createTask: (data: {
    name: string; description: string; scenario: string;
    source_type: string; source_id: string; source_name: string;
    backtest_task_id?: string; backtest_rank?: number;
    deploy_config: DeployConfig; release_strategy: ReleaseStrategy;
  }) => request<DeploymentTask>(`${API_BASE}/tasks`, { method: 'POST', body: JSON.stringify(data) }),
  deleteTask: (id: string) => request<{ success: boolean }>(`${API_BASE}/tasks/${id}`, { method: 'DELETE' }),
  cloneTask: (id: string) => request<DeploymentTask>(`${API_BASE}/tasks/${id}/clone`, { method: 'POST' }),
  deployTask: (id: string) => request<{ success: boolean; service_id: string }>(`${API_BASE}/tasks/${id}/deploy`, { method: 'POST' }),

  // Service management
  listServices: () => request<DeployedService[]>(`${API_BASE}/services`),
  getService: (id: string) => request<DeployedService>(`${API_BASE}/services/${id}`),
  startService: (id: string) => request<{ success: boolean }>(`${API_BASE}/services/${id}/start`, { method: 'POST' }),
  stopService: (id: string) => request<{ success: boolean }>(`${API_BASE}/services/${id}/stop`, { method: 'POST' }),
  restartService: (id: string) => request<{ success: boolean }>(`${API_BASE}/services/${id}/restart`, { method: 'POST' }),
  scaleService: (id: string, replicas: number) => request<{ success: boolean }>(`${API_BASE}/services/${id}/scale`, { method: 'PUT', body: JSON.stringify({ replicas }) }),
  rollbackService: (id: string, version: string) => request<{ success: boolean }>(`${API_BASE}/services/${id}/rollback`, { method: 'POST', body: JSON.stringify({ version }) }),
  getServiceVersions: (id: string) => request<Array<{ version: string; published_at: string; status: string }>>(`${API_BASE}/services/${id}/versions`),
  updateCanary: (id: string, canary_percent: number) => request<{ success: boolean }>(`${API_BASE}/services/${id}/canary`, { method: 'PUT', body: JSON.stringify({ canary_percent }) }),

  // Monitoring
  getServiceMetrics: (id: string, time_range?: string) => {
    const sp = new URLSearchParams();
    if (time_range) sp.set('time_range', time_range);
    return request<ServiceMetricPoint[]>(`${API_BASE}/services/${id}/metrics?${sp}`);
  },
  getServiceLogs: (id: string, page?: number, page_size?: number) => {
    const sp = new URLSearchParams();
    if (page) sp.set('page', String(page));
    if (page_size) sp.set('page_size', String(page_size));
    return request<{ total: number; items: AccessLog[] }>(`${API_BASE}/services/${id}/logs?${sp}`);
  },

  // Alerts
  listAlertRules: () => request<AlertRule[]>(`${API_BASE}/alerts/rules`),
  createAlertRule: (data: Omit<AlertRule, 'id'>) => request<AlertRule>(`${API_BASE}/alerts/rules`, { method: 'POST', body: JSON.stringify(data) }),
  updateAlertRule: (id: string, data: Partial<AlertRule>) => request<AlertRule>(`${API_BASE}/alerts/rules/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAlertRule: (id: string) => request<{ success: boolean }>(`${API_BASE}/alerts/rules/${id}`, { method: 'DELETE' }),
  listAlertHistory: (service_id?: string) => {
    const sp = new URLSearchParams();
    if (service_id) sp.set('service_id', service_id);
    return request<AlertHistoryItem[]>(`${API_BASE}/alerts/history?${sp}`);
  },
};
// @AI_GENERATED: end
