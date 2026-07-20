// @AI_GENERATED
/**
 * accuracyOperationsApi.ts — 精度运营 API 客户端
 *
 * 封装后端 `/api/accuracy-operations` 下的所有端点，供精度运营页面
 * （AccuracyOperationsPage）及关联子面板消费。
 * 风格与 `deploymentApi.ts` 一致：复用共享 axios 实例 `./api`
 * （baseURL='/api'，响应拦截器已自动 unwrap `response.data`），
 * 因此每个方法直接返回解析后的响应体。
 *
 * 相关 spec：`.kiro/specs/accuracy-operations/`
 *   - Requirements 9.1~9.8（HTTP API 路由）
 *   - Task 12.2 前端 API 客户端创建
 *
 * 端点一览（相对 baseURL '/api'）：
 *   GET  /accuracy-operations/overview                    — 运营总览
 *   GET  /accuracy-operations/alerts                      — 告警列表
 *   POST /accuracy-operations/alerts/{alert_id}/rca       — 触发 RCA
 *   GET  /accuracy-operations/rca/{rca_report_id}         — RCA 报告详情
 *   POST /accuracy-operations/recovery/decide             — 仲裁触发
 *   POST /accuracy-operations/recovery/shadow-switch      — 手动通道A切换
 *   GET  /accuracy-operations/monitoring/snapshot         — 精度监控快照
 *   GET  /accuracy-operations/models/lifecycle            — 生命周期视图
 *   POST /accuracy-operations/alerts/{alert_id}/close     — 关闭告警
 */

import api from './api';
import type {
  AlertStatus,
  RCATriggerType,
  AccuracyAlert,
  RCAReport,
  RecoveryDecision,
  MonitoringSnapshot,
  OverviewResponse,
  AlertsResponse,
  LifecycleResponse,
  RecoveryEvidence,
} from '../types/accuracy-operations';

/**
 * accuracyOperationsApi — 精度运营 API 方法集
 *
 * 所有方法返回 Promise<T>，T 为后端响应体直接映射的类型。
 * axios 实例已配置 baseURL='/api'，此处路径均为相对于 /api 的子路径。
 */
