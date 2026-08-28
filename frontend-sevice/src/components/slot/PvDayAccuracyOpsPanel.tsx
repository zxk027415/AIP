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
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { getSlotWorkflowConfig } from '../../config/slotProductConfig';
import { pipelineApi } from '../../services/workflowEnhancedApi';
import SlotObservabilityCalendar from './SlotObservabilityCalendar';

const { Paragraph } = Typography;

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

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') {
    if (key.includes('rate') || key.includes('coverage') || key.includes('accuracy') || key.includes('f1')) {
      return value <= 1 ? `${(value * 100).toFixed(2)}%` : value.toFixed(4);
    }
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value);
}

interface Props {
  refreshKey?: number;
}

const PvDayAccuracyOpsPanel: React.FC<Props> = ({ refreshKey = 0 }) => {
  const config = getSlotWorkflowConfig('pv_day');
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

  const refresh = useCallback(async () => {
    if (!config) return;
    setLoading(true);
    try {
      const state = await pipelineApi.getSlotLatestExecution('pv_day', 'predict');
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
      const statusCode = (err as { response?: { status?: number } })?.response?.status;
      if (statusCode === 404) {
        setMissing(true);
        setError(null);
        setTraces([]);
        setPredictionOverview(null);
      } else {
        setError((err as { message?: string })?.message || '日预测结果读取失败');
      }
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  const metrics = useMemo(() => collectMetrics(traces), [traces]);
  const failedNode = traces.find((node) => node.status === 'failed');
  const predictedCount = useMemo(() => {
    if (typeof predictionOverview?.n_predicted === 'number') return predictionOverview.n_predicted;
    const summary = traces
      .map((node) => node.summary.prediction_summary)
      .find((item) => item && typeof item === 'object') as { n_predicted?: number } | undefined;
    if (typeof summary?.n_predicted === 'number') return summary.n_predicted;
    const match = String(metrics.predictions || '').match(/DataFrame\[(\d+)/);
    return match ? Number(match[1]) : undefined;
  }, [predictionOverview, traces, metrics.predictions]);
  const labelCounts = useMemo(() => {
    if (predictionOverview?.label_counts && Object.keys(predictionOverview.label_counts).length) {
      return predictionOverview.label_counts;
    }
    const summary = traces
      .map((node) => node.summary.prediction_summary)
      .find((item) => item && typeof item === 'object') as { label_counts?: Record<string, number> } | undefined;
    return summary?.label_counts || {};
  }, [predictionOverview, traces]);
  const headline = [
    { title: '检测样本', value: predictedCount, isCount: true },
    { title: '平均置信度', value: predictionOverview?.confidence_mean },
  ].filter((item) => typeof item.value === 'number');

  const labelDistOption = useMemo(() => {
    const entries = Object.entries(labelCounts);
    if (entries.length === 0) return null;
    return {
      animationDuration: 200,
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 16, top: 24, bottom: 48 },
      xAxis: { type: 'category', data: entries.map(([key]) => `类别 ${key}`), axisLabel: { rotate: 25, fontSize: 10 } },
      yAxis: { type: 'value', minInterval: 1 },
      series: [{ type: 'bar', data: entries.map(([, value]) => value), barMaxWidth: 36, itemStyle: { color: '#1677ff' } }],
    };
  }, [labelCounts]);

  if (!config) return null;

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card size="small" title="到达 / 检测日历（只读）">
          <SlotObservabilityCalendar slot="pv_day" schedulerHref="/algorithm-deployment?slot=pv_day&tab=scheduler" />
        </Card>
        <Card
          size="small"
          title={
            <Space>
              <span>天路径按日滚动检测</span>
              <Tag color="blue">pv_day</Tag>
            </Space>
          }
          extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()}>刷新</Button>}
        >
          <Paragraph type="secondary" style={{ marginBottom: 12, maxWidth: '72ch' }}>
            定时任务按业务日跑预测。本页展示最近一次执行状态、节点流水线和能拿到的指标。打标不在这里；任务配置在算法部署 → 定时调度。
          </Paragraph>
          {error && status !== 'failed' ? (
            <Alert type="error" showIcon message={error} />
          ) : missing ? (
            <Alert
              type="info"
              showIcon
              message="还没有日预测记录"
              description="到算法部署页启动或触发 pv_day 日预测任务。"
              action={(
                <Link to="/algorithm-deployment?slot=pv_day&tab=scheduler">
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
                  description={failedNode?.error || error || '预测流水线中途失败，下面节点表可以看出卡在哪一步。本次没有可画的预测曲线。'}
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
            <Link to="/algorithm-deployment?slot=pv_day&tab=scheduler">
              <Button size="small">定时调度</Button>
            </Link>
            <Link to={`/algorithm-dev/workflow-editor/${config.predictWorkflowId}?slot=pv_day`}>
              <Button size="small">打开预测模板</Button>
            </Link>
          </Space>
        </Card>

        {!missing && (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={12}>
                <Card size="small" title="本次检测标签分布">
                  {labelDistOption ? (
                    <ReactECharts option={labelDistOption} style={{ height: 260 }} />
                  ) : (
                    <Alert
                      type="info"
                      showIcon
                      message={typeof predictedCount === 'number' ? `本次预测了 ${predictedCount} 个样本` : '这次执行还没有逐条预测分布'}
                      description="日预测没有当天真值，所以这里不是混淆矩阵；下次跑完检测后会显示各类预测计数。"
                    />
                  )}
                </Card>
              </Col>
              <Col xs={24} lg={12}>
                <Card size="small" title="预测流水线">
                  <Table
                    size="small"
                    rowKey="nodeId"
                    pagination={false}
                    dataSource={traces}
                    locale={{ emptyText: '暂无节点结果' }}
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
                        render: (_: unknown, row: NodeTrace) => row.error || formatValue('data', row.summary.data),
                      },
                    ]}
                  />
                </Card>
              </Col>
            </Row>
          </>
        )}

        <Alert
          type="info"
          showIcon
          message="精度运营 vs 算法部署 vs 打标"
          description={
            <>
              本页只看最近一次日预测（样本数、标签分布、流水线）。训练混淆矩阵在
              <Link to="/algorithm-deployment?slot=pv_day"> 算法部署 · 当前生产模型 </Link>
              ；无标签打标在
              <Link to="/iterative-labeling?tab=pv_label&slot=pv_day"> 人工标注审核 </Link>
              。
            </>
          }
        />
      </Space>
    </Spin>
  );
};

export default PvDayAccuracyOpsPanel;
