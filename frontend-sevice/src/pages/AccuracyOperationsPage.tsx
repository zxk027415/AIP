// @AI_GENERATED
/**
 * AccuracyOperationsPage.tsx — 精度运营主页面。
 *
 * 汇合负荷预测的“指标 → 告警 → RCA → 仲裁 → 通道 A → 部署审计”故事线。
 * 支持显式「人工注入劣化」实验控件；不伪造未来真值，不绕过 gap-1。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Row, Select, Space, Typography, message } from 'antd';
import { ExperimentOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import { useAccuracyOperationsStore } from '../stores/accuracyOperationsStore';
import { accuracyOperationsApi } from '../services/accuracyOperationsApi';
import { schedulerTaskApi, type ScheduledTaskSummary } from '../services/deploymentApi';
import ModelLifecycleCard from './accuracy-operations/ModelLifecycleCard';
import MonitoringPanel from './accuracy-operations/MonitoringPanel';
import AlertPanel from './accuracy-operations/AlertPanel';
import RCAReportViewer from './accuracy-operations/RCAReportViewer';
import RecoveryDecisionPanel from './accuracy-operations/RecoveryDecisionPanel';
import DeploymentSwitchLogCard from './accuracy-operations/DeploymentSwitchLogCard';
import LoadForecastStoryRail from './accuracy-operations/LoadForecastStoryRail';
import DegradationExperimentPanel from './accuracy-operations/DegradationExperimentPanel';
import AccuracyTrendChart from './accuracy-operations/AccuracyTrendChart';
import PvFaultStoryRail from './accuracy-operations/PvFaultStoryRail';
import PvFaultPredictionEvidencePanel from './accuracy-operations/PvFaultPredictionEvidencePanel';
import PvFaultSplitModeOpsPanel from './accuracy-operations/PvFaultSplitModeOpsPanel';
import PvFaultWorkspaceShell from '../components/pv-fault/PvFaultWorkspaceShell';
import PvFaultErrorBoundary from '../components/pv-fault/PvFaultErrorBoundary';
import { usePvFaultAccuracyOpsBundle } from '../hooks/usePvFaultAccuracyOpsBundle';
import './accuracy-operations/accuracyOperationsWorkspace.css';
import type { AccuracyAlert, RecoveryDecision } from '../types/accuracy-operations';
// @AI_GENERATED: PV 故障运营分支内联组件
import { trainingWorkspaceApi } from '../services/iterativeLabelingApi';
// @AI_GENERATED: end

const { Title, Text } = Typography;

/** 历史隔离槽位仅保留 URL 兼容，不作为正式运营入口展示。 */
const DEMO_SLOT = 'load_forecast_e2e_demo';
const PRIMARY_SLOT_OPTIONS = [
  { label: 'load_forecast（正式负荷预测）', value: 'load_forecast' },
  // @AI_GENERATED: 光伏故障诊断正式槽位
  { label: 'pv_fault（光伏故障诊断）', value: 'pv_fault' },
  // @AI_GENERATED: end
  { label: 'default（legacy 默认槽）', value: 'default' },
];
const SUPPORTED_SLOT_VALUES = new Set([...PRIMARY_SLOT_OPTIONS.map((option) => option.value), DEMO_SLOT]);