export const accuracyOperationsApi = {
  /**
   * getOverview — 获取运营总览
   *
   * 用途：AccuracyOperationsPage 主页面初始化时调用，获取生产模型当前指标
   *       和告警统计。
   * @param slot — 槽位名称（如 "default"），精度运营的分区键
   */
  getOverview: (slot: string): Promise<OverviewResponse> =>
    api.get('/accuracy-operations/overview', { params: { slot } }),

  /**
   * getAlerts — 获取告警列表
   *
   * 用途：AlertPanel 展示当前 production/shadow 告警，支持按状态过滤。
   * @param slot — 槽位名称（必填）
   * @param status — 告警状态过滤（可选，不传则返回所有状态）
   */
  getAlerts: (slot: string, status?: AlertStatus): Promise<AlertsResponse> => {
    const params: Record<string, string> = { slot };
    if (status !== undefined) params['status'] = status;
    return api.get('/accuracy-operations/alerts', { params });
  },

  /**
   * triggerRCA — 触发根因分析
   *
   * 用途：AlertPanel 中用户点击"触发 RCA"按钮时调用；接口幂等，
   *       冷却期内会返回已有 RCAReport。
   * @param alertId — 告警 ID（格式 alert-{8hex}）
   * @param triggerType — 触发方式（scheduled=定时 / alert=告警驱动 / manual=手动）
   */
  triggerRCA: (alertId: string, triggerType: RCATriggerType): Promise<RCAReport> =>
    api.post(`/accuracy-operations/alerts/${encodeURIComponent(alertId)}/rca`, {
      trigger_type: triggerType,
    }),

  /**
   * getRCAReport — 获取 RCA 报告详情
   *
   * 用途：RCAReportViewer 组件展示完整诊断报告，包含 error_profile、
   *       data_quality_diagnosis、actionable_insights。
   * @param rcaReportId — RCA 报告 ID（格式 rca-{8hex}）
   * @param slot — 槽位名称（用于定位存储目录）
   */
  getRCAReport: (rcaReportId: string, slot: string): Promise<RCAReport> =>
    api.get(`/accuracy-operations/rca/${encodeURIComponent(rcaReportId)}`, {
      params: { slot },
    }),

  /**
   * triggerDecision — 触发恢复仲裁
   *
   * 用途：用户或系统在 RCA 完成后调用，仲裁器根据置信度和影子池状态
   *       选择 shadow_switch 或 observe 通道。
   * @param slot — 槽位名称（必填）
   * @param rcaReportId — 引用的 RCA 报告 ID（必须对应已存在的 RCAReport）
   */
  triggerDecision: (slot: string, rcaReportId: string): Promise<RecoveryDecision> =>
    api.post('/accuracy-operations/recovery/decide', {
      slot,
      rca_report_id: rcaReportId,
    }),

  /**
   * executeShadowSwitch — 手动执行通道A影子切换
   *
   * 用途：ShadowSwitchModal 确认后调用，直接触发影子模型切换为生产。
   * @param slot — 槽位名称（必填）
   * @param shadowWorkflowId — 目标影子模型的 workflow_id（必填）
   * @param decisionId — 关联的恢复决策 ID（必填，确保与仲裁决策联动）
   */
  executeShadowSwitch: (
    slot: string,
    shadowWorkflowId: string,
    decisionId: string,
  ): Promise<RecoveryDecision> =>
    api.post('/accuracy-operations/recovery/shadow-switch', {
      slot,
      shadow_workflow_id: shadowWorkflowId,
      decision_id: decisionId,
    }),

  /**
   * getRecoveryDecision — 获取一条已持久化的恢复决策。
   *
   * 用途：页面刷新或重新选择告警后，按 `recovery_decision_id`（恢复决策 ID）恢复
   * 通道 A / observe（观察）状态；这是只读请求，不会再次触发仲裁。
   */
  getRecoveryDecision: (decisionId: string, slot: string): Promise<RecoveryDecision> =>
    api.get(`/accuracy-operations/recovery/decisions/${encodeURIComponent(decisionId)}`, {
      params: { slot },
    }),

  /**
   * getMonitoringSnapshot — 获取精度监控快照
   *
   * 用途：MonitoringPanel 展示所有形态（生产/影子/预上线）当前 MAPE/MAE，只读。
   * @param slot — 槽位名称（必填）
   */
  getMonitoringSnapshot: (slot: string): Promise<MonitoringSnapshot> =>
    api.get('/accuracy-operations/monitoring/snapshot', { params: { slot } }),

  /**
   * getLifecycle — 获取模型生命周期视图
   *
   * 用途：ModelLifecycleCard 展示四形态生命周期有向图（节点+边）。
   * @param slot — 槽位名称（必填）
   */
  getLifecycle: (slot: string): Promise<LifecycleResponse> =>
    api.get('/accuracy-operations/models/lifecycle', { params: { slot } }),

  /**
   * closeAlert — 关闭告警
   *
   * 用途：用户手动关闭告警时调用，必须提供 recovery_evidence。
   *       关闭前后端会校验 evidence.type ∈ {passed, manual_close}。
   * @param alertId — 告警 ID（格式 alert-{8hex}）
   * @param slot — 槽位名称（用于定位存储目录）
   * @param recoveryEvidence — 恢复证据（type=manual_close 时必填）
   */
  closeAlert: (
    alertId: string,
    slot: string,
    recoveryEvidence: RecoveryEvidence,
  ): Promise<AccuracyAlert> =>
    api.post(`/accuracy-operations/alerts/${encodeURIComponent(alertId)}/close`, {
      slot,
      recovery_evidence: recoveryEvidence,
    }),
};

export default accuracyOperationsApi;
// @AI_GENERATED: end
