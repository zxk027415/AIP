/**
 * PvDayAccuracyOpsPanel — 天路径精度运营：最近一次按日预测结果、失败节点、指标卡。
 * 不含打标、Promote、闭环治理。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from 'antd';
import { AuditOutlined, ReloadOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { getSlotWorkflowConfig } from '../../config/slotProductConfig';
import { pipelineApi } from '../../services/workflowEnhancedApi';
import SlotObservabilityCalendar from './SlotObservabilityCalendar';
import SlotOpsClockBar from './SlotOpsClockBar';
import SlotAccuracyMetricsCard from './SlotAccuracyMetricsCard';
import SlotClassificationViz, { type ClassPair } from './SlotClassificationViz';
import FeedSourceCard from './FeedSourceCard';
import { slotObservabilityApi, type MockAccuracyView, type ObservabilityStatus } from '../../services/slotObservabilityApi';

const { Text, Paragraph } = Typography;

type DayOutcome = {
  kind?: string;
  label?: number | null;
  goldLabel?: number | null;
  confidence?: number | null;
  entity_key?: string;
  point_time?: string;
  iCal?: number | null;
};

function calendarDay(value: unknown): string {
  const text = String(value || '').trim();
  const match = text.match(/(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : '';
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

function mapDemoOutcomes(items: Array<Record<string, unknown>>): DayOutcome[] {
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

function collectMetrics(traces: NodeTrace[]): Record<string, unknown> {
  const metrics: Record<string, unknown> = {};
  for (const node of traces) {
    for (const [key, value] of Object.entries(node.summary)) {
      if (metrics[key] !== undefined) continue;
      if (value === null || value === undefined || value === '') continue;
      metrics[key] = value;
    }
  }
  return metrics;
}

interface Props {
  refreshKey?: number;
  slot?: string;
}

const PvDayAccuracyOpsPanel: React.FC<Props> = ({ refreshKey = 0, slot: slotProp = 'pv_day' }) => {
  const config = getSlotWorkflowConfig(slotProp);
  const [loading, setLoading] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | undefined>();
  const [executionId, setExecutionId] = useState<string | undefined>();
  const [workflowId, setWorkflowId] = useState<string | undefined>();
  const [finishedAt, setFinishedAt] = useState<string | undefined>();
  const [schedulerTrigger, setSchedulerTrigger] = useState(false);
  const [traces, setTraces] = useState<NodeTrace[]>([]);
  const [predictionOverview, setPredictionOverview] = useState<{
    n_predicted?: number;
    label_counts?: Record<string, number>;
    confidence_mean?: number;
  } | null>(null);
  const [modelId, setModelId] = useState<string | undefined>();
  const [obsStatus, setObsStatus] = useState<ObservabilityStatus | null>(null);
  const [calendarRange, setCalendarRange] = useState<{ from: string; to: string } | null>(null);
  const [anchorReady, setAnchorReady] = useState(false);
  const [dailyAcc, setDailyAcc] = useState<MockAccuracyView | null>(null);
  const [outcomes, setOutcomes] = useState<DayOutcome[]>([]);
  const [dailyUnits, setDailyUnits] = useState<DayOutcome[]>([]);
  const [chartDevice, setChartDevice] = useState<string>('');
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
    try {
      const from = calendarRange?.from;
      const to = calendarRange?.to;
      const [execResult, accResult, outcomesResult] = await Promise.allSettled([
        pipelineApi.getSlotLatestExecution(slotProp, 'predict'),
        slotObservabilityApi.getMockAccuracy(slotProp),
        slotObservabilityApi.getOutcomes(slotProp, from, to),
      ]);

      if (accResult.status === 'fulfilled') {
        setDailyAcc(accResult.value);
      } else {
        setDailyAcc(null);
      }
      if (outcomesResult.status === 'fulfilled') {
        setOutcomes(mapDemoOutcomes((outcomesResult.value.items || []) as Array<Record<string, unknown>>));
        setDailyUnits(mapDemoOutcomes((outcomesResult.value.daily_units || []) as Array<Record<string, unknown>>));
        // @AI_GENERATED
        const names = outcomesResult.value.label_names;
        if (names && typeof names === 'object') setLabelNames(names);
        // @AI_GENERATED: end
      } else {
        setOutcomes([]);
        setDailyUnits([]);
      }

      if (execResult.status === 'rejected') {
        const err = execResult.reason as { response?: { status?: number }; message?: string };
        if (err?.response?.status === 404) {
          setMissing(true);
          setError(null);
          setTraces([]);
          setPredictionOverview(null);
        } else {
          setError(err?.message || '日预测结果读取失败');
        }
        return;
      }

      const state = execResult.value;
      setMissing(false);
      setError((state?.error as string | undefined) || null);
      setStatus(state?.status as string | undefined);
      setExecutionId(state?.execution_id as string | undefined);
      setWorkflowId(state?.workflow_id as string | undefined);
      setFinishedAt((state?.finished_at || state?.started_at) as string | undefined);
      setSchedulerTrigger(Boolean(state?.scheduler_trigger));
      setTraces(collectNodeTraces(state?.nodeResults as Record<string, unknown> | undefined));
      const payloadMetrics = state?.metrics;
      const overview = state?.prediction_overview;
      setPredictionOverview(
        overview && typeof overview === 'object'
          ? overview as { n_predicted?: number; label_counts?: Record<string, number>; confidence_mean?: number }
          : null,
      );
      setModelId(
        (typeof state?.model_id === 'string' && state.model_id)
        || (typeof (payloadMetrics as { model_id?: string } | null)?.model_id === 'string'
          ? (payloadMetrics as { model_id?: string }).model_id
          : undefined),
      );
    } catch (err: unknown) {
      setError((err as { message?: string })?.message || '日预测结果读取失败');
    } finally {
      setLoading(false);
    }
  }, [config, calendarRange]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await slotObservabilityApi.getStatus(slotProp);
        if (cancelled) return;
        setObsStatus(status);
        const from = status.window?.from;
        const to = status.window?.to;
        if (from && to) setCalendarRange({ from, to });
      } catch {
        // 日历回落后端默认窗口
      } finally {
        if (!cancelled) setAnchorReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  useEffect(() => {
    if (!anchorReady) return;
    void refresh();
  }, [refresh, refreshKey, anchorReady]);

  const metrics = useMemo(() => collectMetrics(traces), [traces]);
  const windowedOutcomes = useMemo(() => {
    if (!calendarRange) return [];
    return outcomes.filter((item) => inCalendarWindow(item.point_time, calendarRange.from, calendarRange.to));
  }, [outcomes, calendarRange]);
  const windowedDailyUnits = useMemo(() => {
    if (!calendarRange) return [];
    return dailyUnits.filter((item) => inCalendarWindow(item.point_time, calendarRange.from, calendarRange.to));
  }, [dailyUnits, calendarRange]);
  const windowPairs: ClassPair[] = useMemo(
    () => windowedDailyUnits.map((item) => ({ goldLabel: item.goldLabel ?? null, label: item.label ?? null })),
    [windowedDailyUnits],
  );
  const windowMetrics = useMemo(() => {
    const pairs = windowPairs.filter((item) => item.goldLabel != null && item.label != null);
    const counted = pairs.length;
    const confirm = pairs.filter((item) => item.label === item.goldLabel).length;
    return {
      countedUnits: counted,
      classifierAccuracy: counted ? confirm / counted : null,
      confirmCount: confirm,
      correctCount: counted - confirm,
    };
  }, [windowPairs]);
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
  const avgConfidence = useMemo(() => {
    const values = chartRows
      .map((item) => item.confidence)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    if (values.length === 0) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }, [chartRows]);
  const resultChartOption = useMemo(() => {
    if (chartRows.length === 0) return null;
    const categories = chartRows.map((item) => formatAxisTime(String(item.point_time || '')));
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
        formatter: (params: Array<{ dataIndex?: number }>) => {
          const index = Number(params?.[0]?.dataIndex ?? 0);
          const row = chartRows[index];
          if (!row) return '';
          const time = formatAxisTime(String(row.point_time || ''));
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
              const gf = goldFault[Number(params?.dataIndex ?? 0)];
              if (!gf) return '';
              const row = chartRows[gf[0]];
              if (!row) return '';
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
              const pf = predFault[Number(params?.dataIndex ?? 0)];
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
  const outcomeLabelDistOption = useMemo(() => {
    if (windowedOutcomes.length === 0) return null;
    const counts = new Map<string, number>();
    for (const item of windowedOutcomes) {
      const key = labelNames[String(item.label ?? '')] || `label ${item.label ?? '—'}`;
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
  const latestReviewId = dailyAcc?.latest?.review_id || obsStatus?.accuracy?.review_id;
  const failedNode = traces.find((node) => node.status === 'failed');
  const predictedCount = useMemo(() => {
    if (typeof predictionOverview?.n_predicted === 'number') return predictionOverview.n_predicted;
    const summary = traces
      .map((node) => node.summary.prediction_summary)
      .find((item) => item && typeof item === 'object') as { n_predicted?: number } | undefined;
    if (typeof summary?.n_predicted === 'number') return summary.n_predicted;
    const match = String(metrics.predictions || '').match(/DataFrame\[(\d+)/);
    return match ? Number(match[1]) : (windowedOutcomes.length || undefined);
  }, [predictionOverview, traces, metrics.predictions, windowedOutcomes.length]);
  const headline = [
    { title: '检测样本', value: predictedCount, isCount: true },
    { title: '平均置信度', value: predictionOverview?.confidence_mean },
  ].filter((item) => typeof item.value === 'number');

  if (!config) return null;

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <FeedSourceCard
          slot="pv_day"
          progress={obsStatus}
          onChanged={() => {
            slotObservabilityApi.getStatus('pv_day').then(setObsStatus).catch(() => undefined);
          }}
        />
        <SlotOpsClockBar status={obsStatus} />
        <SlotAccuracyMetricsCard
          metrics={{
            day: calendarRange?.from === calendarRange?.to
              ? (calendarRange?.from || obsStatus?.accuracy?.day || obsStatus?.clock?.day)
              : `${calendarRange?.from || ''}～${calendarRange?.to || ''}`,
            countedUnits: windowMetrics.countedUnits || obsStatus?.accuracy?.counted_units,
            classifierAccuracy: windowMetrics.classifierAccuracy ?? obsStatus?.accuracy?.classifier_accuracy,
            macroF1: dailyAcc?.latest?.macro_f1 ?? obsStatus?.accuracy?.macro_f1,
            precision: dailyAcc?.latest?.macro_precision ?? obsStatus?.accuracy?.macro_precision,
            recall: dailyAcc?.latest?.macro_recall ?? obsStatus?.accuracy?.macro_recall,
            confirmCount: windowMetrics.countedUnits ? windowMetrics.confirmCount : obsStatus?.accuracy?.confirm_count,
            correctCount: windowMetrics.countedUnits ? windowMetrics.correctCount : obsStatus?.accuracy?.correct_count,
            note: '天路径 Acc 按设备-日（每天约 3 台），不是点路径那套按 5 分钟点计。下面曲线仍是日内点，方便对照形态。未写入累计账本。',
          }}
          latestDayAcc={windowMetrics.classifierAccuracy ?? dailyAcc?.latest?.classifier_accuracy ?? obsStatus?.accuracy?.classifier_accuracy}
          cumulativeAcc={windowMetrics.classifierAccuracy ?? dailyAcc?.cumulative?.classifier_accuracy}
          cumulativeDays={dailyAcc?.cumulative?.day_count}
          extra={(
            <Space wrap>
              <Link to={
                latestReviewId
                  ? `/iterative-labeling/review?review_id=${encodeURIComponent(latestReviewId)}&slot=${encodeURIComponent(slotProp)}`
                  : `/iterative-labeling?tab=pv_label&slot=${encodeURIComponent(slotProp)}`
              }>
                <Button size="small" type="primary" icon={<AuditOutlined />}>
                  {latestReviewId ? '打开当天审核' : '去审核工作台'}
                </Button>
              </Link>
              <Link to={`/iterative-labeling?tab=pv_label&slot=${encodeURIComponent(slotProp)}`}>
                <Button size="small">审核列表</Button>
              </Link>
            </Space>
          )}
        />
        <SlotClassificationViz
          slot={slotProp}
          pairs={windowPairs}
          byDay={dailyAcc?.by_day || []}
          latestReviewId={latestReviewId}
        />
        <Card size="small" title="到达 / 检测日历（只读）">
          {anchorReady ? (
            <SlotObservabilityCalendar
              slot={slotProp}
              schedulerHref={`/algorithm-deployment?slot=${encodeURIComponent(slotProp)}&tab=scheduler`}
              preferredRange={calendarRange || undefined}
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
              <span>天路径按日滚动检测</span>
              <Tag color="blue">{slotProp}</Tag>
            </Space>
          }
          extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()}>刷新</Button>}
        >
          <Paragraph type="secondary" style={{ marginBottom: 12, maxWidth: '72ch' }}>
            定时任务按业务日跑预测。本页日历和 Acc 跟调度页同一演示时钟。演示自动审核不算 gold holdout，也不会写入累计。打标不在这里；推进水位在算法部署 → 定时调度。
          </Paragraph>
          {error && status !== 'failed' ? (
            <Alert type="error" showIcon message={error} />
          ) : missing ? (
            <Alert
              type="info"
              showIcon
              message="还没有日预测记录"
              description={`到算法部署页启动或触发 ${slotProp} 日预测任务。`}
              action={(
                <Link to={`/algorithm-deployment?slot=${encodeURIComponent(slotProp)}&tab=scheduler`}>
                  <Button size="small" type="primary">去定时调度</Button>
                </Link>
              )}
            />
          ) : (
            <>
              {status === 'failed' && (
                <Alert
                  type="error"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="最近一次日预测失败"
                  description={failedNode?.error || error || '最近一次日预测失败。下面仍可看演示检测曲线（若当天已喂数）。'}
                />
              )}
              {headline.length > 0 && (
                <Row gutter={[16, 16]} style={{ marginBottom: 12 }}>
                  {headline.map((item) => (
                    <Col xs={12} md={6} key={item.title}>
                      <Statistic
                        title={item.title}
                        value={item.value as number}
                        precision={'isCount' in item && item.isCount ? 0 : 4}
                      />
                    </Col>
                  ))}
                </Row>
              )}
              <Descriptions size="small" column={2} bordered>
                <Descriptions.Item label="状态">
                  <Space>
                    {schedulerTrigger ? <Tag color="gold">调度触发</Tag> : null}
                    <Tag color={status === 'success' ? 'success' : status === 'failed' ? 'error' : 'processing'}>
                      {status || '未知'}
                    </Tag>
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="workflow">{workflowId || config.predictWorkflowId}</Descriptions.Item>
                <Descriptions.Item label="execution_id" span={2}>{executionId || '—'}</Descriptions.Item>
                <Descriptions.Item label="检测模型" span={2}>{modelId || '—'}</Descriptions.Item>
                <Descriptions.Item label="finished_at" span={2}>{finishedAt || '—'}</Descriptions.Item>
              </Descriptions>
            </>
          )}
          <Space style={{ marginTop: 12 }}>
            <Link to={`/algorithm-deployment?slot=${encodeURIComponent(slotProp)}&tab=scheduler`}>
              <Button size="small">定时调度</Button>
            </Link>
            <Link to={`/algorithm-dev/workflow-editor/${config.predictWorkflowId}?slot=${encodeURIComponent(slotProp)}`}>
              <Button size="small">打开预测模板</Button>
            </Link>
          </Space>
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
                value={chartDevice || defaultEntity || undefined}
                options={entityOptions.map((key) => ({ value: key, label: key }))}
                onChange={(value) => setChartDevice(String(value))}
              />
              <Text type="secondary">{calendarRange ? `${calendarRange.from}～${calendarRange.to} · ${chartRows.length} 点` : '等待日历窗口'}</Text>
            </Space>
          }
        >
          <Paragraph type="secondary" style={{ marginBottom: 12, maxWidth: '80ch' }}>
            和点路径同一套 mock：蓝线是这台设备当天的实测电流。绿色菱形是真值故障段，橙色圆点是模型预测故障段。推进水位在算法部署 → 定时调度。
          </Paragraph>
          <Row gutter={[16, 16]} style={{ marginBottom: 12 }}>
            <Col xs={12} md={6}>
              <Text type="secondary">窗口全部点</Text>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{windowedOutcomes.length}</div>
              <Text type="secondary" style={{ fontSize: 12 }}>3 台 × 当天点数</Text>
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
                {outcomeLabelDistOption && <ReactECharts option={outcomeLabelDistOption} style={{ height: 280 }} />}
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
        </Card>

        <Alert
          type="info"
          showIcon
          message="精度运营 vs 算法部署 vs 打标"
          description={
            <>
              本页日历、窗口 Acc、混淆矩阵跟调度页同一演示时钟。推进水位请到
              <Link to={`/algorithm-deployment?slot=${encodeURIComponent(slotProp)}&tab=scheduler`}> 定时调度 </Link>
              。「打开当天审核」进入最近一次演示会话。演示自动审核不会写入累计账本。
            </>
          }
        />
      </Space>
    </Spin>
  );
};

export default PvDayAccuracyOpsPanel;
