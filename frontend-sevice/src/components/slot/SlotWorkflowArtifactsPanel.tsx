/**
 * SlotWorkflowArtifactsPanel — G3/G7 最小 slot UI：展示 train/predict 最近 execution 产物。
 * 支持 pv_day / pv_point 产品槽与 benchmark_* 复用槽（benchmark 隐藏治理 UI）。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ApartmentOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import {
  getSlotWorkflowConfig,
  isBenchmarkSlot,
  type SlotWorkflowConfig,
} from '../../config/slotProductConfig';
import { pipelineApi } from '../../services/workflowEnhancedApi';
import { slotGovernanceApi, type ModelCandidateView, type SlotRegistryView } from '../../services/slotGovernanceApi';
import { slotDatasetsApi, type SnapshotChainView } from '../../services/slotDatasetsApi';
import { freezeIdOf, slotCumulativeApi } from '../../services/slotCumulativeApi';
import { timeseriesReplayApi, type PointAlarmSummary } from '../../services/timeseriesReplayApi';

const { Paragraph, Text } = Typography;

const DASHBOARD_CACHE_TTL_MS = 20_000;

function pickList<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === 'object') {
    const nested = (payload as Record<string, unknown>)[key];
    if (Array.isArray(nested)) return nested as T[];
  }
  return [];
}

type DashboardCacheEntry = {
  trainExec: ExecutionSnapshot | null;
  predictExec: ExecutionSnapshot | null;
  registry: SlotRegistryView | null;
  candidates: ModelCandidateView[];
  snapshotChain: SnapshotChainView | null;
  annotationPending: number;
  annotationRows: unknown[];
  reviewedAnnotationIds: string[];
  alarmSummary: PointAlarmSummary | null;
  alarmLoadError: string | null;
};

const dashboardCache = new Map<string, { ts: number; entry: DashboardCacheEntry }>();

type ExecutionSnapshot = {
  workflowId: string;
  templateRole: string;
  status?: string;
  executionId?: string;
  finishedAt?: string;
  startedAt?: string;
  slot?: string;
  modelPath?: string;
  metrics?: Record<string, unknown>;
  error?: string;
  missing?: boolean;
  schedulerTrigger?: boolean;
  triggerSource?: string;
};

function extractArtifacts(nodeResults: Record<string, unknown> | undefined): {
  modelPath?: string;
  metrics: Record<string, unknown>;
} {
  const metrics: Record<string, unknown> = {};
  let modelPath: string | undefined;
  if (!nodeResults) return { metrics };

  for (const node of Object.values(nodeResults)) {
    const summary = (node as { outputSummary?: Record<string, unknown> })?.outputSummary;
    if (!summary || typeof summary !== 'object') continue;
    if (typeof summary.model_path === 'string' && summary.model_path) {
      modelPath = summary.model_path;
    }
    for (const key of [
      'accuracy_mean',
      'macro_f1_mean',
      'point_accuracy',
      'coverage',
      'no_decision_rate',
      'latency_p95_ms',
      'event_f1',
      'replay_session_id',
      'cursor',
      'total',
      'points_processed',
      'point_outcome_kind',
      'point_label',
      'point_confidence',
      'point_reason',
      'replay_status',
      'alarm_phase',
      'active_alarm_id',
    ]) {
      if (summary[key] !== undefined && metrics[key] === undefined) {
        metrics[key] = summary[key];
      }
    }
  }
  return { modelPath, metrics };
}

async function loadRoleExecution(
  config: SlotWorkflowConfig,
  templateRole: string,
): Promise<ExecutionSnapshot> {
  const workflowId =
    templateRole === 'train_eval'
      ? config.trainWorkflowId
      : config.predictWorkflowId;

  const roleParam =
    templateRole === 'train_eval'
      ? 'train_eval'
      : config.predictTemplateRole === 'predict_replay'
        ? 'predict_replay'
        : 'predict';

  try {
    const state = await pipelineApi.getSlotLatestExecution(config.slot, roleParam);
    const { modelPath, metrics } = extractArtifacts(
      state?.nodeResults as Record<string, unknown> | undefined,
    );
    return {
      workflowId,
      templateRole,
      status: state?.status as string | undefined,
      executionId: state?.execution_id as string | undefined,
      finishedAt: state?.finished_at as string | undefined,
      startedAt: state?.started_at as string | undefined,
      slot: (state?.slot as string | undefined) || config.slot,
      modelPath,
      metrics,
      error: state?.error as string | undefined,
      schedulerTrigger: Boolean(state?.scheduler_trigger),
      triggerSource: state?.trigger_source as string | undefined,
    };
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const missing = err?.response?.status === 404;
    return {
      workflowId,
      templateRole,
      missing,
      error: typeof detail === 'string' ? detail : err?.message || '读取失败',
    };
  }
}

async function pollExecution(workflowId: string, executionId: string) {
  const deadline = Date.now() + 15 * 60 * 1000;
  while (Date.now() < deadline) {
    const resp = await pipelineApi.getExecutionStatus(workflowId, executionId);
    const status = resp?.status;
    if (status === 'success' || status === 'failed' || status === 'cancelled') {
      return resp;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error('执行超时（15 分钟）');
}

function statusTag(status?: string, missing?: boolean) {
  if (missing) return <Tag>暂无记录</Tag>;
  if (status === 'success') return <Tag color="success">succeeded</Tag>;
  if (status === 'running' || status === 'pending') return <Tag color="processing">{status}</Tag>;
  if (status === 'failed') return <Tag color="error">failed</Tag>;
  return <Tag>{status || '未知'}</Tag>;
}

function formatMetricValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') {
    if (key.includes('rate') || key.includes('coverage')) {
      return `${(value * 100).toFixed(2)}%`;
    }
    return value.toFixed(4);
  }
  return String(value);
}

interface Props {
  slot: string;
  /** accuracy-operations | algorithm-deployment */
  context?: 'accuracy-operations' | 'algorithm-deployment';
  /** bump to trigger reload */
  refreshKey?: number;
}

