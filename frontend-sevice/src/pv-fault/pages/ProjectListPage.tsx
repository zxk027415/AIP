// @AI_GENERATED
/**
 * 项目列表与创建（design §12）。跨领域列出项目，先选行业场景 + 算法方案再接入数据。
 * requirements.md R1.1、R2.1、R13.2–R13.4、R13.23–R13.24。
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import { pvProjectsApi } from '../../services/pvProjectsApi';
import type { CatalogEntry, CreateProjectRequest, ProjectSummary } from '../../services/pvProjectsApi';
import { listSolutionAdapters } from '../adapters';
import ProjectEfficiencyBar from '../components/ProjectEfficiencyBar';
import CommandPalette from '../components/CommandPalette';

const { Title, Text } = Typography;

export function ProjectListPage(): JSX.Element {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm<CreateProjectRequest>();
  const [catalogEntries, setCatalogEntries] = useState<CatalogEntry[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const selectedEntryId = Form.useWatch('catalog_entry_id', form);
  const selectedEntry = catalogEntries.find((e) => e.entry_id === selectedEntryId);

  const applicableSlots = Object.entries(selectedEntry?.applicable_paths || {})
    .filter(([, info]) => info?.applicable)
    .map(([slot]) => slot);
  const defaultMountSlot = selectedEntry?.origin_slot && applicableSlots.includes(selectedEntry.origin_slot)
    ? selectedEntry.origin_slot
    : (applicableSlots.length === 1 ? applicableSlots[0] : undefined);

  const solutionOptions = listSolutionAdapters().map((a) => ({ value: a.solutionId, label: a.displayName }));

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    pvProjectsApi
      .listProjects(true)
      .then((res) => setProjects(res.projects))
      .catch(() => setError('项目列表读取失败'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!createOpen) return;
    setCatalogLoading(true);
    pvProjectsApi
      .listCatalog()
      .then((res) => setCatalogEntries(res.entries || []))
      .catch(() => setCatalogEntries([]))
      .finally(() => setCatalogLoading(false));
  }, [createOpen]);

  useEffect(() => {
    // 切换数据集时必须同步清掉上一条目的路径，不能把旧 mount_slot 带到新条目。
    form.setFieldValue('mount_slot', defaultMountSlot);
  }, [defaultMountSlot, form]);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      const created = await pvProjectsApi.createProject(values);
      message.success('项目已创建');
      setCreateOpen(false);
      form.resetFields();
      navigate(`/projects/${created.project_id}/overview`);
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return; // 表单校验失败
      message.error('创建项目失败');
    } finally {
      setCreating(false);
    }
  };

  const columns: ColumnsType<ProjectSummary> = [
    {
      title: '项目名称',
      dataIndex: 'project_name',
      render: (name: string | undefined, row) => (
        <a onClick={() => navigate(`/projects/${row.project_id}/overview`)}>{name || row.project_id}</a>
      ),
    },
    { title: '行业场景', dataIndex: 'scenario_id', render: (v?: string) => v || <Text type="secondary">—</Text> },
    { title: '算法方案', dataIndex: 'solution_id', render: (v?: string) => v || <Text type="secondary">—</Text> },
    { title: '负责人', dataIndex: 'owner', render: (v?: string) => v || <Text type="secondary">—</Text> },
    {
      title: '状态',
      dataIndex: 'read_only',
      render: (readOnly?: boolean) => (readOnly ? <Tag color="default">历史只读</Tag> : <Tag color="green">可写</Tag>),
    },
  ];

  return (
    <div style={{ padding: 24, minHeight: '100%' }}>
      <div style={{ maxWidth: 1440, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <Title level={3} style={{ margin: 0 }}>
              项目工作台
            </Title>
            <Text type="secondary">先选可直接挂载的数据集，再进入项目看对应路径和工作流模板。</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            创建项目
          </Button>
        </div>

        {/* 效率层：继续上次 + 最近访问；命令面板由 Ctrl/Cmd+K 触发 */}
        <ProjectEfficiencyBar />
        <CommandPalette />

        {error && (
          <Alert
            type="error"
            showIcon
            message={error}
            action={<Button size="small" onClick={load}>重试</Button>}
            style={{ marginBottom: 16 }}
          />
        )}

        {loading ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : projects.length === 0 ? (
          <Alert
            type="info"
            showIcon
            message="还没有项目"
            description="创建项目时先选可挂载数据集；没有已发布条目请先到数据集目录检测发布。"
          />
        ) : (
          <Table
            rowKey="project_id"
            columns={columns}
            dataSource={projects}
            pagination={{ pageSize: 20, hideOnSinglePage: true }}
            size="middle"
          />
        )}
      </div>

      <Modal
        title="创建项目"
        open={createOpen}
        onOk={handleCreate}
        confirmLoading={creating}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
        cancelText="取消"
        destroyOnClose
        width={560}
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="catalog_entry_id"
            label="可直接挂载的数据集"
            extra={
              catalogEntries.length === 0 && !catalogLoading
                ? '目录里还没有已发布条目。可先创建空项目，或到数据集目录检测并发布。'
                : '选数据集后会带出对应路径；路径可改，但不能先空着选路径。'
            }
          >
            <Select
              allowClear
              showSearch
              loading={catalogLoading}
              placeholder="先选数据集"
              optionFilterProp="label"
              options={catalogEntries.map((entry) => ({
                value: entry.entry_id,
                label: `${entry.display_name}（${entry.origin_slot || '未判定路径'}）`,
              }))}
            />
          </Form.Item>
          {selectedEntry && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message={`来源路径 ${selectedEntry.origin_slot || '未判定'}；适用 ${applicableSlots.join(' / ') || '未检出'}`}
              description={selectedEntry.dataset_ref}
            />
          )}
          <Form.Item name="mount_slot" label="对应诊断路径">
            <Select
              allowClear
              placeholder={selectedEntry ? '确认该数据集对应哪条路径' : '先选数据集'}
              disabled={!selectedEntry}
              options={applicableSlots.map((slot) => ({
                value: slot,
                label: slot,
              }))}
            />
          </Form.Item>
          <Form.Item name="project_name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="如：外部电站A 三路径复验" />
          </Form.Item>
          <Form.Item name="owner" label="负责人">
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item name="scenario_id" label="行业场景">
            <Input placeholder="如：renewable-energy" />
          </Form.Item>
          <Form.Item name="solution_id" label="算法方案">
            <Select allowClear placeholder="选择已接入工作台的算法方案" options={solutionOptions} />
          </Form.Item>
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              不选数据集也可以创建空项目；已选数据集将在创建时挂载，不继承其它项目的审核 / 模型状态。
            </Text>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}

export default ProjectListPage;

// @AI_GENERATED: end
