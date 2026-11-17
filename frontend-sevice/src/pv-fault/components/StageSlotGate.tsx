// @AI_GENERATED
/**
 * 阶段闸：先展示本项目已挂载数据集，再进入对应诊断路径。
 * 不再在未选 slot 时只给一条「请选路径」空态（用户已推翻不静默默认 slot 的旧闸门形态）。
 */

import type { ReactNode } from 'react';
import { useOutletContext, useSearchParams, useNavigate } from 'react-router-dom';
import { Button, Empty, Segmented, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useProjectScope } from '../../contexts/ProjectScopeContext';
import type { WorkbenchOutletContext } from '../pages/ProjectWorkbenchLayout';
import type { MountedDatasetView } from '../../services/pvProjectsApi';

const { Text } = Typography;

const SLOT_LABEL: Record<string, string> = {
  pv_day: '天路径',
  pv_point: '点路径',
  pv_tsc: 'TSC 路径',
};

export interface StageSlotGateProps {
  children: (slot: string) => ReactNode;
  prompt?: string;
}

export function StageSlotGate({ children, prompt }: StageSlotGateProps): JSX.Element {
  const { adapter, overview } = useOutletContext<WorkbenchOutletContext>();
  const { scope } = useProjectScope();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const projectId = overview?.project_id || scope.projectId;
  const datasets = overview?.mounted_datasets ?? [];

  const pickSlot = (slot: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('slot', slot);
    setSearchParams(next, { replace: false });
  };

  if (scope.slot) {
    return <>{children(scope.slot)}</>;
  }

  const columns: ColumnsType<MountedDatasetView> = [
    {
      title: '数据集',
      render: (_: unknown, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.display_name || row.dataset_ref}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.dataset_ref}
          </Text>
        </Space>
      ),
    },
    {
      title: '对应路径',
      render: (_: unknown, row) => (
        <Space wrap>
          {(row.applicable_slots?.length ? row.applicable_slots : row.origin_slot ? [row.origin_slot] : []).map(
            (slot) => (
              <Tag key={slot} color={slot === 'pv_point' ? 'purple' : slot === 'pv_tsc' ? 'geekblue' : 'blue'}>
                {SLOT_LABEL[slot] || slot}
              </Tag>
            ),
          )}
        </Space>
      ),
    },
    {
      title: '',
      render: (_: unknown, row) => {
        const slot = row.origin_slot || row.applicable_slots?.[0];
        if (!slot) return null;
        return (
          <Button type="link" onClick={() => pickSlot(slot)}>
            用该数据集进入路径
          </Button>
        );
      },
    },
  ];

  const options = (adapter?.paths ?? []).map((p) => ({ label: `${p.label}（${p.slot}）`, value: p.slot }));

  return (
    <Empty
      description={
        <Space direction="vertical" size={12} style={{ width: 'min(720px, 100%)' }}>
          <Text>{prompt || '先选择已挂载的数据集，再进入对应诊断路径。'}</Text>
          {datasets.length > 0 ? (
            <Table
              rowKey="dataset_id"
              columns={columns}
              dataSource={datasets}
              pagination={false}
              size="small"
            />
          ) : (
            <Space>
              <Button type="primary" onClick={() => navigate(`/projects/${projectId}/overview`)}>
                去看本项目数据集
              </Button>
              <Button onClick={() => navigate('/datasets/catalog')}>打开平台数据集目录</Button>
            </Space>
          )}
          {options.length > 0 && (
            <div>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                或直接选路径（兼容深链接）
              </Text>
              <Segmented options={options} onChange={(value) => pickSlot(String(value))} />
            </div>
          )}
        </Space>
      }
    />
  );
}

export default StageSlotGate;
// @AI_GENERATED: end
