// @AI_GENERATED: algorithm-deployment-refactor 9.1/9.2/9.3 + 阶段3
/**
 * AlgorithmDeploymentPage.tsx — 算法部署统一入口页面（四 Tab）
 *
 * Tab 列表：
 *   1. 模型管理（?tab=model）  — 生产/影子/预上线三区布局，切换/回滚/配置
 *   2. 数据管线（?tab=pipeline）— 管线启停
 *   3. 定时调度（?tab=scheduler）— cron 可编辑可触发
 *   4. 预上线（?tab=prelaunch）  — 入池/观察进度/手动毕业
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Descriptions, Divider, Input, Modal, Progress, Row, Select, Space, Spin, Statistic, Table, Tabs, Tag, Typography, message } from 'antd';
import type { TableColumnsType } from 'antd';
import {
  ApartmentOutlined,
  ClockCircleOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import ModelManagementTab from './deployment/ModelManagementTab';
import PipelineTab from './deployment/PipelineTab';
import SchedulerTab from './deployment/SchedulerTab';
import PrelaunchTab from './deployment/PrelaunchTab';
import PvFaultClassificationMetrics from '../components/pv-fault/PvFaultClassificationMetrics';
import PvFaultWorkspaceShell from '../components/pv-fault/PvFaultWorkspaceShell';
import PvFaultErrorBoundary from '../components/pv-fault/PvFaultErrorBoundary';
import { PV_FAULT_PRIMARY } from '../theme/pvFaultTheme';
import './deployment/algorithmDeploymentWorkspace.css';
// @AI_GENERATED: pv_fault 专用部署视图依赖
import { cumulativeTrainingApi } from '../services/iterativeLabelingApi';
// @AI_GENERATED: end

const { Title, Paragraph } = Typography;

interface LabelWaveform {
  label_id: number;
  label_name: string;
  timestamps: string[];
  series: Record<string, Array<number | null>>;
  point_count: number;
}

const formatDeploymentTime = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
};

const retrainStatusTag = (status?: string) => {
  if (status === 'completed') return <Tag color="success">已完成</Tag>;
  if (status === 'queued') return <Tag color="processing">等待执行</Tag>;
  if (status === 'running') return <Tag color="processing">训练中</Tag>;
  if (status === 'failed') return <Tag color="error">失败</Tag>;
  if (status === 'cancelled') return <Tag>已取消</Tag>;
  return <Tag>{status || '未知'}</Tag>;
};

type TabKey = 'model' | 'pipeline' | 'scheduler' | 'prelaunch';
const VALID_TABS: readonly TabKey[] = ['model', 'pipeline', 'scheduler', 'prelaunch'] as const;
const DEFAULT_TAB: TabKey = 'model';

// @AI_GENERATED: 部署页槽位选项和受控选择器
const DEPLOYMENT_SLOT_OPTIONS = [
  { label: 'load_forecast（负荷预测）', value: 'load_forecast' },
  { label: 'pv_fault（光伏故障诊断）', value: 'pv_fault' },
  { label: 'default（默认）', value: 'default' },
];
// @AI_GENERATED: end

const AlgorithmDeploymentPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // @AI_GENERATED: 槽位受控 — URL ?slot= 参数驱动
  const storySlot = searchParams.get('slot')?.trim() || 'load_forecast';

  const handleSlotChange = (value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('slot', value);
    if (value === 'pv_fault' && next.get('tab') === 'prelaunch') {
      next.set('tab', DEFAULT_TAB);
    }
    setSearchParams(next, { replace: true });
  };
  // @AI_GENERATED: end

  const activeTab: TabKey = useMemo(() => {
    const raw = searchParams.get('tab');
    const tab = raw && (VALID_TABS as readonly string[]).includes(raw) ? (raw as TabKey) : DEFAULT_TAB;
    if (storySlot === 'pv_fault' && tab === 'prelaunch') {
      return DEFAULT_TAB;
    }
    return tab;
  }, [searchParams, storySlot]);

  useEffect(() => {
    if (storySlot !== 'pv_fault') return;
    if (searchParams.get('tab') === 'prelaunch') {
      const next = new URLSearchParams(searchParams);
      next.set('tab', DEFAULT_TAB);
      setSearchParams(next, { replace: true });
    }
  }, [storySlot, searchParams, setSearchParams]);

  const handleTabChange = (key: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', key);
    setSearchParams(next, { replace: false });
  };

  const isPvFault = storySlot === 'pv_fault';
  const workspaceClass = isPvFault
    ? 'algorithm-deployment-workspace algorithm-deployment-workspace--pv'
    : 'algorithm-deployment-workspace';

  const pageContent = (
    <div className={workspaceClass}>
      <div className="algorithm-deployment-container">
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="deployment-page-header" bordered={false}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <Space align="center" size={12}>
                  <RocketOutlined className="pv-accent-icon" style={{ fontSize: 22, color: isPvFault ? PV_FAULT_PRIMARY : '#1677ff' }} />
                  <Title level={3} style={{ margin: 0 }}>算法部署</Title>
                  <Tag color={isPvFault ? 'orange' : 'blue'}>模型全生命周期管理</Tag>
                </Space>
                {/* @AI_GENERATED: 槽位选择器 */}
                <Space size={8}>
                  <span style={{ fontSize: 13, color: '#64748b' }}>槽位</span>
                  <Select
                    value={storySlot}
                    onChange={handleSlotChange}
                    options={DEPLOYMENT_SLOT_OPTIONS}
                    style={{ width: 240 }}
                    size="middle"
                  />
                </Space>
                {/* @AI_GENERATED: end */}
              </div>
              <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 900 }}>
                按槽位管理模型上线、生产/影子/预上线切换、数据管线和定时调度。
              </Paragraph>
            </Space>
          </Card>

          <Card className="deployment-page-tabs" bordered={false} bodyStyle={{ padding: '8px 16px 16px' }}>
            <Tabs
              key={storySlot}
              activeKey={activeTab}
              onChange={handleTabChange}
              destroyInactiveTabPane={storySlot === 'pv_fault'}
              items={storySlot === 'pv_fault' ? [
                {
                  key: 'model',
                  label: <Space size={6}><DeploymentUnitOutlined />模型状态</Space>,
                  children: <PvFaultDeploymentView />,
                },
                {
                  key: 'pipeline',
                  label: <Space size={6}><ApartmentOutlined />数据管线</Space>,
                  children: <PipelineTab storySlot={storySlot} />,
                },
                {
                  key: 'scheduler',
                  label: <Space size={6}><ClockCircleOutlined />定时调度</Space>,
                  children: <SchedulerTab storySlot={storySlot} />,
                },
              ] : [
                {
                  key: 'model',
                  label: <Space size={6}><DeploymentUnitOutlined />模型管理</Space>,
                  children: <ModelManagementTab storySlot={storySlot} />,
                },
                {
                  key: 'pipeline',
                  label: <Space size={6}><ApartmentOutlined />数据管线</Space>,
                  children: <PipelineTab storySlot={storySlot} />,
                },
                {
                  key: 'scheduler',
                  label: <Space size={6}><ClockCircleOutlined />定时调度</Space>,
                  children: <SchedulerTab storySlot={storySlot} />,
                },
                {
                  key: 'prelaunch',
                  label: <Space size={6}><ExperimentOutlined />预上线</Space>,
                  children: <PrelaunchTab />,
                },
              ]}
            />
          </Card>
        </Space>
      </div>
    </div>
  );

  if (isPvFault) {
    return (
      <PvFaultErrorBoundary title="算法部署（光伏）渲染失败">
        <PvFaultWorkspaceShell>{pageContent}</PvFaultWorkspaceShell>
      </PvFaultErrorBoundary>
    );
  }

  return pageContent;
};

