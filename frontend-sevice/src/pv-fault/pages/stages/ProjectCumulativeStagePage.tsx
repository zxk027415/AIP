// @AI_GENERATED
/**
 * 三层累计 + 冻结确认区（design §19；任务 4.3）。
 *
 * 三层：已准入事件 admitted_events / 已冻结快照 frozen_snapshots / 训练结果 training_results（互不混淆）。
 * 冻结确认区：reviewed_at_cutoff、included/excluded、标签 / 设备 / 日期分布、输出快照类型、重复输入检测；
 * 执行冻结幂等（同 plan 命中已有快照）。冻结与训练结果登记不等于模型准入；Promote 仍需正式复验 + 生产授权。
 * wrap-first：底部保留现有累计训练页深链接。
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import StageSlotGate from '../../components/StageSlotGate';
import { ActionStateView } from '../../components/ActionStateView';
import { useProjectScope } from '../../../contexts/ProjectScopeContext';
import { buildJourneyHref } from '../../../utils/journeyParams';
import { pvProjectsApi } from '../../../services/pvProjectsApi';
import type {
  AdmissionEvent,
  CumulativeOverview,
  FreezePlan,
  FrozenSnapshot,
  TrainingResult,
} from '../../../services/pvProjectsApi';

const { Text, Title } = Typography;

function extractErr(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
  return detail?.message || fallback;
}

function distText(dist: Record<string, number>): string {
  const entries = Object.entries(dist || {});
  if (entries.length === 0) return '—';
  return entries.map(([k, v]) => `${k}:${v}`).join(', ');
}

function FreezePanel({ slot, onFrozen }: { slot: string; onFrozen: () => void }): JSX.Element {
  const { scope } = useProjectScope();
  const projectId = scope.projectId;
  const [plan, setPlan] = useState<FreezePlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadPlan = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    pvProjectsApi
      .getFreezePlan(projectId, slot)
      .then((p) => setPlan(p))
      .catch((e) => message.error(extractErr(e, '冻结计划读取失败')))
      .finally(() => setLoading(false));
  }, [projectId, slot]);

  useEffect(() => {
    loadPlan();
  }, [loadPlan]);

  const onFreeze = async () => {
    if (!plan) return;
    setBusy(true);
    try {
      const res = await pvProjectsApi.executeFreeze(projectId, slot, {
        reviewed_at_cutoff: plan.reviewed_at_cutoff ?? null,
        idempotency_key: `freeze-${slot}-${plan.plan_fingerprint}`,
        operator: 'workbench-user',
      });
      message.success(res.idempotent_replay ? '命中已有快照（幂等，未重复冻结）' : '已生成不可变冻结快照');
      loadPlan();
      onFrozen();
    } catch (e) {
      message.error(extractErr(e, '执行冻结失败'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <ActionStateView descriptor={{ state: 'loading', title: '正在计算冻结计划' }} />;
  if (!plan) return <Text type="secondary">冻结计划不可用</Text>;

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Descriptions size="small" column={2} bordered title="冻结确认区">
        <Descriptions.Item label="审核时间上界">{plan.reviewed_at_cutoff || '不限（全部已准入）'}</Descriptions.Item>
        <Descriptions.Item label="输出快照类型">
          <Tag color="blue">{plan.output_snapshot_type}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="纳入 / 排除事件">
          {plan.included_count} 纳入 / {plan.excluded_count} 排除
        </Descriptions.Item>
        <Descriptions.Item label="重复输入检测">
          {plan.duplicate_input_detected ? (
            <Tag color="orange">已存在相同快照（{plan.duplicate_snapshot_id}）</Tag>
          ) : (
            <Tag color="green">无重复</Tag>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="标签分布" span={2}>
          {distText(plan.label_distribution)}
        </Descriptions.Item>
        <Descriptions.Item label="设备分布" span={2}>
          {distText(plan.device_distribution)}
        </Descriptions.Item>
        <Descriptions.Item label="日期分布" span={2}>
          {distText(plan.date_distribution)}
        </Descriptions.Item>
        <Descriptions.Item label="路径备注" span={2}>
          {plan.path_note || '—'}
        </Descriptions.Item>
      </Descriptions>
      <Space>
        <Button type="primary" onClick={onFreeze} loading={busy} disabled={!plan.freezable}>
          {plan.duplicate_input_detected ? '已冻结（重复输入）' : plan.included_count === 0 ? '无可冻结事件' : '执行冻结'}
        </Button>
        <Button onClick={loadPlan}>刷新计划</Button>
      </Space>
      <Text type="secondary" style={{ fontSize: 12 }}>
        冻结产出不可变快照，供后续训练；训练成功仍须经候选治理 + 正式复验 + 生产授权，才可能成为检测模型。
      </Text>
    </Space>
  );
}

function CumulativeLayers({ slot }: { slot: string }): JSX.Element {
  const navigate = useNavigate();
  const { scope, generation, refresh } = useProjectScope();
  const projectId = scope.projectId;
  const [overview, setOverview] = useState<CumulativeOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    pvProjectsApi
      .getCumulative(projectId, slot)
      .then((o) => setOverview(o))
      .catch((e) => setError(extractErr(e, '累计视图读取失败')))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, slot, generation]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <ActionStateView descriptor={{ state: 'loading', title: '正在读取累计视图' }} />;
  if (error || !overview) {
    return (
      <ActionStateView
        descriptor={{
          state: 'recoverable_failure',
          title: '累计视图加载失败',
          reason: error || '空响应',
          nextAction: '刷新当前项目后重试',
          scope: { projectId, slot },
        }}
        onRefresh={refresh}
      />
    );
  }

  const admissionColumns: ColumnsType<AdmissionEvent> = [
    { title: '事件', dataIndex: 'event_id', render: (v: string) => <Text code>{v}</Text> },
    { title: '来源审核', dataIndex: 'review_id', render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text> },
    {
      title: '采纳 / 拒绝 / 存疑',
      render: (_: unknown, rec) => (
        <Text style={{ fontSize: 12 }}>
          {rec.admitted_count} / {rec.rejected_count} / {rec.uncertain_count}
        </Text>
      ),
    },
    { title: '准入时间', dataIndex: 'admitted_at', render: (v?: string) => <Text style={{ fontSize: 11 }}>{v || '—'}</Text> },
  ];

  const snapshotColumns: ColumnsType<FrozenSnapshot> = [
    { title: '快照', dataIndex: 'snapshot_id', render: (v: string) => <Text code>{v}</Text> },
    { title: '类型', dataIndex: 'snapshot_type', render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: '纳入事件', dataIndex: 'included_count' },
    {
      title: 'cutoff / digest',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 11 }}>{rec.reviewed_at_cutoff || '不限'}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {rec.content_digest.slice(0, 22)}…
          </Text>
        </Space>
      ),
    },
  ];

  const resultColumns: ColumnsType<TrainingResult> = [
    { title: '训练结果', dataIndex: 'result_id', render: (v: string) => <Text code>{v}</Text> },
    { title: '来源快照', dataIndex: 'source_snapshot_id', render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text> },
    {
      title: '模型工件',
      dataIndex: 'model_artifact_ref',
      render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
    },
  ];

  const { summary } = overview;

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="累计训练集（三层）"
        description={`已准入 ${summary.admission_count} 事件（${summary.admitted_units} 单元）/ 已冻结 ${summary.snapshot_count} 快照 / 训练结果 ${summary.training_result_count} 条。三层互不混淆；冻结与训练结果登记均不等于模型准入。`}
      />

      <div>
        <Title level={5} style={{ marginBottom: 8 }}>
          ① 已准入事件（来自审核 complete-and-admit）
        </Title>
        {overview.admitted_events.length === 0 ? (
          <Empty description="暂无准入事件；先在审核队列完成裁定并准入。" />
        ) : (
          <Table rowKey="event_id" size="small" columns={admissionColumns} dataSource={overview.admitted_events} pagination={false} />
        )}
      </div>
      <Divider style={{ margin: 0 }} />

      <div>
        <Title level={5} style={{ marginBottom: 8 }}>
          ② 已冻结快照（不可变）
        </Title>
        {overview.frozen_snapshots.length === 0 ? (
          <Text type="secondary">暂无冻结快照。</Text>
        ) : (
          <Table rowKey="snapshot_id" size="small" columns={snapshotColumns} dataSource={overview.frozen_snapshots} pagination={false} />
        )}
      </div>
      <Divider style={{ margin: 0 }} />

      <div>
        <Title level={5} style={{ marginBottom: 8 }}>
          ③ 训练结果（基于快照，非模型准入）
        </Title>
        {overview.training_results.length === 0 ? (
          <Text type="secondary">暂无训练结果登记。</Text>
        ) : (
          <Table rowKey="result_id" size="small" columns={resultColumns} dataSource={overview.training_results} pagination={false} />
        )}
      </div>
      <Divider style={{ margin: 0 }} />

      <FreezePanel slot={slot} onFrozen={load} />

      <Collapse
        ghost
        size="small"
        items={[
          {
            key: 'legacy',
            label: '现有累计训练页（wrap-first 深链接）',
            children: (
              <Button
                onClick={() =>
                  navigate(
                    buildJourneyHref('/datasets/cumulative-training', {
                      projectId,
                      slot,
                      datasetVersionId: scope.datasetVersionId,
                    }),
                  )
                }
              >
                打开累计训练集（携当前项目 / 路径）
              </Button>
            ),
          },
        ]}
      />
    </Space>
  );
}

export function ProjectCumulativeStagePage(): JSX.Element {
  return (
    <StageSlotGate prompt="选择一条诊断路径以查看累计训练集。">
      {(slot) => <CumulativeLayers slot={slot} />}
    </StageSlotGate>
  );
}

export default ProjectCumulativeStagePage;
// @AI_GENERATED: end
