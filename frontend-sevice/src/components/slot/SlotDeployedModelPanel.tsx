/**
 * SlotDeployedModelPanel — 算法部署页只读观察：当前模型、标签空间、训练指标、标签形态。
 * 不含打标执行、确认提案、闭环四动作。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { getSlotWorkflowConfig } from '../../config/slotProductConfig';
import { pipelineApi } from '../../services/workflowEnhancedApi';
import { slotGovernanceApi, type ModelCandidateView, type SlotRegistryView } from '../../services/slotGovernanceApi';
import { slotDatasetsApi, type SnapshotChainView } from '../../services/slotDatasetsApi';
import { freezeIdOf, slotCumulativeApi, type CumulativeLedger } from '../../services/slotCumulativeApi';
import { slotObservabilityApi, type MockAccuracyView, type TimeWallView } from '../../services/slotObservabilityApi';
import { timeseriesReplayApi } from '../../services/timeseriesReplayApi';
import { schedulerTaskApi } from '../../services/deploymentApi';
import PvFaultClassificationMetrics, {
  type PvClassificationMetrics,
} from '../pv-fault/PvFaultClassificationMetrics';

const { Text, Paragraph } = Typography;

type LabelRow = { label_id: number; label_name?: string };
type LabelWaveform = {
  label_id: number;
  label_name: string;
  timestamps: string[];
  series: Record<string, Array<number | null>>;
  point_count: number;
};

type NodeTrace = {
  nodeId: string;
  status?: string;
  error?: string;
  summary: Record<string, unknown>;
};

function collectNodeTraces(nodeResults: Record<string, unknown> | undefined): NodeTrace[] {
  if (!nodeResults) return [];
  return Object.entries(nodeResults).map(([nodeId, raw]) => {
    const node = (raw || {}) as { status?: string; error?: string; outputSummary?: Record<string, unknown> };
    return {
      nodeId,
      status: node.status,
      error: node.error,
      summary: node.outputSummary && typeof node.outputSummary === 'object' ? node.outputSummary : {},
    };
  });
}

function collectNumericMetrics(traces: NodeTrace[]): Record<string, number | string> {
  const metrics: Record<string, number | string> = {};
  for (const node of traces) {
    for (const [key, value] of Object.entries(node.summary)) {
      if (metrics[key] !== undefined) continue;
      if (typeof value === 'number' && Number.isFinite(value)) metrics[key] = value;
      if (key === 'model_path' && typeof value === 'string') metrics[key] = value;
      if (key === 'classification_report' && typeof value === 'string') metrics[key] = value;
    }
  }
  return metrics;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4);
  return String(value);
}

// @AI_GENERATED: pv_tsc 训练工作流为 3 节点（load → train_eval → 产物）。
const TRAIN_NODE_TOTAL: Record<string, number> = {
  pv_day: 8,
  pv_point: 6,
  pv_tsc: 3,
};
// @AI_GENERATED: end

type TrainRunView = {
  phase: 'freezing' | 'running' | 'success' | 'failed';
  workflowId?: string;
  executionId?: string;
  percent: number;
  doneNodes: number;
  totalNodes: number;
  currentLabel?: string;
  lastLog?: string;
  error?: string;
  startedAt: number;
};

function trainRunStorageKey(slot: string): string {
  return `aip.slotTrainRun.${slot}`;
}

function formatElapsed(startedAt: number): string {
  const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${String(rest).padStart(2, '0')}`;
}

function summarizeTrainStatus(resp: Record<string, unknown>, totalNodes: number): Pick<TrainRunView, 'phase' | 'percent' | 'doneNodes' | 'currentLabel' | 'lastLog' | 'error'> {
  const nodeResults = (resp.nodeResults || {}) as Record<string, { status?: string }>;
  const doneNodes = Object.values(nodeResults).filter((node) => {
    const status = String(node?.status || '');
    return status === 'success' || status === 'failed' || status === 'skipped';
  }).length;
  const logs = Array.isArray(resp.logs) ? resp.logs as Array<{ message?: string }> : [];
  const lastLog = logs.length ? String(logs[logs.length - 1]?.message || '') : '';
  const currentStart = [...logs].reverse().find((item) => String(item.message || '').includes('开始执行'));
  const currentLabel = currentStart
    ? String(currentStart.message || '').replace(/^▶\s*/, '').replace(/\s*开始执行.*$/, '')
    : undefined;
  const status = String(resp.status || 'running');
  if (status === 'success') {
    return { phase: 'success', percent: 100, doneNodes: Math.max(doneNodes, totalNodes), currentLabel, lastLog, error: undefined };
  }
  if (status === 'failed' || status === 'cancelled') {
    return {
      phase: 'failed',
      percent: Math.max(8, Math.round((doneNodes / Math.max(totalNodes, 1)) * 100)),
      doneNodes,
      currentLabel,
      lastLog,
      error: String(resp.error || lastLog || '训练失败'),
    };
  }
  const percent = Math.min(95, Math.max(6, Math.round(((doneNodes + 0.4) / Math.max(totalNodes, doneNodes + 1)) * 100)));
  return { phase: 'running', percent, doneNodes, currentLabel, lastLog, error: undefined };
}

function pickList<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === 'object') {
    const nested = (payload as Record<string, unknown>)[key];
    if (Array.isArray(nested)) return nested as T[];
  }
  return [];
}

