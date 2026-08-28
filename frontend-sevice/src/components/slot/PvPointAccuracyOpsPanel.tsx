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
  Descriptions,
  InputNumber,
  Progress,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  BellOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { getSlotWorkflowConfig } from '../../config/slotProductConfig';
import { pipelineApi } from '../../services/workflowEnhancedApi';
import SlotObservabilityCalendar from './SlotObservabilityCalendar';
import {
  timeseriesReplayApi,
  type PointAlarmSummary,
} from '../../services/timeseriesReplayApi';

const { Text, Paragraph } = Typography;

const DEFAULT_REPLAY_SESSION_ID = 'sched-pv_point-default';

type ReplayOutcome = {
  kind?: string;
  label?: number | null;
  confidence?: number | null;
  reason?: string | null;
  entity_key?: string;
  point_time?: string;
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

function formatAxisTime(value: string | undefined): string {
  if (!value) return '';
  const text = String(value);
  if (text.includes('T')) {
    const datePart = text.slice(0, 10);
    const timePart = text.slice(11, 16);
    return `${datePart.slice(5)} ${timePart}`;
  }
  return text.slice(0, 16);
}

function pickOutcomes(body: Record<string, unknown>): ReplayOutcome[] {
  const raw = body.recent_outcomes || body.outcomes;
  return Array.isArray(raw) ? (raw as ReplayOutcome[]) : [];
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

  const refresh = useCallback(async () => {
    if (!config) return;
    setLoading(true);
    setAlarmError(null);
    setReplayError(null);
    try {
      const [alarmsResult, sessionResult, latestResult, policyResult] = await Promise.allSettled([
        timeseriesReplayApi.getAlarmSummary('pv_point'),
        timeseriesReplayApi.getReplaySession(DEFAULT_REPLAY_SESSION_ID),
        pipelineApi.getSlotLatestExecution('pv_point', 'predict_replay'),
        timeseriesReplayApi.getAlarmPolicy('pv_point'),
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
        setOutcomes(pickOutcomes(body));
      } else {
        setReplaySession(null);
        setOutcomes([]);
        setReplayError('replay 会话尚未创建；请先在部署页触发 pv_point_replay_tick');
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
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  const replayPercent = useMemo(() => {
    if (!replaySession?.total) return 0;
    return Math.min(100, Math.round((replaySession.cursor / replaySession.total) * 10000) / 100);
  }, [replaySession]);

  const tickReason = latestTick?.metrics?.point_reason;
  const tickKind = latestTick?.metrics?.point_outcome_kind;
  const hasArtifactIssue = tickReason === 'artifact_load_failed';

  const predictionCount = outcomes.filter((item) => item.kind === 'prediction').length;
  const noDecisionCount = outcomes.filter((item) => item.kind === 'no_decision').length;
  const avgConfidence = useMemo(() => {
    const values = outcomes
      .map((item) => item.confidence)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    if (values.length === 0) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }, [outcomes]);

  const resultChartOption = useMemo(() => {
    if (outcomes.length === 0) return null;
    const categories = outcomes.map((item) => formatAxisTime(item.point_time));
    return {
      animationDuration: 200,
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 48, right: 24, top: 36, bottom: 48 },
      xAxis: { type: 'category', data: categories, axisLabel: { rotate: 35, fontSize: 10 } },
      yAxis: [
        { type: 'value', name: '置信度', min: 0, max: 1, axisLabel: { formatter: (v: number) => `${Math.round(v * 100)}%` } },
        { type: 'value', name: '标签', minInterval: 1 },
      ],
      series: [
        {
          name: '置信度',
          type: 'line',
          yAxisIndex: 0,
          data: outcomes.map((item) => (typeof item.confidence === 'number' ? Number(item.confidence.toFixed(4)) : null)),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: '#1677ff' },
          itemStyle: { color: '#1677ff' },
        },
        {
          name: '预测标签',
          type: 'line',
          yAxisIndex: 1,
          step: 'end',
          data: outcomes.map((item) => (item.label === null || item.label === undefined ? null : Number(item.label))),
          showSymbol: true,
          symbolSize: 6,
          lineStyle: { width: 1.5, color: '#fa8c16' },
          itemStyle: { color: '#fa8c16' },
        },
      ],
    };
  }, [outcomes]);

  const labelDistOption = useMemo(() => {
    if (outcomes.length === 0) return null;
    const counts = new Map<string, number>();
    for (const item of outcomes) {
      const key = item.kind === 'prediction' ? `label ${item.label ?? '—'}` : String(item.kind || 'unknown');
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
  }, [outcomes]);

  const alarmTimelineOption = useMemo(() => {
    const events = alarmSummary?.recent_events || [];
    if (events.length === 0) return null;
    return {
      animationDuration: 200,
      tooltip: { trigger: 'item' },
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
  }, [alarmSummary]);

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
      width: 72,
    },
    {
      title: '时间',
      dataIndex: 'point_time',
      key: 'point_time',
      ellipsis: true,
    },
  ];

  if (!config) return null;

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card size="small" title="到达 / 检测日历（只读）">
          <SlotObservabilityCalendar slot="pv_point" schedulerHref="/algorithm-deployment?slot=pv_point&tab=scheduler" />
        </Card>
        <Card
          size="small"
          title={
            <Space>
              <BellOutlined />
              <span>点路径日内滚动告警</span>
              <Tag color="blue">G12</Tag>
            </Space>
          }
          extra={
            <Button icon={<ReloadOutlined />} size="small" onClick={() => void refresh()}>
              刷新
            </Button>
          }
        >
          {alarmError ? (
            <Alert type="error" showIcon message="告警 API 不可用" description={alarmError} />
          ) : (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={8}>
                  <Text type="secondary">活跃告警</Text>
                  <div style={{ fontSize: 28, fontWeight: 600, color: (alarmSummary?.active_alarm_count || 0) > 0 ? '#d48806' : '#389e0d' }}>
                    {alarmSummary?.active_alarm_count ?? 0}
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <Text type="secondary">跟踪实体</Text>
                  <div style={{ fontSize: 28, fontWeight: 600 }}>{alarmSummary?.entity_count ?? 0}</div>
                </Col>
                <Col xs={24} sm={8}>
                  <Text type="secondary">最近事件</Text>
                  <div style={{ fontSize: 16, marginTop: 8 }}>
                    {alarmSummary?.recent_events?.[0]
                      ? `${ALARM_EVENT_LABELS[String(alarmSummary.recent_events[0].event_type)] || alarmSummary.recent_events[0].event_type}`
                      : '尚无'}
                  </div>
                </Col>
              </Row>
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
              {(alarmSummary?.active_alarms?.length || 0) > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginTop: 12 }}
                  message={`${alarmSummary?.active_alarm_count} 条活跃告警`}
                  description={
                    <Space direction="vertical" size={4}>
                      {(alarmSummary?.active_alarms || []).slice(0, 3).map((item) => (
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
                dataSource={alarmSummary?.recent_events || []}
                pagination={{ pageSize: 5, hideOnSinglePage: true }}
                locale={{ emptyText: '尚无告警事件；需 replay 产出 prediction 且连续 fault 点才会 open' }}
              />
            </>
          )}
        </Card>

        <Card
          size="small"
          title="滚动检测结果曲线"
          extra={<Text type="secondary">最近 {outcomes.length} 个点</Text>}
        >
          <Paragraph type="secondary" style={{ marginBottom: 12, maxWidth: '72ch' }}>
            来自当前 replay 会话的最近检测点：标签、置信度、prediction / no_decision 分布。不是训练 MAPE，也不是打标提案。
          </Paragraph>
          <Row gutter={[16, 16]} style={{ marginBottom: 12 }}>
            <Col xs={12} md={6}>
              <Text type="secondary">检测点</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{replaySession?.outcome_count ?? outcomes.length}</div>
            </Col>
            <Col xs={12} md={6}>
              <Text type="secondary">prediction</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{predictionCount}</div>
            </Col>
            <Col xs={12} md={6}>
              <Text type="secondary">no_decision</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{noDecisionCount}</div>
            </Col>
            <Col xs={12} md={6}>
              <Text type="secondary">平均置信度</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{avgConfidence === null ? '—' : avgConfidence.toFixed(3)}</div>
            </Col>
          </Row>
          {resultChartOption ? (
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={16}>
                <ReactECharts option={resultChartOption} style={{ height: 280 }} />
              </Col>
              <Col xs={24} lg={8}>
                {labelDistOption && <ReactECharts option={labelDistOption} style={{ height: 280 }} />}
              </Col>
            </Row>
          ) : (
            <Alert type="info" showIcon message="还没有检测点曲线。触发 replay tick 后会出现标签和置信度。" />
          )}
          <Table
            style={{ marginTop: 12 }}
            size="small"
            rowKey={(row, index) => `${row.point_time || 't'}-${index}`}
            dataSource={[...outcomes].reverse()}
            pagination={{ pageSize: 8, hideOnSinglePage: true }}
            locale={{ emptyText: '暂无检测结果' }}
            columns={[
              { title: '时间', dataIndex: 'point_time', ellipsis: true, render: (value: string) => formatAxisTime(value) || '—' },
              {
                title: '结果',
                dataIndex: 'kind',
                width: 160,
                render: (value: string, row: ReplayOutcome) => outcomeKindTag(value, row.reason),
              },
              { title: '标签', dataIndex: 'label', width: 72, render: (value: number | null) => (value === null || value === undefined ? '—' : value) },
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

        <Alert
          type="info"
          showIcon
          message="精度运营 vs 算法部署 vs 打标"
          description={
            <>
              本页只看 <Text code>replay tick</Text>、结果曲线与日内告警。
              模型、标签空间和训练指标在
              <Link to="/algorithm-deployment?slot=pv_point"> 算法部署 </Link>
              ；无标签打标在
              <Link to="/iterative-labeling?tab=pv_label&slot=pv_point"> 人工标注审核 </Link>
              。
            </>
          }
        />
      </Space>
    </Spin>
  );
};

export default PvPointAccuracyOpsPanel;
