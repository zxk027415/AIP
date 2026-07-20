// @AI_GENERATED: pv-fault-prediction-evidence
/**
 * PvFaultPredictionEvidencePanel.tsx
 *
 * 精度运营页的光伏预测结果证据面板。展示调度回执、预测批次列表、时间窗、
 * 样本预测表与基于人工裁决的混淆矩阵，用于核对“触发预测是否真正写出批次”。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { QuestionCircleOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  schedulerTaskApi,
  type PvPredictionCursorStatusResponse,
  type ScheduledTaskSummary,
} from '../../services/deploymentApi';
import { trainingWorkspaceApi } from '../../services/iterativeLabelingApi';
import PvFaultClassificationMetrics, {
  type PvClassificationMetrics,
} from '../../components/pv-fault/PvFaultClassificationMetrics';

const { Text, Paragraph } = Typography;

interface PredictionBatchSummary {
  batch_id: string;
  model_ref?: string | null;
  prediction_count?: number;
  created_at?: string | null;
  time_window_min?: string | null;
  time_window_max?: string | null;
  label_distribution?: Record<string, number>;
  confidence_distribution?: Record<string, number>;
}

interface PredictionSample {
  site_id?: string;
  device_id?: string;
  branch_id?: string;
  time_window?: string;
  predicted_label?: number;
  confidence?: number | null;
}

interface SlotOverviewPayload {
  model_ref?: string | null;
  prediction_summary?: { total_batches?: number; total_predictions?: number };
  prediction_batches?: PredictionBatchSummary[];
  latest_prediction_detail?: PredictionBatchSummary & {
    dataset_version?: string | null;
    sample_predictions?: PredictionSample[];
    label_distribution?: Record<string, number>;
    confidence_distribution?: Record<string, number>;
  } | null;
  batch_label_distribution?: Record<string, number>;
  batch_confidence_distribution?: Record<string, number>;
  quality_metrics?: PvClassificationMetrics | null;
}

interface PvFaultPredictionEvidencePanelProps {
  slot: string;
  refreshing?: boolean;
}

function parseDateTime(value: string | null | undefined, assumeUtc = false): Date | null {
  if (!value) return null;
  const hasTimeZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  const normalized = assumeUtc && !hasTimeZone ? `${value}Z` : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value: string | null | undefined, assumeUtc = false): string {
  if (!value) return '暂无';
  const date = parseDateTime(value, assumeUtc);
  return date ? date.toLocaleString('zh-CN', { hour12: false }) : value;
}

function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function helpTitle(label: string, tip: string): React.ReactNode {
  return (
    <Space size={4}>
      <span>{label}</span>
      <Tooltip title={tip}>
        <QuestionCircleOutlined style={{ color: '#94a3b8' }} />
      </Tooltip>
    </Space>
  );
}

function statusText(result: string | null | undefined): string {
  if (result === 'success') return '已完成';
  if (result === 'failed') return '失败';
  if (result === 'skipped') return '已跳过';
  return '无记录';
}

const PvFaultPredictionEvidencePanel: React.FC<PvFaultPredictionEvidencePanelProps> = ({
  slot,
  refreshing,
}) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [overview, setOverview] = useState<SlotOverviewPayload | null>(null);
  const [predictionTask, setPredictionTask] = useState<ScheduledTaskSummary | null>(null);
  const [cursorStatus, setCursorStatus] = useState<PvPredictionCursorStatusResponse | null>(null);
  const [resettingCursor, setResettingCursor] = useState(false);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [batchDetail, setBatchDetail] = useState<(PredictionBatchSummary & {
    sample_predictions?: PredictionSample[];
    predictions?: PredictionSample[];
    quality_metrics?: PvClassificationMetrics | null;
    ground_truth_summary?: {
      has_ground_truth?: boolean;
      counted_units?: number;
      pending_ground_truth_units?: number;
      coverage_rate?: number | null;
    };
  }) | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const [overviewResp, tasksResp, cursorResp] = await Promise.all([
        trainingWorkspaceApi.getSlotOverview(slot),
        schedulerTaskApi.listScheduledTasks().catch(() => ({ tasks: [] as ScheduledTaskSummary[] })),
        schedulerTaskApi.getPvPredictionCursorStatus().catch(() => null),
      ]);
      const payload = overviewResp as SlotOverviewPayload;
      setOverview(payload);
      setPredictionTask(
        (tasksResp.tasks ?? []).find((task) => task.task_id === 'pv_prediction') ?? null,
      );
      setCursorStatus(cursorResp);
      const latestRunBatch = cursorResp?.last_run?.status === 'success'
        ? cursorResp.last_run.batch_id
        : null;
      const preferred = latestRunBatch
        ?? payload.latest_prediction_detail?.batch_id
        ?? payload.prediction_batches?.[0]?.batch_id
        ?? null;
      setSelectedBatchId((current) => latestRunBatch ?? current ?? preferred);
      if (payload.latest_prediction_detail) {
        setBatchDetail(payload.latest_prediction_detail);
      }
    } catch {
      setOverview(null);
      setPredictionTask(null);
      setCursorStatus(null);
    } finally {
      setLoading(false);
    }
  }, [slot]);

  const loadBatchDetail = useCallback(async (batchId: string) => {
    setDetailLoading(true);
    setBatchDetail(null);
    try {
      const detail = await trainingWorkspaceApi.getPredictionBatch(batchId, slot);
      setBatchDetail(detail as any);
    } catch {
      setBatchDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, [slot]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (refreshing) void loadOverview();
  }, [refreshing, loadOverview]);

  useEffect(() => {
    if (!selectedBatchId) return;
    if (overview?.latest_prediction_detail?.batch_id === selectedBatchId && overview.latest_prediction_detail) {
      setBatchDetail(overview.latest_prediction_detail);
      return;
    }
    void loadBatchDetail(selectedBatchId);
  }, [selectedBatchId, overview, loadBatchDetail]);

  const batches = overview?.prediction_batches ?? [];
  const samples = batchDetail?.sample_predictions
    ?? batchDetail?.predictions?.slice(0, 50)
    ?? [];
  const selectedQuality = selectedBatchId
    ? batchDetail?.quality_metrics
    : overview?.quality_metrics;
  const groundTruthSummary = batchDetail?.ground_truth_summary;
  const truthCoverage = groundTruthSummary?.coverage_rate == null
    ? null
    : Math.round(groundTruthSummary.coverage_rate * 1000) / 10;
  const batchLabels = batchDetail?.label_distribution
    ?? overview?.batch_label_distribution
    ?? {};
  const batchConfidence = batchDetail?.confidence_distribution
    ?? overview?.batch_confidence_distribution
    ?? {};

  const scheduleGapAlert = useMemo(() => {
    const lastRun = cursorStatus?.last_run;
    if (lastRun?.status === 'skipped' && lastRun.message) {
      return lastRun.message;
    }
    if (!predictionTask?.last_execution_time) return null;
    const latestBatchId = overview?.latest_prediction_detail?.batch_id
      ?? batches[0]?.batch_id
      ?? null;
    if (lastRun?.status === 'success' && lastRun.batch_id) {
      if (lastRun.batch_id === latestBatchId) return null;
      return `预测任务已成功写出 ${lastRun.batch_id}，但结果列表最新批次仍为 ${latestBatchId ?? '暂无'}，请刷新结果索引。`;
    }
    const latestCreated = overview?.latest_prediction_detail?.created_at
      ?? batches[0]?.created_at
      ?? null;
    const runAt = parseDateTime(predictionTask.last_execution_time)?.getTime() ?? NaN;
    const batchAt = parseDateTime(latestCreated, true)?.getTime() ?? NaN;
    if (Number.isNaN(runAt)) return null;
    if (predictionTask.last_execution === 'success' && (Number.isNaN(batchAt) || runAt - batchAt > 60_000)) {
      return `预测任务已于 ${formatDateTime(predictionTask.last_execution_time)} 执行，但最新保存结果仍为 ${formatDateTime(latestCreated, true)}。常见原因：本次无新增待预测数据，或数据源时间线与预测游标不一致。`;
    }
    return null;
  }, [predictionTask, overview, batches, cursorStatus]);

  const handleResetCursor = async () => {
    setResettingCursor(true);
    try {
      const resp = await schedulerTaskApi.resetPvPredictionCursor();
      message.success(resp.message || '预测进度已重置');
      await loadOverview();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err?.message || '重置失败');
    } finally {
      setResettingCursor(false);
    }
  };

  const batchColumns = [
    {
      title: helpTitle('结果编号', '每份预测结果的唯一标识。'),
      dataIndex: 'batch_id',
      key: 'batch_id',
      render: (value: string) => <Text code style={{ fontSize: 12 }}>{value}</Text>,
    },
    {
      title: helpTitle('保存时间', '结果写入系统的时间，非数据日期。'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value: string) => formatDateTime(value, true),
    },
    {
      title: helpTitle('设备数', '本份结果中的设备×日期条数。'),
      dataIndex: 'prediction_count',
      key: 'prediction_count',
      width: 90,
    },
    {
      title: helpTitle('数据日期', '模型所预测的数据时间范围。'),
      key: 'time_window',
      render: (_: unknown, row: PredictionBatchSummary) => (
        <Text style={{ fontSize: 12 }}>
          {formatDateTime(row.time_window_min)} ~ {formatDateTime(row.time_window_max)}
        </Text>
      ),
    },
    {
      title: helpTitle('模型', '生成本份结果所用的模型版本。'),
      dataIndex: 'model_ref',
      key: 'model_ref',
      render: (value: string) => <Text code style={{ fontSize: 11 }}>{value || '—'}</Text>,
    },
  ];

  const sampleColumns = [
    { title: '电站', dataIndex: 'site_id', key: 'site_id', width: 70 },
    { title: '设备', dataIndex: 'device_id', key: 'device_id', ellipsis: true },
    { title: '支路', dataIndex: 'branch_id', key: 'branch_id', width: 80 },
    {
      title: helpTitle('数据日期', '该条预测对应的数据时间。'),
      dataIndex: 'time_window',
      key: 'time_window',
      render: (value: string) => formatDateTime(value),
    },
    {
      title: helpTitle('预测标签', '模型输出的故障类别编号。'),
      dataIndex: 'predicted_label',
      key: 'predicted_label',
      width: 100,
    },
    {
      title: helpTitle('置信度', '模型对该预测的置信程度。'),
      dataIndex: 'confidence',
      key: 'confidence',
      width: 90,
      render: (value: number | null) => formatConfidence(value),
    },
  ];

  return (
    <div style={{ marginBottom: 16 }}>
      <Card
        size="small"
        title={
          <Space>
            <ThunderboltOutlined />
            预测结果核对
          </Space>
        }
        extra={(
          <Space>
            <Button
              size="small"
              type="link"
              onClick={() => navigate(`/algorithm-deployment?tab=scheduler&slot=${encodeURIComponent(slot)}`)}
            >
              查看调度
            </Button>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={loading || refreshing}
              onClick={() => void loadOverview()}
            >
              刷新
            </Button>
          </Space>
        )}
        loading={loading && !overview}
        style={{ marginBottom: 12 }}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="如何确认预测成功"
          description="先看最近预测任务是否完成，再核对下方是否出现更新的保存时间。任务已执行但无新结果，通常表示本次无新增待预测数据。"
        />

        {cursorStatus && (
          <Alert
            type={cursorStatus.fingerprint_aligned ? 'success' : 'warning'}
            showIcon
            style={{ marginBottom: 12 }}
            message={cursorStatus.fingerprint_aligned ? '数据源与预测进度已对齐' : '数据源与预测进度未对齐'}
            description={(
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text style={{ fontSize: 12 }}>
                  当前数据源：{cursorStatus.current_source_fingerprint?.source_path ?? '未知'}
                  （{cursorStatus.current_source_fingerprint?.date_min ?? '?'} ~ {cursorStatus.current_source_fingerprint?.date_max ?? '?'}）
                </Text>
                <Text style={{ fontSize: 12 }}>
                  预测游标时间：{formatDateTime(cursorStatus.cursor?.last_predicted_time)}
                  {!cursorStatus.fingerprint_aligned ? '；下次预测将自动按新数据源重置进度' : ''}
                </Text>
                {cursorStatus.last_run?.message && (
                  <Text style={{ fontSize: 12 }}>最近运行说明：{cursorStatus.last_run.message}</Text>
                )}
                <Button size="small" loading={resettingCursor} onClick={() => void handleResetCursor()}>
                  重置预测进度
                </Button>
              </Space>
            )}
          />
        )}

        <Row gutter={[16, 12]} style={{ marginBottom: 12 }}>
          <Col xs={24} sm={8}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {helpTitle('最近预测任务', '最近一次预测任务的执行状态与时间。')}
            </Text>
            <div>
              <Tag color={predictionTask?.last_execution === 'success' ? 'success' : predictionTask?.last_execution === 'failed' ? 'error' : 'default'}>
                {statusText(predictionTask?.last_execution)}
              </Tag>
              <Text style={{ fontSize: 12 }}>{formatDateTime(predictionTask?.last_execution_time)}</Text>
            </div>
          </Col>
          <Col xs={24} sm={8}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {helpTitle('已保存结果', '已写入系统的预测结果份数与设备预测条数。')}
            </Text>
            <div>
              <Text strong>{overview?.prediction_summary?.total_batches ?? 0}</Text>
              <Text type="secondary"> 份 / </Text>
              <Text strong>{overview?.prediction_summary?.total_predictions ?? 0}</Text>
              <Text type="secondary"> 条</Text>
            </div>
          </Col>
          <Col xs={24} sm={8}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {helpTitle('当前模型', '后续预测默认使用的模型版本。')}
            </Text>
            <div><Text code style={{ fontSize: 12 }}>{overview?.model_ref ?? '暂无'}</Text></div>
          </Col>
        </Row>

        {scheduleGapAlert && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message="预测已执行，但未产生新结果"
            description={scheduleGapAlert}
          />
        )}

        <Paragraph type="secondary" style={{ marginBottom: 8, fontSize: 12 }}>
          点击表格行可查看该份结果的设备明细。
        </Paragraph>

        {!batches.length ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无已保存的预测结果。请先完成数据喂入，再执行预测任务。"
          />
        ) : (
          <Table
            size="small"
            rowKey="batch_id"
            pagination={false}
            dataSource={batches}
            columns={batchColumns}
            rowClassName={(row) => (row.batch_id === selectedBatchId ? 'ant-table-row-selected' : '')}
            onRow={(row) => ({
              onClick: () => setSelectedBatchId(row.batch_id),
              style: { cursor: 'pointer' },
            })}
          />
        )}
      </Card>

      {selectedBatchId && (
        <Card
          size="small"
          title={
            scheduleGapAlert
              ? `结果明细（最新已保存，非本次任务）· ${selectedBatchId}`
              : `结果明细（${selectedBatchId}）`
          }
          loading={detailLoading}
          style={{ marginBottom: 12 }}
          extra={(
            <Button
              size="small"
              type="primary"
              onClick={() => {
                const latestReviewId = cursorStatus?.last_run?.batch_id === selectedBatchId
                  ? cursorStatus.last_run.review_id
                  : null;
                navigate(
                  latestReviewId
                    ? `/iterative-labeling/review?review_id=${encodeURIComponent(latestReviewId)}&slot=${encodeURIComponent(slot)}`
                    : `/iterative-labeling?slot=${encodeURIComponent(slot)}`,
                );
              }}
            >
              进入审核
            </Button>
          )}
        >
          {scheduleGapAlert && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="下方为最近一次已保存结果"
              description="最近一次预测任务未写出新结果，因此明细不会显示本次任务内容。点上方表格可切换查看历史保存结果。"
            />
          )}
          <Row gutter={[16, 12]} style={{ marginBottom: 12 }}>
            <Col xs={24} md={8}>
              <Paragraph style={{ marginBottom: 4 }}>
                <Text type="secondary">保存时间：</Text>
                {formatDateTime(batchDetail?.created_at, true)}
              </Paragraph>
              <Paragraph style={{ marginBottom: 4 }}>
                <Text type="secondary">模型：</Text>
                <Text code>{batchDetail?.model_ref ?? '—'}</Text>
              </Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                <Text type="secondary">输入数据：</Text>
                <Text code style={{ fontSize: 11 }}>{(batchDetail as any)?.dataset_version ?? '—'}</Text>
              </Paragraph>
            </Col>
            <Col xs={24} md={8}>
              <Paragraph style={{ marginBottom: 4 }}>
                <Text type="secondary">数据日期：</Text>
                {formatDateTime(batchDetail?.time_window_min)} ~ {formatDateTime(batchDetail?.time_window_max)}
              </Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                <Text type="secondary">设备数：</Text>
                <Text strong>{batchDetail?.prediction_count ?? samples.length}</Text>
              </Paragraph>
            </Col>
            <Col xs={24} md={8}>
              <Text type="secondary" style={{ fontSize: 12 }}>标签分布</Text>
              {Object.keys(batchLabels).length === 0 ? (
                <div><Text type="secondary">暂无</Text></div>
              ) : (
                Object.entries(batchLabels).map(([name, count]) => (
                  <div key={name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <Text>{name}</Text>
                    <Text strong>{count}</Text>
                  </div>
                ))
              )}
              <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
                置信度：高 {batchConfidence.high ?? 0} / 中 {batchConfidence.medium ?? 0} / 低 {batchConfidence.low ?? 0} / 未知 {batchConfidence.unknown ?? 0}
              </div>
            </Col>
          </Row>

          <Table
            size="small"
            rowKey={(_, index) => String(index)}
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
            dataSource={samples}
            columns={sampleColumns}
            locale={{ emptyText: '该结果暂无可展示样本' }}
          />
        </Card>
      )}

      <Card
        size="small"
        title={helpTitle(
          selectedBatchId ? `预测精度（${selectedBatchId}）` : '预测精度（人工核对后）',
          '基于所选预测批次的人工真值与模型预测计算；未审核前不生成精度。',
        )}
      >
        <Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 12 }}>
          {selectedBatchId
            ? '指标与上方所选预测结果联动；只有该批次完成人工核对后才会显示。'
            : '当前展示所有已完成人工核对样本的汇总指标。'}
        </Paragraph>
        {selectedBatchId && (
          <div style={{ marginBottom: 16 }}>
            <Row gutter={[16, 8]} align="middle">
              <Col xs={24} md={8}>
                <Text type="secondary">真值覆盖率</Text>
                <Progress
                  percent={truthCoverage ?? 0}
                  status={truthCoverage === 100 ? 'success' : 'active'}
                  format={percent => `${percent ?? 0}%`}
                />
              </Col>
              <Col xs={12} md={8}>
                <Text type="secondary">可评估样本</Text>
                <div><Text strong>{groundTruthSummary?.counted_units ?? 0}</Text></div>
              </Col>
              <Col xs={12} md={8}>
                <Text type="secondary">待真值回流</Text>
                <div><Text strong>{groundTruthSummary?.pending_ground_truth_units ?? batchDetail?.prediction_count ?? 0}</Text></div>
              </Col>
            </Row>
          </div>
        )}
        <PvFaultClassificationMetrics
          metrics={selectedQuality}
          emptyText="该预测批次尚无人工真值。完成审核后将展示 Accuracy、Macro 指标、类别指标和混淆矩阵。"
        />
      </Card>
    </div>
  );
};

export default PvFaultPredictionEvidencePanel;
// @AI_GENERATED: end
