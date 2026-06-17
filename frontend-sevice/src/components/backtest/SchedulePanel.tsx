// @AI_GENERATED: Kiro v1.0
/**
 * 智能调度面板组件
 * 显示调度队列、资源配额、优化建议，支持手动调整优先级
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Progress, Row, Col, Statistic, Modal,
  Form, Select, DatePicker, InputNumber, Switch, message, Tooltip, Alert,
  Drawer, Typography, Divider, Badge, Popconfirm,
} from 'antd';
import {
  ThunderboltOutlined, ClockCircleOutlined, SettingOutlined,
  PlayCircleOutlined, DeleteOutlined, EditOutlined, RocketOutlined,
  WarningOutlined, CheckCircleOutlined, SyncOutlined, OrderedListOutlined,
  CloudServerOutlined, DesktopOutlined, DatabaseOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { backtestApi } from '../../services/backtestApi';
import type {
  ScheduledTask, ResourceQuota, ScheduleOptimizationResult,
  TaskScheduleConfig,
} from '../../types/backtest';
import { PRIORITY_CONFIG } from '../../types/backtest';

const { Text } = Typography;

interface SchedulePanelProps {
  visible: boolean;
  onClose: () => void;
  onTaskStarted?: () => void;
}

const SchedulePanel: React.FC<SchedulePanelProps> = ({ visible, onClose, onTaskStarted }) => {
  const [loading, setLoading] = useState(false);
  const [queue, setQueue] = useState<ScheduledTask[]>([]);
  const [quota, setQuota] = useState<ResourceQuota | null>(null);
  const [optimization, setOptimization] = useState<ScheduleOptimizationResult | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [quotaModalOpen, setQuotaModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [quotaForm] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [queueRes, quotaRes] = await Promise.all([
        backtestApi.getScheduleQueue(),
        backtestApi.getResourceQuota(),
      ]);
      setQueue(queueRes.queue);
      setOptimization(queueRes.optimization);
      setQuota(quotaRes);
    } catch (error) {
      console.error('Failed to fetch schedule data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (visible) {
      fetchData();
    }
  }, [visible, fetchData]);

  const handleEditTask = (task: ScheduledTask) => {
    setEditingTask(task);
    form.setFieldsValue({
      priority: task.schedule_config.priority,
      deadline: task.schedule_config.deadline ? dayjs(task.schedule_config.deadline) : null,
      estimated_duration_minutes: task.schedule_config.estimated_duration_minutes,
      gpu_required: task.schedule_config.gpu_required,
      cpu_required: task.schedule_config.cpu_required,
      memory_required_gb: task.schedule_config.memory_required_gb,
      allow_preemption: task.schedule_config.allow_preemption,
    });
    setEditModalOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!editingTask) return;
    try {
      const values = await form.validateFields();
      const config: Partial<TaskScheduleConfig> = {
        priority: values.priority,
        deadline: values.deadline ? values.deadline.toISOString() : undefined,
        estimated_duration_minutes: values.estimated_duration_minutes,
        gpu_required: values.gpu_required,
        cpu_required: values.cpu_required,
        memory_required_gb: values.memory_required_gb,
        allow_preemption: values.allow_preemption,
      };
      await backtestApi.updateTaskSchedule(editingTask.task_id, config);
      message.success('调度配置已更新');
      setEditModalOpen(false);
      fetchData();
    } catch (error) {
      message.error('更新失败');
    }
  };

  const handleRemoveTask = async (taskId: string) => {
    try {
      await backtestApi.removeTaskFromSchedule(taskId);
      message.success('已从调度队列移除');
      fetchData();
    } catch (error) {
      message.error('移除失败');
    }
  };

  const handleStartTask = async (taskId: string) => {
    try {
      await backtestApi.startScheduledTask(taskId);
      message.success('任务已启动');
      fetchData();
      onTaskStarted?.();
    } catch (error: any) {
      message.error(error.message || '启动失败');
    }
  };

  const handleOptimize = async () => {
    try {
      const result = await backtestApi.optimizeSchedule();
      setOptimization(result);
      message.success('调度优化完成');
      fetchData();
    } catch (error) {
      message.error('优化失败');
    }
  };

  const handleUpdateQuota = async () => {
    try {
      const values = await quotaForm.validateFields();
      await backtestApi.updateResourceQuota(values);
      message.success('资源配额已更新');
      setQuotaModalOpen(false);
      fetchData();
    } catch (error) {
      message.error('更新失败');
    }
  };

  const columns: ColumnsType<ScheduledTask> = [
    {
      title: '队列位置',
      dataIndex: 'queue_position',
      key: 'queue_position',
      width: 80,
      render: (pos) => (
        <Badge count={pos} style={{ backgroundColor: pos === 1 ? '#52c41a' : '#1890ff' }} />
      ),
    },
    {
      title: '任务名称',
      dataIndex: 'task_name',
      key: 'task_name',
      width: 180,
      render: (name) => <Text strong>{name}</Text>,
    },
    {
      title: '优先级',
      key: 'priority',
      width: 80,
      render: (_, record) => {
        const priority = record.schedule_config.priority;
        const config = PRIORITY_CONFIG[priority];
        return <Tag color={config.color}>{config.label}</Tag>;
      },
    },
    {
      title: '截止时间',
      key: 'deadline',
      width: 140,
      render: (_, record) => {
        const deadline = record.schedule_config.deadline;
        if (!deadline) return <Text type="secondary">无</Text>;
        const dt = dayjs(deadline);
        const isUrgent = dt.diff(dayjs(), 'hour') < 4;
        return (
          <Tooltip title={dt.format('YYYY-MM-DD HH:mm')}>
            <Text type={isUrgent ? 'danger' : undefined}>
              {isUrgent && <WarningOutlined style={{ marginRight: 4 }} />}
              {dt.format('MM-DD HH:mm')}
            </Text>
          </Tooltip>
        );
      },
    },
    {
      title: '资源需求',
      key: 'resources',
      width: 140,
      render: (_, record) => {
        const config = record.schedule_config;
        return (
          <Space direction="vertical" size={0}>
            <Text style={{ fontSize: 11 }}>GPU: {config.gpu_required} 核</Text>
            <Text style={{ fontSize: 11 }}>CPU: {config.cpu_required} 核</Text>
            <Text style={{ fontSize: 11 }}>内存: {config.memory_required_gb} GB</Text>
          </Space>
        );
      },
    },
    {
      title: '预估时长',
      key: 'duration',
      width: 90,
      render: (_, record) => (
        <Text>{record.schedule_config.estimated_duration_minutes} 分钟</Text>
      ),
    },
    {
      title: '预计开始',
      dataIndex: 'scheduled_start',
      key: 'scheduled_start',
      width: 100,
      render: (time) => time ? dayjs(time).format('HH:mm') : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status) => {
        const statusMap: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
          queued: { label: '排队中', color: 'default', icon: <ClockCircleOutlined /> },
          scheduled: { label: '已调度', color: 'blue', icon: <OrderedListOutlined /> },
          running: { label: '运行中', color: 'processing', icon: <SyncOutlined spin /> },
          completed: { label: '已完成', color: 'success', icon: <CheckCircleOutlined /> },
          preempted: { label: '被抢占', color: 'warning', icon: <WarningOutlined /> },
        };
        const config = statusMap[status] || statusMap.queued;
        return <Tag color={config.color} icon={config.icon}>{config.label}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Space size={4}>
          {record.status === 'queued' && (
            <Tooltip title="启动">
              <Button type="text" size="small" icon={<PlayCircleOutlined />} onClick={() => handleStartTask(record.task_id)} />
            </Tooltip>
          )}
          <Tooltip title="编辑">
            <Button type="text" size="small" icon={<EditOutlined />} onClick={() => handleEditTask(record)} />
          </Tooltip>
          <Popconfirm title="确定移除？" onConfirm={() => handleRemoveTask(record.task_id)}>
            <Tooltip title="移除">
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Drawer
      title={
        <Space>
          <ThunderboltOutlined style={{ color: '#722ed1' }} />
          <span>智能调度中心</span>
        </Space>
      }
      placement="right"
      width={900}
      open={visible}
      onClose={onClose}
      extra={
        <Space>
          <Button icon={<SettingOutlined />} onClick={() => {
            quotaForm.setFieldsValue(quota);
            setQuotaModalOpen(true);
          }}>
            资源配额
          </Button>
          <Button type="primary" icon={<RocketOutlined />} onClick={handleOptimize}>
            优化调度
          </Button>
        </Space>
      }
    >
      {/* 资源配额概览 */}
      {quota && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={8}>
              <div style={{ textAlign: 'center' }}>
                <CloudServerOutlined style={{ fontSize: 24, color: '#722ed1', marginBottom: 8 }} />
                <div style={{ marginBottom: 4 }}>
                  <Text strong>GPU</Text>
                </div>
                <Progress
                  type="circle"
                  size={80}
                  percent={Math.round((quota.gpu_reserved / quota.gpu_total) * 100)}
                  format={() => `${quota.gpu_reserved}/${quota.gpu_total}`}
                  strokeColor="#722ed1"
                />
                <div style={{ marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                  可用: {quota.gpu_available} 核
                </div>
              </div>
            </Col>
            <Col span={8}>
              <div style={{ textAlign: 'center' }}>
                <DesktopOutlined style={{ fontSize: 24, color: '#1890ff', marginBottom: 8 }} />
                <div style={{ marginBottom: 4 }}>
                  <Text strong>CPU</Text>
                </div>
                <Progress
                  type="circle"
                  size={80}
                  percent={Math.round((quota.cpu_reserved / quota.cpu_total) * 100)}
                  format={() => `${quota.cpu_reserved}/${quota.cpu_total}`}
                  strokeColor="#1890ff"
                />
                <div style={{ marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                  可用: {quota.cpu_available} 核
                </div>
              </div>
            </Col>
            <Col span={8}>
              <div style={{ textAlign: 'center' }}>
                <DatabaseOutlined style={{ fontSize: 24, color: '#52c41a', marginBottom: 8 }} />
                <div style={{ marginBottom: 4 }}>
                  <Text strong>内存</Text>
                </div>
                <Progress
                  type="circle"
                  size={80}
                  percent={Math.round(((quota.memory_total_gb - quota.memory_available_gb) / quota.memory_total_gb) * 100)}
                  format={() => `${quota.memory_total_gb - quota.memory_available_gb}/${quota.memory_total_gb}`}
                  strokeColor="#52c41a"
                />
                <div style={{ marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                  可用: {quota.memory_available_gb} GB
                </div>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* 优化建议 */}
      {optimization && optimization.recommendations.length > 0 && (
        <Alert
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          message="调度建议"
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {optimization.recommendations.map((rec, idx) => (
                <li key={idx}>{rec}</li>
              ))}
            </ul>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      {/* 截止时间违规警告 */}
      {optimization && optimization.deadline_violations.length > 0 && (
        <Alert
          type="error"
          showIcon
          message={`${optimization.deadline_violations.length} 个任务可能无法按时完成`}
          description={
            <Space direction="vertical" size={4}>
              {optimization.deadline_violations.slice(0, 3).map((v) => (
                <Text key={v.task_id} style={{ fontSize: 12 }}>
                  <WarningOutlined style={{ color: '#f5222d', marginRight: 4 }} />
                  {v.task_name}: 预计延迟 {v.delay_minutes} 分钟
                </Text>
              ))}
            </Space>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      {/* 调度统计 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Statistic title="队列任务" value={queue.filter(t => t.status === 'queued').length} />
        </Col>
        <Col span={6}>
          <Statistic title="运行中" value={queue.filter(t => t.status === 'running').length} valueStyle={{ color: '#1890ff' }} />
        </Col>
        <Col span={6}>
          <Statistic title="预计总时长" value={optimization?.total_estimated_time_minutes || 0} suffix="分钟" />
        </Col>
        <Col span={6}>
          <Statistic 
            title="资源利用率" 
            value={optimization?.resource_utilization.gpu_utilization || 0} 
            suffix="%" 
            valueStyle={{ color: '#722ed1' }}
          />
        </Col>
      </Row>

      <Divider style={{ margin: '12px 0' }} />

      {/* 调度队列表格 */}
      <Table
        dataSource={queue}
        columns={columns}
        rowKey="task_id"
        size="small"
        loading={loading}
        pagination={false}
        scroll={{ y: 400 }}
      />

      {/* 编辑调度配置弹窗 */}
      <Modal
        title="编辑调度配置"
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        onOk={handleSaveEdit}
        width={500}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="priority" label="优先级" rules={[{ required: true }]}>
            <Select>
              {Object.entries(PRIORITY_CONFIG).map(([key, config]) => (
                <Select.Option key={key} value={key}>
                  <Tag color={config.color}>{config.label}</Tag>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="deadline" label="截止时间">
            <DatePicker showTime style={{ width: '100%' }} placeholder="选择截止时间（可选）" />
          </Form.Item>
          <Form.Item name="estimated_duration_minutes" label="预估时长（分钟）" rules={[{ required: true }]}>
            <InputNumber min={1} max={1440} style={{ width: '100%' }} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="gpu_required" label="GPU 需求" rules={[{ required: true }]}>
                <InputNumber min={0} max={8} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="cpu_required" label="CPU 需求" rules={[{ required: true }]}>
                <InputNumber min={1} max={64} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="memory_required_gb" label="内存 (GB)" rules={[{ required: true }]}>
                <InputNumber min={1} max={256} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="allow_preemption" label="允许被抢占" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 资源配额设置弹窗 */}
      <Modal
        title="资源配额设置"
        open={quotaModalOpen}
        onCancel={() => setQuotaModalOpen(false)}
        onOk={handleUpdateQuota}
        width={400}
      >
        <Form form={quotaForm} layout="vertical">
          <Form.Item name="gpu_total" label="GPU 总量（核）" rules={[{ required: true }]}>
            <InputNumber min={1} max={32} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="cpu_total" label="CPU 总量（核）" rules={[{ required: true }]}>
            <InputNumber min={1} max={256} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="memory_total_gb" label="内存总量（GB）" rules={[{ required: true }]}>
            <InputNumber min={1} max={1024} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
};

export default SchedulePanel;
// @AI_GENERATED: end