// @AI_GENERATED: 光伏故障诊断部署专用视图 — 模型版本、累计训练、标签、重训
const PvFaultDeploymentView: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState<Record<string, any> | null>(null);
  const [labels, setLabels] = useState<Array<Record<string, any>>>([]);
  const [retrainRunning, setRetrainRunning] = useState(false);
  const [lastTrainResult, setLastTrainResult] = useState<Record<string, any> | null>(null);
  const [selectedRetrainId, setSelectedRetrainId] = useState<string | null>(null);
  // @AI_GENERATED: 下次重训的切分策略选择器状态（默认 by_day，A/B 验证最优）
  const [nextSplitMode, setNextSplitMode] = useState<string>(
    () => String((state as any)?.split_mode || 'by_day')
  );
  // @AI_GENERATED: end
  const [waveformOpen, setWaveformOpen] = useState(false);
  const [waveformLoading, setWaveformLoading] = useState(false);
  const [labelWaveforms, setLabelWaveforms] = useState<LabelWaveform[]>([]);
  const [labelRegistrationMode, setLabelRegistrationMode] = useState(false);
  const [reconcileNames, setReconcileNames] = useState<Record<string, string>>({});
  const [reconcileSaving, setReconcileSaving] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ctState, labelsResp] = await Promise.all([
        cumulativeTrainingApi.getState('pv_fault'),
        fetch('/api/iterative-labeling/label-registry?slot=pv_fault').then(r => r.json()),
      ]);
      setState(ctState as Record<string, any>);
      setLabels(labelsResp?.labels ?? []);
      const statePayload = ctState as Record<string, any>;
      setSelectedRetrainId(current => current
        ?? statePayload.production_model?.request_id
        ?? statePayload.latest_completed_retrain?.request_id
        ?? null);
    } catch {
      setState(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const refreshRetrainState = useCallback(async () => {
    try {
      const nextState = await cumulativeTrainingApi.getState('pv_fault');
      setState(nextState as Record<string, any>);
    } catch {
      // 单次轮询失败不终止仍在执行的重训请求，下一轮继续读取。
    }
  }, []);

  useEffect(() => {
    const status = state?.latest_retrain_request?.status;
    if (!retrainRunning && status !== 'running') return undefined;
    void refreshRetrainState();
    const timer = window.setInterval(() => {
      void refreshRetrainState();
    }, 1200);
    return () => window.clearInterval(timer);
  }, [refreshRetrainState, retrainRunning, state?.latest_retrain_request?.status]);

  const handleRetrain = async () => {
    if (state?.latest_retrain_request?.status === 'running') {
      messageApi.warning('重训正在执行中，请等待完成');
      return;
    }
    setRetrainRunning(true);
    try {
      const created = await cumulativeTrainingApi.createManualRetrainRequest('pv_fault', nextSplitMode);
      const requestId = String((created.retrain_request as Record<string, any> | undefined)?.request_id ?? '');
      if (!requestId) {
        throw new Error('无法创建手动重训请求');
      }
      const resp = await cumulativeTrainingApi.runRetrainRequest(
        requestId,
        'pv_fault',
      );
      const trainResult = resp.train_result as Record<string, any>;
      const accuracy = trainResult?.accuracy_record as Record<string, any> | undefined;
      setLastTrainResult(trainResult as Record<string, any>);
      setSelectedRetrainId((resp.request as Record<string, any>)?.request_id ?? requestId);
      const f1 = accuracy?.macro_f1_mean;
      const acc = accuracy?.accuracy_mean;
      messageApi.success(
        f1 != null || acc != null
          ? `重训并切换生产模型完成（切分=${selectedSolarMode || '整天'}）：Macro-F1=${f1 ?? '—'}，Accuracy=${acc ?? '—'}`
          : `重训完成，生产模型已切换为 ${resp.production_model_ref}`,
      );
      await load();
    } catch (err: any) {
      messageApi.error(err?.response?.data?.detail || '重训失败');
    } finally {
      setRetrainRunning(false);
    }
  };

  const handleViewLabelWaveforms = async (registrationMode = false) => {
    const snapshotPath = String(state?.latest_snapshot?.dataset_path ?? '').trim();
    if (!snapshotPath) {
      messageApi.warning('当前没有可读取的训练快照');
      return;
    }
    setLabelRegistrationMode(registrationMode);
    setWaveformOpen(true);
    setWaveformLoading(true);
    try {
      const response = await fetch(
        `/api/iterative-labeling/reference-waveforms?train_csv_path=${encodeURIComponent(snapshotPath)}&slot=pv_fault`,
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || '标签波形加载失败');
      }
      const payload = await response.json();
      setLabelWaveforms(Array.isArray(payload.categories) ? payload.categories : []);
    } catch (error: any) {
      setLabelWaveforms([]);
      messageApi.error(error?.message || '标签波形加载失败');
    } finally {
      setWaveformLoading(false);
    }
  };

  const handleReconcileLabels = async () => {
    const labelsToRegister = missingLabelIds.map(labelId => ({
      label_id: Number(labelId),
      label_name: String(reconcileNames[labelId] ?? '').trim(),
    }));
    const unnamed = labelsToRegister.filter(item => !item.label_name);
    if (unnamed.length > 0) {
      messageApi.warning(`请填写标签 ${unnamed.map(item => item.label_id).join('、')} 的业务名称`);
      return;
    }
    setReconcileSaving(true);
    try {
      const response = await fetch('/api/iterative-labeling/label-registry/reconcile?slot=pv_fault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ labels: labelsToRegister }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || '标签登记失败');
      }
      const registry = await response.json();
      setLabels(Array.isArray(registry.labels) ? registry.labels : []);
      setLabelRegistrationMode(false);
      setReconcileNames({});
      messageApi.success(`缺失标签已登记，注册表已更新为 ${registry.label_space_version}`);
    } catch (error: any) {
      messageApi.error(error?.message || '标签登记失败');
    } finally {
      setReconcileSaving(false);
    }
  };

  if (loading && !state) return <Spin style={{ display: 'block', margin: '60px auto' }} />;

  if (!state) {
    return (
      <div>
        {contextHolder}
        <Alert
          type="warning"
          showIcon
          message="光伏部署数据暂不可用"
          description="请确认后端已启动，或点击刷新后重试。"
          action={
            <Button size="small" onClick={() => void load()}>
              重试
            </Button>
          }
        />
      </div>
    );
  }

  const latestRequest = state.latest_retrain_request;
  const retrainProgress = latestRequest?.progress as Record<string, any> | undefined;
  const retrainPercent = Number(
    retrainProgress?.percent
      ?? (latestRequest?.status === 'completed' ? 100 : latestRequest?.status === 'running' ? 5 : 0),
  );
  const retrainStageLabels: Record<string, string> = {
    queued: '等待执行',
    preparing_snapshot: '校验训练快照',
    training_and_evaluation: '训练与交叉验证',
    registering_model: '登记模型版本',
    promoting_model: '切换生产模型',
    completed: '已完成',
    failed: '执行失败',
  };
  const latestCompleted = state?.latest_completed_retrain as Record<string, any> | undefined;
  const productionModel = state?.production_model as Record<string, any> | undefined;
  const latestSnapshot = state?.latest_snapshot;
  const modelRef = state?.production_model_ref ?? state?.latest_completed_model_ref;
  const trainSummary = (latestCompleted?.train_summary ?? lastTrainResult) as Record<string, any> | undefined;
  const accuracyRecord = trainSummary?.accuracy_record as Record<string, any> | undefined;
  const pendingCount = Number(state?.pending_change_count ?? 0);
  const retrainThreshold = Number(state?.retrain_label_threshold ?? 20);
  const retrainHistory = (state?.retrain_history ?? []) as Array<Record<string, any>>;
  const completedRetrains = retrainHistory.filter(item => item.status === 'completed');
  const newestCompleted = completedRetrains[0];
  const previousCompleted = completedRetrains[1];
  const newestF1 = newestCompleted?.train_summary?.accuracy_record?.macro_f1_mean;
  const previousF1 = previousCompleted?.train_summary?.accuracy_record?.macro_f1_mean;
  const f1Delta =
    newestF1 != null && previousF1 != null && !Number.isNaN(Number(newestF1)) && !Number.isNaN(Number(previousF1))
      ? Number(newestF1) - Number(previousF1)
      : null;
  const selectedRetrain = retrainHistory.find(item => item.request_id === selectedRetrainId)
    ?? productionModel
    ?? latestCompleted
    ?? null;
  const selectedMetrics = selectedRetrain?.train_summary?.accuracy_record as Record<string, any> | undefined;
  const labelNameMap = Object.fromEntries(
    labels.map(item => [String(item.label_id), String(item.label_name ?? `类别 ${item.label_id}`)]),
  );
  const snapshotLabelIds = Object.keys(accuracyRecord?.class_distribution ?? {})
    .sort((left, right) => Number(left) - Number(right));
  const missingLabelIds = snapshotLabelIds.filter(labelId => !labelNameMap[labelId]);
  const historyColumns: TableColumnsType<Record<string, any>> = [
    {
      title: '完成时间',
      key: 'finished_at',
      width: 172,
      render: (_, record) => formatDeploymentTime(record.finished_at ?? record.created_at),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 150,
      render: (status, record) => (
        <Space size={4} wrap>
          {retrainStatusTag(status)}
          {record.is_production && <Tag color="blue">当前生产</Tag>}
        </Space>
      ),
    },
    {
      title: '模型 ID',
      dataIndex: 'model_ref',
      width: 285,
      render: value => value
        ? <Typography.Text code copyable style={{ fontSize: 11 }}>{value}</Typography.Text>
        : '—',
    },
    {
      title: '训练快照',
      key: 'snapshot',
      width: 250,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text code style={{ fontSize: 11 }}>{record.snapshot_id ?? '—'}</Typography.Text>
          <Typography.Text type="secondary">{record.sample_count ?? '—'} 样本 · {record.label_count ?? '—'} 类</Typography.Text>
        </Space>
      ),
    },
    {
      title: 'Macro-F1',
      key: 'macro_f1',
      width: 110,
      render: (_, record) => record.train_summary?.accuracy_record?.macro_f1_mean ?? '—',
    },
    {
      title: 'Accuracy',
      key: 'accuracy',
      width: 110,
      render: (_, record) => record.train_summary?.accuracy_record?.accuracy_mean ?? '—',
    },
    {
      title: '说明',
      key: 'message',
      width: 240,
      ellipsis: true,
      render: (_, record) => record.error
        ?? (record.cancelled_reason === 'superseded_by_newer_snapshot' ? '已由更新的全量快照替代' : '—'),
    },
    {
      title: '请求 ID',
      dataIndex: 'request_id',
      width: 190,
      render: value => <Typography.Text code style={{ fontSize: 11 }}>{value}</Typography.Text>,
    },
  ];

  return (
    <div>
      {contextHolder}
      {productionModel?.status === 'completed' && modelRef && (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 16 }}
          message="当前生产模型已就绪"
          description={(
            <Space direction="vertical" size={4}>
              <span>模型：<Typography.Text code>{modelRef}</Typography.Text></span>
              {accuracyRecord && (
                <span>
                  评估：Macro-F1={accuracyRecord.macro_f1_mean ?? '—'}
                  {accuracyRecord.macro_f1_std != null ? ` ± ${accuracyRecord.macro_f1_std}` : ''}
                  {' '}· Accuracy={accuracyRecord.accuracy_mean ?? '—'}
                  {accuracyRecord.accuracy_std != null ? ` ± ${accuracyRecord.accuracy_std}` : ''}
                </span>
              )}
              {productionModel.snapshot_id && (
                <span>训练快照：<Typography.Text code style={{ fontSize: 11 }}>{productionModel.snapshot_id}</Typography.Text>
                  {productionModel.sample_count != null ? `（${productionModel.sample_count} 样本）` : ''}
                </span>
              )}
              <span>上线时间：{formatDeploymentTime(state?.production_promoted_at)}</span>
              <Typography.Text type="secondary">
                下一次定时预测将自动读取该生产模型，并在预测记录中保存模型 ID。
              </Typography.Text>
            </Space>
          )}
        />
      )}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card size="small" title="当前模型与训练集" bordered>
            <Descriptions column={1} size="small" labelStyle={{ width: 140, color: '#64748b' }}>
              <Descriptions.Item label="生产模型">
                {modelRef ? <Tag color="success">{modelRef}</Tag> : <Tag>暂无模型</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="训练集快照">
                {latestSnapshot?.snapshot_id ? <Typography.Text code style={{ fontSize: 11 }}>{latestSnapshot.snapshot_id}</Typography.Text> : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="快照样本数">{latestSnapshot?.sample_count ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="快照标签类别">{latestSnapshot?.label_count ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="有效真值单元">{state?.effective_labeled_unit_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="距下次自动重训">
                {pendingCount >= retrainThreshold
                  ? <Tag color="processing">已达阈值，将自动重训</Tag>
                  : `${state?.next_retrain_in ?? Math.max(0, retrainThreshold - pendingCount)} 次变更`}
              </Descriptions.Item>
              <Descriptions.Item label="未冻结变更计数">
                {pendingCount}
                <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                  （登记大数据集后若仍有 queued 旧请求，刷新后会自动换新快照）
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="样本策略">
                <Space direction="vertical" size={4}>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>当前模型：</Typography.Text>
                    <Tag color="blue">
                      {String(
                        (latestSnapshot?.sample_strategy as Record<string, any> | undefined)?.split_mode
                        ?? latestSnapshot?.snapshot_mode
                        ?? '未知',
                      )}
                    </Tag>
                  </div>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>下次重训：</Typography.Text>
                    <Tag color="green">{nextSplitMode}</Tag>
                  </div>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    策略随模型 pickle 持久化；可在重训按钮旁切换下次策略。
                  </Typography.Text>
                  <Button
                    size="small"
                    type="link"
                    onClick={() => navigate('/accuracy-operations?slot=pv_fault')}
                  >
                    去精度运营查看待标注队列
                  </Button>
                </Space>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="标签体系"
            bordered
            extra={
              <Space size={8}>
                <Button size="small" onClick={() => void handleViewLabelWaveforms()}>
                  查看标签形态
                </Button>
                {missingLabelIds.length > 0 && (
                  <Button type="primary" size="small" onClick={() => void handleViewLabelWaveforms(true)}>
                    识别并登记 {missingLabelIds.length} 个缺失标签
                  </Button>
                )}
              </Space>
            }
          >
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 6, fontSize: 12 }}>
              标签注册表（{labels.length} 类）
            </Typography.Text>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {labels.length > 0 ? labels.map((l: any) => (
                <Tag key={l.label_id} color="blue" style={{ margin: 0 }}>
                  {l.label_name}（{l.label_id}）
                </Tag>
              )) : <Typography.Text type="secondary">暂无标签</Typography.Text>}
            </div>
            <Divider style={{ margin: '12px 0' }} />
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 6, fontSize: 12 }}>
              当前生产模型训练快照实际类别（{snapshotLabelIds.length || latestSnapshot?.label_count || 0} 类）
            </Typography.Text>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {snapshotLabelIds.length > 0 ? snapshotLabelIds.map(labelId => (
                <Tag key={labelId} color={labelNameMap[labelId] ? 'orange' : 'gold'} style={{ margin: 0 }}>
                  {labelNameMap[labelId] ?? `类别 ${labelId}`}（{labelId}）
                </Tag>
              )) : <Typography.Text type="secondary">暂无快照类别明细</Typography.Text>}
            </div>
            {snapshotLabelIds.length > labels.length && (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 12 }}
                message={`训练快照有 ${snapshotLabelIds.length} 类，但标签注册表只登记了 ${labels.length} 类`}
                description="黄色类别来自训练数据，但缺少业务名称登记；不影响模型识别类别编码，建议后续补齐标签名称。"
              />
            )}
          </Card>

          <Card size="small" title="重训控制" bordered style={{ marginTop: 12 }}>
            <Descriptions column={1} size="small" labelStyle={{ width: 120, color: '#64748b' }}>
              <Descriptions.Item label="重训请求">
                {latestRequest?.request_id ? <Typography.Text code style={{ fontSize: 11 }}>{latestRequest.request_id}</Typography.Text> : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {latestRequest ? retrainStatusTag(latestRequest.status) : <Tag>未创建</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="距下次自动重训">{state?.next_retrain_in ?? '—'} 次变更</Descriptions.Item>
            </Descriptions>
            {latestRequest && (
              <div style={{ marginTop: 12, padding: '12px 14px', borderRadius: 8, background: '#f7f9fc' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 6 }}>
                  <Space size={6}>
                    <Typography.Text strong>执行进度</Typography.Text>
                    <Tag color={
                      latestRequest.status === 'failed'
                        ? 'error'
                        : latestRequest.status === 'completed'
                          ? 'success'
                          : 'processing'
                    }>
                      {retrainStageLabels[String(retrainProgress?.stage ?? latestRequest.status)] ?? '处理中'}
                    </Tag>
                  </Space>
                  <Typography.Text type="secondary">{Math.max(0, Math.min(100, retrainPercent))}%</Typography.Text>
                </div>
                <Progress
                  percent={Math.max(0, Math.min(100, retrainPercent))}
                  status={
                    latestRequest.status === 'failed'
                      ? 'exception'
                      : latestRequest.status === 'completed'
                        ? 'success'
                        : 'active'
                  }
                  showInfo={false}
                  strokeColor={latestRequest.status === 'failed' ? undefined : { from: PV_FAULT_PRIMARY, to: '#FFB366' }}
                />
                <Typography.Text
                  type={latestRequest.status === 'failed' ? 'danger' : 'secondary'}
                  style={{ display: 'block', marginTop: 4, fontSize: 12 }}
                >
                  {retrainProgress?.message
                    ?? latestRequest.error
                    ?? (latestRequest.status === 'queued'
                      ? '已排队，点击「立即执行重训」开始'
                      : '正在读取执行状态')}
                </Typography.Text>
              </div>
            )}
            <div style={{ marginTop: 12, textAlign: 'right' }}>
              <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
                可随时手动重训（例如切换切分模式后）；累计 {retrainThreshold} 次标签变更将自动重训。
              </Typography.Text>
              <Space>
                <Select
                  size="small"
                  value={nextSplitMode}
                  onChange={(v: string) => setNextSplitMode(v)}
                  style={{ width: 150 }}
                  options={[
                    { label: 'by_day（按天）', value: 'by_day' },
                    { label: 'by_day_night（日夜）', value: 'by_day_night' },
                  ]}
                />
                <Button
                  type="primary"
                  loading={retrainRunning}
                  disabled={retrainRunning || latestRequest?.status === 'running'}
                  onClick={handleRetrain}
                >
                  立即执行重训
                </Button>
              </Space>
            </div>
          </Card>
        </Col>
      </Row>

      {previousCompleted && newestCompleted && (
        <Card size="small" title="重训前后 Macro-F1 对照" bordered style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={8}>
              <Statistic
                title={`上一版（${previousCompleted.request_id ?? '—'}）`}
                value={previousF1 ?? '—'}
                precision={typeof previousF1 === 'number' ? 4 : undefined}
              />
            </Col>
            <Col span={8}>
              <Statistic
                title={`当前（${newestCompleted.request_id ?? '—'}）`}
                value={newestF1 ?? '—'}
                precision={typeof newestF1 === 'number' ? 4 : undefined}
              />
            </Col>
            <Col span={8}>
              <Statistic
                title="Δ Macro-F1"
                value={f1Delta ?? '—'}
                precision={typeof f1Delta === 'number' ? 4 : undefined}
                valueStyle={{
                  color:
                    f1Delta == null
                      ? undefined
                      : f1Delta > 0
                        ? '#3f8600'
                        : f1Delta < 0
                          ? '#cf1322'
                          : undefined,
                }}
              />
            </Col>
          </Row>
          {(newestCompleted?.train_summary?.accuracy_record?.confusion_matrix
            || previousCompleted?.train_summary?.accuracy_record?.confusion_matrix) && (
            <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0, fontSize: 12 }}>
              混淆矩阵细节见下方「选中重训」评估区；此处仅对照相邻两次 completed 重训的 Macro-F1。
            </Typography.Paragraph>
          )}
        </Card>
      )}

      <Card size="small" title="重训历史" bordered style={{ marginTop: 16 }}>
        <Table
          rowKey="request_id"
          columns={historyColumns}
          dataSource={retrainHistory}
          size="small"
          scroll={{ x: 1507 }}
          pagination={{ pageSize: 8, showSizeChanger: false, showTotal: total => `共 ${total} 次重训请求` }}
          locale={{ emptyText: '暂无重训记录；手动触发或达到自动重训阈值后会记录在这里。' }}
          rowClassName={record => record.request_id === selectedRetrain?.request_id ? 'ant-table-row-selected' : ''}
          onRow={record => ({
            onClick: () => setSelectedRetrainId(record.request_id),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>
      <Card
        size="small"
        title="重训结果详情"
        extra={selectedRetrain?.model_ref
          ? <Typography.Text code>{selectedRetrain.model_ref}</Typography.Text>
          : undefined}
        bordered
        style={{ marginTop: 16 }}
      >
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          点击上方历史记录切换结果。训练指标来自该次无泄漏重复分层评估，不与预测后的人工核对指标混用。
        </Typography.Paragraph>
        <PvFaultClassificationMetrics
          metrics={selectedMetrics}
          labelNames={labelNameMap}
          emptyText={
            selectedRetrain?.status === 'completed'
              ? '该历史模型完成于指标持久化功能上线前，暂无可恢复的详细评估结果。'
              : '该重训请求尚未成功完成，暂无模型评估结果。'
          }
        />
      </Card>
      <Modal
        title={labelRegistrationMode
          ? `识别并登记缺失标签（${missingLabelIds.length} 类）`
          : `当前训练快照标签形态（${labelWaveforms.length || snapshotLabelIds.length} 类）`}
        open={waveformOpen}
        onCancel={() => {
          setWaveformOpen(false);
          setLabelRegistrationMode(false);
        }}
        footer={labelRegistrationMode ? (
          <Space>
            <Button onClick={() => navigate('/iterative-labeling')}>进入人工打标工作台</Button>
            <Button onClick={() => {
              setWaveformOpen(false);
              setLabelRegistrationMode(false);
            }}>
              取消
            </Button>
            <Button type="primary" loading={reconcileSaving} onClick={() => void handleReconcileLabels()}>
              按原 ID 登记到注册表
            </Button>
          </Space>
        ) : <Button onClick={() => setWaveformOpen(false)}>关闭</Button>}
        width={1200}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="每个类别展示一个代表性设备日窗口"
          description="代表窗口从当前最新训练快照中选取，优先选择理论电流波动最明显的窗口，用于观察类别形态，不代表该类别的全部样本。"
        />
        {labelRegistrationMode && (
          <div style={{ marginBottom: 16, padding: 14, borderRadius: 8, background: '#f6f9fc' }}>
            <Typography.Text strong>填写业务名称</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ margin: '4px 0 12px', maxWidth: '72ch' }}>
              请先对照下方同 ID 的代表波形，再填写来自数据字典或业务人员确认的正式名称。登记会保留原始数字 ID，不会重新编码。
            </Typography.Paragraph>
            <Row gutter={[12, 12]}>
              {missingLabelIds.map(labelId => (
                <Col xs={24} md={12} key={labelId}>
                  <Input
                    addonBefore={`label_${labelId}`}
                    placeholder="输入正式业务名称"
                    value={reconcileNames[labelId] ?? ''}
                    onChange={event => setReconcileNames(current => ({
                      ...current,
                      [labelId]: event.target.value,
                    }))}
                    maxLength={50}
                  />
                </Col>
              ))}
            </Row>
          </div>
        )}
        {waveformLoading ? (
          <div style={{ padding: 80, textAlign: 'center' }}>
            <Spin tip="正在从训练快照提取各类别代表波形…" />
          </div>
        ) : labelWaveforms.length > 0 ? (
          <Row gutter={[12, 12]}>
            {labelWaveforms.map(waveform => (
              <Col xs={24} md={12} xl={8} key={waveform.label_id}>
                <Card
                  size="small"
                  title={
                    <Space size={6}>
                      <Tag color={labelNameMap[String(waveform.label_id)] ? 'blue' : 'gold'}>
                        label_{waveform.label_id}
                      </Tag>
                      <Typography.Text>{labelNameMap[String(waveform.label_id)] ?? waveform.label_name}</Typography.Text>
                    </Space>
                  }
                  extra={<Typography.Text type="secondary" style={{ fontSize: 11 }}>{waveform.point_count} 点</Typography.Text>}
                >
                  <ReactECharts
                    style={{ height: 210 }}
                    option={{
                      animation: false,
                      tooltip: { trigger: 'axis' },
                      legend: { bottom: 0, textStyle: { fontSize: 10 } },
                      grid: { left: 46, right: 12, top: 10, bottom: 48 },
                      xAxis: {
                        type: 'category',
                        data: waveform.timestamps.map(timestamp => {
                          const text = String(timestamp);
                          return text.includes(' ') ? text.split(' ')[1]?.slice(0, 5) : text.slice(11, 16);
                        }),
                        axisLabel: { fontSize: 9, rotate: 35 },
                      },
                      yAxis: { type: 'value', axisLabel: { fontSize: 9 } },
                      series: Object.entries(waveform.series).map(([seriesName, values], index) => ({
                        name: seriesName === 'value' ? '实测电流' : seriesName === 'i_cal' ? '理论电流' : seriesName,
                        type: 'line',
                        data: values,
                        smooth: true,
                        showSymbol: false,
                        lineStyle: { width: 1.5 },
                        itemStyle: { color: index === 0 ? PV_FAULT_PRIMARY : '#fa8c16' },
                      })),
                    }}
                  />
                </Card>
              </Col>
            ))}
          </Row>
        ) : (
          <Alert type="warning" showIcon message="当前快照未提取到可展示的标签波形" />
        )}
      </Modal>
    </div>
  );
};
// @AI_GENERATED: end

export default AlgorithmDeploymentPage;
// @AI_GENERATED: end
