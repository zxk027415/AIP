// @AI_GENERATED
/**
 * accuracyOperationsStore.ts — 精度运营 Zustand 状态管理 Store
 *
 * 管理精度运营页面的全局状态：当前槽位、运营总览、告警列表、选中告警、
 * RCA 报告、精度监控快照、生命周期视图，以及各异步操作的 loading/error 状态。
 *
 * 相关 spec：`.kiro/specs/accuracy-operations/`
 *   - Requirements 10.1~10.5（前端状态管理）
 *   - Task 12.3 Zustand store 创建
 */

import { create } from 'zustand';
import { accuracyOperationsApi } from '../services/accuracyOperationsApi';
import type {
  AlertStatus,
  RCATriggerType,
  AccuracyAlert,
  RCAReport,
  RecoveryDecision,
  MonitoringSnapshot,
  OverviewResponse,
  LifecycleResponse,
} from '../types/accuracy-operations';

// ===========================================================================
// Store 接口定义
// ===========================================================================

interface LoadingState {
  /** overview — 运营总览是否正在加载 */
  overview: boolean;
  /** alerts — 告警列表是否正在加载 */
  alerts: boolean;
  /** rca — RCA 报告是否正在加载/触发 */
  rca: boolean;
  /** snapshot — 精度监控快照是否正在加载 */
  snapshot: boolean;
  /** lifecycle — 生命周期视图是否正在加载 */
  lifecycle: boolean;
}

interface ErrorState {
  /** overview — 运营总览请求错误信息（null 表示无错误） */
  overview: string | null;
  /** alerts — 告警列表请求错误信息 */
  alerts: string | null;
  /** rca — RCA 报告请求错误信息 */
  rca: string | null;
  /** snapshot — 精度监控快照请求错误信息 */
  snapshot: string | null;
  /** lifecycle — 生命周期视图请求错误信息 */
  lifecycle: string | null;
}

interface AccuracyOperationsState {
  // ---------- 数据状态 ----------

  /** currentSlot — 当前操作的槽位名称（如 "default"） */
  currentSlot: string;
  /** overview — 运营总览数据（null 表示尚未加载） */
  overview: OverviewResponse | null;
  /** alerts — 当前加载的告警列表 */
  alerts: AccuracyAlert[];
  /** selectedAlert — 当前选中的告警（用于展示详情/触发 RCA）*/
  selectedAlert: AccuracyAlert | null;
  /** rcaReport — 当前展示的 RCA 报告（null 表示尚未加载） */
  rcaReport: RCAReport | null;
  /** monitoringSnapshot — 精度监控快照（null 表示尚未加载） */
  monitoringSnapshot: MonitoringSnapshot | null;
  /** lifecycle — 模型生命周期视图数据（null 表示尚未加载） */
  lifecycle: LifecycleResponse | null;

  // ---------- 异步操作状态 ----------

  /** loading — 各模块加载状态 */
  loading: LoadingState;
  /** error — 各模块错误信息 */
  error: ErrorState;

  // ---------- 同步 Actions ----------

  /**
   * setCurrentSlot — 切换当前操作槽位
   * @param slot — 槽位名称（如 "default"、"load_forecast"）
   */
  setCurrentSlot: (slot: string) => void;

  /**
   * setSelectedAlert — 设置当前选中的告警
   * @param alert — 选中的 AccuracyAlert，null 表示取消选中
   */
  setSelectedAlert: (alert: AccuracyAlert | null) => void;

  // ---------- 异步 Actions ----------

  /**
   * fetchOverview — 获取运营总览
   * 失败时设置 error.overview，不抛异常。
   * @param slot — 槽位名称
   */
  fetchOverview: (slot: string) => Promise<void>;

  /**
   * fetchAlerts — 获取告警列表
   * 失败时设置 error.alerts，不抛异常。
   * @param slot — 槽位名称
   * @param status — 告警状态过滤（可选，不传则返回所有状态）
   */
  fetchAlerts: (slot: string, status?: AlertStatus) => Promise<void>;

  /**
   * triggerRCA — 触发根因分析
   * 成功时返回 RCAReport 并更新 rcaReport，失败时设置 error.rca 并返回 null。
   * @param alertId — 告警 ID
   * @param triggerType — 触发方式（默认 'manual'）
   */
  triggerRCA: (alertId: string, triggerType?: RCATriggerType) => Promise<RCAReport | null>;

  /**
   * fetchRCAReport — 获取 RCA 报告详情
   * 失败时设置 error.rca，不抛异常。
   * @param rcaReportId — RCA 报告 ID
   * @param slot — 槽位名称
   */
  fetchRCAReport: (rcaReportId: string, slot: string) => Promise<void>;

  /**
   * triggerDecision — 触发恢复仲裁
   * 成功时返回 RecoveryDecision，失败时设置 error.rca 并返回 null。
   * @param slot — 槽位名称
   * @param rcaReportId — 关联的 RCA 报告 ID
   */
  triggerDecision: (slot: string, rcaReportId: string) => Promise<RecoveryDecision | null>;

  /**
   * fetchMonitoringSnapshot — 获取精度监控快照
   * 失败时设置 error.snapshot，不抛异常。
   * @param slot — 槽位名称
   */
  fetchMonitoringSnapshot: (slot: string) => Promise<void>;

