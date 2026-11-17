// @AI_GENERATED
/**
 * pv_tsc precision operations: real persisted review-session accuracy, candidate
 * offline evidence, scheduler health and read-only device-day observability.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { Link } from 'react-router-dom';
import { schedulerTaskApi, type PvTscPredictRunStatus } from '../../services/deploymentApi';
import {
  reviewSessionApi,
  type GetAccuracyResponse,
} from '../../services/iterativeLabelingApi';
import { slotObservabilityApi, type ObservabilityStatus } from '../../services/slotObservabilityApi';
import {
  slotGovernanceApi,
  type ModelCandidateView,
  type ModelEvaluationContract,
} from '../../services/slotGovernanceApi';
import SlotOpsClockBar from './SlotOpsClockBar';
import SlotObservabilityCalendar from './SlotObservabilityCalendar';
import FeedSourceCard from './FeedSourceCard';

const { Text } = Typography;

const TSC_RUN_STATE_META: Record<string, { color: string; label: string; hint: string }> = {
  success: { color: 'success', label: '运行正常', hint: '最近一次 pv_tsc_predict 已产出真实预测回执，且模型与当前 registry 一致。' },
  model_pending: { color: 'warning', label: '待登记模型', hint: '尚未登记可用的 Champion/rolling/Challenger 模型工件。' },
  no_run_yet: { color: 'default', label: '尚未运行', hint: '模型已就绪，但 pv_tsc_predict 还没有运行回执。' },
  stale: { color: 'error', label: '状态过期', hint: '回执过期、模型已变更或调度失败；请检查 pv_tsc_predict。' },
};

function extractError(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string | { message?: string } } }; message?: string })
    ?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object' && detail?.message) return detail.message;
  return (err as Error)?.message || fallback;
}

// @AI_GENERATED
// P1-3 改动 D：null 安全——缺失指标返回 null 而非 0，Statistic 显示 '—'。
function percentValue(value?: number | null): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return Number((value * 100).toFixed(1));
}
// @AI_GENERATED: end

function metricText(value?: number | null, std?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '未产出';
  const mean = `${(value * 100).toFixed(2)}%`;
  return typeof std === 'number' && Number.isFinite(std)
    ? `${mean} ± ${(std * 100).toFixed(2)}%`
    : mean;
}

const PvTscAccuracyOpsPanel: React.FC<{ refreshKey?: number }> = ({ refreshKey }) => {
  const [runStatus, setRunStatus] = useState<PvTscPredictRunStatus | null>(null);
  const [runStatusLoading, setRunStatusLoading] = useState(false);
  const [runStatusError, setRunStatusError] = useState<string | null>(null);
  const [obsStatus, setObsStatus] = useState<ObservabilityStatus | null>(null);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [reviewAccuracy, setReviewAccuracy] = useState<GetAccuracyResponse | null>(null);
  const [reviewAccuracyError, setReviewAccuracyError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<ModelCandidateView | null>(null);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [demoAdvancing, setDemoAdvancing] = useState(false);

  const load = useCallback(async () => {
    setRunStatusLoading(true);
    setEvidenceLoading(true);
    setRunStatusError(null);
    setReviewAccuracyError(null);
    setCandidateError(null);
    setReviewAccuracy(null);
    setCandidate(null);
    setReviewId(null);
    try {
      const [statusResult, obsResult] = await Promise.allSettled([
        schedulerTaskApi.getPvTscPredictRunStatus(),
        slotObservabilityApi.getStatus('pv_tsc'),
      ]);
      setObsStatus(obsResult.status === 'fulfilled' ? obsResult.value : null);
      if (statusResult.status !== 'fulfilled') {
        setRunStatus(null);
        setRunStatusError(extractError(statusResult.reason, '加载 pv_tsc_predict 运行状态失败'));
        return;
      }

      const status = statusResult.value;
      setRunStatus(status);
      const reviewIds = status.last_run?.review_ids || [];
      const latestReviewId = reviewIds.length ? reviewIds[reviewIds.length - 1] : null;
      const candidateId = status.model?.model_candidate_id
        || status.last_run?.model_candidate_id
        || null;
      setReviewId(latestReviewId);

      const evidenceTasks: Promise<void>[] = [];
      if (latestReviewId) {
        evidenceTasks.push(
          reviewSessionApi.getAccuracy(latestReviewId, 'pv_tsc')
            .then(setReviewAccuracy)
            .catch((error) => setReviewAccuracyError(
              extractError(error, '加载真实审核批次精度失败'),
            )),
        );
      }
      if (candidateId) {
        evidenceTasks.push(
          slotGovernanceApi.getModelCandidate(candidateId)
            .then((body) => setCandidate(body.candidate))
            .catch((error) => setCandidateError(
              extractError(error, '加载模型候选评估合同失败'),
            )),
        );
      }
      await Promise.all(evidenceTasks);
    } finally {
      setRunStatusLoading(false);
      setEvidenceLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const advanceDemo = async () => {
    setDemoAdvancing(true);
    try {
      const body = await slotObservabilityApi.replayAdvanceTsc();
      if (body.fed_day) {
        message.success(body.note || `演示已推进到 ${body.fed_day}`);
      } else {
        message.info(body.note || '演示未过到达门禁，未写入生产观测');
      }
      await load();
    } catch (err: unknown) {
      message.error(extractError(err, '演示回放推进失败'));
    } finally {
      setDemoAdvancing(false);
    }
  };

  const stateMeta = runStatus
    ? (TSC_RUN_STATE_META[runStatus.state] || TSC_RUN_STATE_META.stale)
    : null;
  const evaluation: ModelEvaluationContract = candidate?.evaluation_contract || {};
  const contractValid = evaluation.production_contract_valid === true
    || candidate?.production_contract_valid === true;
  const actionSummary = reviewAccuracy?.actionSummary || {};

  const confusionColumns = useMemo(() => {
    const labels = reviewAccuracy?.confusionMatrix.labels || [];
    const columns: Array<Record<string, unknown>> = [
      {
        title: '人工真值 ↓ / 模型预测 →',
        dataIndex: 'trueLabel',
        key: 'trueLabel',
        fixed: 'left',
        render: (value: number | string) => <Tag color="blue">标签 {value}</Tag>,
      },
    ];
    labels.forEach((label) => {
      columns.push({
        title: `预测 ${label}`,
        key: `pred-${label}`,
        align: 'center',
        render: (_: unknown, row: { predictedCounts: Record<string, number> }) => (
          row.predictedCounts[String(label)] || 0
        ),
      });
    });
    columns.push({ title: '真值数', dataIndex: 'support', key: 'support', align: 'center' });
    return columns;
  }, [reviewAccuracy]);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="时序分类（MultiRocket）设备日精度运营 · 真实证据"
        description="本页严格分开两种口径：人工审核批次精度来自持久化设备日 verdict；模型离线指标来自候选评估合同。当前 3-seed 指标不是 strict-10，production_contract_valid=false 时不会包装成生产验收。"
      />

      <Card
        size="small"
        title="演示回放（独立通道）"
        extra={<Tag color="gold">不写生产观测</Tag>}
      >
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message="只推进 loop_demo，不会改 Challenger 调度或 pv_tsc 生产 ledger。"
          />
          <FeedSourceCard
            slot="pv_tsc"
            progress={obsStatus?.demo_replay}
            onChanged={() => void load()}
          />
          <Space wrap>
            <Button type="primary" loading={demoAdvancing} onClick={() => void advanceDemo()}>
              推进演示下一天
            </Button>
            <Text type="secondary">{obsStatus?.demo_replay?.note || '尚未开始演示回放'}</Text>
          </Space>
        </Space>
      </Card>

      {runStatusError ? (
        <Alert
          type="error"
          showIcon
          message="加载 pv_tsc_predict 运行状态失败"
          description={runStatusError}
          action={<Button size="small" onClick={() => void load()}>重试</Button>}
        />
      ) : (
        <Card
          size="small"
          title="pv_tsc_predict 运行状态（只读）"
          loading={runStatusLoading}
          extra={<Button size="small" onClick={() => void load()}>刷新</Button>}
        >
          {runStatus && stateMeta ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space wrap>
                <Tag color={stateMeta.color}>{stateMeta.label}</Tag>
                <Text type="secondary">{runStatus.reason}</Text>
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>{stateMeta.hint}</Text>
              <Descriptions size="small" column={2} bordered>
                <Descriptions.Item label="模型来源">{runStatus.model?.source || '—'}</Descriptions.Item>
                <Descriptions.Item label="候选 ID">
                  <Text code style={{ fontSize: 11 }}>{runStatus.model?.model_candidate_id || '—'}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="registry 版本">{runStatus.model?.registry_version ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="模型已登记">{runStatus.model?.artifact_registered ? '是' : '否'}</Descriptions.Item>
                <Descriptions.Item label="回执时间">{runStatus.freshness?.updated_at || '尚无回执'}</Descriptions.Item>
                <Descriptions.Item label="新鲜度">
                  {runStatus.freshness?.is_stale ? '已过期' : '新鲜'}
                  {runStatus.freshness?.age_seconds != null
                    ? ` · ${Math.round(runStatus.freshness.age_seconds / 60)} 分钟前`
                    : ''}
                </Descriptions.Item>
              </Descriptions>
              {runStatus.last_run && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  上次运行：{runStatus.last_run.outcome || '—'}
                  {runStatus.last_run.devices_processed != null ? ` · 处理设备 ${runStatus.last_run.devices_processed}` : ''}
                  {runStatus.last_run.points_detected != null ? ` · 设备日预测 ${runStatus.last_run.points_detected}` : ''}
                </Text>
              )}
            </Space>
          ) : (
            <Empty description="暂无运行状态" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Card>
      )}

      <Card
        size="small"
        title="真实审核批次精度（设备日口径）"
        loading={evidenceLoading && Boolean(reviewId)}
        extra={reviewId ? <Text code>{reviewId}</Text> : undefined}
      >
        {reviewAccuracyError ? (
          <Alert
            type="error"
            showIcon
            message="真实审核精度读取失败"
            description={reviewAccuracyError}
            action={<Button size="small" onClick={() => void load()}>重试</Button>}
          />
        ) : reviewAccuracy && reviewAccuracy._accuracy_available === false ? (
          /* @AI_GENERATED */
          /* P1-2 改动 D：存在不一致重复裁决时降级为 warning。 */
          <Alert
            type="warning"
            showIcon
            message="审核精度数据存在冲突"
            description={reviewAccuracy._accuracy_unavailable_reason || '存在不一致的重复裁决，精度不可信'}
            action={<Button size="small" onClick={() => void load()}>重试</Button>}
          />
          /* @AI_GENERATED: end */
        ) : reviewAccuracy && reviewAccuracy.countedUnits === 0 ? (
          /* @AI_GENERATED */
          /* P1-3 改动 C：有效计量单元为 0 时显示 Empty 而非 0%。 */
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="该审核批次尚无有效人工真值，无法计算精度"
            />
            <Descriptions size="small" bordered column={2}>
              <Descriptions.Item label="审核进度">
                {reviewAccuracy.reviewedCount} / {reviewAccuracy.totalCount}
              </Descriptions.Item>
              <Descriptions.Item label="事实来源">{reviewAccuracy.computedFrom}</Descriptions.Item>
            </Descriptions>
          </Space>
          /* @AI_GENERATED: end */
        ) : reviewAccuracy ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Row gutter={[12, 12]}>
              <Col xs={24} md={8}>
                <Statistic
                  title="Classifier Accuracy"
                  value={percentValue(reviewAccuracy.classifierAccuracy) ?? '—'}
                  precision={percentValue(reviewAccuracy.classifierAccuracy) != null ? 1 : undefined}
                  suffix={percentValue(reviewAccuracy.classifierAccuracy) != null ? '%' : undefined}
                />
              </Col>
              <Col xs={24} md={8}>
                <Statistic
                  title="本批 Macro-F1"
                  value={percentValue(reviewAccuracy.macro.f1) ?? '—'}
                  precision={percentValue(reviewAccuracy.macro.f1) != null ? 1 : undefined}
                  suffix={percentValue(reviewAccuracy.macro.f1) != null ? '%' : undefined}
                />
              </Col>
              <Col xs={24} md={8}>
                <Statistic title="有效人工真值设备日" value={reviewAccuracy.countedUnits} />
              </Col>
            </Row>
            {/* @AI_GENERATED */}
            {/* P1-3 改动 C：Alert type 条件化，countedUnits > 0 且精度可用时才为 success。 */}
            <Alert
              type={reviewAccuracy.countedUnits > 0 ? 'success' : 'info'}
              showIcon
              message={`真实人工裁决：${actionSummary.confirm || 0} 个确认，${actionSummary.correct || 0} 个纠正，${actionSummary.new_label || 0} 个新标签`}
              description="Accuracy 比较聚合后的设备日模型预测与人工 verdict；Macro-F1 只在本审核批次实际出现的标签集合上计算，不等同于 strict-10 全标签空间指标。"
            />
            <Descriptions size="small" bordered column={2}>
              <Descriptions.Item label="事实来源">{reviewAccuracy.computedFrom}</Descriptions.Item>
              <Descriptions.Item label="统计粒度">{reviewAccuracy.metricScope}</Descriptions.Item>
              <Descriptions.Item label="审核进度">
                {reviewAccuracy.reviewedCount} / {reviewAccuracy.totalCount}
              </Descriptions.Item>
              <Descriptions.Item label="重建诊断">
                冲突 {reviewAccuracy.diagnostics.unit_verdict_conflicts || 0} · 缺失 {reviewAccuracy.diagnostics.missing_prediction_or_truth || 0}
              </Descriptions.Item>
            </Descriptions>
            <Card size="small" title="混淆矩阵（真值行 / 预测列）">
              <Table
                size="small"
                pagination={false}
                rowKey={(row) => String(row.trueLabel)}
                columns={confusionColumns as any}
                dataSource={reviewAccuracy.confusionMatrix.rows}
                scroll={{ x: 'max-content' }}
              />
            </Card>
          </Space>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={reviewId ? '该审核批次尚无有效人工真值' : '最近运行没有可关联的真实审核批次'}
          />
        )}
      </Card>

      <Card
        size="small"
        title="当前模型候选离线评估（与人工审核分开）"
        loading={evidenceLoading && Boolean(runStatus?.model?.model_candidate_id)}
      >
        {candidateError ? (
          <Alert type="error" showIcon message="候选评估合同读取失败" description={candidateError} />
        ) : candidate ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Space wrap>
              <Text code>{candidate.model_candidate_id}</Text>
              <Tag color={contractValid ? 'success' : 'error'}>
                {contractValid ? '生产合同通过' : '生产合同未通过'}
              </Tag>
              <Tag>{evaluation.evaluation || '评估类型未记录'}</Tag>
            </Space>
            <Row gutter={[12, 12]}>
              <Col xs={24} md={8}>
                <Statistic
                  title="离线 Macro-F1"
                  value={metricText(evaluation.macro_f1_mean)}
                />
                {typeof evaluation.macro_f1_mean === 'number'
                  && Number.isFinite(evaluation.macro_f1_mean)
                  && typeof evaluation.macro_f1_std === 'number'
                  && Number.isFinite(evaluation.macro_f1_std) && (
                    <Text type="secondary">± {percentValue(evaluation.macro_f1_std).toFixed(2)}%</Text>
                )}
              </Col>
              <Col xs={24} md={8}>
                <Statistic
                  title="离线 Accuracy"
                  value={metricText(evaluation.accuracy_mean)}
                />
              </Col>
              <Col xs={24} md={8}>
                <Statistic title="随机种子" value={evaluation.n_seeds ?? '—'} />
              </Col>
            </Row>
            <Descriptions size="small" bordered column={2}>
              <Descriptions.Item label="表示合同">{evaluation.representation || '—'}</Descriptions.Item>
              <Descriptions.Item label="通道">{(evaluation.channels || []).join(' + ') || '—'}</Descriptions.Item>
              <Descriptions.Item label="评估样本 / 类别">
                {evaluation.n_samples ?? '—'} / {evaluation.n_classes ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="Balanced Accuracy">
                {metricText(evaluation.balanced_accuracy_mean, evaluation.balanced_accuracy_std)}
              </Descriptions.Item>
              <Descriptions.Item label="strict 划分完成 / 要求">
                {evaluation.n_splits_completed != null || evaluation.n_splits_requested != null
                  ? `${evaluation.n_splits_completed ?? '—'} / ${evaluation.n_splits_requested ?? '—'}`
                  : '未产出'}
              </Descriptions.Item>
              <Descriptions.Item label="来源累计快照">
                {candidate.source_snapshot_id || '未关联（历史一次性重训）'}
              </Descriptions.Item>
            </Descriptions>
            {!contractValid && (
              <Alert
                type="warning"
                showIcon
                message="这是 3-seed 设备隔离 holdout，不是 strict-10 生产验收"
                description="当前可以作为 Challenger 运营证据，但 balanced accuracy 与 strict 划分次数尚未产出，禁止据此 Promote。需用新的 288×3 累计冻结走正式 strict-10 工作流。"
              />
            )}
          </Space>
        ) : (
          <Empty description="当前运行没有可读取的模型候选" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <SlotOpsClockBar
        status={obsStatus ? { ...obsStatus, slot: obsStatus.slot || 'pv_tsc' } : { slot: 'pv_tsc' }}
        writable={false}
      />

      <Card size="small" title="设备日到达完整度（只读）">
        <SlotObservabilityCalendar slot="pv_tsc" writable={false} />
      </Card>

      <Space wrap>
        <Link to="/algorithm-deployment?slot=pv_tsc">
          <Button type="primary">去算法部署查看候选</Button>
        </Link>
        <Link to="/iterative-labeling?tab=review&review_slot=pv_tsc">
          <Button>去人工审核回流</Button>
        </Link>
      </Space>
    </Space>
  );
};

export default PvTscAccuracyOpsPanel;
// @AI_GENERATED: end