function parseLabels(payload: unknown): LabelRow[] {
  const body = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  const nested = body.labels;
  if (Array.isArray(nested) && nested.length > 0) {
    return nested.map((item) => {
      const row = (item || {}) as { label_id?: number; labelId?: number; label_name?: string; labelName?: string };
      return {
        label_id: Number(row.label_id ?? row.labelId),
        label_name: String(row.label_name ?? row.labelName ?? ''),
      };
    }).filter((item) => Number.isFinite(item.label_id));
  }
  const map = (body.label_map || body.labelMap) as Record<string, number> | undefined;
  if (map && typeof map === 'object') {
    return Object.entries(map).map(([name, id]) => ({
      label_id: Number(id),
      label_name: name,
    })).filter((item) => Number.isFinite(item.label_id));
  }
  return [];
}

function detectTaskId(slot: string): string | null {
  if (slot === 'pv_day') return 'pv_day_predict';
  if (slot === 'pv_point') return 'pv_point_replay_tick';
  // @AI_GENERATED: pv_tsc 走独立 MultiRocket Challenger 检测任务。
  if (slot === 'pv_tsc') return 'pv_tsc_predict';
  // @AI_GENERATED: end
  return null;
}

interface Props {
  slot: string;
  /** 部署页已用 Tab 显示「当前生产模型」标题时去掉卡片标题，避免重复。 */
  embedded?: boolean;
}

