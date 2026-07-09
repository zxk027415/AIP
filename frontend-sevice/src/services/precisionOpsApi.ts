/**
 * Precision Ops API Service
 * 精度运营 API 服务
 */

import api from './api';
import type {
  VersionEntry,
  LeaderboardEntry,
  SwitchEvent,
  SlotConfig,
  ProductionRegistryEntry,
  SwitchLogQueryResult,
  PrelaunchItem,
  PrelaunchEnqueueRequest,
  PrelaunchQueueResult,
} from '../types/precision-ops';

const BASE = '/precision-ops';

// 版本管理
export const registerVersion = (slot: string, entry: Partial<VersionEntry>): Promise<VersionEntry> =>
  api.post(`${BASE}/${slot}/versions`, entry);

// 后端返回 {slot, versions: [...]}，解包取 versions 数组
export const listVersions = (slot: string): Promise<VersionEntry[]> =>
  api.get(`${BASE}/${slot}/versions`).then((res: any) => res?.versions ?? res ?? []);

export const updateVersionStatus = (
  slot: string,
  versionTag: string,
  workflowId: string,
  newStatus: string,
): Promise<void> =>
  api.patch(`${BASE}/${slot}/versions/${encodeURIComponent(versionTag)}/status`, {
    workflow_id: workflowId,
    new_status: newStatus,
  });

// 精度监控
// 后端返回 {slot, leaderboard: [...]}，解包取 leaderboard 数组
export const getLeaderboard = (slot: string): Promise<LeaderboardEntry[]> =>
  api.get(`${BASE}/${slot}/leaderboard`).then((res: any) => res?.leaderboard ?? res ?? []);

export const getMetricsHistory = (slot: string, windowDays?: number): Promise<unknown> =>
  api.get(`${BASE}/${slot}/metrics-history`, { params: { window_days: windowDays } });

// 后端返回 {slot, production: {...} | null}，解包取 production 字段
export const getProductionRegistry = (slot: string): Promise<ProductionRegistryEntry | null> =>
  api.get(`${BASE}/${slot}/production`).then((res: any) => res?.production ?? res ?? null);

// 切换操作
export const executeSwitch = (
  slot: string,
  targetWorkflowId: string,
  reason?: string,
): Promise<SwitchEvent> =>
  api.post(`${BASE}/${slot}/switch`, { target_workflow_id: targetWorkflowId, reason: reason ?? '' });

export const rollback = (slot: string): Promise<SwitchEvent> =>
  api.post(`${BASE}/${slot}/rollback`);

export const getSwitchLog = (
  slot: string,
  params?: {
    page?: number;
    page_size?: number;
    trigger_type?: string;
    start_time?: string;
    end_time?: string;
  },
): Promise<SwitchLogQueryResult> =>
  api.get(`${BASE}/${slot}/switch-log`, { params });

// 配置管理
export const getConfig = (slot: string): Promise<SlotConfig> =>
  api.get(`${BASE}/${slot}/config`);

export const updateConfig = (slot: string, updates: Partial<SlotConfig>): Promise<SlotConfig> =>
  api.put(`${BASE}/${slot}/config`, updates);

// 预上线管理

export const getPrelaunchQueue = (slot: string, status?: string): Promise<PrelaunchQueueResult> =>
  api.get(`${BASE}/${slot}/prelaunch`, { params: status ? { status } : {} }).then((res: any) => res ?? { slot, queue: [], total: 0 });

export const enqueuePrelaunch = (slot: string, body: PrelaunchEnqueueRequest): Promise<{ success: boolean; item: PrelaunchItem }> =>
  api.post(`${BASE}/${slot}/prelaunch`, body);

export const graduatePrelaunch = (slot: string, prelaunchId: string): Promise<{ success: boolean; item: PrelaunchItem; switch_event: SwitchEvent | null }> =>
  api.post(`${BASE}/${slot}/prelaunch/${prelaunchId}/graduate`);

export const cancelPrelaunch = (slot: string, prelaunchId: string, reason?: string): Promise<{ success: boolean; item: PrelaunchItem }> =>
  api.post(`${BASE}/${slot}/prelaunch/${prelaunchId}/cancel`, undefined, { params: { reason: reason ?? '' } });