const SlotWorkflowArtifactsPanel: React.FC<Props> = ({ slot, context = 'algorithm-deployment', refreshKey = 0 }) => {
  const config = getSlotWorkflowConfig(slot);
  const benchmark = isBenchmarkSlot(slot);
  const [loading, setLoading] = useState(false);
  const [executingRole, setExecutingRole] = useState<string | null>(null);
  const [trainExec, setTrainExec] = useState<ExecutionSnapshot | null>(null);
  const [predictExec, setPredictExec] = useState<ExecutionSnapshot | null>(null);
  const [registry, setRegistry] = useState<SlotRegistryView | null>(null);
  const [candidates, setCandidates] = useState<ModelCandidateView[]>([]);
  const [snapshotChain, setSnapshotChain] = useState<SnapshotChainView | null>(null);
  const [annotationPending, setAnnotationPending] = useState(0);
  const [annotationRows, setAnnotationRows] = useState<unknown[]>([]);
  const [reviewedAnnotationIds, setReviewedAnnotationIds] = useState<string[]>([]);
  const [alarmSummary, setAlarmSummary] = useState<PointAlarmSummary | null>(null);
  const [alarmLoadError, setAlarmLoadError] = useState<string | null>(null);

  const predictRole = config?.predictTemplateRole ?? 'predict';
  const isAccuracyOps = context === 'accuracy-operations';

  const applyDashboard = useCallback((entry: DashboardCacheEntry) => {
    setTrainExec(entry.trainExec);
    setPredictExec(entry.predictExec);
    setRegistry(entry.registry);
    setCandidates(entry.candidates);
    setSnapshotChain(entry.snapshotChain);
    setAnnotationPending(entry.annotationPending);
    setAnnotationRows(entry.annotationRows);
    setReviewedAnnotationIds(entry.reviewedAnnotationIds);
    setAlarmSummary(entry.alarmSummary);
    setAlarmLoadError(entry.alarmLoadError);
  }, []);

  const refresh = useCallback(async (opts?: { force?: boolean }) => {
    if (!config) return;
    const cacheKey = `${slot}:${predictRole}`;
    const cached = dashboardCache.get(cacheKey);
    const cacheFresh = Boolean(cached && Date.now() - cached.ts < DASHBOARD_CACHE_TTL_MS);
    if (!opts?.force && cacheFresh && cached) {
      applyDashboard(cached.entry);
      return;
    }
    if (cached && !opts?.force) {
      applyDashboard(cached.entry);
    } else {
      setLoading(true);
    }
    try {
      const wantAlarms = config.slot === 'pv_point' && config.predictTemplateRole === 'predict_replay';
      const productLoads = benchmark
        ? Promise.resolve([null, { candidates: [] as ModelCandidateView[] }, null, { candidates: [] }, { annotations: [] }] as const)
        : Promise.all([
            slotGovernanceApi.getRegistry(slot).catch(() => null),
            slotGovernanceApi.listModelCandidates(slot).catch(() => ({ candidates: [] as ModelCandidateView[] })),
            slotDatasetsApi.getSnapshotChain(slot).catch(() => null),
            slotDatasetsApi.listAnnotationCandidates(slot, 'pending').catch(() => ({ candidates: [] })),
            slotDatasetsApi.listReviewedAnnotations(slot).catch(() => ({ annotations: [] })),
          ]);

      const [product, train, predict, alarms] = await Promise.all([
        productLoads,
        loadRoleExecution(config, 'train_eval'),
        loadRoleExecution(config, predictRole),
        wantAlarms
          ? timeseriesReplayApi.getAlarmSummary(config.slot).then((value) => ({ ok: true as const, value })).catch((err: unknown) => ({
              ok: false as const,
              error: (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
                || (err as Error)?.message
                || '告警摘要读取失败',
            }))
          : Promise.resolve(null),
      ]);

      const [reg, cand, chain, ann, reviewed] = product;
      const reviewedRows = pickList<Record<string, unknown>>(reviewed, 'annotations');
      const reviewedIds = reviewedRows
        .map((item) => String(item.reviewed_annotation_id || ''))
        .filter(Boolean);
      const pendingRows = pickList<unknown>(ann, 'candidates');
      const entry: DashboardCacheEntry = {
        trainExec: train,
        predictExec: predict,
        registry: (reg as SlotRegistryView | null) ?? null,
        candidates: pickList<ModelCandidateView>(cand, 'candidates'),
        snapshotChain: (chain as SnapshotChainView | null) ?? null,
        annotationPending: pendingRows.length,
        annotationRows: pendingRows,
        reviewedAnnotationIds: reviewedIds,
        alarmSummary: alarms && alarms.ok ? alarms.value : null,
        alarmLoadError: alarms && !alarms.ok ? String(alarms.error || '告警摘要读取失败') : null,
      };
      dashboardCache.set(cacheKey, { ts: Date.now(), entry });
      applyDashboard(entry);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        || (err as Error)?.message
        || '产物读取失败';
      message.error(typeof detail === 'string' ? detail : '产物读取失败');
    } finally {
      setLoading(false);
    }
  }, [config, benchmark, slot, predictRole, isAccuracyOps, applyDashboard]);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  const handleExecute = async (role: 'train_eval' | 'predict' | 'predict_replay') => {
    if (!config) return;
    const workflowId =
      role === 'train_eval' ? config.trainWorkflowId : config.predictWorkflowId;
    setExecutingRole(role);
    try {
      let datasetId: string | undefined;
      if (role === 'train_eval' && slot === 'pv_point') {
        try {
          const ledger = await slotCumulativeApi.getLedger(slot);
          datasetId = freezeIdOf(slot, ledger.latest_freeze) || undefined;
        } catch {
          datasetId = undefined;
        }
      }
      const { execution_id: executionId } = await pipelineApi.executeAsync(workflowId, {
        slot: config.slot,
        execution_purpose: config.executionPurpose,
        ...(datasetId ? { dataset_id: datasetId } : {}),
      });
      message.info(`已启动 ${role}：${executionId}`);
      await pollExecution(workflowId, executionId);
      message.success(`${role} 执行结束，正在刷新产物…`);
      await refresh({ force: true });
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err?.message || '执行失败');
    } finally {
      setExecutingRole(null);
    }
  };

  const registryHint = useMemo(() => {
    if (benchmark) return 'benchmark 场景禁止产品治理写入（governance_eligible=false）';
    if (loading && !registry) return '正在读取 registry…';
    if (!registry) return '治理 registry 读取失败，请点刷新产物';
    if (registry.empty) return registry.diagnostic || 'registry 为空，等待 Promote 写入';
    return `registry v${registry.registry_version}`;
  }, [benchmark, loading, registry]);

  if (!config) {
    return (
      <Alert
        type="warning"
        showIcon
        message={`未知 workflow slot：${slot}`}
        description="请在 slotProductConfig 中注册该场景后再使用本面板。"
      />
    );
  }

  const renderExecutionCard = (snap: ExecutionSnapshot | null, title: string, role: string) => {
    if (!snap) return null;
    const editorPath = `/algorithm-dev/workflow-editor/${snap.workflowId}`;
    return (
      <Card size="small" title={title} extra={(
        <Space size={4}>
          {snap.schedulerTrigger ? <Tag color="gold">调度触发</Tag> : null}
          {statusTag(snap.status, snap.missing)}
        </Space>
      )}>
        {snap.missing ? (
          <Alert
            type="info"
            showIcon
            message="尚无 persisted execution"
            description={snap.error || '请先在编辑器执行一次，或点击下方「执行」按钮。'}
          />
        ) : (
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="workflow_id">
              <Link to={editorPath}>{snap.workflowId}</Link>
            </Descriptions.Item>
            <Descriptions.Item label="execution_id">{snap.executionId || '—'}</Descriptions.Item>
            {snap.triggerSource ? (
              <Descriptions.Item label="trigger_source">{snap.triggerSource}</Descriptions.Item>
            ) : null}
            <Descriptions.Item label="slot">{snap.slot || slot}</Descriptions.Item>
            <Descriptions.Item label="model_path">{snap.modelPath || '—'}</Descriptions.Item>
            {Object.entries(snap.metrics ?? {}).map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                {formatMetricValue(key, value)}
              </Descriptions.Item>
            ))}
            <Descriptions.Item label="finished_at">{snap.finishedAt || snap.startedAt || '—'}</Descriptions.Item>
          </Descriptions>
        )}
        <Space style={{ marginTop: 12 }} wrap>
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            loading={executingRole === role}
            onClick={() => void handleExecute(role as 'train_eval' | 'predict' | 'predict_replay')}
          data-testid={`execute-${role}`}
          >
            执行 {role}
          </Button>
          <Link to={editorPath}>
            <Button size="small" icon={<ApartmentOutlined />}>打开模板</Button>
          </Link>
        </Space>
      </Card>
    );
  };

  return (
    <Card
      className="slot-workflow-artifacts-panel"
      title={
        <Space>
          <span>{config.label}</span>
          <Tag color={benchmark ? 'purple' : 'blue'}>{config.shortLabel}</Tag>
          {benchmark && <Tag>benchmark_reuse</Tag>}
        </Space>
      }
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => void refresh({ force: true })} loading={loading}>
          刷新产物
        </Button>
      }
    >
      <Spin spinning={loading}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {config.description}
            {benchmark
              ? ' 本页仅观测 workflow execution；Promote/annotation/snapshot 对产品治理关闭。'
              : context === 'accuracy-operations'
                ? ' 本页展示最近一次 succeeded workflow execution 的可追溯指标。'
                : ' 部署页消费 workflow 产物；完整 Promote/复验在 G4 治理层。'}
          </Paragraph>
          <Alert
            type={benchmark ? 'warning' : 'info'}
            showIcon
            message={benchmark ? 'Benchmark 复用槽' : 'Slot 治理'}
            description={registryHint}
          />
          {!benchmark && candidates.length > 0 && (
            <Text type="secondary">
              已登记 model candidate：{candidates.length} 条（最近：
              {candidates[candidates.length - 1]?.model_candidate_id}）
            </Text>
          )}
          {!benchmark && (
            <Text type="secondary">
              快照链：
              {snapshotChain?.empty || !snapshotChain?.snapshot_id
                ? ' 未 bootstrap'
                : ` ${snapshotChain.snapshot_id} · v${snapshotChain.latest_version}`}
              {' · '}
              待审核 annotation candidate：{annotationPending}
            </Text>
          )}
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              {renderExecutionCard(trainExec, 'train_eval 最近执行', 'train_eval')}
            </Col>
            <Col xs={24} lg={12}>
              {renderExecutionCard(predictExec, `${predictRole} 最近执行`, predictRole)}
            </Col>
          </Row>
        </Space>
      </Spin>
    </Card>
  );
};

export default SlotWorkflowArtifactsPanel;