function formatMetric(value: number | null | undefined, suffix = ''): string {
  return value === null || value === undefined ? '暂无数据' : `${value.toFixed(2)}${suffix}`;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '暂无';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

function formatUtcDateTime(value: string | null | undefined): string {
  if (!value) return '暂无';
  const hasTimeZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  const date = new Date(hasTimeZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

const AccuracyOperationsPage: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage();
  const [searchParams, setSearchParams] = useSearchParams();
  const [decision, setDecision] = useState<RecoveryDecision | null>(null);
  const [switchLogRefreshKey, setSwitchLogRefreshKey] = useState(0);
  const [schedulerTasks, setSchedulerTasks] = useState<ScheduledTaskSummary[]>([]);
  const [schedulerLoading, setSchedulerLoading] = useState(false);
  const [schedulerError, setSchedulerError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pvRefreshKey, setPvRefreshKey] = useState(0);
  const {
    currentSlot,
    setCurrentSlot,
    overview,
    alerts,
    selectedAlert,
    setSelectedAlert,
    rcaReport,
    monitoringSnapshot,
    loading,
    error,
    triggerRCA,
    fetchOverview,
    fetchRCAReport,
    triggerDecision,
    fetchAlerts,
    fetchMonitoringSnapshot,
    fetchLifecycle,
  } = useAccuracyOperationsStore();
  const isPvFaultSlot = currentSlot === 'pv_fault';
  const { bundle: pvOpsBundle, loading: pvOpsLoading } = usePvFaultAccuracyOpsBundle(
    currentSlot,
    pvRefreshKey,
    isPvFaultSlot,
  );

  const visibleRcaReport = selectedAlert?.rca_report_id === rcaReport?.rca_report_id
    ? rcaReport
    : null;

  const loadSchedulerTasks = useCallback(async () => {
    setSchedulerLoading(true);
    setSchedulerError(null);
    try {
      const response = await schedulerTaskApi.listScheduledTasks();
      setSchedulerTasks(response.tasks ?? []);
    } catch (err: any) {
      setSchedulerTasks([]);
      setSchedulerError(err?.response?.data?.detail || err?.message || '调度摘要读取失败');
    } finally {
      setSchedulerLoading(false);
    }
  }, []);

  const refreshStory = useCallback(async () => {
    if (currentSlot === 'pv_fault') {
      setPvRefreshKey((key) => key + 1);
      return;
    }
    setRefreshing(true);
    await Promise.all([
      fetchOverview(currentSlot),
      fetchAlerts(currentSlot),
      fetchMonitoringSnapshot(currentSlot),
      fetchLifecycle(currentSlot),
      loadSchedulerTasks(),
    ]);
    setRefreshing(false);
  }, [currentSlot, fetchAlerts, fetchLifecycle, fetchMonitoringSnapshot, fetchOverview, loadSchedulerTasks]);

  useEffect(() => {
    if (currentSlot === 'pv_fault') return;
    void refreshStory();
  }, [refreshStory, currentSlot]);

  useEffect(() => {
    const requestedSlot = searchParams.get('slot');
    if (requestedSlot && SUPPORTED_SLOT_VALUES.has(requestedSlot) && requestedSlot !== currentSlot) {
      setCurrentSlot(requestedSlot);
      setSelectedAlert(null);
      setDecision(null);
    }
  }, [currentSlot, searchParams, setCurrentSlot, setSelectedAlert]);

  const selectedSchedulerTask = useMemo(
    () => schedulerTasks.find((task) => task.slot === currentSlot && task.pipeline === 'load_forecast')
      ?? schedulerTasks.find((task) => task.slot === currentSlot)
      ?? null,
    [currentSlot, schedulerTasks],
  );

  const productionMetrics = overview?.production ?? monitoringSnapshot?.production ?? null;
  const openAlertCount = overview?.open_alert_count ?? alerts.filter((alert) => alert.status !== 'closed').length;
  const activeRecoveryCount = overview?.active_recovery_count ?? (decision && ['pending', 'executing'].includes(decision.status) ? 1 : 0);
  const slotOptions = useMemo(
    () => currentSlot === DEMO_SLOT
      ? [...PRIMARY_SLOT_OPTIONS, { label: 'load_forecast_e2e_demo（历史隔离槽位，非正式主线）', value: DEMO_SLOT, disabled: true }]
      : PRIMARY_SLOT_OPTIONS,
    [currentSlot],
  );

  const handleSlotChange = (slot: string) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('slot', slot);
    setSearchParams(nextParams, { replace: true });
    setCurrentSlot(slot);
    setSelectedAlert(null);
    setDecision(null);
  };

  const handleSelectAlert = async (alert: AccuracyAlert) => {
    setSelectedAlert(alert);
    setDecision(null);
    if (alert.rca_report_id) {
      await fetchRCAReport(alert.rca_report_id, alert.slot);
    }
    if (alert.recovery_decision_id) {
      try {
        const persistedDecision = await accuracyOperationsApi.getRecoveryDecision(
          alert.recovery_decision_id,
          alert.slot,
        );
        setDecision(persistedDecision);
      } catch (err: any) {
        messageApi.warning(err?.response?.data?.detail || err?.message || '恢复决策读取失败，请重新触发仲裁或刷新告警。');
      }
    }
  };

  const handleTriggerRca = async (alert: AccuracyAlert) => {
    const report = await triggerRCA(alert.alert_id, 'manual');
    if (!report) return;
    const nextAlert = { ...alert, rca_report_id: report.rca_report_id, status: 'open' as const };
    setSelectedAlert(nextAlert);
    setDecision(null);
    await fetchAlerts(alert.slot);
    if (report.status === 'succeeded') {
      messageApi.success('RCA 已完成，已定位数据层问题，可查看诊断证据并触发恢复仲裁。');
    } else {
      messageApi.warning(`RCA 状态：${report.status}，请查看详情或重试。`);
    }
  };

  const handleTriggerDecision = async (slot: string, rcaReportId: string) => {
    const nextDecision = await triggerDecision(slot, rcaReportId);
    if (!nextDecision) return;
    setDecision(nextDecision);
    await fetchAlerts(slot);
    messageApi.success(nextDecision.channel === 'shadow_switch' ? '仲裁通过：已生成通道 A 切换建议。' : '仲裁结果为观察通道，请按决策理由继续跟踪。');
  };

  const handleSwitchExecuted = async (updatedDecision: RecoveryDecision) => {
    setDecision(updatedDecision);
    await refreshStory();
    setSwitchLogRefreshKey((value) => value + 1);
    messageApi.success('通道 A 已执行：请查看模型生命周期和部署切换审计确认角色变化。');
  };

  const isPvFault = currentSlot === 'pv_fault';
  const pageClassName = isPvFault
    ? 'accuracy-operations-page accuracy-operations-page--pv'
    : 'accuracy-operations-page';

  const pageBody = (
    <>
      {contextHolder}
      <header className="accuracy-page-header">
        <div className="accuracy-page-heading">
          <Title level={3} className="accuracy-page-title">精度运营</Title>
          <Text className="accuracy-page-subtitle">
            {currentSlot === 'pv_fault'
              ? '查看光伏闭环各阶段状态：新数据、自动预测、预测结果、人工核对、训练集积累与可用模型。'
              : '围绕同一槽位核对调度、真值回填、精度退化、根因分析、恢复仲裁和部署审计。状态只展示已读取证据，不替代真实运行记录。'}
          </Text>
        </div>
        <div className="accuracy-page-actions">
          <Button icon={<ReloadOutlined />} onClick={() => void refreshStory()} loading={isPvFaultSlot ? pvOpsLoading : refreshing}>刷新证据</Button>
          <span className="accuracy-page-actions-label">槽位</span>
          <Select<string>
            value={currentSlot}
            onChange={handleSlotChange}
            options={slotOptions}
            style={{ width: 270 }}
            showSearch
            filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            aria-label="选择操作槽位"
          />
        </div>
      </header>

      <Alert
        type={currentSlot === DEMO_SLOT ? 'info' : currentSlot === 'pv_fault' ? 'info' : 'warning'}
        showIcon
        icon={currentSlot === 'pv_fault' ? <ExperimentOutlined /> : <SafetyCertificateOutlined />}
        message={
          currentSlot === DEMO_SLOT
            ? '历史隔离槽位（非正式主线）'
            : currentSlot === 'pv_fault'
              ? '光伏故障诊断正式链路'
              : '正式链路观测'
        }
        description={
          currentSlot === DEMO_SLOT
            ? '该槽位仅为既有兼容数据保留；不会从正式入口创建或推荐进入，当前不建设虚拟演练能力。'
            : currentSlot === 'pv_fault'
              ? '光伏重训仍需人工确认执行；训练成功后自动切换生产模型，滚动预测默认使用该模型。预测精度只在人工真值回流后计算。'
              : '通道 A 会真实变更当前槽位的生产身份。只有仲裁推荐且经过人工二次确认后，才会执行影子切换。'
        }
      />

      {/* @AI_GENERATED: 光伏分支使用专用运营视图，负荷预测保留原故事线 */}
      {currentSlot === 'pv_fault' ? (
        <>
          <div className="accuracy-story-scroll">
            <PvFaultStoryRail
              slot={currentSlot}
              opsBundle={pvOpsBundle}
              bundleLoading={pvOpsLoading}
              onRefresh={() => setPvRefreshKey((key) => key + 1)}
            />
          </div>
          <div className="pv-section-label">切分模式与精度对比</div>
          <PvFaultSplitModeOpsPanel
            slot={currentSlot}
            opsBundle={pvOpsBundle}
          />
          <div className="pv-section-label">预测证据与样本明细</div>
          <PvFaultPredictionEvidencePanel
            slot={currentSlot}
            opsBundle={pvOpsBundle}
            bundleLoading={pvOpsLoading}
          />
          <div className="pv-section-label">运营总览</div>
          <PvFaultOverviewSection
            slot={currentSlot}
            opsBundle={pvOpsBundle}
            bundleLoading={pvOpsLoading}
          />
        </>
      ) : (
      <>
      <section className="accuracy-overview-grid" aria-label="精度运营总览">
        <div className="accuracy-overview-item">
          <Text className="accuracy-overview-item-label">当前生产版本</Text>
          <Text className="accuracy-overview-item-value">{productionMetrics?.version_tag ?? '暂无生产模型'}</Text>
          <Text className="accuracy-overview-item-detail">{productionMetrics?.workflow_id ?? '等待部署登记'}</Text>
        </div>
        <div className="accuracy-overview-item">
          <Text className="accuracy-overview-item-label">滚动 WMAPE</Text>
          <Text className="accuracy-overview-item-value">{loading.overview ? '读取中' : formatMetric(productionMetrics?.rolling_wmape ?? productionMetrics?.rolling_mape, '%')}</Text>
          <Text className="accuracy-overview-item-detail">{error.overview ? '总览读取失败，请刷新' : '优先用于退化检测'}</Text>
        </div>
        <div className="accuracy-overview-item">
          <Text className="accuracy-overview-item-label">有效周期与真值覆盖</Text>
          <Text className="accuracy-overview-item-value">{productionMetrics?.valid_cycle_count ?? 0} 个周期</Text>
          <Text className="accuracy-overview-item-detail">覆盖率 {formatMetric(productionMetrics?.coverage_rate === null || productionMetrics?.coverage_rate === undefined ? null : productionMetrics.coverage_rate * 100, '%')}</Text>
        </div>
        <div className="accuracy-overview-item">
          <Text className="accuracy-overview-item-label">待处置事件</Text>
          <Text className="accuracy-overview-item-value">{openAlertCount} 告警 / {activeRecoveryCount} 恢复</Text>
          <Text className="accuracy-overview-item-detail">仅统计当前槽位的未关闭事件</Text>
        </div>
      </section>
      <div className="accuracy-story-scroll">
        <LoadForecastStoryRail
          slot={currentSlot}
          schedulerTask={selectedSchedulerTask}
          schedulerLoading={schedulerLoading}
          schedulerError={schedulerError}
          overview={overview}
          monitoringSnapshot={monitoringSnapshot}
          alerts={alerts}
          selectedAlert={selectedAlert}
          decision={decision}
          refreshing={refreshing}
          onRefresh={() => void refreshStory()}
        />
      </div>
      </>
      )}
      {/* @AI_GENERATED: end */}

      {/* @AI_GENERATED: 负荷预测专用模块（模型生命周期、精度监控、告警、RCA、恢复决策、切换审计）在 pv_fault 下隐藏 */}
      {currentSlot !== 'pv_fault' && (
      <>
      <DegradationExperimentPanel
        slot={currentSlot}
        onChanged={() => void refreshStory()}
      />
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={24}><AccuracyTrendChart slot={currentSlot} /></Col>
      </Row>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={24}><ModelLifecycleCard slot={currentSlot} /></Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}><MonitoringPanel slot={currentSlot} /></Col>
        <Col xs={24} lg={12}>
          <AlertPanel
            slot={currentSlot}
            onSelectAlert={handleSelectAlert}
            onTriggerRCA={handleTriggerRca}
            rcaLoading={loading.rca}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} xl={14}>
          {selectedAlert ? (
            <Card size="small" title={<Space><ExperimentOutlined />当前告警</Space>} style={{ marginBottom: 16 }}>
              <Space direction="vertical" size={2}>
                <Text>告警 ID：<Text code>{selectedAlert.alert_id}</Text></Text>
                <Text>退化版本：<Text code>{selectedAlert.workflow_id}@{selectedAlert.version_tag}</Text></Text>
                <Text>
                  基线 / 当前 MAPE：
                  {(selectedAlert.baseline_metric ?? selectedAlert.baseline_mape).toFixed(2)}% /{' '}
                  {(selectedAlert.current_metric ?? selectedAlert.current_rolling_mape).toFixed(2)}%
                  {(selectedAlert.recovery_evidence as { type?: string } | null)?.type === 'experiment_inject'
                    ? `（线上口径；AR 参考 ${selectedAlert.baseline_mape.toFixed(2)}%）`
                    : ''}
                </Text>
                <Text>退化趋势：{selectedAlert.degradation_trend === 'sudden' ? '骤升' : selectedAlert.degradation_trend === 'gradual' ? '渐升' : '持续高位'}；退化幅度 {selectedAlert.degradation_pct.toFixed(2)}%</Text>
                <Text>冷却截止：{formatDateTime(selectedAlert.cooldown_until)}</Text>
                <Text>RCA / 恢复决策：<Text code>{selectedAlert.rca_report_id ?? '未生成'}</Text> / <Text code>{selectedAlert.recovery_decision_id ?? '未生成'}</Text></Text>
              </Space>
            </Card>
          ) : null}
          <RCAReportViewer rcaReport={visibleRcaReport} loading={loading.rca} />
        </Col>
        <Col xs={24} xl={10}>
          <RecoveryDecisionPanel
            decision={decision}
            alert={selectedAlert}
            onTriggerDecision={handleTriggerDecision}
            onSwitchExecuted={handleSwitchExecuted}
          />
        </Col>
      </Row>

      <DeploymentSwitchLogCard slot={currentSlot} refreshKey={switchLogRefreshKey} />
      </>
      )}
      {/* @AI_GENERATED: end */}
    </>
  );

  if (isPvFault) {
    return (
      <PvFaultErrorBoundary title="精度运营（光伏）渲染失败">
        <PvFaultWorkspaceShell as="main" className={pageClassName} aria-label="精度运营页面">
          {pageBody}
        </PvFaultWorkspaceShell>
      </PvFaultErrorBoundary>
    );
  }

  return (
    <main className={pageClassName} aria-label="精度运营页面">
      {pageBody}
    </main>
  );
};

