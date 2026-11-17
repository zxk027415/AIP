/**
 * PvPointAccuracyOpsPanel — pv_point 精度运营：replay 进度、告警、结果曲线。
 * 与算法部署页分离：本页不展示 Promote / 打标 / 闭环治理。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  InputNumber,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  BellOutlined,
  AuditOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { getSlotWorkflowConfig } from '../../config/slotProductConfig';
import { pipelineApi } from '../../services/workflowEnhancedApi';
import SlotObservabilityCalendar from './SlotObservabilityCalendar';
import SlotOpsClockBar from './SlotOpsClockBar';
import SlotAccuracyMetricsCard from './SlotAccuracyMetricsCard';
import SlotClassificationViz from './SlotClassificationViz';
import FeedSourceCard from './FeedSourceCard';
import { slotObservabilityApi, type MockAccuracyView, type ObservabilityStatus } from '../../services/slotObservabilityApi';
import {
  timeseriesReplayApi,
  type PointAlarmSummary,
} from '../../services/timeseriesReplayApi';

const { Text, Paragraph } = Typography;

const DEFAULT_REPLAY_SESSION_ID = 'sched-pv_point-default';

type ReplayOutcome = {
  kind?: string;
  label?: number | null;
  goldLabel?: number | null;
  confidence?: number | null;
  reason?: string | null;
  entity_key?: string;
  point_time?: string;
  iCal?: number | null;
};

type ReplaySessionView = {
  session_id: string;
  status: string;
  cursor: number;
  total: number;
  outcome_count?: number;
  model_ref?: string | null;
  error?: string | null;
};

type LatestReplayTick = {
  executionId?: string;
  finishedAt?: string;
  schedulerTrigger?: boolean;
  metrics: Record<string, unknown>;
  status?: string;
  missing?: boolean;
  error?: string;
};

const ALARM_EVENT_LABELS: Record<string, string> = {
  alarm_open: '告警产生',
  alarm_close: '告警消除',
  alarm_dedupe: '告警去重',
  alarm_label_switch: '标签切换',
};

function readAlarmInput(testid: string, fallback: number): number {
  const root = document.querySelector(`[data-testid="${testid}"]`);
  const input = (root instanceof HTMLInputElement
    ? root
    : root?.querySelector('input')) as HTMLInputElement | null;
  const parsed = Number(input?.value);
  if (Number.isFinite(parsed) && parsed >= 1) return Math.trunc(parsed);
  return fallback;
}

function formatMetricValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') {
    if (key.includes('coverage')) return `${(value * 100).toFixed(4)}%`;
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (Array.isArray(value)) return `[${value.length} 项]`;
  return String(value);
}

function outcomeKindTag(kind: unknown, reason: unknown) {
  const k = String(kind || '');
  if (k === 'prediction') return <Tag color="orange">prediction</Tag>;
  if (k === 'no_decision') {
    return (
      <Tag color="default">
        no_decision
        {reason ? ` · ${String(reason)}` : ''}
      </Tag>
    );
  }
  return <Tag>{k || '—'}</Tag>;
}

function calendarDay(value: unknown): string {
  const text = String(value || '').trim();
  const match = text.match(/(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : '';
}

function outcomeStamp(item: ReplayOutcome): unknown {
  return item.point_time || (item as { time?: string }).time;
}

function inCalendarWindow(value: unknown, from?: string, to?: string): boolean {
  if (!from || !to) return false;
  const day = calendarDay(value);
  return Boolean(day) && day >= from && day <= to;
}

function formatAxisTime(value: string | undefined): string {
  if (!value) return '';
  const text = String(value);
  const day = calendarDay(text);
  const timeMatch = text.match(/[T ](\d{2}:\d{2})/);
  if (day && timeMatch) return `${day} ${timeMatch[1]}`;
  if (day) return day;
  return text.slice(0, 19);
}

function pickOutcomes(body: Record<string, unknown>): ReplayOutcome[] {
  const raw = body.recent_outcomes || body.outcomes;
  return Array.isArray(raw) ? (raw as ReplayOutcome[]) : [];
}

function mapDemoOutcomes(items: Array<Record<string, unknown>>): ReplayOutcome[] {
  return items.map((item) => ({
    kind: String(item.kind || 'prediction'),
    label: typeof item.predicted_label === 'number' ? item.predicted_label : null,
    goldLabel: typeof item.gold_label === 'number' ? item.gold_label : null,
    confidence: typeof item.confidence === 'number' ? item.confidence : null,
    entity_key: `${item.site_id || ''}|${item.device_id || ''}|${item.branch_id || ''}`,
    point_time: String(item.time || item.date || ''),
    iCal: typeof item.i_cal === 'number' ? item.i_cal : (typeof item.value === 'number' ? item.value : null),
  }));
}

function computeWindowMetrics(items: ReplayOutcome[]) {
  const pairs = items.filter((item) => item.goldLabel != null && item.label != null);
  const counted = pairs.length;
  const confirm = pairs.filter((item) => item.label === item.goldLabel).length;
  const classes = [0, 1, 3];
  const precisions: number[] = [];
  const recalls: number[] = [];
  const f1s: number[] = [];
  for (const cls of classes) {
    const tp = pairs.filter((item) => item.label === cls && item.goldLabel === cls).length;
    const fp = pairs.filter((item) => item.label === cls && item.goldLabel !== cls).length;
    const fn = pairs.filter((item) => item.label !== cls && item.goldLabel === cls).length;
    if (tp + fp + fn === 0) continue;
    const precision = tp + fp ? tp / (tp + fp) : 0;
    const recall = tp + fn ? tp / (tp + fn) : 0;
    const f1 = precision + recall ? (2 * precision * recall) / (precision + recall) : 0;
    precisions.push(precision);
    recalls.push(recall);
    f1s.push(f1);
  }
  return {
    countedUnits: counted,
    classifierAccuracy: counted ? confirm / counted : null,
    confirmCount: confirm,
    correctCount: counted - confirm,
    precision: precisions.length ? precisions.reduce((sum, value) => sum + value, 0) / precisions.length : null,
    recall: recalls.length ? recalls.reduce((sum, value) => sum + value, 0) / recalls.length : null,
    macroF1: f1s.length ? f1s.reduce((sum, value) => sum + value, 0) / f1s.length : null,
  };
}

function deriveDemoAlarms(items: ReplayOutcome[], openN: number, closeN: number): PointAlarmSummary {
  const events: Array<Record<string, unknown>> = [];
  const active: Array<Record<string, unknown>> = [];
  const byEntity = new Map<string, ReplayOutcome[]>();
  for (const item of items) {
    const key = String(item.entity_key || '');
    if (!key) continue;
    const bucket = byEntity.get(key) || [];
    bucket.push(item);
    byEntity.set(key, bucket);
  }
  for (const [entity, rows] of byEntity) {
    const sorted = [...rows].sort((a, b) => String(a.point_time || '').localeCompare(String(b.point_time || '')));
    let faultStreak = 0;
    let normalStreak = 0;
    let open = false;
    let alarmId = '';
    let activeLabel: number | null = null;
    for (const row of sorted) {
      const label = Number(row.label);
      const isFault = Number.isFinite(label) && label !== 0;
      if (isFault) {
        faultStreak += 1;
        normalStreak = 0;
        if (!open && faultStreak >= openN) {
          open = true;
          alarmId = `demo-${entity}-${row.point_time}`;
          activeLabel = label;
          events.push({
            event_type: 'alarm_open',
            entity_key: entity,
            label,
            point_time: row.point_time,
            event_id: `${alarmId}-open`,
          });
        }
      } else {
        normalStreak += 1;
        faultStreak = 0;
        if (open && normalStreak >= closeN) {
          events.push({
            event_type: 'alarm_close',
            entity_key: entity,
            label: 0,
            point_time: row.point_time,
            event_id: `${alarmId}-close`,
          });
          open = false;
          alarmId = '';
          activeLabel = null;
        }
      }
    }
    if (open) {
      active.push({ entity_key: entity, active_label: activeLabel, active_alarm_id: alarmId });
    }
  }
  return {
    slot: 'pv_point',
    entity_count: byEntity.size,
    active_alarm_count: active.length,
    active_alarms: active,
    recent_events: events,
  };
}

interface Props {
  refreshKey?: number;
}

const PvPointAccuracyOpsPanel: React.FC<Props> = ({ refreshKey = 0 }) => {
  const config = getSlotWorkflowConfig('pv_point');
  const [loading, setLoading] = useState(false);
  const [alarmSummary, setAlarmSummary] = useState<PointAlarmSummary | null>(null);
  const [alarmError, setAlarmError] = useState<string | null>(null);
  const [replaySession, setReplaySession] = useState<ReplaySessionView | null>(null);
  const [outcomes, setOutcomes] = useState<ReplayOutcome[]>([]);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [latestTick, setLatestTick] = useState<LatestReplayTick | null>(null);
  const [openConsecutive, setOpenConsecutive] = useState<number>(3);
  const [closeConsecutive, setCloseConsecutive] = useState<number>(3);
  const [savingPolicy, setSavingPolicy] = useState(false);

  const [calendarRange, setCalendarRange] = useState<{ from: string; to: string } | null>(null);
  const [anchorReady, setAnchorReady] = useState(false);
  const [obsStatus, setObsStatus] = useState<ObservabilityStatus | null>(null);
  const [chartDevice, setChartDevice] = useState<string>('');
  const [dailyAcc, setDailyAcc] = useState<MockAccuracyView | null>(null);
  // @AI_GENERATED
  const [labelNames, setLabelNames] = useState<Record<string, string>>({});
  const labelName = useCallback((id: number | null | undefined): string => {
    if (id == null) return '—';
    return labelNames[String(id)] || `label ${id}`;
  }, [labelNames]);
  // @AI_GENERATED: end

  const refresh = useCallback(async () => {
    if (!config) return;
    setLoading(true);
    setAlarmError(null);
    setReplayError(null);
    const from = calendarRange?.from;
    const to = calendarRange?.to;
    try {
      const [alarmsResult, sessionResult, latestResult, policyResult, statusResult, demoOutcomesResult, accResult] = await Promise.allSettled([
        timeseriesReplayApi.getAlarmSummary('pv_point', from, to),
        timeseriesReplayApi.getReplaySession(DEFAULT_REPLAY_SESSION_ID, from, to),
        pipelineApi.getSlotLatestExecution('pv_point', 'predict_replay'),
        timeseriesReplayApi.getAlarmPolicy('pv_point'),
        slotObservabilityApi.getStatus('pv_point'),
        slotObservabilityApi.getOutcomes('pv_point', from, to),
        slotObservabilityApi.getMockAccuracy('pv_point'),
      ]);

      if (alarmsResult.status === 'fulfilled') {
        setAlarmSummary(alarmsResult.value);
      } else {
        setAlarmSummary(null);
        setAlarmError(
          (alarmsResult.reason as { response?: { data?: { detail?: string } }; message?: string })
            ?.response?.data?.detail
            || (alarmsResult.reason as Error)?.message
            || '告警摘要读取失败',
        );
      }

      if (sessionResult.status === 'fulfilled') {
        const body = sessionResult.value as Record<string, unknown>;
        setReplaySession({
          session_id: String(body.session_id || DEFAULT_REPLAY_SESSION_ID),
          status: String(body.status || 'unknown'),
          cursor: Number(body.cursor || 0),
          total: Number(body.total || body.total_points || 0),
          outcome_count: Number(body.outcome_count || 0),
          model_ref: (body.model_ref as string | null | undefined) ?? null,
          error: (body.error as string | null | undefined) ?? null,
        });
      } else {
        setReplaySession(null);
        setReplayError('replay 会话尚未创建；调试折叠里可看。演示检测点不走这条会话。');
      }

      const demoItems = demoOutcomesResult.status === 'fulfilled'
        ? (demoOutcomesResult.value.items || [])
        : [];
      if (demoItems.length > 0) {
        setOutcomes(mapDemoOutcomes(demoItems as Array<Record<string, unknown>>));
        setReplayError(null);
        setAlarmError(null);
        // @AI_GENERATED
        if (demoOutcomesResult.status === 'fulfilled') {
          const names = demoOutcomesResult.value.label_names;
          if (names && typeof names === 'object') setLabelNames(names);
        }
        // @AI_GENERATED: end
      } else if (sessionResult.status === 'fulfilled') {
        setOutcomes(pickOutcomes(sessionResult.value as Record<string, unknown>));
      } else {
        setOutcomes([]);
      }

      if (latestResult.status === 'fulfilled') {
        const state = latestResult.value as Record<string, unknown>;
        const nodeResults = state.nodeResults as Record<string, { outputSummary?: Record<string, unknown> }> | undefined;
        const summary =
          nodeResults?.replay_activity?.outputSummary
          || (state.metrics as Record<string, unknown> | undefined)
          || {};
        setLatestTick({
          executionId: state.execution_id as string | undefined,
          finishedAt: (state.finished_at as string | undefined) || (state.started_at as string | undefined),
          schedulerTrigger: Boolean(state.scheduler_trigger),
          metrics: summary,
          status: state.status as string | undefined,
        });
      } else {
        const err = latestResult.reason as { response?: { status?: number; data?: { detail?: string } }; message?: string };
        setLatestTick({
          missing: err?.response?.status === 404,
          error: typeof err?.response?.data?.detail === 'string' ? err.response.data.detail : err?.message,
          metrics: {},
        });
      }

      if (policyResult.status === 'fulfilled') {
        setOpenConsecutive(Number(policyResult.value.open_consecutive_points || 3));
        setCloseConsecutive(Number(policyResult.value.close_consecutive_points || 3));
      }

      if (statusResult.status === 'fulfilled') {
        setObsStatus(statusResult.value);
      }
      if (accResult.status === 'fulfilled') {
        setDailyAcc(accResult.value);
      } else {
        setDailyAcc(null);
      }
    } finally {
      setLoading(false);
    }
  }, [config, calendarRange]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await slotObservabilityApi.getStatus('pv_point');
        if (cancelled) return;
        setObsStatus(status);
        const from = status.window?.from;
        const to = status.window?.to;
        if (from && to) {
          setCalendarRange({ from, to });
        } else if (status.progress?.fed_days?.length) {
          const days = status.progress.fed_days;
          setCalendarRange({ from: days[0], to: days[days.length - 1] });
        }
      } catch {
        // 日历会回落到后端默认窗口
      } finally {
        if (!cancelled) setAnchorReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!anchorReady) return;
    void refresh();
  }, [refresh, refreshKey, anchorReady]);

  const replayPercent = useMemo(() => {
    if (!replaySession?.total) return 0;
    return Math.min(100, Math.round((replaySession.cursor / replaySession.total) * 10000) / 100);
  }, [replaySession]);

  const tickReason = latestTick?.metrics?.point_reason;
  const tickKind = latestTick?.metrics?.point_outcome_kind;
  const hasArtifactIssue = tickReason === 'artifact_load_failed';

  const windowedOutcomes = useMemo(() => {
    if (!calendarRange) return [];
    return outcomes.filter((item) => inCalendarWindow(outcomeStamp(item), calendarRange.from, calendarRange.to));
  }, [outcomes, calendarRange]);

  const windowMetrics = useMemo(() => computeWindowMetrics(windowedOutcomes), [windowedOutcomes]);

  const entityOptions = useMemo(() => {
    return [...new Set(windowedOutcomes.map((item) => String(item.entity_key || '')).filter(Boolean))].sort();
  }, [windowedOutcomes]);

  const defaultEntity = useMemo(() => {
    const withFault = entityOptions.find((key) =>
      windowedOutcomes.some((item) => item.entity_key === key && item.goldLabel != null && item.goldLabel !== 0),
    );
    return withFault || entityOptions[0] || '';
  }, [entityOptions, windowedOutcomes]);

  const chartRows = useMemo(() => {
    const key = chartDevice || defaultEntity;
    const rows = key ? windowedOutcomes.filter((item) => item.entity_key === key) : windowedOutcomes;
    return [...rows].sort((a, b) => String(a.point_time || '').localeCompare(String(b.point_time || '')));
  }, [windowedOutcomes, chartDevice, defaultEntity]);

  const demoAlarmSummary = useMemo(() => {
    if (!obsStatus?.demo || windowedOutcomes.length === 0) return null;
    return deriveDemoAlarms(windowedOutcomes, openConsecutive, closeConsecutive);
  }, [obsStatus?.demo, windowedOutcomes, openConsecutive, closeConsecutive]);

  const effectiveAlarms = demoAlarmSummary || alarmSummary;

  const windowedAlarmEvents = useMemo(() => {
    const events = effectiveAlarms?.recent_events || [];
    if (demoAlarmSummary) return events;
    if (!calendarRange) return [];
    return events.filter((item) => inCalendarWindow(item.point_time, calendarRange.from, calendarRange.to));
  }, [effectiveAlarms, calendarRange, demoAlarmSummary]);

  const avgConfidence = useMemo(() => {
    const values = chartRows
      .map((item) => item.confidence)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    if (values.length === 0) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }, [chartRows]);

  const resultChartOption = useMemo(() => {
    if (chartRows.length === 0) return null;
    const categories = chartRows.map((item) => formatAxisTime(String(outcomeStamp(item) || '')));
    const currentLine = chartRows.map((item) => (typeof item.iCal === 'number' ? Number(item.iCal.toFixed(3)) : null));
    const goldFault = chartRows.map((item, index) => (
      item.goldLabel != null && item.goldLabel !== 0 && typeof item.iCal === 'number'
        ? [index, Number(item.iCal.toFixed(3))]
        : null
    )).filter((point): point is [number, number] => point != null);
    const predFault = chartRows.map((item, index) => (
      item.label != null && item.label !== 0 && typeof item.iCal === 'number'
        ? [index, Number(item.iCal.toFixed(3))]
        : null
    )).filter((point): point is [number, number] => point != null);
    return {
      animationDuration: 200,
      tooltip: {
        trigger: 'axis',
        formatter: (params: Array<{ dataIndex?: number; axisValue?: string }>) => {
          const index = Number(params?.[0]?.dataIndex ?? 0);
          const row = chartRows[index];
          if (!row) return '';
          const time = formatAxisTime(String(outcomeStamp(row) || ''));
          const gold = row.goldLabel == null ? '—' : labelName(row.goldLabel);
          const pred = row.label == null ? '—' : labelName(row.label);
          const amp = typeof row.iCal === 'number' ? row.iCal.toFixed(2) : '—';
          return `${time}<br/>电流 ${amp}<br/>真值 ${gold}　预测 ${pred}`;
        },
      },
      legend: { top: 0 },
      grid: { left: 52, right: 24, top: 36, bottom: 48 },
      xAxis: { type: 'category', data: categories, axisLabel: { rotate: 35, fontSize: 10 } },
      yAxis: { type: 'value', name: '电流 i_cal', scale: true },
      series: [
        {
          name: '实测电流',
          type: 'line',
          data: currentLine,
          showSymbol: false,
          lineStyle: { width: 2, color: '#1677ff' },
          itemStyle: { color: '#1677ff' },
          z: 1,
        },
        {
          name: '真值故障',
          type: 'scatter',
          data: goldFault,
          symbol: 'diamond',
          symbolSize: 14,
          itemStyle: { color: '#389e0d' },
          // @AI_GENERATED
          tooltip: {
            formatter: (params: { dataIndex?: number }) => {
              const idx = Number(params?.dataIndex ?? 0);
              const row = chartRows.find((_r, i) => goldFault.some((gf) => gf[0] === i && i === idx));
              if (!row) {
                const gf = goldFault.find((_gf) => true);
                if (gf) {
                  const r2 = chartRows[gf[0]];
                  if (r2) return `真值 ${labelName(r2.goldLabel)} · 电流 ${r2.iCal?.toFixed(2) ?? '—'}`;
                }
                return '';
              }
              return `真值 ${labelName(row.goldLabel)} · 电流 ${row.iCal?.toFixed(2) ?? '—'}`;
            },
          },
          // @AI_GENERATED: end
          z: 3,
        },
        {
          name: '预测故障',
          type: 'scatter',
          data: predFault,
          symbolSize: 7,
          itemStyle: { color: '#fa8c16' },
          // @AI_GENERATED
          tooltip: {
            formatter: (params: { dataIndex?: number }) => {
              const idx = Number(params?.dataIndex ?? 0);
              const pf = predFault[idx];
              if (!pf) return '';
              const row = chartRows[pf[0]];
              if (!row) return '';
              return `预测 ${labelName(row.label)} · 电流 ${row.iCal?.toFixed(2) ?? '—'}`;
            },
          },
          // @AI_GENERATED: end
          z: 2,
        },
      ],
    };
  }, [chartRows]);

  const labelDistOption = useMemo(() => {
    if (windowedOutcomes.length === 0) return null;
    const counts = new Map<string, number>();
    for (const item of windowedOutcomes) {
      const key = item.kind === 'prediction' ? (labelNames[String(item.label ?? '')] || `label ${item.label ?? '—'}`) : String(item.kind || 'unknown');
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const entries = Array.from(counts.entries());
    return {
      animationDuration: 200,
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 16, top: 24, bottom: 32 },
      xAxis: { type: 'category', data: entries.map(([name]) => name) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [{ type: 'bar', data: entries.map(([, value]) => value), barMaxWidth: 36, itemStyle: { color: '#1677ff' } }],
    };
  }, [windowedOutcomes]);

  const alarmTimelineOption = useMemo(() => {
    const events = windowedAlarmEvents;
    if (events.length === 0) return null;
    return {
      animationDuration: 200,
      tooltip: {
        trigger: 'item',
        // @AI_GENERATED
        formatter: (params: { data?: { name?: string; value?: unknown[] }; dataIndex?: number }) => {
          const idx = Number(params?.dataIndex ?? 0);
          const ev = events[idx];
          if (!ev) return params?.data?.name || '';
          const evName = ALARM_EVENT_LABELS[String(ev.event_type)] || String(ev.event_type);
          const lbl = labelName(ev.label as number | null | undefined);
          const time = formatAxisTime(String(ev.point_time || ''));
          return `${evName}<br/>标签 ${lbl}<br/>${time}`;
        },
        // @AI_GENERATED: end
      },
      grid: { left: 88, right: 16, top: 16, bottom: 48 },
      xAxis: {
        type: 'category',
        data: events.map((item) => formatAxisTime(String(item.point_time || ''))),
        axisLabel: { rotate: 35, fontSize: 10 },
      },
      yAxis: { type: 'category', data: ['事件'] },
      series: [{
        type: 'scatter',
        symbolSize: 14,
        data: events.map((item, index) => ({
          value: [index, 0],
          name: ALARM_EVENT_LABELS[String(item.event_type)] || String(item.event_type),
          itemStyle: {
            color: String(item.event_type) === 'alarm_open'
              ? '#d48806'
              : String(item.event_type) === 'alarm_close'
                ? '#389e0d'
                : '#1677ff',
          },
        })),
      }],
    };
  }, [windowedAlarmEvents]);

  const handleSaveAlarmPolicy = async () => {
    const openValue = readAlarmInput('alarm-open-consecutive', openConsecutive);
    const closeValue = readAlarmInput('alarm-close-consecutive', closeConsecutive);
    setOpenConsecutive(openValue);
    setCloseConsecutive(closeValue);
    setSavingPolicy(true);
    try {
      const saved = await timeseriesReplayApi.updateAlarmPolicy('pv_point', {
        open_consecutive_points: openValue,
        close_consecutive_points: closeValue,
        label_switch_consecutive_points: openValue,
      });
      setOpenConsecutive(saved.open_consecutive_points);
      setCloseConsecutive(saved.close_consecutive_points);
      message.success(`已保存：连续 ${saved.open_consecutive_points} 个故障点开告警`);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      message.error(err.response?.data?.detail || err.message || '保存告警阈值失败');
    } finally {
      setSavingPolicy(false);
    }
  };

  const alarmColumns = [
    {
      title: '事件',
      dataIndex: 'event_type',
      key: 'event_type',
      render: (value: string) => ALARM_EVENT_LABELS[value] || value,
    },
    {
      title: '实体',
      dataIndex: 'entity_key',
      key: 'entity_key',
      ellipsis: true,
    },
    {
      title: '标签',
      dataIndex: 'label',
      key: 'label',
      width: 100,
      // @AI_GENERATED
      render: (value: number | null | undefined) => (value == null ? '—' : labelName(value)),
      // @AI_GENERATED: end
    },
    {
      title: '时间',
      dataIndex: 'point_time',
      key: 'point_time',
      ellipsis: true,
      render: (value: string) => formatAxisTime(value) || value || '—',
    },
  ];

  if (!config) return null;

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <FeedSourceCard
          slot="pv_point"
          progress={obsStatus}
          onChanged={() => {
            slotObservabilityApi.getStatus('pv_point').then(setObsStatus).catch(() => undefined);
          }}
        />
        <SlotOpsClockBar status={obsStatus} />
        <SlotAccuracyMetricsCard
          metrics={{
            day: calendarRange?.from === calendarRange?.to ? calendarRange?.from : `${calendarRange?.from || ''}～${calendarRange?.to || ''}`,
            countedUnits: windowMetrics.countedUnits || obsStatus?.accuracy?.counted_units,
            classifierAccuracy: windowMetrics.classifierAccuracy ?? obsStatus?.accuracy?.classifier_accuracy,
            macroF1: windowMetrics.macroF1 ?? obsStatus?.accuracy?.macro_f1,
            precision: windowMetrics.precision ?? obsStatus?.accuracy?.macro_precision,
            recall: windowMetrics.recall ?? obsStatus?.accuracy?.macro_recall,
            confirmCount: windowMetrics.confirmCount ?? obsStatus?.accuracy?.confirm_count,
            correctCount: windowMetrics.correctCount ?? obsStatus?.accuracy?.correct_count,
            note: '当前日历窗口内：预测 vs gold。命中=预测等于真值，纠错=预测被真值改掉。未写入累计。',
          }}
          latestDayAcc={dailyAcc?.latest?.classifier_accuracy ?? obsStatus?.accuracy?.classifier_accuracy}
          cumulativeAcc={dailyAcc?.cumulative?.classifier_accuracy}
          cumulativeDays={dailyAcc?.cumulative?.day_count}
          extra={(
            <Space wrap>
              <Link to={
                (dailyAcc?.latest?.review_id || obsStatus?.accuracy?.review_id)
                  ? `/iterative-labeling/review?review_id=${encodeURIComponent(String(dailyAcc?.latest?.review_id || obsStatus?.accuracy?.review_id))}&slot=pv_point`
                  : '/iterative-labeling?tab=pv_label&slot=pv_point'
              }>
                <Button size="small" type="primary" icon={<AuditOutlined />}>
                  {(dailyAcc?.latest?.review_id || obsStatus?.accuracy?.review_id) ? '打开当天审核' : '去审核工作台'}
                </Button>
              </Link>
              <Link to="/iterative-labeling?tab=pv_label&slot=pv_point">
                <Button size="small">审核列表</Button>
              </Link>
            </Space>
          )}
        />
        <SlotClassificationViz
          slot="pv_point"
          pairs={windowedOutcomes}
          byDay={dailyAcc?.by_day || []}
          latestReviewId={dailyAcc?.latest?.review_id || obsStatus?.accuracy?.review_id}
        />
        <Card size="small" title="到达 / 检测日历（只读）">
          <Paragraph type="secondary" style={{ marginBottom: 12, maxWidth: '72ch' }}>
            下面告警和检测曲线都跟这个日期窗口走。默认对齐调度页已经喂到的演示业务日，不是 gold 最晚一周。改区间后三块一起变。
            {calendarRange ? ` 当前 ${calendarRange.from}～${calendarRange.to}` : ''}
          </Paragraph>
          {anchorReady ? (
            <SlotObservabilityCalendar
              slot="pv_point"
              preferredRange={calendarRange || undefined}
              schedulerHref="/algorithm-deployment?slot=pv_point&tab=scheduler"
              onRangeChange={(from, to) => {
                setCalendarRange((prev) => (prev?.from === from && prev?.to === to ? prev : { from, to }));
              }}
            />
          ) : (
            <Spin />
          )}
        </Card>
        <Card
          size="small"
          title={
            <Space>
              <BellOutlined />
              <span>点路径日内滚动告警</span>
              <Tag color="blue">{demoAlarmSummary ? '演示检测推导' : 'G12'}</Tag>
              {calendarRange ? <Tag>{`${calendarRange.from}～${calendarRange.to}`}</Tag> : null}
            </Space>
          }
          extra={
            <Button icon={<ReloadOutlined />} size="small" onClick={() => void refresh()}>
              刷新
            </Button>
          }
        >
          {alarmError && !demoAlarmSummary ? (
            <Alert type="error" showIcon message="告警 API 不可用" description={alarmError} />
          ) : (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={8}>
                  <Text type="secondary">活跃告警</Text>
                  <div style={{ fontSize: 28, fontWeight: 600, color: (effectiveAlarms?.active_alarm_count || 0) > 0 ? '#d48806' : '#389e0d' }}>
                    {effectiveAlarms?.active_alarm_count ?? 0}
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <Text type="secondary">跟踪实体</Text>
                  <div style={{ fontSize: 28, fontWeight: 600 }}>{effectiveAlarms?.entity_count ?? 0}</div>
                </Col>
                <Col xs={24} sm={8}>
                  <Text type="secondary">最近事件</Text>
                  <div style={{ fontSize: 16, marginTop: 8 }}>
                    {windowedAlarmEvents[0]
                      ? `${ALARM_EVENT_LABELS[String(windowedAlarmEvents[0].event_type)] || windowedAlarmEvents[0].event_type}`
                      : '尚无'}
                  </div>
                </Col>
              </Row>
              {demoAlarmSummary && windowedAlarmEvents.length === 0 ? (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginTop: 12 }}
                  message="当天没有告警是对的"
                  description={`${calendarRange?.from || '该日'} 真值全是正常（label=0）。预测误报最长只连续 2 个点，开告警门槛是连续 ${openConsecutive} 个非 0，所以不会 open。`}
                />
              ) : null}
              <Space wrap style={{ marginTop: 12 }}>
                <Text type="secondary">连续故障点数开告警</Text>
                <InputNumber
                  min={1}
                  max={48}
                  value={openConsecutive}
                  data-testid="alarm-open-consecutive"
                  onChange={(value) => setOpenConsecutive(Number(value || 1))}
                />
                <Text type="secondary">连续正常点数关告警</Text>
                <InputNumber
                  min={1}
                  max={48}
                  value={closeConsecutive}
                  data-testid="alarm-close-consecutive"
                  onChange={(value) => setCloseConsecutive(Number(value || 1))}
                />
                <Button
                  size="small"
                  type="primary"
                  loading={savingPolicy}
                  data-testid="save-alarm-policy"
                  onClick={() => void handleSaveAlarmPolicy()}
                >
                  保存阈值
                </Button>
              </Space>
              {(effectiveAlarms?.active_alarms?.length || 0) > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginTop: 12 }}
                  message={`${effectiveAlarms?.active_alarm_count} 条活跃告警`}
                  description={
                    <Space direction="vertical" size={4}>
                      {(effectiveAlarms?.active_alarms || []).slice(0, 3).map((item) => (
                        <Text key={String(item.entity_key)}>
                          {String(item.entity_key)} · label={String(item.active_label)} · {String(item.active_alarm_id)}
                        </Text>
                      ))}
                    </Space>
                  }
                />
              )}
              {alarmTimelineOption && (
                <ReactECharts option={alarmTimelineOption} style={{ height: 160, marginTop: 8 }} />
              )}
              <Table
                style={{ marginTop: 12 }}
                size="small"
                rowKey={(row) => String(row.event_id || `${row.event_type}-${row.point_time}`)}
                columns={alarmColumns}
                dataSource={windowedAlarmEvents}
                pagination={{ pageSize: 5, hideOnSinglePage: true }}
                locale={{ emptyText: calendarRange ? `日历窗口 ${calendarRange.from}～${calendarRange.to} 内没有告警事件（连续 ${openConsecutive} 个非 0 标签才会 open）` : '尚无告警事件' }}
              />
            </>
          )}
        </Card>

        <Card
          size="small"
          title="滚动检测结果曲线（真值 + 预测）"
          extra={
            <Space>
              <Select
                size="small"
                style={{ minWidth: 220 }}
                placeholder="选择设备"
                value={chartDevice || defaultEntity}
                options={entityOptions.map((key) => ({ value: key, label: key }))}
                onChange={(value) => setChartDevice(String(value))}
              />
              <Text type="secondary">{calendarRange ? `${calendarRange.from}～${calendarRange.to} · ${chartRows.length} 点` : '等待日历窗口'}</Text>
            </Space>
          }
        >
          <Paragraph type="secondary" style={{ marginBottom: 12, maxWidth: '80ch' }}>
            蓝线是这台设备当天的实测电流。10:00–12:00 电流掉到 3–5 是真故障段（绿点）。橙点是规则把电流判成故障：掉谷里和绿点叠上是检出；电流还在 8 附近也出橙点是误报（阈值 7.8 偏紧）。
          </Paragraph>
          <Row gutter={[16, 16]} style={{ marginBottom: 12 }}>
            <Col xs={12} md={6}>
              <Text type="secondary">窗口全部点</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{windowedOutcomes.length}</div>
              <Text type="secondary" style={{ fontSize: 12 }}>3 台 × 当天点数</Text>
            </Col>
            <Col xs={12} md={6}>
              <Text type="secondary">当前设备点</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{chartRows.length}</div>
              <Text type="secondary" style={{ fontSize: 12 }}>下拉选中的这一台</Text>
            </Col>
            <Col xs={12} md={6}>
              <Text type="secondary">当前设备真值故障</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{chartRows.filter((item) => item.goldLabel != null && item.goldLabel !== 0).length}</div>
            </Col>
            <Col xs={12} md={6}>
              <Text type="secondary">平均置信度</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{avgConfidence === null ? '—' : avgConfidence.toFixed(3)}</div>
              <Text type="secondary" style={{ fontSize: 12 }}>离阈值越远越高，不是模型概率</Text>
            </Col>
          </Row>
          {resultChartOption ? (
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={16}>
                <ReactECharts option={resultChartOption} style={{ height: 320 }} />
              </Col>
              <Col xs={24} lg={8}>
                {labelDistOption && <ReactECharts option={labelDistOption} style={{ height: 280 }} />}
              </Col>
            </Row>
          ) : (
            <Alert
              type="info"
              showIcon
              message={calendarRange ? `日历窗口 ${calendarRange.from}～${calendarRange.to} 内没有检测点。` : '还没有检测点曲线。'}
              description="默认窗口对齐调度页已喂演示日。刷新本页即可拉演示检测点；没有点说明这一天还没推进。"
            />
          )}
          <Table
            style={{ marginTop: 12 }}
            size="small"
            rowKey={(row, index) => `${row.point_time || 't'}-${index}`}
            dataSource={[...windowedOutcomes].reverse()}
            pagination={{ pageSize: 8, hideOnSinglePage: true }}
            locale={{ emptyText: calendarRange ? `日历窗口 ${calendarRange.from}～${calendarRange.to} 内没有检测点` : '暂无检测结果' }}
            columns={[
              { title: '时间', dataIndex: 'point_time', ellipsis: true, render: (_value: string, row: ReplayOutcome) => formatAxisTime(String(outcomeStamp(row) || '')) || '—' },
              {
                title: '结果',
                dataIndex: 'kind',
                width: 160,
                render: (value: string, row: ReplayOutcome) => outcomeKindTag(value, row.reason),
              },
              { title: '预测', dataIndex: 'label', width: 72, render: (value: number | null) => (value === null || value === undefined ? '—' : labelName(value)) },
              { title: '真值', dataIndex: 'goldLabel', width: 72, render: (value: number | null) => (value === null || value === undefined ? '—' : labelName(value)) },
              {
                title: '置信度',
                dataIndex: 'confidence',
                width: 96,
                render: (value: number | null) => (typeof value === 'number' ? value.toFixed(3) : '—'),
              },
              { title: '实体', dataIndex: 'entity_key', ellipsis: true },
            ]}
          />
        </Card>

        <Collapse
          items={[{
            key: 'replay-debug',
            label: 'Replay 会话 / 最近 tick（调试，不是演示进度）',
            children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card size="small" title="Replay 会话进度">
              {replayError ? (
                <Alert type="info" showIcon message={replayError} />
              ) : replaySession ? (
                <Space direction="vertical" style={{ width: '100%' }} size={12}>
                  {replaySession.error && (
                    <Alert type="error" showIcon message="会话报错" description={replaySession.error} />
                  )}
                  <Descriptions size="small" column={1} bordered>
                    <Descriptions.Item label="session_id">{replaySession.session_id}</Descriptions.Item>
                    <Descriptions.Item label="status">
                      <Tag color={replaySession.status === 'running' ? 'processing' : replaySession.status === 'completed' ? 'success' : 'default'}>
                        {replaySession.status}
                      </Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="cursor / total">
                      {replaySession.cursor} / {replaySession.total}
                    </Descriptions.Item>
                    <Descriptions.Item label="model_ref">{replaySession.model_ref || '—'}</Descriptions.Item>
                  </Descriptions>
                  <Progress percent={replayPercent} size="small" status={replaySession.status === 'completed' ? 'success' : 'active'} />
                  {replaySession.status === 'completed' && (
                    <Alert
                      type="info"
                      showIcon
                      message="本轮 replay 已跑完"
                      description="下次调度触发会自动轮换新会话；也可在部署页手动再点「触发」。"
                    />
                  )}
                </Space>
              ) : null}
            </Card>
          </Col>

          <Col xs={24} lg={12}>
            <Card
              size="small"
              title="最近 replay tick"
              extra={
                latestTick?.schedulerTrigger ? <Tag color="gold">调度触发</Tag> : null
              }
            >
              {latestTick?.missing ? (
                <Alert
                  type="info"
                  showIcon
                  message="尚无 predict_replay 执行记录"
                  description="请到 算法部署 → pv_point → 定时调度，触发 pv_point_replay_tick。"
                  action={
                    <Link to="/algorithm-deployment?slot=pv_point&tab=scheduler">
                      <Button size="small" type="primary">去触发</Button>
                    </Link>
                  }
                />
              ) : (
                <Space direction="vertical" style={{ width: '100%' }} size={8}>
                  {hasArtifactIssue && (
                    <Alert
                      type="error"
                      showIcon
                      icon={<WarningOutlined />}
                      message="模型工件加载失败"
                      description="point_reason=artifact_load_failed：replay 无法产出 prediction，告警状态机不会 open。请确认 registry 中 artifact 路径有效且已修复 slot_minutes=0 兼容。"
                    />
                  )}
                  <Descriptions size="small" column={1} bordered>
                    <Descriptions.Item label="execution_id">{latestTick?.executionId || '—'}</Descriptions.Item>
                    <Descriptions.Item label="outcome">
                      {outcomeKindTag(tickKind, tickReason)}
                    </Descriptions.Item>
                    <Descriptions.Item label="point_label">{formatMetricValue('point_label', latestTick?.metrics?.point_label)}</Descriptions.Item>
                    <Descriptions.Item label="point_confidence">{formatMetricValue('point_confidence', latestTick?.metrics?.point_confidence)}</Descriptions.Item>
                    <Descriptions.Item label="alarm_phase">{String(latestTick?.metrics?.alarm_phase || '—')}</Descriptions.Item>
                    <Descriptions.Item label="cursor">{formatMetricValue('cursor', latestTick?.metrics?.cursor)}</Descriptions.Item>
                    <Descriptions.Item label="finished_at">{latestTick?.finishedAt || '—'}</Descriptions.Item>
                  </Descriptions>
                  <Link to="/algorithm-deployment?slot=pv_point&tab=scheduler">
                    <Button size="small" icon={<PlayCircleOutlined />}>部署页 · 定时调度</Button>
                  </Link>
                </Space>
              )}
            </Card>
          </Col>
        </Row>
            ),
          }]}
        />

        <Alert
          type="info"
          showIcon
          message="精度运营 vs 算法部署 vs 打标"
          description={
            <>
              本页只读：日历窗口和 Acc 跟调度页同一演示时钟。推进水位请到
              <Link to="/algorithm-deployment?slot=pv_point&tab=scheduler"> 定时调度 </Link>
              。演示自动审核不会写入累计账本。
            </>
          }
        />
      </Space>
    </Spin>
  );
};

export default PvPointAccuracyOpsPanel;