const SlotDeployedModelPanel: React.FC<Props> = ({ slot, embedded = false }) => {
  const config = getSlotWorkflowConfig(slot);
  // @AI_GENERATED: pv_tsc 首发为 MultiRocket Challenger：禁用直接 Promote 与 mock 精度换产；只允许冻结训练、登记 Challenger、触发真实检测。
  const isTsc = slot === 'pv_tsc';
  // @AI_GENERATED: end
  const [loading, setLoading] = useState(false);
  const [registry, setRegistry] = useState<SlotRegistryView | null>(null);
  const [snapshotChain, setSnapshotChain] = useState<SnapshotChainView | null>(null);
  const [ledger, setLedger] = useState<CumulativeLedger | null>(null);
  const [candidates, setCandidates] = useState<ModelCandidateView[]>([]);
  const [labels, setLabels] = useState<LabelRow[]>([]);
  const [trainStatus, setTrainStatus] = useState<string | undefined>();
  const [trainExecutionId, setTrainExecutionId] = useState<string | undefined>();
  const [trainFinishedAt, setTrainFinishedAt] = useState<string | undefined>();
  const [trainTraces, setTrainTraces] = useState<NodeTrace[]>([]);
  const [trainMetrics, setTrainMetrics] = useState<PvClassificationMetrics | null>(null);
  const [waveformOpen, setWaveformOpen] = useState(false);
  const [waveformLoading, setWaveformLoading] = useState(false);
  const [waveforms, setWaveforms] = useState<LabelWaveform[]>([]);
  const [waveformError, setWaveformError] = useState<string | null>(null);
  const [replayModelRef, setReplayModelRef] = useState<string | null>(null);
  const [replayCursor, setReplayCursor] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | undefined>();
  const [acting, setActing] = useState(false);
  const [mocking, setMocking] = useState(false);
  const [trainRun, setTrainRun] = useState<TrainRunView | null>(null);
  const [elapsedTick, setElapsedTick] = useState(0);
  const [mockAccuracy, setMockAccuracy] = useState<MockAccuracyView | null>(null);
  const [timeWall, setTimeWall] = useState<TimeWallView | null>(null);
  const trainPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    if (!config) return;
    setLoading(true);
    try {
      const replayId = `sched-${slot}-default`;
      const [reg, chain, ledgerBody, candBody, train, labelResp, replay, mockAcc, wall] = await Promise.all([
        slotGovernanceApi.getRegistry(slot).catch(() => null),
        slotDatasetsApi.getSnapshotChain(slot).catch(() => null),
        slotCumulativeApi.getLedger(slot).catch(() => null),
        slotGovernanceApi.listModelCandidates(slot).catch(() => ({ candidates: [] })),
        pipelineApi.getSlotLatestExecution(slot, 'train_eval').catch(() => null),
        fetch(`/api/iterative-labeling/label-registry?slot=${encodeURIComponent(slot)}`)
          .then((response) => (response.ok ? response.json() : null))
          .catch(() => null),
        slot === 'pv_point'
          ? timeseriesReplayApi.getReplaySession(replayId).catch(() => null)
          : Promise.resolve(null),
        slotObservabilityApi.getMockAccuracy(slot).catch(() => null),
        slotObservabilityApi.getTimeWall(slot).catch(() => null),
      ]);
      setRegistry(reg);
      setSnapshotChain(chain);
      setLedger(ledgerBody);
      setCandidates(pickList<ModelCandidateView>(candBody, 'candidates'));
      setMockAccuracy(mockAcc);
      setTimeWall(wall);
      setLabels(parseLabels(labelResp));
      setTrainStatus(train?.status as string | undefined);
      setTrainExecutionId(train?.execution_id as string | undefined);
      setTrainFinishedAt((train?.finished_at || train?.started_at) as string | undefined);
      setTrainTraces(collectNodeTraces(train?.nodeResults as Record<string, unknown> | undefined));
      const payloadMetrics = train?.metrics;
      setTrainMetrics(
        payloadMetrics && typeof payloadMetrics === 'object'
          ? payloadMetrics as PvClassificationMetrics
          : null,
      );
      const productionId = typeof (reg as SlotRegistryView | null)?.champion?.champion_model_ref === 'string'
        ? String((reg as SlotRegistryView).champion?.champion_model_ref)
        : undefined;
      const rollingId = typeof (reg as SlotRegistryView | null)?.rolling_detect_model?.model_candidate_id === 'string'
        ? String((reg as SlotRegistryView).rolling_detect_model?.model_candidate_id)
        : undefined;
      setSelectedCandidateId(productionId || rollingId);
      if (replay && typeof replay === 'object') {
        const body = replay as Record<string, unknown>;
        setReplayModelRef(typeof body.model_ref === 'string' ? body.model_ref : null);
        setReplayCursor(`${Number(body.cursor || 0)} / ${Number(body.total || 0)}`);
      } else {
        setReplayModelRef(null);
        setReplayCursor(null);
      }
    } catch (err: unknown) {
      message.error((err as Error)?.message || '模型状态读取失败');
    } finally {
      setLoading(false);
    }
  }, [config, slot]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const stopTrainPoll = useCallback(() => {
    if (trainPollRef.current) {
      clearInterval(trainPollRef.current);
      trainPollRef.current = null;
    }
  }, []);

  const pollTrainOnce = useCallback(async (workflowId: string, executionId: string, startedAt: number) => {
    const totalNodes = TRAIN_NODE_TOTAL[slot] || 8;
    try {
      let resp: Record<string, unknown>;
      try {
        resp = await pipelineApi.getExecutionStatus(workflowId, executionId);
      } catch (error: unknown) {
        const statusCode = (error as { response?: { status?: number } })?.response?.status;
        if (statusCode !== 404) throw error;
        const latest = await pipelineApi.getLatestExecution(workflowId);
        if (String(latest?.execution_id || '') !== executionId) {
          throw error;
        }
        resp = latest;
      }
      const summary = summarizeTrainStatus(resp, totalNodes);
      const next: TrainRunView = {
        ...summary,
        workflowId,
        executionId,
        totalNodes,
        startedAt,
      };
      setTrainRun(next);
      if (summary.phase === 'success' || summary.phase === 'failed') {
        stopTrainPoll();
        window.sessionStorage.removeItem(trainRunStorageKey(slot));
        if (summary.phase === 'success') {
          message.success('训练完成，正在刷新模型列表');
          void refresh();
        } else {
          message.error(summary.error || '训练失败');
        }
      }
    } catch (error: unknown) {
      const text = (error as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        || (error as Error)?.message
        || '训练状态读取失败';
      stopTrainPoll();
      setTrainRun((prev) => prev ? {
        ...prev,
        phase: 'failed',
        error: String(text),
        lastLog: '执行状态已丢失，可能是后端重启；请看最近一次训练记录。',
      } : prev);
      window.sessionStorage.removeItem(trainRunStorageKey(slot));
    }
  }, [refresh, slot, stopTrainPoll]);

  const startTrainPoll = useCallback((workflowId: string, executionId: string, startedAt: number) => {
    stopTrainPoll();
    window.sessionStorage.setItem(trainRunStorageKey(slot), JSON.stringify({ workflowId, executionId, startedAt }));
    void pollTrainOnce(workflowId, executionId, startedAt);
    trainPollRef.current = setInterval(() => {
      void pollTrainOnce(workflowId, executionId, startedAt);
    }, 2000);
  }, [pollTrainOnce, slot, stopTrainPoll]);

  useEffect(() => {
    if (!config?.trainWorkflowId) return undefined;
    try {
      const raw = window.sessionStorage.getItem(trainRunStorageKey(slot));
      if (!raw) return undefined;
      const saved = JSON.parse(raw) as { workflowId?: string; executionId?: string; startedAt?: number };
      if (!saved.workflowId || !saved.executionId) return undefined;
      setTrainRun({
        phase: 'running',
        workflowId: saved.workflowId,
        executionId: saved.executionId,
        percent: 8,
        doneNodes: 0,
        totalNodes: TRAIN_NODE_TOTAL[slot] || 8,
        startedAt: Number(saved.startedAt) || Date.now(),
        lastLog: '正在恢复训练进度…',
      });
      startTrainPoll(saved.workflowId, saved.executionId, Number(saved.startedAt) || Date.now());
    } catch {
      window.sessionStorage.removeItem(trainRunStorageKey(slot));
    }
    return () => stopTrainPoll();
  }, [config?.trainWorkflowId, slot, startTrainPoll, stopTrainPoll]);

  useEffect(() => {
    if (!trainRun || (trainRun.phase !== 'freezing' && trainRun.phase !== 'running')) return undefined;
    const timer = setInterval(() => setElapsedTick((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [trainRun?.phase, trainRun]);

  const metrics = useMemo(() => collectNumericMetrics(trainTraces), [trainTraces]);
  const labelNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of labels) {
      map[String(row.label_id)] = row.label_name || `类别 ${row.label_id}`;
    }
    return map;
  }, [labels]);
  const classificationMetrics = useMemo<PvClassificationMetrics | null>(() => {
    if (trainMetrics && (trainMetrics.confusion_matrix || trainMetrics.per_class_metrics || trainMetrics.macro_f1_mean)) {
      return trainMetrics;
    }
    const merged: Record<string, unknown> = { ...metrics };
    for (const node of trainTraces) {
      Object.assign(merged, node.summary);
    }
    if (merged.confusion_matrix || merged.per_class_metrics || merged.macro_f1_mean) {
      return merged as PvClassificationMetrics;
    }
    return null;
  }, [trainMetrics, trainTraces, metrics]);
  const freezeId = freezeIdOf(slot, ledger?.latest_freeze);
  const freezePath = ledger?.latest_freeze?.artifact_ref || '';
  const champion = (registry?.champion || {}) as Record<string, unknown>;
  const championRef = formatValue(
    champion.model_ref
    || champion.model_artifact_ref
    || champion.artifact_ref
    || metrics.model_path
    || replayModelRef,
  );
  const trainHref = freezeId
    ? `/algorithm-dev/workflow-editor/${config?.trainWorkflowId}?dataset_id=${encodeURIComponent(freezeId)}&slot=${slot}`
    : `/algorithm-dev/workflow-editor/${config?.trainWorkflowId}?slot=${slot}`;

  const handleViewWaveforms = async () => {
    if (!freezePath) {
      message.warning('还没有冻结训练快照，无法读取标签形态');
      return;
    }
    setWaveformOpen(true);
    setWaveformLoading(true);
    setWaveformError(null);
    try {
      const response = await fetch(
        `/api/iterative-labeling/reference-waveforms?train_csv_path=${encodeURIComponent(freezePath)}&slot=${encodeURIComponent(slot)}`,
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '标签波形加载失败');
      setWaveforms(Array.isArray(payload.categories) ? payload.categories : []);
      if (!Array.isArray(payload.categories) || payload.categories.length === 0) {
        setWaveformError('冻结快照里没有可用的标签列或代表性窗口，所以画不出类别波形。标签 Tag 仍以注册表为准。');
      }
    } catch (error: unknown) {
      setWaveforms([]);
      const text = (error as Error)?.message || '标签波形加载失败';
      setWaveformError(text);
      message.error(text);
    } finally {
      setWaveformLoading(false);
    }
  };

  const rollingDetect = registry?.rolling_detect_model;
  const productionId = String((registry?.champion as Record<string, unknown> | null)?.champion_model_ref || '');
  const candidateRoleId = String(
    (registry?.challenger as Record<string, unknown> | null)?.challenger_model_candidate_id
    || (registry?.challenger as Record<string, unknown> | null)?.challenger_model_ref
    || '',
  );
  const detectTask = detectTaskId(slot);
  const mockById = mockAccuracy?.by_model || {};
  const mockUsable = Boolean(mockAccuracy?.usable) && !mockAccuracy?.empty;
  const promoteEligible = Boolean(mockAccuracy?.promote_eligible);
  const betterMockId = promoteEligible ? String(mockAccuracy?.better_model_candidate_id || '') : '';
  const wallView = mockAccuracy?.time_wall || timeWall;
  const formatMockPct = (value?: number | null) =>
    (mockUsable && typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—');
  const supportText = Object.entries(mockAccuracy?.class_support || {})
    .map(([label, count]) => `${label}×${count}`)
    .join('、');
  const wallRange = wallView?.holdout_start_day
    ? `${wallView.holdout_start_day}～${wallView.holdout_end_day || wallView.holdout_start_day}`
    : null;

  const handlePromoteByMockAccuracy = () => {
    // @AI_GENERATED: pv_tsc 不接 loop-demo mock gold，禁止按 mock 精度换产（handler 层防御）。
    if (isTsc) {
      message.warning('时序分类首发为 Challenger，不支持按 mock 精度设为生产');
      return;
    }
    // @AI_GENERATED: end
    if (!promoteEligible || !betterMockId) {
      message.warning('当前是 holdout 烟测，不能作为换生产依据');
      return;
    }
    Modal.confirm({
      title: '按 holdout 对照精度设为生产？',
      content: `候选 ${betterMockId} 在完整 holdout 上优于当前生产。确认后才改生产检测模型。烟测分数不能换生产。`,
      okText: '设为生产',
      onOk: async () => {
        setActing(true);
        try {
          const result = await slotGovernanceApi.setProductionModel(slot, {
            model_candidate_id: betterMockId,
            operator: 'ui',
            reason: 'mock gold 对照精度更优',
          });
          setRegistry(result.registry);
          setSelectedCandidateId(betterMockId);
          message.success('已按 mock 精度把更优模型设为生产');
        } catch (error: unknown) {
          const err = error as { response?: { data?: { detail?: string } }; message?: string };
          message.error(err.response?.data?.detail || err.message || '设为生产失败');
          throw error;
        } finally {
          setActing(false);
        }
      },
    });
  };

  const handleSetProduction = async () => {
    // @AI_GENERATED: pv_tsc 首发只跑 Challenger，禁止直接设为生产（handler 层防御）。
    if (isTsc) {
      message.warning('时序分类首发为 Challenger，需先滚动检测并复验，暂不支持直接设为生产');
      return;
    }
    // @AI_GENERATED: end
    if (!selectedCandidateId) {
      message.warning('请先选择一套已登记模型');
      return;
    }
    setActing(true);
    try {
      const result = await slotGovernanceApi.setProductionModel(slot, {
        model_candidate_id: selectedCandidateId,
        operator: 'ui',
        reason: '部署页设为生产',
      });
      setRegistry(result.registry);
      message.success('已设为生产：按日/按点检测将用这套模型');
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      message.error(err.response?.data?.detail || err.message || '设为生产失败');
    } finally {
      setActing(false);
    }
  };

  const handleSetCandidate = async () => {
    if (!selectedCandidateId) {
      message.warning('请先选择一套已登记模型');
      return;
    }
    setActing(true);
    try {
      const result = await slotGovernanceApi.setCandidateModel(slot, {
        model_candidate_id: selectedCandidateId,
        operator: 'ui',
        reason: '部署页设为候选',
      });
      setRegistry(result.registry);
      message.success('已设为候选，不会进入按日检测');
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      message.error(err.response?.data?.detail || err.message || '设为候选失败');
    } finally {
      setActing(false);
    }
  };

  const handleTriggerDetect = async () => {
    if (!detectTask) return;
    setActing(true);
    try {
      const result = await schedulerTaskApi.triggerTaskNow(detectTask);
      message.success(result.message || '已触发生产模型检测');
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      message.error(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : (err.message || '触发失败'));
    } finally {
      setActing(false);
      void refresh();
    }
  };

  const handleMockGold = async () => {
    // @AI_GENERATED: pv_tsc 只读，不接 loop-demo mock gold（handler 层防御）。
    if (isTsc) {
      message.warning('时序分类不提供演示推进，检测由真实 pv_tsc_predict 调度驱动');
      return;
    }
    // @AI_GENERATED: end
    setMocking(true);
    try {
      const result = await slotObservabilityApi.mockGoldReview(slot);
      if (result.usable === false) {
        message.warning(result.note || 'holdout 不足，未写入精度');
      } else {
        message.success(result.note || `已推进演示日，Acc ${result.accuracy?.classifier_accuracy != null ? `${(Number(result.accuracy.classifier_accuracy) * 100).toFixed(1)}%` : '—'}`);
      }
      await refresh();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: { message?: string } | string } }; message?: string };
      const detail = err.response?.data?.detail;
      const text = typeof detail === 'string' ? detail : detail?.message;
      message.error(text || err.message || 'mock 审核失败');
    } finally {
      setMocking(false);
    }
  };

  const handleFreezeAndTrain = async () => {
    if (trainRun && (trainRun.phase === 'freezing' || trainRun.phase === 'running')) {
      message.warning('已有训练在进行，请等它结束');
      return;
    }
    setActing(true);
    const startedAt = Date.now();
    setTrainRun({
      phase: 'freezing',
      percent: 4,
      doneNodes: 0,
      totalNodes: TRAIN_NODE_TOTAL[slot] || 8,
      startedAt,
      lastLog: '正在冻结累计训练集…',
    });
    try {
      const body = ledger || await slotCumulativeApi.getLedger(slot);
      const cutoff = body.latest_freeze?.reviewed_at_cutoff
        || body.events[body.events.length - 1]?.reviewed_at;
      if (!cutoff) {
        setTrainRun(null);
        message.warning('累计账本还没有审核记录，无法冻结。请先到人工标注审核确认提案。');
        return;
      }
      const frozen = await slotCumulativeApi.freezeAt(slot, cutoff, `部署页冻结并训练 ${cutoff}`);
      setLedger(frozen.ledger);
      const canvasId = (frozen.freeze?.canvas_row as { dataset_id?: string } | undefined)?.dataset_id
        || freezeIdOf(slot, frozen.ledger.latest_freeze);
      if (!config?.trainWorkflowId) {
        setTrainRun(null);
        message.error('没有训练模板');
        return;
      }
      const started = await pipelineApi.executeAsync(config.trainWorkflowId, {
        slot,
        dataset_id: canvasId || undefined,
        execution_purpose: 'product_workflow',
      });
      const executionId = String(started.execution_id || '');
      setTrainRun({
        phase: 'running',
        workflowId: config.trainWorkflowId,
        executionId,
        percent: 8,
        doneNodes: 0,
        totalNodes: TRAIN_NODE_TOTAL[slot] || 8,
        startedAt,
        lastLog: `已启动训练 ${executionId}`,
      });
      message.success(`已冻结并启动训练 execution=${executionId}`);
      startTrainPoll(config.trainWorkflowId, executionId, startedAt);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: { message?: string } | string } }; message?: string };
      const detail = err.response?.data?.detail;
      const text = typeof detail === 'string' ? detail : detail?.message;
      setTrainRun({
        phase: 'failed',
        percent: 8,
        doneNodes: 0,
        totalNodes: TRAIN_NODE_TOTAL[slot] || 8,
        startedAt,
        error: text || err.message || '冻结/训练启动失败',
      });
      message.error(text || err.message || '冻结/训练启动失败');
    } finally {
      setActing(false);
    }
  };

  const metricChartOption = useMemo(() => {
    const pairs = [
      ['Accuracy', metrics.accuracy_mean ?? metrics.point_accuracy],
      ['Macro-F1', metrics.macro_f1_mean ?? metrics.point_macro_f1],
      ['Precision', metrics.macro_precision_mean],
      ['Recall', metrics.macro_recall_mean],
    ].filter(([, value]) => typeof value === 'number') as Array<[string, number]>;
    if (pairs.length === 0) return null;
    return {
      animationDuration: 200,
      tooltip: { trigger: 'axis', valueFormatter: (value: number) => `${(Number(value) * 100).toFixed(2)}%` },
      grid: { left: 48, right: 16, top: 24, bottom: 32 },
      xAxis: { type: 'category', data: pairs.map(([name]) => name) },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (v: number) => `${Math.round(v * 100)}%` } },
      series: [{ type: 'bar', data: pairs.map(([, value]) => value), barMaxWidth: 36, itemStyle: { color: '#1677ff' } }],
    };
  }, [metrics]);

  if (!config) {
    return <Alert type="warning" showIcon message={`未知场景：${slot}`} />;
  }

  const headlineMetrics = [
    { title: 'Accuracy', value: metrics.accuracy_mean ?? metrics.point_accuracy },
    { title: 'Macro-F1', value: metrics.macro_f1_mean ?? metrics.point_macro_f1 },
    { title: '类别数', value: metrics.n_classes ?? labels.length, isCount: true },
    { title: '训练样本', value: metrics.n_samples, isCount: true },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title={embedded ? undefined : (
          <Space>
            <span>当前生产模型</span>
            <Tag color="blue">{config.shortLabel}</Tag>
          </Space>
        )}
        extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()} loading={loading}>刷新</Button>}
      >
        <Spin spinning={loading}>
          <Paragraph type="secondary" style={{ marginBottom: 12, maxWidth: '72ch' }}>
            观察已训练模型、标签空间和最近一次训练指标。打标仍在「人工标注审核」，训练集版本在「累计训练数据集」。
          </Paragraph>
          <Row gutter={[16, 16]} style={{ marginBottom: 12 }}>
            {headlineMetrics.map((item) => (
              <Col xs={12} md={6} key={item.title}>
                <Statistic
                  title={item.title}
                  value={typeof item.value === 'number' ? item.value : '—'}
                  precision={item.isCount || typeof item.value !== 'number' ? 0 : 4}
                  suffix={item.isCount || typeof item.value !== 'number' ? undefined : undefined}
                />
              </Col>
            ))}
          </Row>
          <Descriptions size="small" bordered column={2}>
            <Descriptions.Item label="诊断路径">{slot}</Descriptions.Item>
            <Descriptions.Item label="Registry">
              {registry?.empty || !registry ? '尚未登记生产模型' : `v${registry.registry_version}`}
            </Descriptions.Item>
            <Descriptions.Item label="当前模型" span={2}>
              {championRef === '—' ? <Text type="secondary">暂无生产模型，下方展示最近训练产物</Text> : <Text code copyable>{championRef}</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="训练冻结版">{freezeId || '尚无冻结版本'}</Descriptions.Item>
            <Descriptions.Item label="快照链">
              {snapshotChain?.snapshot_id ? `${snapshotChain.snapshot_id} · v${snapshotChain.latest_version}` : '未初始化'}
            </Descriptions.Item>
            <Descriptions.Item label="冻结文件" span={2}>{freezePath || '—'}</Descriptions.Item>
            <Descriptions.Item label="最近训练">
              {trainStatus ? <Tag color={trainStatus === 'success' ? 'success' : trainStatus === 'failed' ? 'error' : 'processing'}>{trainStatus}</Tag> : '暂无记录'}
            </Descriptions.Item>
            <Descriptions.Item label="训练 execution">{trainExecutionId || '—'}</Descriptions.Item>
            <Descriptions.Item label="完成时间" span={2}>{trainFinishedAt || '—'}</Descriptions.Item>
            {replayModelRef ? (
              <Descriptions.Item label="线上 replay 模型" span={2}>
                <Text code copyable>{replayModelRef}</Text>
              </Descriptions.Item>
            ) : null}
            {replayCursor ? (
              <Descriptions.Item label="replay 进度">{replayCursor}</Descriptions.Item>
            ) : null}
            <Descriptions.Item label="生产检测模型" span={2}>
              {rollingDetect?.model_artifact_ref
                ? <Text code copyable>{String(rollingDetect.model_artifact_ref)}</Text>
                : <Text type="secondary">尚未指定生产模型；调度会回退到候选 / 最新登记模型</Text>}
            </Descriptions.Item>
          </Descriptions>
          <Space wrap style={{ marginTop: 12 }}>
            {/* @AI_GENERATED: pv_tsc 的真实审核队列在 review tab，天/点在 pv_label 打标 tab。 */}
            <Link
              to={
                slot === 'pv_tsc'
                  ? `/iterative-labeling?tab=review&review_slot=${slot}`
                  : `/iterative-labeling?tab=pv_label&slot=${slot}`
              }
            >
              <Button size="small">人工标注审核</Button>
            </Link>
            {/* @AI_GENERATED: end */}
            <Link to={`/datasets/cumulative-training?slot=${slot}`}><Button size="small">累计训练数据集</Button></Link>
            <Link to={trainHref}><Button size="small">打开训练模板</Button></Link>
          </Space>
        </Spin>
      </Card>

      <Card
        size="small"
        title={`标签空间（${labels.length}）`}
        extra={(
          <Button size="small" onClick={() => void handleViewWaveforms()} disabled={!freezePath}>
            查看标签形态
          </Button>
        )}
      >
        {labels.length === 0 ? (
          <Alert type="info" showIcon message="该场景还没有标签注册表，确认提案后会出现在这里。" />
        ) : (
          <Space wrap>
            {labels.map((item) => (
              <Tag key={item.label_id} color="blue">
                {item.label_name || `类别 ${item.label_id}`}（{item.label_id}）
              </Tag>
            ))}
          </Space>
        )}
      </Card>

      <Card size="small" title="最近一次训练评估">
        <Paragraph type="secondary" style={{ marginBottom: 8, maxWidth: '72ch' }}>
          来自最近一次 train_eval。混淆矩阵行是真值、列是预测；重复评估曲线看 Macro-F1 稳不稳。
        </Paragraph>
        {classificationMetrics ? (
          <PvFaultClassificationMetrics
            metrics={classificationMetrics}
            labelNames={labelNames}
            emptyText="这次训练没有可展示的分类评估。"
          />
        ) : metricChartOption ? (
          <ReactECharts option={metricChartOption} style={{ height: 240 }} />
        ) : (
          <Alert type="info" showIcon message="最近一次训练没有可绘图的分类指标（点路径可能只落了 model_path）。" />
        )}
        {typeof (classificationMetrics?.classification_report || metrics.classification_report) === 'string' && (
          <Collapse
            size="small"
            style={{ marginTop: 8 }}
            items={[{
              key: 'report',
              label: '分类报告',
              children: (
                <pre style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap' }}>
                  {String(classificationMetrics?.classification_report || metrics.classification_report)}
                </pre>
              ),
            }]}
          />
        )}
      </Card>

      <Card size="small" title="训练流水线">
        <Table
          size="small"
          rowKey="nodeId"
          pagination={false}
          dataSource={trainTraces}
          locale={{ emptyText: '暂无训练执行' }}
          columns={[
            { title: '节点', dataIndex: 'nodeId', ellipsis: true },
            {
              title: '状态',
              dataIndex: 'status',
              width: 90,
              render: (value: string) => (
                <Tag color={value === 'success' ? 'success' : value === 'failed' ? 'error' : 'default'}>{value || '—'}</Tag>
              ),
            },
            {
              title: '说明',
              key: 'hint',
              ellipsis: true,
              render: (_: unknown, row: NodeTrace) => row.error
                || (typeof row.summary.model_path === 'string' ? String(row.summary.model_path) : formatValue(row.summary.data)),
            },
          ]}
        />
      </Card>

      <Card
        size="small"
        title={`已登记模型（${candidates.length}）— 生产 / 候选`}
        extra={(
          <Space wrap>
            <Button
              size="small"
              onClick={() => void handleFreezeAndTrain()}
              loading={acting || trainRun?.phase === 'freezing'}
              disabled={trainRun?.phase === 'running'}
            >
              冻结并训练
            </Button>
            {/* @AI_GENERATED: pv_tsc 首发为 Challenger：隐藏"设为生产"与全部 mock 操作，只保留登记 Challenger + 触发真实检测。 */}
            {!isTsc && (
              <Button size="small" type="primary" onClick={() => void handleSetProduction()} loading={acting} disabled={!selectedCandidateId}>
                设为生产
              </Button>
            )}
            <Button size="small" onClick={() => void handleSetCandidate()} loading={acting} disabled={!selectedCandidateId}>
              {isTsc ? '登记为 Challenger' : '设为候选'}
            </Button>
            {!isTsc && (
              <Button
                size="small"
                onClick={() => void handleMockGold()}
                loading={mocking}
              >
                推进演示下一天（不入库）
              </Button>
            )}
            {!isTsc && (
              <Button
                size="small"
                disabled={!betterMockId || !promoteEligible}
                onClick={() => handlePromoteByMockAccuracy()}
                loading={acting}
              >
                按 mock 精度设为生产
              </Button>
            )}
            <Button
              size="small"
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={() => void handleTriggerDetect()}
              loading={acting}
              disabled={!detectTask}
            >
              立即触发检测
            </Button>
          </Space>
        )}
      >
        {/* @AI_GENERATED: end */}
        {/* @AI_GENERATED: 三槽文案；pv_tsc 说明首发 Challenger + strict 合同 + 未 Promote。 */}
        <Paragraph type="secondary" style={{ marginBottom: 8, maxWidth: '72ch' }}>
          {isTsc
            ? '时序分类（MultiRocket）首发以 Challenger 身份滚动检测：冻结并训练产出候选后登记为 Challenger，由 pv_tsc_predict 调度按设备日跑真实检测与人工审核回流。本页不提供直接设为生产或 mock 精度换产；strict 生产合同（Macro-F1、balanced accuracy、≥10 次 strict 划分且全部隔离干净）见上方「最近一次训练评估」。'
            : '生产模型用于按日/按点检测。候选只作对照，不会进检测。演示推进会喂数、检测、用真值自动审核并算精度，但不会写入累计账本。'}
        </Paragraph>
        {isTsc && (
          <Alert
            style={{ marginBottom: 12 }}
            type="info"
            showIcon
            message="时序分类首发为 Challenger（未 Promote 为生产）"
            description="MultiRocket 训练产物以目录工件形式保存（model.pt + 窗口契约）。先以 Challenger 跑一段，多窗口复验通过后再考虑 Promote。"
          />
        )}
        {/* @AI_GENERATED: end */}
        {wallRange ? (
          <Alert
            style={{ marginBottom: 12 }}
            type="info"
            showIcon
            message={`时间墙 holdout ${wallRange}`}
            description={`训练侧截止 ${wallView?.train_end_day || '（不足）'}；冻结会丢掉 holdout 日的标签行。点路径特征仍可用墙左边的历史。`}
          />
        ) : null}
        {mockAccuracy?.reason === 'no_unseen_holdout' ? (
          <Alert
            style={{ marginBottom: 12 }}
            type="warning"
            showIcon
            message="没有未见过的对照集"
            description={mockAccuracy.note || 'holdout 不足，不展示精度，也不退回全量 gold。'}
          />
        ) : mockAccuracy?.note && mockAccuracy?.empty !== true ? (
          <Alert
            style={{ marginBottom: 12 }}
            type={promoteEligible ? 'success' : 'warning'}
            showIcon
            message={mockAccuracy.note}
            description={(
              <>
                {mockAccuracy.origin === 'detection_join' ? '来自最近检测批次与 holdout gold join。' : '检测批次在 holdout 上命中不足，已对 holdout 子集跑生产/候选预测。'}
                {supportText ? ` 类别 support：${supportText}。` : ''}
                {mockAccuracy.holdout_unit_count != null ? ` holdout 单元 ${mockAccuracy.holdout_unit_count} 条。` : ''}
                {promoteEligible ? '' : ' 当前是烟测，不能作为换生产依据。'}
              </>
            )}
          />
        ) : null}
        {trainRun ? (
          <Alert
            style={{ marginBottom: 12 }}
            type={trainRun.phase === 'failed' ? 'error' : trainRun.phase === 'success' ? 'success' : 'info'}
            showIcon
            message={
              trainRun.phase === 'freezing' ? '正在冻结累计集'
                : trainRun.phase === 'running' ? '训练进行中'
                  : trainRun.phase === 'success' ? '训练完成'
                    : '训练失败'
            }
            description={(
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Progress
                  percent={trainRun.percent}
                  status={trainRun.phase === 'failed' ? 'exception' : trainRun.phase === 'success' ? 'success' : 'active'}
                />
                <Space wrap>
                  <Tag color={trainRun.phase === 'failed' ? 'error' : trainRun.phase === 'success' ? 'success' : 'processing'}>
                    {trainRun.phase}
                  </Tag>
                  <Text type="secondary">
                    节点 {trainRun.doneNodes}/{trainRun.totalNodes}
                    {elapsedTick >= 0 ? ` · 已用 ${formatElapsed(trainRun.startedAt)}` : ''}
                  </Text>
                  {trainRun.executionId ? <Text code copyable>{trainRun.executionId}</Text> : null}
                </Space>
                {trainRun.currentLabel ? <div>当前节点：{trainRun.currentLabel}</div> : null}
                {trainRun.lastLog ? <Text type="secondary">{trainRun.lastLog}</Text> : null}
                {trainRun.error ? <Text type="danger">{trainRun.error}</Text> : null}
              </Space>
            )}
          />
        ) : null}
        <Select
          style={{ minWidth: 420, marginBottom: 12 }}
          placeholder="选择已登记模型"
          value={selectedCandidateId}
          onChange={(value) => setSelectedCandidateId(value)}
          options={candidates.map((item) => ({
            value: item.model_candidate_id,
            label: `${item.model_candidate_id} · ${String(item.model_artifact_ref || '').split(/[/\\]/).slice(-1)[0]}`,
          }))}
        />
        <Table
          size="small"
          rowKey="model_candidate_id"
          dataSource={candidates}
          pagination={{ pageSize: 5, hideOnSinglePage: true }}
          locale={{ emptyText: '还没有登记过模型候选；先冻结并训练' }}
          rowClassName={(row) => (row.model_candidate_id === productionId ? 'ant-table-row-selected' : '')}
          onRow={(row) => ({
            onClick: () => setSelectedCandidateId(row.model_candidate_id),
          })}
          columns={[
            { title: 'candidate', dataIndex: 'model_candidate_id', ellipsis: true },
            {
              title: '角色',
              key: 'role',
              width: 120,
              render: (_: unknown, row: ModelCandidateView) => (
                <Space size={4}>
                  {row.model_candidate_id === productionId ? <Tag color="green">生产</Tag> : null}
                  {/* @AI_GENERATED: pv_tsc 候选角色显示为 Challenger。 */}
                  {row.model_candidate_id === candidateRoleId ? <Tag color={isTsc ? 'purple' : 'gold'}>{isTsc ? 'Challenger' : '候选'}</Tag> : null}
                  {/* @AI_GENERATED: end */}
                </Space>
              ),
            },
            {
              // @AI_GENERATED: 模型来自哪个项目 —— 项目训练产出经领域桥进池后在这里可见。
              // 无归属不写"未知"：那会让人以为是解析失败，实际是「非项目来源」（如累计重训）。
              title: '来源项目',
              key: 'project',
              width: 180,
              render: (_: unknown, row: ModelCandidateView) => {
                const att = row.project_attribution;
                if (!att) {
                  return (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {row.source_kind === 'cumulative_retrain' ? '累计重训' : '非项目来源'}
                    </Text>
                  );
                }
                return (
                  <Space direction="vertical" size={0}>
                    <Link to={`/projects/${encodeURIComponent(att.project_id)}/overview`}>
                      {att.project_name || att.project_id}
                    </Link>
                    {att.project_candidate_id ? (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {att.project_candidate_id}
                      </Text>
                    ) : null}
                  </Space>
                );
              },
              // @AI_GENERATED: end
            },
            {
              title: 'mock Acc',
              key: 'mock_acc',
              width: 100,
              render: (_: unknown, row: ModelCandidateView) => formatMockPct(mockById[row.model_candidate_id]?.classifier_accuracy),
            },
            {
              title: 'mock F1',
              key: 'mock_f1',
              width: 100,
              render: (_: unknown, row: ModelCandidateView) => formatMockPct(mockById[row.model_candidate_id]?.macro_f1),
            },
            { title: '状态', dataIndex: 'status', width: 100, render: (value: string) => <Tag>{value || '—'}</Tag> },
            { title: '工件', dataIndex: 'model_artifact_ref', ellipsis: true },
            { title: '登记时间', dataIndex: 'registered_at', width: 180 },
          ]}
        />
      </Card>

      <Modal
        title={`训练快照标签形态（${waveforms.length} 类）`}
        open={waveformOpen}
        onCancel={() => setWaveformOpen(false)}
        footer={<Button onClick={() => setWaveformOpen(false)}>关闭</Button>}
        width={1100}
      >
        {waveformLoading ? (
          <div style={{ padding: 80, textAlign: 'center' }}><Spin tip="正在提取各类别代表波形…" /></div>
        ) : waveforms.length > 0 ? (
          <Row gutter={[12, 12]}>
            {waveforms.map((waveform) => (
              <Col xs={24} md={12} xl={8} key={waveform.label_id}>
                <Card
                  size="small"
                  title={(
                    <Space size={6}>
                      <Tag color="blue">label_{waveform.label_id}</Tag>
                      <Text>{waveform.label_name}</Text>
                    </Space>
                  )}
                  extra={<Text type="secondary" style={{ fontSize: 11 }}>{waveform.point_count} 点</Text>}
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
                        data: waveform.timestamps.map((timestamp) => {
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
                        itemStyle: { color: index === 0 ? '#1677ff' : '#fa8c16' },
                      })),
                    }}
                  />
                </Card>
              </Col>
            ))}
          </Row>
        ) : (
          <Alert type="warning" showIcon message={waveformError || '当前冻结快照没有可展示的标签波形'} />
        )}
      </Modal>
    </Space>
  );
};

export default SlotDeployedModelPanel;