// @AI_GENERATED: 光伏故障诊断运营分支组件 — 展示分类精度、标签分布、置信度和审核进度
const PvFaultOverviewSection: React.FC<{
  slot: string;
  opsBundle?: import('../hooks/usePvFaultAccuracyOpsBundle').PvFaultOpsBundle | null;
  bundleLoading?: boolean;
}> = ({ slot, opsBundle, bundleLoading }) => {
  const [overview, setOverview] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);
  const usingBundle = opsBundle !== undefined;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await trainingWorkspaceApi.getSlotOverview(slot);
      setOverview(data as Record<string, any>);
    } catch {
      setOverview(null);
    } finally {
      setLoading(false);
    }
  }, [slot]);

  useEffect(() => {
    if (usingBundle) {
      setOverview((opsBundle?.overview as Record<string, any> | null) ?? null);
      return;
    }
    void load();
  }, [load, usingBundle, opsBundle]);

  const showLoading = usingBundle ? Boolean(bundleLoading && !opsBundle) : loading && !overview;
  if (showLoading) return <Card loading style={{ marginBottom: 16 }} />;
  if (!overview) return <Alert type="info" message="光伏运营数据暂不可用" style={{ marginBottom: 16 }} />;

  const qm = overview.quality_metrics as Record<string, any> | null;
  const rp = overview.review_progress as Record<string, number> | null;
  const ld = (overview.batch_label_distribution || overview.label_distribution) as Record<string, number> | null;
  const cd = (overview.batch_confidence_distribution || overview.confidence_distribution) as Record<string, number> | null;
  const latestDetail = overview.latest_prediction_detail as Record<string, any> | null;

  return (
    <div className="pv-overview-section" style={{ marginBottom: 16 }}>
      <Card size="small" title="光伏故障诊断总览" style={{ marginBottom: 12 }}>
        <Row gutter={[16, 12]}>
          <Col xs={12} sm={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>当前模型</Text>
            <div><Text code style={{ fontSize: 12 }}>{overview.model_ref ?? '暂无'}</Text></div>
          </Col>
          <Col xs={12} sm={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>已保存结果</Text>
            <div><Text strong>{(overview.prediction_summary as any)?.total_batches ?? 0}</Text> 份</div>
          </Col>
          <Col xs={12} sm={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>最近保存时间</Text>
            <div style={{ fontSize: 12 }}>
              {latestDetail?.created_at
                ? formatUtcDateTime(latestDetail.created_at)
                : '暂无'}
            </div>
          </Col>
          <Col xs={12} sm={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>最近数据日期</Text>
            <div style={{ fontSize: 12 }}>
              {latestDetail?.time_window_min
                ? `${new Date(latestDetail.time_window_min).toLocaleString('zh-CN', { hour12: false })}`
                : '暂无'}
            </div>
          </Col>
          <Col xs={12} sm={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>审核会话</Text>
            <div><Text strong>{rp?.reviewed_sessions ?? 0}</Text> / {rp?.total_sessions ?? 0} 完成</div>
          </Col>
          <Col xs={12} sm={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>审核单元</Text>
            <div><Text strong>{rp?.reviewed_units ?? 0}</Text> / {rp?.total_units ?? 0}</div>
          </Col>
        </Row>
      </Card>

      {qm && (
        <Card size="small" title="分类精度（基于人工核对）" className="pv-metrics-card" style={{ marginBottom: 12 }}>
          <div className="pv-quality-grid">
            <div className="pv-quality-metric">
              <span className="pv-metric-label">Accuracy</span>
              <span className="pv-metric-value">{(qm.accuracy * 100).toFixed(1)}%</span>
            </div>
            <div className="pv-quality-metric">
              <span className="pv-metric-label">Macro Precision</span>
              <span className="pv-metric-value">{(qm.macro_precision * 100).toFixed(1)}%</span>
            </div>
            <div className="pv-quality-metric">
              <span className="pv-metric-label">Macro Recall</span>
              <span className="pv-metric-value">{(qm.macro_recall * 100).toFixed(1)}%</span>
            </div>
            <div className="pv-quality-metric pv-quality-metric--highlight">
              <span className="pv-metric-label">Macro F1</span>
              <span className="pv-metric-value">{(qm.macro_f1 * 100).toFixed(1)}%</span>
            </div>
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: '#8c8c8c' }}>统计样本：{qm.counted_units} 个已审核单元</div>
        </Card>
      )}

      <Row gutter={[12, 12]}>
        {ld && Object.keys(ld).length > 0 && (
          <Col xs={24} sm={12}>
            <Card size="small" title="标签分布（预测）">
              {Object.entries(ld).map(([name, count]) => (
                <div key={name} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 13 }}>
                  <Text>{name}</Text><Text strong>{count as number}</Text>
                </div>
              ))}
            </Card>
          </Col>
        )}
        {cd && (
          <Col xs={24} sm={12}>
            <Card size="small" title="置信度分布">
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 13 }}><Text>高（≥0.8）</Text><Text strong>{cd.high ?? 0}</Text></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 13 }}><Text>中（0.5–0.8）</Text><Text strong>{cd.medium ?? 0}</Text></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 13 }}><Text>低（&lt;0.5）</Text><Text strong>{cd.low ?? 0}</Text></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 13 }}><Text>未知</Text><Text strong>{cd.unknown ?? 0}</Text></div>
            </Card>
          </Col>
        )}
      </Row>
    </div>
  );
};
// @AI_GENERATED: end

export default AccuracyOperationsPage;
// @AI_GENERATED: end
