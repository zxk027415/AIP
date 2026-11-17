// @AI_GENERATED
/**
 * 统一审核队列 / 审核详情 / 精度表面（design §17 / §18；任务 4.2）。
 *
 * 队列按 (project_id, review_slot) 分区，展示来源 / 粒度 / 数据版本 / 模型 / 执行 / 进度 / 准入就绪。
 * 审核详情逐条裁定；**裁定、完成审核、完成并准入是三个独立动作**（分别对应三个后端接口）。
 * 精度只读：无有效人工真值时渲染「未产出」而非 0%，低分不联动调参 / Promote。
 * 并发重判用 review_version 乐观锁；版本冲突刷新后重试。
 * wrap-first：底部保留现有审核 / 精度页深链接。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Radio,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import StageSlotGate from '../../components/StageSlotGate';
import { ActionStateView } from '../../components/ActionStateView';
import ProjectPathModelAccuracySummary from '../../components/ProjectPathModelAccuracySummary';
import { useProjectScope } from '../../../contexts/ProjectScopeContext';
import { buildJourneyHref } from '../../../utils/journeyParams';
import { pvProjectsApi } from '../../../services/pvProjectsApi';
import type {
  ItemVerdict,
  ReviewAccuracy,
  ReviewQueueRow,
  ReviewSession,
} from '../../../services/pvProjectsApi';

const { Text, Title } = Typography;

const SOURCE_LABEL: Record<string, string> = {
  label_proposal: '模型辅助打标提案',
  detection_batch: '检测批次',
  model_assisted_label: '模型辅助标注',
};

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  open: { color: 'default', label: '待开始' },
  in_review: { color: 'processing', label: '审核中' },
  completed: { color: 'blue', label: '已完成（未准入）' },
  admitted: { color: 'success', label: '已准入' },
};

function extractErr(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: { message?: string; reason_code?: string } } } })?.response?.data
    ?.detail;
  return detail?.message || fallback;
}

function AccuracyPanel({ accuracy }: { accuracy: ReviewAccuracy }): JSX.Element {
  return (
    <Descriptions size="small" column={1} bordered>
      <Descriptions.Item label="统计范围">
        {accuracy.statistical_scope.review_slot} / {accuracy.statistical_scope.unit_granularity}（共{' '}
        {accuracy.statistical_scope.total_items} 条，采纳 {accuracy.statistical_scope.accepted_items} 条）
      </Descriptions.Item>
      <Descriptions.Item label="精度值">
        {accuracy.value === null ? (
          <Tag color="default">{accuracy.value_display}</Tag>
        ) : (
          <Text strong>{String(accuracy.value)}</Text>
        )}
      </Descriptions.Item>
      <Descriptions.Item label="人工真值数">{accuracy.human_truth_count}</Descriptions.Item>
      <Descriptions.Item label="类别支持度">
        {Object.keys(accuracy.class_support).length === 0
          ? '—'
          : Object.entries(accuracy.class_support).map(([k, v]) => (
              <Tag key={k}>
                {k}: {v}
              </Tag>
            ))}
      </Descriptions.Item>
      <Descriptions.Item label="指标定义">{accuracy.metric_definition}</Descriptions.Item>
      <Descriptions.Item label="数据 / 模型版本">
        {accuracy.dataset_version_id || '—'} / {accuracy.model_ref || '—'}
      </Descriptions.Item>
      <Descriptions.Item label="是否可比">
        {accuracy.comparable ? (
          <Tag color="green">可比</Tag>
        ) : (
          <Space direction="vertical" size={0}>
            <Tag color="orange">不可比</Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              原因：{accuracy.non_comparability_reasons.join(', ') || '—'}
            </Text>
          </Space>
        )}
      </Descriptions.Item>
      <Descriptions.Item label="说明">{accuracy.auto_action_note}</Descriptions.Item>
    </Descriptions>
  );
}

function ReviewDetail({
  slot,
  reviewId,
  onChanged,
}: {
  slot: string;
  reviewId: string;
  onChanged: () => void;
}): JSX.Element {
  const { scope, generation, refresh } = useProjectScope();
  const projectId = scope.projectId;
  const [review, setReview] = useState<ReviewSession | null>(null);
  const [accuracy, setAccuracy] = useState<ReviewAccuracy | null>(null);
  const [verdicts, setVerdicts] = useState<Record<string, ItemVerdict | null>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      pvProjectsApi.getReviewDetail(projectId, slot, reviewId),
      pvProjectsApi.getReviewAccuracy(projectId, slot, reviewId),
    ])
      .then(([d, acc]) => {
        setReview(d.review);
        setAccuracy(acc);
        const seed: Record<string, ItemVerdict | null> = {};
        (d.review.items || []).forEach((it) => {
          seed[it.item_id] = it.verdict;
        });
        setVerdicts(seed);
      })
      .catch((e) => setError(extractErr(e, '审核详情读取失败')))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, slot, reviewId, generation]);

  useEffect(() => {
    load();
  }, [load]);

  const allJudged = useMemo(
    () => !!review && review.items.length > 0 && review.items.every((it) => verdicts[it.item_id]),
    [review, verdicts],
  );
  const persistedAllJudged = useMemo(
    () => !!review && review.items.length > 0 && review.items.every((it) => it.verdict),
    [review],
  );

  if (loading) return <ActionStateView descriptor={{ state: 'loading', title: '正在读取审核详情' }} />;
  if (error || !review) {
    return (
      <ActionStateView
        descriptor={{
          state: 'recoverable_failure',
          title: '审核详情加载失败',
          reason: error || '空响应',
          nextAction: '刷新当前项目后重试',
          scope: { projectId, slot },
        }}
        onRefresh={refresh}
      />
    );
  }

  const admitted = review.status === 'admitted';

  const onSaveVerdict = async () => {
    setBusy(true);
    try {
      await pvProjectsApi.saveReviewVerdict(projectId, slot, reviewId, {
        expected_review_version: review.review_version,
        item_verdicts: review.items.map((it) => ({ item_id: it.item_id, verdict: verdicts[it.item_id] ?? null })),
      });
      message.success('裁定已保存（尚未完成 / 准入）');
      load();
      onChanged();
    } catch (e) {
      message.error(extractErr(e, '保存裁定失败'));
      load();
    } finally {
      setBusy(false);
    }
  };

  const onComplete = async () => {
    setBusy(true);
    try {
      await pvProjectsApi.completeReview(projectId, slot, reviewId, { expected_review_version: review.review_version });
      message.success('审核已完成（未写累计台账）');
      load();
      onChanged();
    } catch (e) {
      message.error(extractErr(e, '完成审核失败'));
      load();
    } finally {
      setBusy(false);
    }
  };

  const onCompleteAndAdmit = async () => {
    setBusy(true);
    try {
      const res = await pvProjectsApi.completeAndAdmitReview(projectId, slot, reviewId, {
        expected_review_version: review.review_version,
        idempotency_key: `admit-${reviewId}-${review.review_version}`,
        operator: 'workbench-user',
      });
      message.success(`已准入 ${res.admission.admitted_count} 条到累计台账`);
      load();
      onChanged();
    } catch (e) {
      message.error(extractErr(e, '完成并准入失败'));
      load();
    } finally {
      setBusy(false);
    }
  };

  const itemColumns: ColumnsType<ReviewSession['items'][number]> = [
    { title: '单元', dataIndex: 'unit_ref', render: (v?: string) => <Text style={{ fontSize: 12 }}>{v || '—'}</Text> },
    { title: '建议标签', dataIndex: 'proposed_label', render: (v?: string) => <Tag>{v || '—'}</Tag> },
    {
      title: '裁定',
      render: (_: unknown, rec) => (
        <Radio.Group
          size="small"
          disabled={admitted}
          value={verdicts[rec.item_id] ?? undefined}
          onChange={(e) => setVerdicts((prev) => ({ ...prev, [rec.item_id]: e.target.value as ItemVerdict }))}
        >
          <Radio.Button value="accept">采纳</Radio.Button>
          <Radio.Button value="reject">拒绝</Radio.Button>
          <Radio.Button value="uncertain">存疑</Radio.Button>
        </Radio.Group>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Descriptions size="small" column={2} bordered title={`审核详情 ${reviewId}`}>
        <Descriptions.Item label="状态">
          <Tag color={STATUS_TAG[review.status]?.color}>{STATUS_TAG[review.status]?.label || review.status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="review_version（乐观锁）">{review.review_version}</Descriptions.Item>
        <Descriptions.Item label="来源">{SOURCE_LABEL[review.source_kind] || review.source_kind}</Descriptions.Item>
        <Descriptions.Item label="单元粒度">{review.unit_granularity}</Descriptions.Item>
        <Descriptions.Item label="数据版本">{review.dataset_version_id || '—'}</Descriptions.Item>
        <Descriptions.Item label="模型 / 执行">
          {review.model_ref || '—'} / {review.source_execution_id || '—'}
        </Descriptions.Item>
      </Descriptions>

      <Table rowKey="item_id" size="small" columns={itemColumns} dataSource={review.items} pagination={false} />

      {/* 三个独立动作 */}
      <Space wrap>
        <Button onClick={onSaveVerdict} loading={busy} disabled={admitted}>
          保存裁定
        </Button>
        <Button onClick={onComplete} loading={busy} disabled={admitted || !allJudged}>
          完成审核{!allJudged && !admitted ? '（需全部裁定）' : ''}
        </Button>
        <Button type="primary" onClick={onCompleteAndAdmit} loading={busy} disabled={admitted || !persistedAllJudged}>
          完成并准入
        </Button>
      </Space>
      {!admitted && allJudged && !persistedAllJudged && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          提示：本地裁定尚未保存，准入按当前已保存的裁定执行；请先「保存裁定」以纳入最新改动。
        </Text>
      )}
      {admitted && (
        <Alert
          type="success"
          showIcon
          message="该审核已准入"
          description={`准入事件：${review.admitted_event_id}；裁定已冻结不可修改。准入只写 scoped 累计台账，不改生产模型。`}
        />
      )}

      <Divider style={{ margin: 0 }} />
      <Title level={5} style={{ margin: 0 }}>
        精度（只读，未产出而非 0%）
      </Title>
      {accuracy ? <AccuracyPanel accuracy={accuracy} /> : <Text type="secondary">精度不可用</Text>}
    </Space>
  );
}

