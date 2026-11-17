// @AI_GENERATED
/**
 * 运行中心（design D-RUN-01 / D-STATE-01；任务 3.2）。
 *
 * 展示 scoped execution：状态、运行模式 / 域、治理资格、节点时间线（而非单一"运行中"标签）、
 * 结果去向与失败原因；提供"用原输入重试"（新尝试，不覆盖失败证据）。
 * 覆盖 loading / empty / error / running / success / failed / cancelled / 后端记录缺失。
 */
import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import StageSlotGate from '../../components/StageSlotGate';
import { ActionStateView } from '../../components/ActionStateView';
import { useProjectScope } from '../../../contexts/ProjectScopeContext';
import { pvProjectsApi } from '../../../services/pvProjectsApi';
import type { ScopedExecution, NodeTimelineEntry } from '../../../services/pvProjectsApi';

const { Text } = Typography;

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  running: { color: 'processing', label: '运行中' },
  success: { color: 'success', label: '成功' },
  failed: { color: 'error', label: '失败' },
  cancelled: { color: 'default', label: '已取消' },
};

const NODE_TAG: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  cancelled: 'default',
};

const RESULT_DESTINATION_LABEL: Record<string, string> = {
  experiment_artifact_only: '仅实验工件',
  validation_execution: '验证执行（非可治理）',
  governable_candidate: '可治理候选',
  labeling_proposal: '打标提案',
  prediction_batch_and_pending_review: '预测批次 + 待审核会话',
};

function NodeTimeline({ timeline }: { timeline: NodeTimelineEntry[] }): JSX.Element {
  if (!timeline || timeline.length === 0) {
    return <Text type="secondary">无节点时间线</Text>;
  }
  return (
    <Space wrap size={6}>
      {timeline.map((n) => (
        <Tag key={n.node_id} color={NODE_TAG[n.status] || 'default'}>
          {n.node_id}: {n.status}
          {n.error ? `（${n.error}）` : ''}
        </Tag>
      ))}
    </Space>
  );
}

function RunCenter({ slot }: { slot: string }): JSX.Element {
  const { scope, generation, refresh } = useProjectScope();
  const projectId = scope.projectId;
  const [rows, setRows] = useState<ScopedExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    pvProjectsApi
      .listExecutions(projectId, slot)
      .then((res) => setRows(res.executions || []))
      .catch(() => setError('执行列表读取失败'))
      .finally(() => setLoading(false));
  }, [projectId, slot, generation]);

  useEffect(() => {
    load();
  }, [load]);

  const onRetry = async (execution_id: string) => {
    if (!projectId) return;
    try {
      await pvProjectsApi.retryExecution(projectId, execution_id, slot);
      message.success('已用原输入创建新的重试执行（原失败证据保留）');
      load();
    } catch {
      message.error('重试失败');
    }
  };

  const columns: ColumnsType<ScopedExecution> = [
    {
      title: '执行',
      dataIndex: 'execution_id',
      render: (id: string, rec) => (
        <Space direction="vertical" size={0}>
          <Text code>{id}</Text>
          {rec.origin_kind && <Text type="secondary" style={{ fontSize: 11 }}>来历：{rec.origin_kind}</Text>}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      render: (s: string) => {
        const t = STATUS_TAG[s] || { color: 'default', label: s };
        return <Tag color={t.color}>{t.label}</Tag>;
      },
    },
    {
      title: '模式 / 域',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <span>{rec.run_mode} / {rec.run_domain}</span>
          <Tag color={rec.governance_eligible ? 'gold' : 'default'} style={{ marginInlineEnd: 0 }}>
            {rec.governance_eligible ? '可治理' : '非可治理'}
          </Tag>
        </Space>
      ),
    },
    {
      title: '结果去向 / 失败原因',
      render: (_: unknown, rec) => {
        if (rec.status === 'success') {
          return <Text>{rec.result_destination ? RESULT_DESTINATION_LABEL[rec.result_destination] || rec.result_destination : '未标注去向'}</Text>;
        }
        if (rec.status === 'failed') {
          return <Text type="danger">{rec.failure_reason || '未知失败'}</Text>;
        }
        return <Text type="secondary">—</Text>;
      },
    },
    {
      title: '操作',
      render: (_: unknown, rec) =>
        rec.status === 'failed' ? (
          <Button size="small" onClick={() => onRetry(rec.execution_id)}>
            用原输入重试
          </Button>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
  ];

  if (loading) {
    return <ActionStateView descriptor={{ state: 'loading', title: '正在读取执行' }} />;
  }
  if (error) {
    return (
      <ActionStateView
        descriptor={{ state: 'recoverable_failure', title: '运行中心加载失败', reason: error, nextAction: '刷新当前项目后重试', scope: { projectId, slot } }}
        onRefresh={refresh}
      />
    );
  }
  if (rows.length === 0) {
    return (
      <ActionStateView
        descriptor={{ state: 'initial_empty', title: '当前路径暂无执行', reason: '尚未在该项目 / 路径下登记任何 run。', nextAction: '在工作流阶段创建项目工作流并预检后发起执行', scope: { projectId, slot } }}
      />
    );
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="运行中心（scoped executions）"
        description="每次 run 落库 project / slot / 数据版本 / 工作流 / 模式 / 域 / 节点状态 / 治理资格。验证与实验执行恒为非可治理；重试产生新执行，不覆盖历史失败证据。"
      />
      <Table
        rowKey="execution_id"
        size="small"
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 10, size: 'small' }}
        expandable={{
          expandedRowRender: (rec) => <NodeTimeline timeline={rec.node_timeline} />,
          rowExpandable: (rec) => (rec.node_timeline || []).length > 0,
        }}
      />
    </Space>
  );
}

export function ProjectRunsStagePage(): JSX.Element {
  return (
    <StageSlotGate prompt="选择一条诊断路径以查看其运行中心。">
      {(slot) => <RunCenter slot={slot} />}
    </StageSlotGate>
  );
}

export default ProjectRunsStagePage;
// @AI_GENERATED: end
