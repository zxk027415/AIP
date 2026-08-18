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
import { Alert, Button, Card, Col, Collapse, Descriptions, Divider, Input, InputNumber, Modal, Progress, Row, Segmented, Select, Space, Spin, Statistic, Table, Tabs, Tag, Typography, message } from 'antd';
import type { TableColumnsType } from 'antd';
import {
  ApartmentOutlined,
  ClockCircleOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  RocketOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import ModelManagementTab from './deployment/ModelManagementTab';
import PipelineTab from './deployment/PipelineTab';
import SchedulerTab from './deployment/SchedulerTab';
import PrelaunchTab from './deployment/PrelaunchTab';
import PvRetrainResultMetrics from '../components/pv-fault/PvRetrainResultMetrics';
import PvFaultWorkspaceShell from '../components/pv-fault/PvFaultWorkspaceShell';
import PvFaultErrorBoundary from '../components/pv-fault/PvFaultErrorBoundary';
import { PvDualPathGovernancePanel } from './PvDualPathConsole';
import { PV_FAULT_PRIMARY } from '../theme/pvFaultTheme';
import './deployment/algorithmDeploymentWorkspace.css';
// @AI_GENERATED: pv_fault 专用部署视图依赖
import { cumulativeTrainingApi } from '../services/iterativeLabelingApi';
import { formatBackendDateTime } from '../utils/datetime';
// @AI_GENERATED: end

const { Title, Paragraph } = Typography;

interface LabelWaveform {
  label_id: number;
  label_name: string;
  timestamps: string[];
  series: Record<string, Array<number | null>>;
  point_count: number;
}

// @AI_GENERATED: 后端时间戳是不带时区的 UTC 裸字符串，直接 new Date 会被当成本地时间，
// 导致完成时间比真实时间早 8 小时（UTC+8）。改用统一工具补 Z 后再转本地。
const formatDeploymentTime = (value?: string) => formatBackendDateTime(value);
// @AI_GENERATED: end

const RETRAIN_PATH_OPTIONS = [
  { value: 'legacy_day', label: '天级 · legacy_day（传统按天）' },
  { value: 'seq_annotation', label: '点级 · seq_annotation（全天 288 点）' },
];

const retrainPathLabel = (path?: string) => {
  if (path === 'seq_annotation') return '点级 · seq_annotation';
  if (path === 'legacy_day') return '天级 · legacy_day';
  return path || '—';
};

// @AI_GENERATED: 重训记录路径与治理原因统一解释
type RetrainPath = 'legacy_day' | 'seq_annotation';

const resolveRetrainPath = (record?: Record<string, any> | null): RetrainPath => {
  const path = String(
    record?.target_modeling_path
      ?? record?.train_summary?.modeling_path
      ?? record?.train_summary?.sample_strategy?.split_mode
      ?? '',
  );
  return path === 'seq_annotation' ? 'seq_annotation' : 'legacy_day';
};

const governanceReasonLabel = (reason?: string | null) => {
  if (reason === 'evaluation_contract_not_comparable') return '评测样本或口径与当前 Champion 不可直接比较';
  if (reason === 'production_contract_failed') return '未通过全天 288 点生产契约';
  if (reason === 'not_strictly_better') return '同口径指标未严格优于当前 Champion';
  if (reason === 'promote_not_requested') return '本次只登记 Challenger，未请求晋升';
  return reason || '未提供原因';
};
// @AI_GENERATED: end

const retrainStatusTag = (status?: string) => {
  if (status === 'completed') return <Tag color="success">已完成</Tag>;
  if (status === 'queued') return <Tag color="processing">等待执行</Tag>;
  if (status === 'running') return <Tag color="processing">训练中</Tag>;
  if (status === 'failed') return <Tag color="error">失败</Tag>;
  if (status === 'cancelled') return <Tag>已取消</Tag>;
  return <Tag>{status || '未知'}</Tag>;
};

type TabKey = 'model' | 'pipeline' | 'scheduler' | 'prelaunch' | 'governance';
const DEFAULT_TAB: TabKey = 'model';
const PV_FAULT_TABS: readonly TabKey[] = ['model', 'pipeline', 'scheduler', 'governance'];
const OTHER_SLOT_TABS: readonly TabKey[] = ['model', 'pipeline', 'scheduler', 'prelaunch'];

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
    const nextTab = next.get('tab');
    if (value === 'pv_fault' && nextTab === 'prelaunch') {
      next.set('tab', DEFAULT_TAB);
    }
    if (value !== 'pv_fault' && nextTab === 'governance') {
      next.set('tab', DEFAULT_TAB);
    }
    setSearchParams(next, { replace: true });
  };
  // @AI_GENERATED: end

  const activeTab: TabKey = useMemo(() => {
    const raw = searchParams.get('tab');
    const allowed = storySlot === 'pv_fault' ? PV_FAULT_TABS : OTHER_SLOT_TABS;
    if (raw && (allowed as readonly string[]).includes(raw)) {
      return raw as TabKey;
    }
    return DEFAULT_TAB;
  }, [searchParams, storySlot]);

  useEffect(() => {
    const raw = searchParams.get('tab');
    const allowed = storySlot === 'pv_fault' ? PV_FAULT_TABS : OTHER_SLOT_TABS;
    if (raw && !(allowed as readonly string[]).includes(raw)) {
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
                {isPvFault
                  ? 'pv_fault 槽位：模型状态看累计训练产物；路径切换、换将、Epoch 与审计在「双路径治理」。通用 Arena 对该槽位只读。'
                  : '按槽位管理模型上线、生产/影子/预上线切换、数据管线和定时调度。'}
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
                {
                  key: 'governance',
                  label: <Space size={6}><SwapOutlined />双路径治理</Space>,
                  children: <PvDualPathGovernancePanel />,
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
  const [resultPath, setResultPath] = useState<RetrainPath>('seq_annotation');
  // @AI_GENERATED: 本次由本页启动的后台重训 request_id。
  // 重训改为后台执行后，需要它把轮询到的状态和「我刚点的那次」对应上，
  // 否则页面上残留的历史 completed 请求会被误判成本次已完成。
  const [retrainJobId, setRetrainJobId] = useState<string | null>(null);
  // 本次手动重训要训哪条路径；缺省跟当前生产主线，显式改成点级也不会改日滚指针。
  const [retrainTargetPath, setRetrainTargetPath] = useState<string>('legacy_day');
  // @AI_GENERATED: 高级选项——训练轮数 / 批次大小覆盖
  const [retrainEpochs, setRetrainEpochs] = useState<number>(100);
  const [retrainBatchSize, setRetrainBatchSize] = useState<number>(32);
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

  // @AI_GENERATED: 重训期间轮询状态。
  // 只要本页启动过后台任务（retrainJobId 非空）或后端有请求处于 running 就持续轮询；
  // 不能只看 running —— 快照冻结阶段状态是 queued/preparing_snapshot，若不轮询进度条不动。
  useEffect(() => {
    const request = state?.latest_retrain_request as Record<string, any> | undefined;
    const status = request?.status;
    // active_job：后端标记「有后台线程正在推进这条请求」。刷新页面后 retrainJobId
    // 会丢，靠它才能继续把快照冻结阶段的进度刷出来。
    const backendBusy = status === 'running' || (status === 'queued' && Boolean(request?.active_job));
    if (!retrainJobId && !backendBusy) return undefined;
    void refreshRetrainState();
    const timer = window.setInterval(() => {
      void refreshRetrainState();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [
    refreshRetrainState,
    retrainJobId,
    state?.latest_retrain_request?.status,
    state?.latest_retrain_request?.active_job,
  ]);

  // @AI_GENERATED: 后台重训终态收敛 —— 只认本页启动的那条 request_id。
  useEffect(() => {
    if (!retrainJobId) return;
    const request = state?.latest_retrain_request as Record<string, any> | undefined;
    if (!request || String(request.request_id ?? '') !== retrainJobId) return;
    const status = String(request.status ?? '');
    if (status !== 'completed' && status !== 'failed' && status !== 'cancelled') return;

    setRetrainJobId(null);
    setRetrainRunning(false);
    if (status === 'completed') {
      const summary = (request.train_summary ?? {}) as Record<string, any>;
      setLastTrainResult(summary);
      const trainedPath = String(
        request.target_modeling_path
        ?? summary.modeling_path
        ?? retrainTargetPath,
      ) as RetrainPath;
      setSelectedRetrainId(retrainJobId);
      setResultPath(trainedPath === 'seq_annotation' ? 'seq_annotation' : 'legacy_day');
      const productionPath = String(state?.modeling_paths?.production_path || 'legacy_day');
      const accuracy = (summary.accuracy_record ?? {}) as Record<string, any>;
      const governance = (summary.pv_registry_governance
        ?? request.pv_registry_governance
        ?? {}) as Record<string, any>;
      const promoted = governance.promotion_status === 'promoted';
      const metric = trainedPath === 'seq_annotation'
        ? `Point-Macro-F1=${accuracy.point_macro_f1 ?? summary.macro_f1_mean ?? '—'}`
        : `Macro-F1=${accuracy.macro_f1_mean ?? summary.macro_f1_mean ?? '—'}`;
      if (trainedPath !== productionPath) {
        messageApi.success(
          `重训完成，已登记到 ${retrainPathLabel(trainedPath)}（${request.model_ref ?? '—'}，${metric}）。`
          + `日滚预测仍走当前主线 ${retrainPathLabel(productionPath)}，不会自动切换；`
          + '要用这条路径做日滚，请到「双路径治理」切主线。',
        );
      } else if (promoted) {
        messageApi.success(
          `重训完成，当前主线 Champion 已更新为 ${request.model_ref ?? '—'}：`
          + `${metric}，Accuracy=${accuracy.point_accuracy ?? accuracy.accuracy_mean ?? summary.accuracy_mean ?? '—'}`,
        );
      } else {
        messageApi.warning(
          `重训完成，但 ${request.model_ref ?? '—'} 仅登记为 Challenger（${metric}）。`
          + `Registry 治理结论：${governanceReasonLabel(String(governance.reason ?? '未晋升'))}；`
          + '定时调度继续使用当前路径 Champion。',
        );
      }
    } else if (status === 'failed') {
      messageApi.error(`重训失败：${request.error ?? '未知原因'}`);
    } else {
      messageApi.warning('重训已被新的重训请求取代');
    }
    void load();
  }, [retrainJobId, state?.latest_retrain_request, state?.modeling_paths?.production_path, retrainTargetPath, load, messageApi]);
  // @AI_GENERATED: end

  // @AI_GENERATED: 改为「启动后台重训 + 轮询进度」。
  // 原实现同步等待 createManualRetrainRequest 再等 runRetrainRequest，两步都远超
  // axios 的 120s 超时（快照冻结实测 660s），浏览器中断后 run 永不被调用，
  // 请求永久停在 queued/0% —— 这正是「点了立即重训没反应」的根因。
  const handleRetrain = async () => {
    const latest = state?.latest_retrain_request as Record<string, any> | undefined;
    if (latest?.status === 'running' || (latest?.status === 'queued' && latest?.active_job)) {
      messageApi.warning('重训正在执行中，请等待完成');
      return;
    }
    setRetrainRunning(true);
    try {
      const productionPath = String(state?.modeling_paths?.production_path || 'legacy_day');
      const resp = await cumulativeTrainingApi.startManualRetrain('pv_fault', retrainTargetPath, { epochs: retrainEpochs, batch_size: retrainBatchSize });
      const requestId = String(
        (resp.request_id as string | undefined)
        ?? (resp.retrain_request as Record<string, any> | undefined)?.request_id
        ?? '',
      );
      if (!requestId) {
        throw new Error('启动重训失败：后端未返回 request_id');
      }
      setRetrainJobId(requestId);
      const mismatch = retrainTargetPath !== productionPath;
      messageApi.info(
        `已启动「${retrainPathLabel(retrainTargetPath)}」后台重训：先冻结累计训练快照再训练，`
        + '耗时通常十几分钟，进度会自动刷新，可离开本页。'
        + `日滚预测仍走当前主线「${retrainPathLabel(productionPath)}」，不会因本次重训自动切换。`
        + (mismatch
          ? '训完后若要用所选路径做日滚，请到「双路径治理」切主线。'
          : ''),
      );
      await refreshRetrainState();
    } catch (err: any) {
      // 后台化后这里只可能是「启动」失败（并发冲突 409 等），不再有超时中断。
      setRetrainRunning(false);
      messageApi.error(err?.response?.data?.detail || err?.message || '启动重训失败');
    }
  };
  // @AI_GENERATED: end

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
    // @AI_GENERATED: 后台化后 preparing_snapshot 是最耗时的阶段（全量拉测量数据冻结快照）
    preparing_snapshot: '冻结训练快照',
    snapshot_ready: '快照已就绪',
    // @AI_GENERATED: end
    training_and_evaluation: '训练与交叉验证',
    registering_model: '登记模型版本',
    promoting_model: '切换生产模型',
    completed: '已完成',
    failed: '执行失败',
    cancelled: '已被新请求取代',
  };
  // @AI_GENERATED: 后台重训进行中的判定 —— 刷新页面后本地 retrainRunning 会丢，
  // 必须依据后端的 active_job 标记，否则用户重复点击只会拿到 409。
  const retrainInFlight = Boolean(
    latestRequest?.status === 'running'
    || (latestRequest?.status === 'queued' && latestRequest?.active_job),
  );
  // @AI_GENERATED: end
  const latestCompleted = state?.latest_completed_retrain as Record<string, any> | undefined;
  const latestSnapshot = state?.latest_snapshot;
  // Registry 是双路径生产模型的唯一治理真相；仅在旧响应没有 modeling_paths 时兼容旧字段。
  const modelingPaths = (state?.modeling_paths ?? {}) as Record<string, any>;
  const registryConfigured = Boolean(modelingPaths.production_path);
  const productionPath = String(modelingPaths.production_path || 'legacy_day') as RetrainPath;
  const productionPathLifecycle = modelingPaths.path_models?.[productionPath] as Record<string, any> | undefined;
  const productionChampion = productionPathLifecycle?.champion as Record<string, any> | undefined;
  const registryProductionModelRef = String(productionChampion?.model_ref ?? productionPathLifecycle?.model_ref ?? '');
  const modelRef = registryConfigured
    ? registryProductionModelRef
    : String(state?.production_model_ref ?? state?.latest_completed_model_ref ?? '');
  const trainSummary = (latestCompleted?.train_summary ?? lastTrainResult) as Record<string, any> | undefined;
  const accuracyRecord = trainSummary?.accuracy_record as Record<string, any> | undefined;
  const pendingCount = Number(state?.pending_change_count ?? 0);
  const retrainThreshold = Number(state?.retrain_label_threshold ?? 20);
  const retrainHistory = (state?.retrain_history ?? []) as Array<Record<string, any>>;
  // @AI_GENERATED: 重训历史、相邻版本对照和选中详情都按 modeling_path 隔离
  const pathRetrainHistory = retrainHistory.filter(item => resolveRetrainPath(item) === resultPath);
  const completedRetrains = pathRetrainHistory.filter(item => item.status === 'completed');
  const newestCompleted = completedRetrains[0];
  const previousCompleted = completedRetrains[1];
  const selectedMetricKey = resultPath === 'seq_annotation' ? 'point_macro_f1' : 'macro_f1_mean';
  const selectedMetricLabel = resultPath === 'seq_annotation' ? 'Point Macro-F1' : 'Macro-F1';
  const newestF1 = newestCompleted?.train_summary?.accuracy_record?.[selectedMetricKey];
  const previousF1 = previousCompleted?.train_summary?.accuracy_record?.[selectedMetricKey];
  const f1Delta =
    newestF1 != null && previousF1 != null && !Number.isNaN(Number(newestF1)) && !Number.isNaN(Number(previousF1))
      ? Number(newestF1) - Number(previousF1)
      : null;
  const selectedRetrain = pathRetrainHistory.find(item => item.request_id === selectedRetrainId)
    ?? newestCompleted
    ?? pathRetrainHistory[0]
    ?? null;
  const selectedTrainSummary = selectedRetrain?.train_summary as Record<string, any> | undefined;
  const pathLifecycle = modelingPaths.path_models?.[resultPath] as Record<string, any> | undefined;
  const pathChampionRef = String(pathLifecycle?.champion?.model_ref ?? pathLifecycle?.model_ref ?? '');
  const isSelectedPathProduction = resultPath === productionPath;
  const selectedGovernance = (selectedRetrain?.train_summary?.pv_registry_governance
    ?? selectedRetrain?.pv_registry_governance) as Record<string, any> | undefined;
  const pathCounts: Record<RetrainPath, number> = {
    legacy_day: retrainHistory.filter(item => resolveRetrainPath(item) === 'legacy_day').length,
    seq_annotation: retrainHistory.filter(item => resolveRetrainPath(item) === 'seq_annotation').length,
  };
  // @AI_GENERATED: end
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
      render: (status, record) => {
        const isChampion = Boolean(pathChampionRef && record.model_ref === pathChampionRef);
        return (
          <Space size={4} wrap>
            {retrainStatusTag(status)}
            {isChampion && <Tag color="gold">路径 Champion</Tag>}
            {isChampion && isSelectedPathProduction && <Tag color="blue">当前生产</Tag>}
          </Space>
        );
      },
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
      title: selectedMetricLabel,
      key: 'macro_f1',
      width: 130,
      render: (_, record) => record.train_summary?.accuracy_record?.[selectedMetricKey] ?? '—',
    },
    {
      title: resultPath === 'seq_annotation' ? 'Point Accuracy' : 'Accuracy',
      key: 'accuracy',
      width: 130,
      render: (_, record) => record.train_summary?.accuracy_record?.[
        resultPath === 'seq_annotation' ? 'point_accuracy' : 'accuracy_mean'
      ] ?? '—',
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
      {modelRef && (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 16 }}
          message="Registry 当前生产 Champion 已就绪"
          description={(
            <Space direction="vertical" size={4}>
              <span>生产路径：<Tag color="blue">{retrainPathLabel(productionPath)}</Tag></span>
              <span>模型：<Typography.Text code copyable>{modelRef}</Typography.Text></span>
              {productionChampion?.gate_metric_value != null && (
                <span>
                  治理指标：{productionChampion.metric_name ?? 'gate_metric'}={productionChampion.gate_metric_value}
                </span>
              )}
              {modelingPaths.active_activation_epoch_id && (
                <span>激活 Epoch：<Typography.Text code>{modelingPaths.active_activation_epoch_id}</Typography.Text></span>
              )}
              {productionChampion?.registered_at && (
                <span>登记时间：{formatDeploymentTime(String(productionChampion.registered_at))}</span>
              )}
              <Typography.Text type="secondary">
                定时调度每次执行都会重新读取 PV Registry，并使用当前生产路径的 Champion；最新完成的 Challenger 不会自动替代它。
              </Typography.Text>
            </Space>
          )}
        />
      )}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card size="small" title="当前主线与最新训练集" bordered>
            <Descriptions column={1} size="small" labelStyle={{ width: 140, color: '#64748b' }}>
              <Descriptions.Item label="Registry 生产模型">
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
              <Descriptions.Item label="训练快照口径">
                <Space direction="vertical" size={4}>
                  <Tag color="blue">
                    {String(latestSnapshot?.snapshot_mode ?? '') === 'seq_annotation'
                      ? '点级路径 · 全天 288 点'
                      : '天级路径 · 每天一个标签'}
                  </Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    下次重训沿用当前生产路径；昼夜切分不再作为独立路径或手动选项。
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
              最近完成重训快照实际类别（{snapshotLabelIds.length || latestSnapshot?.label_count || 0} 类）
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
              <Descriptions.Item label="日滚主线">
                {retrainPathLabel(String(state?.modeling_paths?.production_path || 'legacy_day'))}
              </Descriptions.Item>
              <Descriptions.Item label="最近一次重训路径">
                {retrainPathLabel(String(latestRequest?.target_modeling_path || '—'))}
              </Descriptions.Item>
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
            <div style={{ marginTop: 12 }}>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12, textAlign: 'left' }}
                message="日滚预测始终走当前主线，重训成功不会自动改路径。"
                description={
                  <span>
                    这里只决定本次模型登记到天级还是点级。若所选路径与日滚主线不一致，训完后请到
                    <Typography.Link
                      onClick={() => navigate('/algorithm-deployment?slot=pv_fault&tab=governance')}
                    >
                      双路径治理
                    </Typography.Link>
                    做跨路径切换。累计 {retrainThreshold} 次标签变更仍会按各路径水位自动重训。
                  </span>
                }
              />
              <Space wrap style={{ width: '100%', justifyContent: 'flex-end' }}>
                <Select
                  value={retrainTargetPath}
                  onChange={setRetrainTargetPath}
                  disabled={retrainRunning || retrainInFlight}
                  options={RETRAIN_PATH_OPTIONS}
                  style={{ width: 280 }}
                  aria-label="本次重训路径"
                />
                <Button
                  type="primary"
                  loading={retrainRunning || retrainInFlight}
                  disabled={retrainRunning || retrainInFlight}
                  onClick={handleRetrain}
                >
                  立即执行重训
                </Button>
              </Space>
              {/* @AI_GENERATED */}
              <Collapse
                size="small"
                ghost
                style={{ marginTop: 8 }}
                items={[{
                  key: 'advanced',
                  label: <Typography.Text type="secondary" style={{ fontSize: 12 }}>高级选项</Typography.Text>,
                  children: (
                    <Space size={16} wrap>
                      <Space size={4}>
                        <Typography.Text style={{ fontSize: 12 }}>训练轮数 (epochs):</Typography.Text>
                        <InputNumber
                          size="small"
                          min={1}
                          max={1000}
                          value={retrainEpochs}
                          onChange={(v) => setRetrainEpochs(v ?? 100)}
                          disabled={retrainRunning || retrainInFlight}
                          style={{ width: 80 }}
                        />
                      </Space>
                      <Space size={4}>
                        <Typography.Text style={{ fontSize: 12 }}>批次大小 (batch_size):</Typography.Text>
                        <InputNumber
                          size="small"
                          min={4}
                          max={512}
                          value={retrainBatchSize}
                          onChange={(v) => setRetrainBatchSize(v ?? 32)}
                          disabled={retrainRunning || retrainInFlight}
                          style={{ width: 80 }}
                        />
                      </Space>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        实验室验证建议 epochs=2；生产默认 100。不改则使用服务端环境变量默认值。
                      </Typography.Text>
                    </Space>
                  ),
                }]}
              />
              {/* @AI_GENERATED: end */}
              {retrainTargetPath !== String(state?.modeling_paths?.production_path || 'legacy_day') && (
                <Typography.Text type="warning" style={{ display: 'block', marginTop: 8, fontSize: 12, textAlign: 'right' }}>
                  当前选择与日滚主线不一致：训完后日滚仍走
                  {retrainPathLabel(String(state?.modeling_paths?.production_path || 'legacy_day'))}。
                </Typography.Text>
              )}
            </div>
          </Card>
        </Col>
      </Row>

      {/* @AI_GENERATED: 路径隔离工具栏、同路径对比和 Registry 治理状态 */}
      <div className="pv-path-scope-toolbar">
        <Segmented<RetrainPath>
          value={resultPath}
          options={[
            { value: 'legacy_day', label: `天级 · legacy_day（${pathCounts.legacy_day}）` },
            { value: 'seq_annotation', label: `点级 · seq_annotation（${pathCounts.seq_annotation}）` },
          ]}
          onChange={value => {
            setResultPath(value);
            setSelectedRetrainId(null);
          }}
          aria-label="重训结果建模路径"
        />
        <Space className="pv-path-scope-toolbar__context" size={8} wrap>
          <Tag color={isSelectedPathProduction ? 'blue' : 'default'}>
            {isSelectedPathProduction ? '当前生产路径' : '非生产路径'}
          </Tag>
          <Typography.Text type="secondary">路径 Champion</Typography.Text>
          {pathChampionRef
            ? <Typography.Text className="pv-path-scope-toolbar__model" code copyable>{pathChampionRef}</Typography.Text>
            : <Typography.Text type="secondary">Registry 未登记 Champion</Typography.Text>}
        </Space>
      </div>

      <Card
        size="small"
        title={`${retrainPathLabel(resultPath)} · 同路径${selectedMetricLabel}对照`}
        bordered
        style={{ marginTop: 16 }}
      >
        {previousCompleted && newestCompleted ? (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={8}>
                <Statistic
                  title={`上一版（${previousCompleted.request_id ?? '—'}）`}
                  value={previousF1 ?? '—'}
                  precision={typeof previousF1 === 'number' ? 4 : undefined}
                />
              </Col>
              <Col xs={24} md={8}>
                <Statistic
                  title={`当前（${newestCompleted.request_id ?? '—'}）`}
                  value={newestF1 ?? '—'}
                  precision={typeof newestF1 === 'number' ? 4 : undefined}
                />
              </Col>
              <Col xs={24} md={8}>
                <Statistic
                  title={`Δ ${selectedMetricLabel}`}
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
                混淆矩阵细节见下方选中重训的评估区；此处只比较同一路径相邻两次 completed 重训的 {selectedMetricLabel}。
              </Typography.Paragraph>
            )}
          </>
        ) : (
          <Alert
            type="info"
            showIcon
            message="同路径历史不足，暂不能比较相邻版本"
            description={`${retrainPathLabel(resultPath)} 至少需要两次带评估指标的已完成重训。系统不会拿另一条路径的指标补位比较。`}
          />
        )}
      </Card>

      <Card
        size="small"
        title={`${retrainPathLabel(resultPath)} · 重训历史`}
        bordered
        style={{ marginTop: 16 }}
      >
        <Table
          rowKey="request_id"
          columns={historyColumns}
          dataSource={pathRetrainHistory}
          size="small"
          scroll={{ x: 1507 }}
          pagination={{ pageSize: 8, showSizeChanger: false, showTotal: total => `共 ${total} 次同路径重训请求` }}
          locale={{ emptyText: `${retrainPathLabel(resultPath)} 暂无重训记录；切换上方路径或触发该路径重训后再查看。` }}
          rowClassName={record => record.request_id === selectedRetrain?.request_id ? 'ant-table-row-selected' : ''}
          onRow={record => ({
            onClick: () => setSelectedRetrainId(record.request_id),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>
      <Card
        size="small"
        title={`${retrainPathLabel(resultPath)} · 重训结果详情`}
        extra={selectedRetrain?.model_ref
          ? <Typography.Text code>{selectedRetrain.model_ref}</Typography.Text>
          : undefined}
        bordered
        style={{ marginTop: 16 }}
      >
        {selectedRetrain?.status === 'completed' && selectedRetrain?.model_ref && (
          selectedRetrain.model_ref === pathChampionRef ? (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 12 }}
              message="当前记录是该路径的 Registry Champion"
              description={isSelectedPathProduction
                ? '定时调度读取当前生产路径时会使用此模型。'
                : '该模型是本路径 Champion，但定时调度仍读取另一条生产路径。'}
            />
          ) : (
            <Alert
              type={selectedGovernance?.reason ? 'warning' : 'info'}
              showIcon
              style={{ marginBottom: 12 }}
              message="当前记录不是该路径 Champion"
              description={selectedGovernance?.reason
                ? `Registry 治理结论：${governanceReasonLabel(String(selectedGovernance.reason))}。定时调度不会自动使用此 Challenger。`
                : '该模型未被 Registry 选为本路径 Champion；定时调度不会自动使用它。'}
            />
          )
        )}
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          {resultPath === 'seq_annotation'
            ? '点击上方同路径历史记录切换结果。点级指标来自设备隔离逐点评估，并同时展示生产后处理和设备日投影口径；不与天级 Macro-F1 混比。'
            : '点击上方同路径历史记录切换结果。天级指标来自无泄漏重复分层评估，不与点级逐点评估或预测后的人工核对指标混用。'}
        </Typography.Paragraph>
        <PvRetrainResultMetrics
          modelingPath={resultPath}
          trainSummary={selectedTrainSummary}
          labelNames={labelNameMap}
          emptyText={
            selectedRetrain?.status === 'completed'
              ? '该历史模型完成于指标持久化功能上线前，暂无可恢复的详细评估结果。'
              : '该路径的重训请求尚未成功完成，暂无模型评估结果。'
          }
        />
      </Card>
      {/* @AI_GENERATED: end */}
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