function ReviewQueue({ slot }: { slot: string }): JSX.Element {
  const navigate = useNavigate();
  const { scope, generation, refresh } = useProjectScope();
  const projectId = scope.projectId;
  const [rows, setRows] = useState<ReviewQueueRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    pvProjectsApi
      .getReviewQueue(projectId, slot)
      .then((res) => setRows(res.reviews || []))
      .catch((e) => setError(extractErr(e, '审核队列读取失败')))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, slot, generation]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<ReviewQueueRow> = [
    {
      title: '审核会话',
      dataIndex: 'review_id',
      render: (id: string, rec) => (
        <Space direction="vertical" size={0}>
          <Text code>{id}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {SOURCE_LABEL[rec.source_kind] || rec.source_kind} · {rec.unit_granularity}
          </Text>
        </Space>
      ),
    },
    {
      title: '状态 / 进度',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={2}>
          <Tag color={STATUS_TAG[rec.status]?.color}>{STATUS_TAG[rec.status]?.label || rec.status}</Tag>
          <Text style={{ fontSize: 12 }}>
            {rec.progress.judged}/{rec.progress.total} 已裁定
          </Text>
        </Space>
      ),
    },
    {
      title: '数据 / 模型',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>{rec.dataset_version_id || '—'}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {rec.model_ref || '—'}
          </Text>
        </Space>
      ),
    },
    {
      title: '准入就绪',
      render: (_: unknown, rec) =>
        rec.admitted_event_id ? (
          <Tag color="success">已准入</Tag>
        ) : rec.admission_ready ? (
          <Tag color="blue">可准入</Tag>
        ) : (
          <Tag color="default">未就绪</Tag>
        ),
    },
    {
      title: '操作',
      render: (_: unknown, rec) => (
        <Button size="small" onClick={() => setSelected(rec.review_id)}>
          {selected === rec.review_id ? '查看中' : '打开'}
        </Button>
      ),
    },
  ];

  const legacyDeepLink = (
    <Collapse
      ghost
      size="small"
      items={[
        {
          key: 'legacy',
          label: '现有审核 / 精度页（wrap-first 深链接）',
          children: (
            <Space wrap>
              <Button
                onClick={() =>
                  navigate(
                    buildJourneyHref(
                      '/iterative-labeling',
                      { projectId, slot, datasetVersionId: scope.datasetVersionId },
                      { tab: 'review', review_slot: slot },
                    ),
                  )
                }
              >
                打开标注 / 三槽审核（review_slot={slot}）
              </Button>
              <Button
                onClick={() =>
                  navigate(
                    buildJourneyHref('/accuracy-operations', {
                      projectId,
                      slot,
                      datasetVersionId: scope.datasetVersionId,
                    }),
                  )
                }
              >
                打开精度运营（携当前项目 / 路径）
              </Button>
            </Space>
          ),
        },
      ]}
    />
  );

  if (loading) return <ActionStateView descriptor={{ state: 'loading', title: '正在读取审核队列' }} />;
  if (error) {
    return (
      <ActionStateView
        descriptor={{
          state: 'recoverable_failure',
          title: '审核队列加载失败',
          reason: error,
          nextAction: '刷新当前项目后重试',
          scope: { projectId, slot },
        }}
        onRefresh={refresh}
      />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="统一审核队列"
        description="裁定、完成审核、完成并准入是三个独立动作；完成审核不写累计台账，准入才写（且幂等）。精度无有效人工真值时显示「未产出」，低分不联动调参 / Promote。"
      />
      {rows.length === 0 ? (
        <Empty
          description={
            <Space direction="vertical" size={0}>
              <Text>当前项目 / 路径暂无审核会话</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                审核会话来自打标提案 / 检测批次 / 模型辅助标注；在运行中心产出提案后回到此处。
              </Text>
            </Space>
          }
        />
      ) : (
        <Table rowKey="review_id" size="small" columns={columns} dataSource={rows} pagination={{ pageSize: 8, size: 'small' }} />
      )}
      {selected && (
        <>
          <Divider style={{ margin: 0 }} />
          <ReviewDetail slot={slot} reviewId={selected} onChanged={load} />
        </>
      )}
      {legacyDeepLink}
    </Space>
  );
}

export function ProjectReviewsStagePage(): JSX.Element {
  return (
    <StageSlotGate prompt="选择一条诊断路径以查看审核与精度。">
      {(slot) => (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <ProjectPathModelAccuracySummary slot={slot} />
          <ReviewQueue slot={slot} />
        </Space>
      )}
    </StageSlotGate>
  );
}

export default ProjectReviewsStagePage;
// @AI_GENERATED: end
