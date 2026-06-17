// @AI_GENERATED: Kiro v1.0
/**
 * Skill 测试任务页面
 * 管理 Skill 的测试任务，支持创建、执行、查看测试任务
 */
import { useState, useEffect, useMemo } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { useNavigate } from 'react-router-dom';
import {
  Card, Table, Space, Typography, Tag, Row, Col, Statistic, Input, Select,
  Button, Tooltip, Empty, Spin, message, Popconfirm, Modal, Form, InputNumber,
} from 'antd';
import {
  ThunderboltOutlined, SearchOutlined, CheckCircleOutlined, SyncOutlined,
  ClockCircleOutlined, DeleteOutlined, EyeOutlined, PlayCircleOutlined,
  PlusOutlined, ReloadOutlined, ExperimentOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { templateSkillApi, type PackagedSkill } from '../services/templateSkillApi';

const { Text, Paragraph } = Typography;

// 测试任务状态
type TaskStatus = 'pending' | 'running' | 'completed' | 'failed';

// @AI_GENERATED
const STATUS_CONFIG: Record<TaskStatus, { labelKey: string; color: string; icon: React.ReactNode }> = {
  pending: { labelKey: 'skillTestTask.pending', color: 'default', icon: <ClockCircleOutlined /> },
  running: { labelKey: 'skillTestTask.running', color: 'processing', icon: <SyncOutlined spin /> },
  completed: { labelKey: 'skillTestTask.completed', color: 'success', icon: <CheckCircleOutlined /> },
  failed: { labelKey: 'skillTestTask.failed', color: 'error', icon: <ClockCircleOutlined /> },
};
// @AI_GENERATED: end

// 测试任务类型
interface SkillTestTask {
  task_id: string;
  skill_id: string;
  skill_name: string;
  test_type: 'training' | 'inference' | 'benchmark';
  status: TaskStatus;
  config: {
    epochs?: number;
    batch_size?: number;
    data_path?: string;
  };
  metrics?: {
    mape?: number;
    rmse?: number;
    duration_seconds?: number;
  };
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

// 模拟测试任务数据
const MOCK_TASKS: SkillTestTask[] = [
  {
    task_id: 'test-001',
    skill_id: 'skill-2365da5d',
    skill_name: '光伏发电功率预测 Skill',
    test_type: 'training',
    status: 'completed',
    config: { epochs: 80, batch_size: 32 },
    metrics: { mape: 6.95, rmse: 105.23, duration_seconds: 245 },
    created_at: '2026-03-23T10:00:00',
    started_at: '2026-03-23T10:00:05',
    completed_at: '2026-03-23T10:04:10',
  },
  {
    task_id: 'test-002',
    skill_id: 'skill-8f4a2b1c',
    skill_name: '电网负荷预测 Skill',
    test_type: 'benchmark',
    status: 'running',
    config: { epochs: 100, batch_size: 64 },
    created_at: '2026-03-23T11:00:00',
    started_at: '2026-03-23T11:00:10',
  },
  {
    task_id: 'test-003',
    skill_id: 'skill-3c7d9e2f',
    skill_name: '设备振动故障诊断 Skill',
    test_type: 'inference',
    status: 'pending',
    config: { batch_size: 16 },
    created_at: '2026-03-23T12:00:00',
  },
];

const SkillTestTaskPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [tasks, setTasks] = useState<SkillTestTask[]>(MOCK_TASKS);
  const [skills, setSkills] = useState<PackagedSkill[]>([]);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    loadSkills();
  }, []);

  const loadSkills = async () => {
    try {
      const response = await templateSkillApi.listSkills();
      setSkills(response.skills);
    } catch (error) {
      console.error(error);
    }
  };

  // 统计数据
  const stats = useMemo(() => {
    const total = tasks.length;
    const pending = tasks.filter(t => t.status === 'pending').length;
    const running = tasks.filter(t => t.status === 'running').length;
    const completed = tasks.filter(t => t.status === 'completed').length;
    const failed = tasks.filter(t => t.status === 'failed').length;
    return { total, pending, running, completed, failed };
  }, [tasks]);

  // 过滤后的任务
  const filteredTasks = useMemo(() => {
    return tasks.filter(t => {
      if (keyword && !t.skill_name.toLowerCase().includes(keyword.toLowerCase())) {
        return false;
      }
      if (statusFilter !== 'all' && t.status !== statusFilter) return false;
      return true;
    });
  }, [tasks, keyword, statusFilter]);

  // 创建测试任务
  const handleCreateTask = async (values: any) => {
    const skill = skills.find(s => s.skill_id === values.skill_id);
    if (!skill) return;

    const newTask: SkillTestTask = {
      task_id: `test-${Date.now()}`,
      skill_id: values.skill_id,
      skill_name: skill.skill_name,
      test_type: values.test_type,
      status: 'pending',
      config: {
        epochs: values.epochs,
        batch_size: values.batch_size,
      },
      created_at: new Date().toISOString(),
    };

    setTasks([newTask, ...tasks]);
    setCreateModalVisible(false);
    form.resetFields();
    message.success(t('skillTestTask.createSuccess'));
  };

  // 执行任务
  const handleRunTask = (task: SkillTestTask) => {
    setTasks(tasks.map(t => 
      t.task_id === task.task_id 
        ? { ...t, status: 'running' as TaskStatus, started_at: new Date().toISOString() }
        : t
    ));
    message.info(t('skillTestTask.startExecution', { name: task.skill_name }));
  };

  // 删除任务
  const handleDeleteTask = (taskId: string) => {
    setTasks(tasks.filter(t => t.task_id !== taskId));
    message.success(t('skillTestTask.deleteSuccess'));
  };

  const columns: ColumnsType<SkillTestTask> = [
    {
      title: t('skillTestTask.taskId'),
      dataIndex: 'task_id',
      key: 'task_id',
      width: 120,
      render: (id) => <Text code>{id}</Text>,
    },
    {
      title: t('skillTestTask.skillName'),
      dataIndex: 'skill_name',
      key: 'skill_name',
      width: 220,
      render: (name, record) => (
        <Space>
          <ThunderboltOutlined style={{ color: '#722ed1' }} />
          <Text
            style={{ cursor: 'pointer', color: '#1890ff' }}
            onClick={() => navigate(`/skill-library/${record.skill_id}`)}
          >
            {name}
          </Text>
        </Space>
      ),
    },
    {
      title: t('skillTestTask.testType'),
      dataIndex: 'test_type',
      key: 'test_type',
      width: 100,
      render: (type) => {
        const typeMap: Record<string, { label: string; color: string }> = {
          training: { label: t('skillTestTask.trainingTest'), color: 'purple' },
          inference: { label: t('skillTestTask.inferenceTest'), color: 'blue' },
          benchmark: { label: t('skillTestTask.benchmarkTest'), color: 'orange' },
        };
        const config = typeMap[type] || { label: type, color: 'default' };
        return <Tag color={config.color}>{config.label}</Tag>;
      },
    },
    {
      title: t('skillTestTask.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: TaskStatus) => {
        const config = STATUS_CONFIG[status];
        // @AI_GENERATED
        return <Tag color={config.color} icon={config.icon}>{t(config.labelKey)}</Tag>;
        // @AI_GENERATED: end
      },
    },
    {
      title: t('skillTestTask.config'),
      key: 'config',
      width: 150,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          {record.config.epochs && <Text style={{ fontSize: 12 }}>Epochs: {record.config.epochs}</Text>}
          {record.config.batch_size && <Text style={{ fontSize: 12 }}>Batch: {record.config.batch_size}</Text>}
        </Space>
      ),
    },
    {
      title: t('skillTestTask.testMetrics'),
      key: 'metrics',
      width: 150,
      render: (_, record) => record.metrics ? (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>MAPE: {record.metrics.mape?.toFixed(2)}%</Text>
          <Text style={{ fontSize: 12 }}>RMSE: {record.metrics.rmse?.toFixed(2)}</Text>
        </Space>
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: t('skillTestTask.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: t('skillTestTask.actions'),
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space size={4}>
          <Tooltip title={t('skillTestTask.viewDetail')}>
            <Button type="text" size="small" icon={<EyeOutlined />} onClick={() => navigate('/skill-test/results')} />
          </Tooltip>
          {record.status === 'pending' && (
            <Tooltip title={t('skillTestTask.execute')}>
              <Button type="text" size="small" icon={<PlayCircleOutlined />} onClick={() => handleRunTask(record)} />
            </Tooltip>
          )}
          <Popconfirm title={t('skillTestTask.confirmDelete')} onConfirm={() => handleDeleteTask(record.task_id)}>
            <Tooltip title={t('skillTestTask.delete')}>
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <ExperimentOutlined style={{ fontSize: 24, color: '#722ed1' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>{t('skillTestTask.title')}</Typography.Title>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          管理 Skill 的训练测试、推理测试和基准测试任务
        </Paragraph>
      </div>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={5}>
          <Card size="small">
            <Statistic title={t('skillTestTask.totalTasks')} value={stats.total} prefix={<ExperimentOutlined />} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title={t('skillTestTask.pendingCount')} value={stats.pending} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title={t('skillTestTask.runningCount')} value={stats.running} prefix={<SyncOutlined />} valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title={t('skillTestTask.completedCount')} value={stats.completed} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title={t('skillTestTask.failedCount')} value={stats.failed} valueStyle={{ color: '#ff4d4f' }} />
          </Card>
        </Col>
      </Row>

      {/* 筛选栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            prefix={<SearchOutlined />}
            placeholder={t('skillTestTask.searchPlaceholder')}
            allowClear
            style={{ width: 200 }}
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
          />
          <Select
            style={{ width: 120 }}
            placeholder={t('skillTestTask.statusFilter')}
            allowClear
            value={statusFilter === 'all' ? undefined : statusFilter}
            onChange={v => setStatusFilter(v || 'all')}
            options={[
              { value: 'pending', label: '待执行' },
              { value: 'running', label: '执行中' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={() => setLoading(false)}>{t('skillTestTask.refresh')}</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
            创建测试任务
          </Button>
        </Space>
      </Card>

      {/* 任务列表 */}
      <Card>
        <Spin spinning={loading}>
          {filteredTasks.length > 0 ? (
            <Table
              dataSource={filteredTasks}
              columns={columns}
              rowKey="task_id"
              size="small"
              pagination={{ pageSize: 10, showTotal: total => t('skillTestTask.totalCount', { count: total }) }}
            />
          ) : (
            <Empty description={t('skillTestTask.noTasks')} />
          )}
        </Spin>
      </Card>

      {/* 创建任务弹窗 */}
      <Modal
        title={t('skillTestTask.createTaskTitle')}
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        onOk={() => form.submit()}
        width={500}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateTask}>
          <Form.Item name="skill_id" label={t('skillTestTask.selectSkill')} rules={[{ required: true }]}>
            <Select placeholder={t('skillTestTask.selectSkillPlaceholder')}>
              {skills.map(s => (
                <Select.Option key={s.skill_id} value={s.skill_id}>{s.skill_name}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="test_type" label={t('skillTestTask.testTypeLabel')} rules={[{ required: true }]}>
            <Select placeholder={t('skillTestTask.selectTestType')}>
              <Select.Option value="training">训练测试</Select.Option>
              <Select.Option value="inference">推理测试</Select.Option>
              <Select.Option value="benchmark">基准测试</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="epochs" label={t('skillTestTask.epochs')} initialValue={80}>
            <InputNumber min={1} max={500} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="batch_size" label={t('skillTestTask.batchSize')} initialValue={32}>
            <InputNumber min={1} max={256} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SkillTestTaskPage;
// @AI_GENERATED: end
