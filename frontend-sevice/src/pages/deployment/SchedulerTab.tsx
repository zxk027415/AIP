// @AI_GENERATED: algorithm-deployment-refactor 9.3 + 阶段3
/**
 * SchedulerTab.tsx — "算法部署 → 定时调度" Tab
 *
 * 新增（阶段3）：cron_expr 列 + 编辑弹窗（热更新）+ 立即触发按钮 + 顶部流程说明
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Button, Descriptions, Form, Input, InputNumber,
  Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  EditOutlined, PlayCircleOutlined, PlusOutlined, ProfileOutlined,
  ReloadOutlined, StopOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import {
  schedulerTaskApi,
  type ScheduledTaskCreate, type ScheduledTaskDetail, type ScheduledTaskSummary,
} from '../../services/deploymentApi';

const { Text } = Typography;

const STATUS_TAG: Record<ScheduledTaskSummary['status'], { color: string; label: string }> = {
  running: { color: 'processing', label: '运行中' },
  stopped: { color: 'default', label: '已停止' },
  failed: { color: 'error', label: '失败' },
};
const LAST_EXEC_TAG: Record<NonNullable<ScheduledTaskSummary['last_execution']>, { color: string; label: string }> = {
  success: { color: 'success', label: '成功' },
  failed: { color: 'error', label: '失败' },
  skipped: { color: 'warning', label: '跳过' },
};
const SCHEDULE_TYPE_LABEL: Record<ScheduledTaskSummary['schedule_type'], string> = {
  rolling_daily: '每日滚动', cron: 'Cron 表达式', interval: '固定间隔',
};
const PIPELINE_OPTIONS = [
  { value: 'load_forecast', label: '负荷预测（load_forecast）' },
  { value: 'pv_fault', label: '光伏故障（pv_fault）' },
];
function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

const SchedulerTab: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage();
  const [tasks, setTasks] = useState<ScheduledTaskSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [rowActionLoading, setRowActionLoading] = useState<Record<string, boolean>>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [form] = Form.useForm<ScheduledTaskCreate>();
  const [editOpen, setEditOpen] = useState(false);
  const [editTask, setEditTask] = useState<ScheduledTaskSummary | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editForm] = Form.useForm<{ cron_expr: string; trigger_time: string; max_window_days: number | null }>();
  const [detail, setDetail] = useState<{ open: boolean; loading: boolean; data: ScheduledTaskDetail | null }>({ open: false, loading: false, data: null });

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try { const res = await schedulerTaskApi.listScheduledTasks(); setTasks(res.tasks ?? []); }
    catch (err: any) { messageApi.error(`加载失败：${err?.message ?? String(err)}`); setTasks([]); }
    finally { setLoading(false); }
  }, [messageApi]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const handleStart = async (task: ScheduledTaskSummary) => {
    setRowActionLoading((s) => ({ ...s, [task.task_id]: true }));
    try { await schedulerTaskApi.startScheduledTask(task.task_id); messageApi.success(`已启动：${task.name}`); await loadTasks(); }
    catch (err: any) { messageApi.error(`启动失败：${err?.message ?? String(err)}`); }
    finally { setRowActionLoading((s) => ({ ...s, [task.task_id]: false })); }
  };

  const handleStop = async (task: ScheduledTaskSummary) => {
    setRowActionLoading((s) => ({ ...s, [task.task_id]: true }));
    try { await schedulerTaskApi.stopScheduledTask(task.task_id); messageApi.success(`已停止：${task.name}`); await loadTasks(); }
    catch (err: any) { messageApi.error(`停止失败：${err?.message ?? String(err)}`); }
    finally { setRowActionLoading((s) => ({ ...s, [task.task_id]: false })); }
  };

  const handleTriggerNow = async (task: ScheduledTaskSummary) => {
    setRowActionLoading((s) => ({ ...s, [task.task_id]: true }));
    try {
      await schedulerTaskApi.triggerTaskNow(task.task_id);
      messageApi.success(`已触发：${task.name}（后台执行中）`);
      // 触发后 3 / 6 / 12 秒自动刷新列表，让状态变化及时反映到 UI
      [3000, 3000, 6000].reduce((chain, delay) => {
        return chain.then(() => new Promise((resolve) => setTimeout(resolve, delay))).then(() => loadTasks());
      }, Promise.resolve());
    } catch (err: any) {
      messageApi.error(`触发失败：${err?.message ?? String(err)}`);
    } finally {
      setRowActionLoading((s) => ({ ...s, [task.task_id]: false }));
    }
  };

  const handleViewDetail = async (task: ScheduledTaskSummary) => {
    setDetail({ open: true, loading: true, data: null });
    try { const data = await schedulerTaskApi.getScheduledTask(task.task_id); setDetail({ open: true, loading: false, data }); }
    catch (err: any) { messageApi.error(`加载详情失败：${err?.message ?? String(err)}`); setDetail({ open: true, loading: false, data: null }); }
  };

  const openEdit = (task: ScheduledTaskSummary) => {
    setEditTask(task);
    editForm.setFieldsValue({ cron_expr: (task as any).cron_expr ?? '', trigger_time: (task as any).trigger_time ?? '02:00', max_window_days: task.max_window_days ?? null });
    setEditOpen(true);
  };

  const submitEdit = async () => {
    try {
      const values = await editForm.validateFields();
      if (!editTask) return;
      setEditSubmitting(true);
      await schedulerTaskApi.updateScheduledTask(editTask.task_id, {
        cron_expr: values.cron_expr || undefined,
        trigger_time: values.trigger_time || undefined,
        max_window_days: values.max_window_days ?? undefined,
      });
      messageApi.success(`已更新：${editTask.name}（运行中任务 cron 立即热更新）`);
      setEditOpen(false); editForm.resetFields(); await loadTasks();
    } catch (err: any) {
      if (err?.errorFields) return;
      messageApi.error(`更新失败：${err?.message ?? String(err)}`);
    } finally { setEditSubmitting(false); }
  };

  const openCreate = () => {
    form.resetFields();
    form.setFieldsValue({ schedule_type: 'cron', trigger_time: '02:00', max_window_days: 365, slot: 'default', status: 'stopped', retry_on_failure: true, max_retries: 3 } as Partial<ScheduledTaskCreate>);
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreateSubmitting(true);
      await schedulerTaskApi.createScheduledTask({ name: values.name, pipeline: values.pipeline, schedule_type: values.schedule_type, cron_expr: values.schedule_type === 'cron' ? values.cron_expr ?? null : null, trigger_time: values.trigger_time ?? '02:00', max_window_days: values.max_window_days ?? null, slot: values.slot ?? 'default', status: 'stopped', retry_on_failure: values.retry_on_failure ?? true, max_retries: values.max_retries ?? 3 });
      messageApi.success(`任务创建成功：${values.name}`); setCreateOpen(false); await loadTasks();
    } catch (err: any) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      messageApi.error(`创建失败：${err?.message ?? String(err)}`);
    } finally { setCreateSubmitting(false); }
  };

  const columns: ColumnsType<ScheduledTaskSummary> = [
    { title: '任务名称', dataIndex: 'name', width: 200, render: (name: string, row) => (<Space direction="vertical" size={2}><Text strong>{name}</Text><Text code style={{ fontSize: 11 }}>{row.task_id}</Text></Space>) },
    { title: '管线', dataIndex: 'pipeline', width: 130, render: (p: string) => <Tag>{p}</Tag> },
    { title: 'Cron 表达式', dataIndex: 'cron_expr', width: 140, render: (v: string | null) => v ? <Text code style={{ fontSize: 12 }}>{v}</Text> : <Text type="secondary" style={{ fontSize: 12 }}>（滚动触发）</Text> },
    { title: '状态', dataIndex: 'status', width: 90, render: (s: ScheduledTaskSummary['status']) => { const cfg = STATUS_TAG[s]; return <Tag color={cfg.color}>{cfg.label}</Tag>; } },
    { title: '上次执行', dataIndex: 'last_execution', width: 100, render: (r: ScheduledTaskSummary['last_execution']) => { if (!r) return <Tag>未执行</Tag>; const cfg = LAST_EXEC_TAG[r]; return <Tag color={cfg.color}>{cfg.label}</Tag>; } },
    { title: '上次执行时间', dataIndex: 'last_execution_time', width: 155, render: (t: string | null) => formatDateTime(t) },
    { title: '下次调度时间', dataIndex: 'next_scheduled_time', width: 155, render: (t: string | null) => formatDateTime(t) },
    {
      title: '操作', key: 'actions', width: 300, fixed: 'right',
      render: (_: unknown, row) => {
        const busy = rowActionLoading[row.task_id] ?? false;
        return (
          <Space size={4} wrap>
            {row.status !== 'running' && <Popconfirm title="确认启动？" onConfirm={() => handleStart(row)} okText="启动" cancelText="取消"><Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={busy}>启动</Button></Popconfirm>}
            {row.status === 'running' && <Popconfirm title="确认停止？" description="正在执行的批次仍会跑完。" onConfirm={() => handleStop(row)} okText="停止" cancelText="取消" okButtonProps={{ danger: true }}><Button size="small" danger icon={<StopOutlined />} loading={busy}>停止</Button></Popconfirm>}
            <Popconfirm title="立即触发一次（后台异步，不改 status）？" onConfirm={() => handleTriggerNow(row)} okText="触发" cancelText="取消"><Button size="small" icon={<ThunderboltOutlined />} loading={busy}>立即触发</Button></Popconfirm>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>编辑</Button>
            <Button size="small" icon={<ProfileOutlined />} onClick={() => handleViewDetail(row)}>详情</Button>
          </Space>
        );
      },
    },
  ];

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert type="info" showIcon message="负荷预测每日自动流程"
          description={<Text style={{ fontSize: 13 }}><strong>01:00</strong> lf_data_pull（拉数据）→ <strong>02:00</strong> lf_daily_rolling（训练+预测 ≤T-1，预测 T+1）→ <strong>次日04:00</strong> lf_accuracy_backfill（回填精度）。编辑 cron 后保存热更新，「立即触发」跳过等待立即执行。</Text>}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary">共 {tasks.length} 个任务</Text>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadTasks} loading={loading}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建任务</Button>
          </Space>
        </div>
        <Table<ScheduledTaskSummary> size="middle" rowKey="task_id" columns={columns} dataSource={tasks} loading={loading} pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 1300 }} locale={{ emptyText: '暂无调度任务（后端启动后自动写入默认任务）' }} />
      </Space>

      <Modal open={editOpen} title={`编辑调度：${editTask?.name ?? ''}`} onCancel={() => { if (!editSubmitting) { setEditOpen(false); editForm.resetFields(); } }} onOk={submitEdit} okText="保存（热更新）" cancelText="取消" confirmLoading={editSubmitting} width={440} destroyOnClose>
        <Alert type="info" showIcon message="cron 表达式保存后立即热更新，无需重启" style={{ marginBottom: 12 }} />
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item name="cron_expr" label="Cron 表达式（schedule_type=cron）"><Input placeholder="如 0 2 * * *（每天凌晨 2 点）" /></Form.Item>
          <Form.Item name="trigger_time" label="每日触发时间 HH:MM（schedule_type=rolling_daily）"><Input placeholder="02:00" /></Form.Item>
          <Form.Item name="max_window_days" label="滚动训练窗口最大天数"><InputNumber min={1} max={3650} style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal open={createOpen} title="新建调度任务" onCancel={() => { if (!createSubmitting) setCreateOpen(false); }} onOk={submitCreate} okText="创建" cancelText="取消" confirmLoading={createSubmitting} maskClosable={!createSubmitting} closable={!createSubmitting} width={560} destroyOnClose>
        <Form<ScheduledTaskCreate> form={form} layout="vertical" preserve={false} disabled={createSubmitting}>
          <Form.Item name="name" label="任务名称" rules={[{ required: true }]}><Input placeholder="如：负荷预测每日滚动训练" maxLength={80} /></Form.Item>
          <Form.Item name="pipeline" label="所属管线" rules={[{ required: true }]}><Select options={PIPELINE_OPTIONS} placeholder="选择管线" /></Form.Item>
          <Form.Item name="schedule_type" label="调度策略" rules={[{ required: true }]}>
            <Select options={[{ value: 'cron', label: 'Cron 表达式' }, { value: 'rolling_daily', label: '每日滚动' }, { value: 'interval', label: '固定间隔' }]} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, curr) => prev.schedule_type !== curr.schedule_type}>
            {({ getFieldValue }) => getFieldValue('schedule_type') === 'cron'
              ? <Form.Item name="cron_expr" label="Cron 表达式" rules={[{ required: true }]}><Input placeholder="如：0 2 * * *" /></Form.Item>
              : <Form.Item name="trigger_time" label="每日触发时间 HH:MM"><Input placeholder="02:00" /></Form.Item>}
          </Form.Item>
          <Form.Item name="max_window_days" label="滚动窗口最大天数"><InputNumber min={1} max={3650} style={{ width: '100%' }} placeholder="365" /></Form.Item>
          <Form.Item name="slot" label="关联槽位"><Input placeholder="default" /></Form.Item>
          <Form.Item name="retry_on_failure" label="失败自动重试" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="max_retries" label="最大重试次数"><InputNumber min={0} max={10} style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <TaskDetailModal open={detail.open} loading={detail.loading} data={detail.data} onClose={() => setDetail({ open: false, loading: false, data: null })} />
    </>
  );
};

const TaskDetailModal: React.FC<{ open: boolean; loading: boolean; data: ScheduledTaskDetail | null; onClose: () => void }> = ({ open, loading, data, onClose }) => (
  <Modal open={open} title="调度任务详情" onCancel={onClose} footer={<Button onClick={onClose}>关闭</Button>} width={640} destroyOnClose>
    {loading || !data ? (
      <Text type="secondary">{loading ? '加载中…' : '未获取到任务详情'}</Text>
    ) : (
      <Descriptions column={2} size="small" labelStyle={{ width: 130, color: '#64748b' }} bordered>
        <Descriptions.Item label="task_id" span={2}><Text code copyable={{ text: data.task_id }}>{data.task_id}</Text></Descriptions.Item>
        <Descriptions.Item label="任务名称" span={2}>{data.name}</Descriptions.Item>
        <Descriptions.Item label="管线">{data.pipeline}</Descriptions.Item>
        <Descriptions.Item label="调度类型">{SCHEDULE_TYPE_LABEL[data.schedule_type] ?? data.schedule_type}</Descriptions.Item>
        <Descriptions.Item label="Cron 表达式">{data.cron_expr ?? '—'}</Descriptions.Item>
        <Descriptions.Item label="每日触发时间">{data.trigger_time}</Descriptions.Item>
        <Descriptions.Item label="滚动窗口最大天数">{data.max_window_days ?? '不限'}</Descriptions.Item>
        <Descriptions.Item label="部署槽位">{data.slot}</Descriptions.Item>
        <Descriptions.Item label="状态"><Tag color={STATUS_TAG[data.status].color}>{STATUS_TAG[data.status].label}</Tag></Descriptions.Item>
        <Descriptions.Item label="上次执行结果">{data.last_result ? <Tag color={LAST_EXEC_TAG[data.last_result].color}>{LAST_EXEC_TAG[data.last_result].label}</Tag> : <Tag>未执行</Tag>}</Descriptions.Item>
        <Descriptions.Item label="上次执行时间">{formatDateTime(data.last_execution_time)}</Descriptions.Item>
        <Descriptions.Item label="下次调度时间">{formatDateTime(data.next_scheduled_time)}</Descriptions.Item>
        <Descriptions.Item label="失败自动重试">{data.retry_on_failure ? '开启' : '关闭'}</Descriptions.Item>
        <Descriptions.Item label="最大重试次数">{data.max_retries}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatDateTime(data.created_at)}</Descriptions.Item>
        <Descriptions.Item label="最后更新">{formatDateTime(data.updated_at)}</Descriptions.Item>
      </Descriptions>
    )}
  </Modal>
);

export default SchedulerTab;
// @AI_GENERATED: end