  /**
   * fetchLifecycle — 获取模型生命周期视图
   * 失败时设置 error.lifecycle，不抛异常。
   * @param slot — 槽位名称
   */
  fetchLifecycle: (slot: string) => Promise<void>;
}

// ===========================================================================
// 初始状态
// ===========================================================================

const initialLoading: LoadingState = {
  overview: false,
  alerts: false,
  rca: false,
  snapshot: false,
  lifecycle: false,
};

const initialError: ErrorState = {
  overview: null,
  alerts: null,
  rca: null,
  snapshot: null,
  lifecycle: null,
};

// ===========================================================================
// Store 实现
// ===========================================================================

export const useAccuracyOperationsStore = create<AccuracyOperationsState>((set) => ({
  // ---------- 初始数据状态 ----------
  currentSlot: 'default',
  overview: null,
  alerts: [],
  selectedAlert: null,
  rcaReport: null,
  monitoringSnapshot: null,
  lifecycle: null,

  // ---------- 初始异步状态 ----------
  loading: { ...initialLoading },
  error: { ...initialError },

  // ---------- 同步 Actions ----------

  setCurrentSlot: (slot) => set({ currentSlot: slot }),

  setSelectedAlert: (alert) => set({ selectedAlert: alert }),

  // ---------- 异步 Actions ----------

  fetchOverview: async (slot) => {
    set((s) => ({
      loading: { ...s.loading, overview: true },
      error: { ...s.error, overview: null },
    }));
    try {
      const data = await accuracyOperationsApi.getOverview(slot);
      set((s) => ({
        overview: data,
        loading: { ...s.loading, overview: false },
      }));
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        '获取运营总览失败';
      set((s) => ({
        loading: { ...s.loading, overview: false },
        error: { ...s.error, overview: msg },
      }));
    }
  },

  fetchAlerts: async (slot, status) => {
    set((s) => ({
      loading: { ...s.loading, alerts: true },
      error: { ...s.error, alerts: null },
    }));
    try {
      const data = await accuracyOperationsApi.getAlerts(slot, status);
      set((s) => ({
        alerts: data.alerts,
        loading: { ...s.loading, alerts: false },
      }));
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        '获取告警列表失败';
      set((s) => ({
        loading: { ...s.loading, alerts: false },
        error: { ...s.error, alerts: msg },
      }));
    }
  },

  triggerRCA: async (alertId, triggerType = 'manual') => {
    set((s) => ({
      loading: { ...s.loading, rca: true },
      error: { ...s.error, rca: null },
    }));
    try {
      const report = await accuracyOperationsApi.triggerRCA(alertId, triggerType);
      set((s) => ({
        rcaReport: report,
        loading: { ...s.loading, rca: false },
      }));
      return report;
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        '触发 RCA 失败';
      set((s) => ({
        loading: { ...s.loading, rca: false },
        error: { ...s.error, rca: msg },
      }));
      return null;
    }
  },

  fetchRCAReport: async (rcaReportId, slot) => {
    set((s) => ({
      loading: { ...s.loading, rca: true },
      error: { ...s.error, rca: null },
    }));
    try {
      const report = await accuracyOperationsApi.getRCAReport(rcaReportId, slot);
      set((s) => ({
        rcaReport: report,
        loading: { ...s.loading, rca: false },
      }));
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        '获取 RCA 报告失败';
      set((s) => ({
        loading: { ...s.loading, rca: false },
        error: { ...s.error, rca: msg },
      }));
    }
  },

  triggerDecision: async (slot, rcaReportId) => {
    set((s) => ({
      loading: { ...s.loading, rca: true },
      error: { ...s.error, rca: null },
    }));
    try {
      const decision = await accuracyOperationsApi.triggerDecision(slot, rcaReportId);
      set((s) => ({
        loading: { ...s.loading, rca: false },
      }));
      return decision;
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        '触发恢复仲裁失败';
      set((s) => ({
        loading: { ...s.loading, rca: false },
        error: { ...s.error, rca: msg },
      }));
      return null;
    }
  },

  fetchMonitoringSnapshot: async (slot) => {
    set((s) => ({
      loading: { ...s.loading, snapshot: true },
      error: { ...s.error, snapshot: null },
    }));
    try {
      const data = await accuracyOperationsApi.getMonitoringSnapshot(slot);
      set((s) => ({
        monitoringSnapshot: data,
        loading: { ...s.loading, snapshot: false },
      }));
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        '获取精度监控快照失败';
      set((s) => ({
        loading: { ...s.loading, snapshot: false },
        error: { ...s.error, snapshot: msg },
      }));
    }
  },

  fetchLifecycle: async (slot) => {
    set((s) => ({
      loading: { ...s.loading, lifecycle: true },
      error: { ...s.error, lifecycle: null },
    }));
    try {
      const data = await accuracyOperationsApi.getLifecycle(slot);
      set((s) => ({
        lifecycle: data,
        loading: { ...s.loading, lifecycle: false },
      }));
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        '获取生命周期视图失败';
      set((s) => ({
        loading: { ...s.loading, lifecycle: false },
        error: { ...s.error, lifecycle: msg },
      }));
    }
  },
}));

export default useAccuracyOperationsStore;
// @AI_GENERATED: end
