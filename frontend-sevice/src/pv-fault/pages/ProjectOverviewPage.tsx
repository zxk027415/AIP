// @AI_GENERATED
/**
 * 项目页：已挂载数据集 → 对应路径 → 该路径工作流模板。
 *
 * 三路径生命周期矩阵不再作为项目主视图（它是平台级精度/部署总览）。
 */

import { useOutletContext, useNavigate } from 'react-router-dom';
import { Alert, Button, Empty, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { WorkbenchOutletContext } from './ProjectWorkbenchLayout';
import type { MountedDatasetView, SlotLifecycle, WorkflowTemplateSummary } from '../../services/pvProjectsApi';
import { useProjectScope } from '../../contexts/ProjectScopeContext';

const { Text, Title } = Typography;

const SLOT_LABEL: Record<string, string> = {
  pv_day: '天路径',
  pv_point: '点路径',
  pv_tsc: 'TSC 路径',
};

const READINESS_BLOCKED = new Set([
  'needs_mapping',
  'needs_labels',
  'insufficient_data',
  'unsupported',
  'unavailable',
]);

/** 该路径当前是否可推进（供其他阶段页复用）。 */
export function isPathAdvanceable(p: SlotLifecycle): boolean {
  if (p.stage === 'UNCONFIGURED') return false;
  if (!p.readiness_status) return false;
  return !READINESS_BLOCKED.has(p.readiness_status);
}

function slotTag(slot: string): JSX.Element {
  const color = slot === 'pv_day' ? 'blue' : slot === 'pv_point' ? 'purple' : 'geekblue';
  return <Tag color={color}>{SLOT_LABEL[slot] || slot}</Tag>;
}

export function ProjectOverviewPage(): JSX.Element {
  const { overview } = useOutletContext<WorkbenchOutletContext>();
  const navigate = useNavigate();
  const { scope } = useProjectScope();
  const projectId = overview?.project_id || scope.projectId;

  if (!overview) {
    return <Alert type="info" showIcon message="暂无项目数据" />;
  }

  const datasets = overview.mounted_datasets ?? [];
  const pathTemplates = overview.path_templates ?? {};

  const openPath = (slot: string) => {
    navigate(`/projects/${projectId}/workflows?slot=${encodeURIComponent(slot)}`);
  };

  const columns: ColumnsType<MountedDatasetView> = [
    {
      title: '数据集',
      render: (_: unknown, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.display_name || row.dataset_ref || row.dataset_id}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.dataset_ref || '（无相对引用）'}
          </Text>
        </Space>
      ),
    },
    {
      title: '对应路径',
      render: (_: unknown, row) => (
        <Space wrap>
          {row.origin_slot ? slotTag(row.origin_slot) : null}
          {(row.applicable_slots || [])
            .filter((slot) => slot !== row.origin_slot)
            .map((slot) => (
              <span key={slot}>{slotTag(slot)}</span>
            ))}
          {!row.origin_slot && (row.applicable_slots || []).length === 0 ? (
            <Text type="secondary">未判定</Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: '该路径已有工作流',
      render: (_: unknown, row) => {
        const slots = row.applicable_slots?.length ? row.applicable_slots : row.origin_slot ? [row.origin_slot] : [];
        if (slots.length === 0) return <Text type="secondary">—</Text>;
        return (
          <Space direction="vertical" size={4}>
            {slots.map((slot) => {
              const wfs = row.workflows_by_slot?.[slot] || [];
              return (
                <div key={slot}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {SLOT_LABEL[slot] || slot}：
                  </Text>
                  {wfs.length === 0 ? (
                    <Text type="secondary"> 尚未创建</Text>
                  ) : (
                    wfs.map((wf) => (
                      <Tag key={wf.project_workflow_id}>{wf.name || wf.project_workflow_id}</Tag>
                    ))
                  )}
                </div>
              );
            })}
          </Space>
        );
      },
    },
    {
      title: '可用工作流模板',
      render: (_: unknown, row) => {
        const slots = row.applicable_slots?.length ? row.applicable_slots : row.origin_slot ? [row.origin_slot] : [];
        const templates: WorkflowTemplateSummary[] = slots.flatMap((slot) => row.templates_by_slot?.[slot] || []);
        if (templates.length === 0) return <Text type="secondary">该路径暂无模板</Text>;
        return (
          <Space wrap>
            {templates.slice(0, 4).map((tpl) => (
              <Tag key={tpl.template_id}>{tpl.name}</Tag>
            ))}
            {templates.length > 4 ? <Text type="secondary">+{templates.length - 4}</Text> : null}
          </Space>
        );
      },
    },
    {
      title: '',
      render: (_: unknown, row) => {
        const slot = row.origin_slot || row.applicable_slots?.[0];
        if (!slot) return null;
        return (
          <Button type="link" onClick={() => openPath(slot)}>
            进入该路径工作流
          </Button>
        );
      },
    },
  ];

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="先看数据集，再看对应路径和工作流模板"
        description="精度、当前模型和三路径并列汇总在「精度运营 / 模型部署」，不在项目页里用生命周期矩阵代替数据集。"
      />

      <Title level={5} style={{ marginTop: 0 }}>
        本项目已挂载的数据集
      </Title>

      {datasets.length === 0 ? (
        <Empty
          description={
            <Space direction="vertical">
              <Text>还没有挂载可直接使用的数据集。</Text>
              <Space>
                <Button type="primary" onClick={() => navigate(`/projects/${projectId}/data`)}>
                  去数据与兼容性接入
                </Button>
                <Button onClick={() => navigate('/datasets/catalog')}>打开平台数据集目录</Button>
              </Space>
            </Space>
          }
        />
      ) : (
        <Table
          rowKey="dataset_id"
          columns={columns}
          dataSource={datasets}
          pagination={false}
          size="middle"
        />
      )}

      <Title level={5} style={{ marginTop: 28 }}>
        三条路径的工作流模板（未挂载数据也可预览）
      </Title>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        {(['pv_day', 'pv_point', 'pv_tsc'] as const).map((slot) => {
          const templates = pathTemplates[slot] || [];
          return (
            <div key={slot} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <div style={{ width: 88 }}>{slotTag(slot)}</div>
              <div style={{ flex: 1 }}>
                {templates.length === 0 ? (
                  <Text type="secondary">暂无模板</Text>
                ) : (
                  <Space wrap>
                    {templates.map((tpl) => (
                      <Tag key={tpl.template_id}>{tpl.name}</Tag>
                    ))}
                  </Space>
                )}
              </div>
              <Button size="small" onClick={() => openPath(slot)}>
                打开工作流
              </Button>
            </div>
          );
        })}
      </Space>
    </div>
  );
}

export default ProjectOverviewPage;
// @AI_GENERATED: end
