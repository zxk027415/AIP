// @AI_GENERATED
/**
 * 三路径 readiness 展示（design §25）。
 *
 * 每条路径独立展示 status / 首要阻断 / 允许运行模式 / 下一步；文字优先、颜色辅助；
 * 明确 ready 不等于生产资格。可复用于数据接入版本行与总览。
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Skeleton, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { pvProjectsApi } from '../../services/pvProjectsApi';
import type { PathReadiness } from '../../services/pvProjectsApi';
import { buildJourneyHref } from '../../utils/journeyParams';
import { READINESS_COPY } from '../copy/stateVocabulary';
import type { ReadinessStatus } from '../types/scope';

const { Text } = Typography;

/** 各槽 canonical 打标工作流（与后端 CANONICAL_LABEL_WORKFLOW_BY_SLOT 一致）。 */
const CANONICAL_LABEL_WORKFLOW: Record<string, string> = {
  pv_day: 'workflow-pv-day-label-v1',
  pv_point: 'workflow-pv-point-label-v1',
  pv_tsc: 'workflow-pv-tsc-label-v1',
};

/** 允许直接启动 canonical 打标的 readiness 状态（needs_labels 为主要触发）。 */
const LABELABLE_STATUSES = new Set(['needs_labels', 'experiment_only', 'ready']);

const STATUS_COLOR: Record<string, string> = {
  ready: 'green',
  experiment_only: 'blue',
  needs_mapping: 'orange',
  needs_labels: 'orange',
  insufficient_data: 'orange',
  unsupported: 'red',
};

function statusTag(status: string): JSX.Element {
  const copy = READINESS_COPY[status as ReadinessStatus];
  return (
    <Tooltip title={copy?.hint}>
      <Tag color={STATUS_COLOR[status] || 'default'}>{copy?.label || status}</Tag>
    </Tooltip>
  );
}

export interface PathReadinessViewProps {
  projectId: string;
  versionId: string;
}

export function PathReadinessView({ projectId, versionId }: PathReadinessViewProps): JSX.Element {
  const navigate = useNavigate();
  const [paths, setPaths] = useState<PathReadiness[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    pvProjectsApi
      .getReadiness(projectId, versionId)
      .then((res) => {
        if (!cancelled) setPaths(res.paths);
      })
      .catch(() => {
        if (!cancelled) setError('readiness 读取失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, versionId]);

  if (loading) return <Skeleton active paragraph={{ rows: 2 }} />;
  if (error) return <Alert type="error" showIcon message={error} />;

  const columns: ColumnsType<PathReadiness> = [
    { title: '诊断路径', dataIndex: 'slot', render: (v: string) => <Text strong>{v}</Text> },
    { title: '状态', dataIndex: 'status', render: (s: string) => statusTag(s) },
    {
      title: '首要阻断',
      dataIndex: 'primary_blocker',
      render: (v: string | null) => v || <Text type="secondary">—</Text>,
    },
    {
      title: '允许运行模式',
      dataIndex: 'allowed_run_modes',
      render: (modes: string[]) =>
        modes.length ? modes.map((m) => <Tag key={m}>{m}</Tag>) : <Text type="secondary">无（需先修复）</Text>,
    },
    {
      title: '下一步',
      dataIndex: 'next_action',
      render: (v: string | null) => v || <Text type="secondary">—</Text>,
    },
    {
      title: 'canonical 打标',
      render: (_: unknown, row) => {
        const wf = CANONICAL_LABEL_WORKFLOW[row.slot];
        if (!wf || !LABELABLE_STATUSES.has(row.status)) {
          return <Text type="secondary">—</Text>;
        }
        // 直接启动 canonical 打标工作流，不经日/点标注 tab。
        return (
          <Button
            size="small"
            type={row.status === 'needs_labels' ? 'primary' : 'default'}
            onClick={() =>
              navigate(
                buildJourneyHref(
                  '/workflow-editor',
                  { projectId, slot: row.slot, datasetVersionId: versionId },
                  { workflow_id: wf, launch: 'canonical_labeling' },
                ),
              )
            }
          >
            启动 canonical 打标
          </Button>
        );
      },
    },
  ];

  return (
    <div>
      <Table rowKey="slot" columns={columns} dataSource={paths} pagination={false} size="small" />
      <Text type="secondary" style={{ fontSize: 12 }}>
        ready 只表示当前路径输入与预检合同可用，不表示生产 / 候选 / Promote 资格；生产由服务端独立门控。
      </Text>
    </div>
  );
}

export default PathReadinessView;

// @AI_GENERATED: end
