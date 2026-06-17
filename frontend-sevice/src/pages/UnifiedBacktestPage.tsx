// @AI_GENERATED: Kiro v1.0
/**
 * 统一回测页面
 * 整合工作流回测和 Skill 测试，支持类型切换
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card, Table, Button, Space, Tag, Badge, Modal, Steps, Form, Input,
  Select, Transfer, Checkbox, message, Popconfirm, Row, Col, Statistic, Tooltip,
  Segmented, Spin, Empty, InputNumber, Typography, DatePicker, Switch,
} from 'antd';
import {
  PlusOutlined, PlayCircleOutlined, DeleteOutlined, CopyOutlined,
  ExperimentOutlined, DatabaseOutlined, RocketOutlined, CheckCircleOutlined,
  ApartmentOutlined, ThunderboltOutlined, SyncOutlined, ClockCircleOutlined,
  EyeOutlined, ReloadOutlined, SearchOutlined, ScheduleOutlined, CalendarOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { backtestApi } from '../services/backtestApi';
import type { BacktestTask, BacktestStats, BacktestDatasetRef, BacktestAlgorithmRef } from '../types/backtest';
import { TASK_STATUS_CONFIG, METRIC_OPTIONS, SCENARIO_METRICS, PRIORITY_CONFIG } from '../types/backtest';
import { templateSkillApi, type PackagedSkill } from '../services/templateSkillApi';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import SchedulePanel from '../components/backtest/SchedulePanel';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

// @AI_GENERATED
// 场景列表
const SCENARIOS = [
  { value: 'renewable-energy', label: '新能源' },
  { value: 'industrial-manufacturing', label: '工业制造' },
  { value: 'grid-load-storage', label: '源网荷储' },
  { value: 'carbon-management', label: '碳管理' },
  { value: 'building-park', label: '楼宇园区' },
  { value: 'port-transport', label: '港口运输' },
  { value: 'general-industry', label: '通用工业' },
];
// @AI_GENERATED: end

// Mock datasets
const MOCK_DATASETS: BacktestDatasetRef[] = [
  { id: 'ds-001', name: '光伏电站A-2025年数据' },
  { id: 'ds-002', name: '光伏电站B-2025年数据' },
  { id: 'ds-003', name: '光伏电站C-2024年数据' },
  { id: 'ds-101', name: '华东电网-2025Q1' },
  { id: 'ds-102', name: '华南电网-2025Q1' },
  { id: 'ds-201', name: '电机振动数据集' },
  { id: 'ds-301', name: '工业园区A碳排放' },
];

const MOCK_ALGORITHMS: BacktestAlgorithmRef[] = [
  { type: 'template', id: 'pv_power_forecast', name: '光伏发电功率预测' },
  { type: 'template', id: 'lstm_forecast', name: 'LSTM时序预测' },
  { type: 'template', id: 'load_forecast_lstm', name: 'LSTM负荷预测' },
  { type: 'workflow', id: 'wf-001', name: '集成预测模板' },
];

// Skill 测试任务类型
type SkillTaskStatus = 'pending' | 'running' | 'completed' | 'failed';

interface SkillTestTask {
  task_id: string;
  skill_id: string;
  skill_name: string;
  test_type: 'training' | 'inference' | 'benchmark';
  status: SkillTaskStatus;
  config: { epochs?: number; batch_size?: number };
  metrics?: { mape?: number; rmse?: number; duration_seconds?: number };
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

const MOCK_SKILL_TASKS: SkillTestTask[] = [
  {
    task_id: 'test-001',
    skill_id: 'skill-2365da5d',
    skill_name: '光伏发电功率预测 Skill',
    test_type: 'training',
    status: 'completed',
    config: { epochs: 80, batch_size: 32 },
    metrics: { mape: 6.95, rmse: 105.23, duration_seconds: 245 },
    created_at: '2026-03-23T10:00:00',
  },
  {
    task_id: 'test-002',
    skill_id: 'skill-8f4a2b1c',
    skill_name: '电网负荷预测 Skill',
    test_type: 'benchmark',
    status: 'running',
    config: { epochs: 100, batch_size: 64 },
    created_at: '2026-03-23T11:00:00',
  },
];

const UnifiedBacktestPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const initialType = searchParams.get('type') === 'skill' ? 'skill' : 'workflow';
  
  const [testType, setTestType] = useState<'workflow' | 'skill'>(initialType);
  
  // 工作流回测状态
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [stats, setStats] = useState<BacktestStats>({ total_tasks: 0, running_tasks: 0, completed_tasks: 0, avg_score: 0 });
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [filterScenario, setFilterScenario] = useState<string | undefined>();
  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [form] = Form.useForm();
  const [selectedDatasetKeys, setSelectedDatasetKeys] = useState<string[]>([]);
  const [selectedAlgorithmKeys, setSelectedAlgorithmKeys] = useState<string[]>([]);
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(['rmse', 'mae', 'r2']);
  const [primaryMetric, setPrimaryMetric] = useState('rmse');

  // Skill 测试状态
  const [skillTasks, setSkillTasks] = useState<SkillTestTask[]>(MOCK_SKILL_TASKS);
  const [skills, setSkills] = useState<PackagedSkill[]>([]);
  const [skillLoading, setSkillLoading] = useState(false);
  const [skillKeyword, setSkillKeyword] = useState('');
  const [skillStatusFilter, setSkillStatusFilter] = useState<SkillTaskStatus | 'all'>('all');
  const [skillModalOpen, setSkillModalOpen] = useState(false);
  const [skillForm] = Form.useForm();

  // @AI_GENERATED: Kiro v1.0
  // 智能调度面板状态
  const [schedulePanelOpen, setSchedulePanelOpen] = useState(false);
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [schedulingTaskId, setSchedulingTaskId] = useState<string | null>(null);
  const [scheduleForm] = Form.useForm();
  
  // 从策划 Agent 跳转时的预选模板状态
  const [preselectedTemplateId, setPreselectedTemplateId] = useState<string | null>(null);
  const [preselectedTemplateType, setPreselectedTemplateType] = useState<'workflow' | 'skill' | null>(null);
  // @AI_GENERATED: end

  // 切换类型时更新 URL
  const handleTypeChange = (type: 'workflow' | 'skill') => {
    setTestType(type);
    setSearchParams({ type });
  };
  
  // @AI_GENERATED: Kiro v1.0
  // 处理从策划 Agent 跳转时的模板预选
  useEffect(() => {
    const templateId = searchParams.get('templateId');
    const templateType = searchParams.get('templateType') as 'workflow' | 'skill' | null;
    
    if (templateId && templateType) {
      setPreselectedTemplateId(templateId);
      setPreselectedTemplateType(templateType);
      
      // 根据模板类型切换到对应的标签页
      if (templateType === 'skill') {
        setTestType('skill');
        // 自动打开 Skill 测试创建弹窗
        setSkillModalOpen(true);
        message.info(t('unifiedBacktest.preselectedSkill'));
      } else {
        setTestType('workflow');
        // 自动打开工作流回测创建弹窗
        setModalOpen(true);
        message.info(t('unifiedBacktest.preselectedWorkflow'));
      }
      
      // 清除 URL 中的模板参数，保留 type 参数
      setSearchParams({ type: templateType });
    }
  }, []);
  // @AI_GENERATED: end

  // 加载工作流回测数据
  const fetchWorkflowData = useCallback(async () => {
    setLoading(true);
    try {
      const [taskRes, statsRes] = await Promise.all([
        backtestApi.listTasks({ scenario: filterScenario, status: filterStatus }),
        backtestApi.getStats(),
      ]);
      setTasks(taskRes.items);
      setStats(statsRes);
    } catch {
      message.error(t('unifiedBacktest.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [filterScenario, filterStatus]);

  // 加载 Skill 数据
  const loadSkills = async () => {
    try {
      const response = await templateSkillApi.listSkills();
      setSkills(response.skills);
    } catch (error) {
      console.error(error);
    }
  };

  useEffect(() => {
    if (testType === 'workflow') {
      fetchWorkflowData();
    } else {
      loadSkills();
    }
  }, [testType, fetchWorkflowData]);

  // 工作流回测操作
  const handleExecute = async (id: string) => {
    try {
      await backtestApi.executeTask(id);
      message.success(t('unifiedBacktest.executeSuccess'));
      fetchWorkflowData();
    } catch {
      message.error(t('unifiedBacktest.executeFailed'));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await backtestApi.deleteTask(id);
      message.success(t('unifiedBacktest.deleted'));
      fetchWorkflowData();
    } catch {
      message.error(t('unifiedBacktest.deleteFailed'));
    }
  };

  const handleClone = async (id: string) => {
    try {
      await backtestApi.cloneTask(id);
      message.success(t('unifiedBacktest.cloned'));
      fetchWorkflowData();
    } catch {
      message.error(t('unifiedBacktest.cloneFailed'));
    }
  };

  // @AI_GENERATED: Kiro v1.0
  // 智能调度操作
  const handleOpenScheduleModal = (taskId: string) => {
    setSchedulingTaskId(taskId);
    scheduleForm.resetFields();
    scheduleForm.setFieldsValue({
      priority: 'normal',
      gpu_required: 2,
      cpu_required: 8,
      memory_required_gb: 16,
      estimated_duration_minutes: 30,
      allow_preemption: false,
    });
    setScheduleModalOpen(true);
  };

  const handleAddToSchedule = async () => {
    if (!schedulingTaskId) return;
    try {
      const values = await scheduleForm.validateFields();
      await backtestApi.addTaskToSchedule(schedulingTaskId, {
        priority: values.priority,
        deadline: values.deadline ? values.deadline.toISOString() : undefined,
        estimated_duration_minutes: values.estimated_duration_minutes,
        gpu_required: values.gpu_required,
        cpu_required: values.cpu_required,
        memory_required_gb: values.memory_required_gb,
        allow_preemption: values.allow_preemption,
      });
      message.success(t('unifiedBacktest.addedToSchedule'));
      setScheduleModalOpen(false);
      setSchedulingTaskId(null);
    } catch (error: any) {
      message.error(error.message || t('unifiedBacktest.addFailed'));
    }
  };
  // @AI_GENERATED: end

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      const datasets = MOCK_DATASETS.filter(d => selectedDatasetKeys.includes(d.id));
      const algorithms = MOCK_ALGORITHMS.filter(a => selectedAlgorithmKeys.includes(a.id));
      if (datasets.length === 0 || algorithms.length === 0) {
        message.warning(t('unifiedBacktest.selectDatasetAndAlgo'));
        return;
      }
      await backtestApi.createTask({
        name: values.name,
        description: values.description || '',
        scenario_id: values.scenario_id,
        datasets,
        algorithms,
        metrics_config: { primary_metric: primaryMetric, metrics: selectedMetrics, thresholds: {} },
      });
      message.success(t('unifiedBacktest.createSuccess'));
      setModalOpen(false);
      resetForm();
      fetchWorkflowData();
    } catch {
      message.error(t('unifiedBacktest.createFailed'));
    }
  };

  const resetForm = () => {
    form.resetFields();
    setCurrentStep(0);
    setSelectedDatasetKeys([]);
    setSelectedAlgorithmKeys([]);
    setSelectedMetrics(['rmse', 'mae', 'r2']);
    setPrimaryMetric('rmse');
  };

  // Skill 测试操作
  const handleCreateSkillTask = async (values: any) => {
    const skill = skills.find(s => s.skill_id === values.skill_id);
    if (!skill) return;
    const newTask: SkillTestTask = {
      task_id: `test-${Date.now()}`,
      skill_id: values.skill_id,
      skill_name: skill.skill_name,
      test_type: values.test_type,
      status: 'pending',
      config: { epochs: values.epochs, batch_size: values.batch_size },
      created_at: new Date().toISOString(),
    };
    setSkillTasks([newTask, ...skillTasks]);
    setSkillModalOpen(false);
    skillForm.resetFields();
    message.success(t('unifiedBacktest.skillTestCreated'));
  };

  const handleRunSkillTask = (task: SkillTestTask) => {
    setSkillTasks(skillTasks.map(t => 
      t.task_id === task.task_id 
        ? { ...t, status: 'running' as SkillTaskStatus, started_at: new Date().toISOString() }
        : t
    ));
    message.info(t('unifiedBacktest.skillTestStarted', { name: task.skill_name }));
  };

  const handleDeleteSkillTask = (taskId: string) => {
    setSkillTasks(skillTasks.filter(t => t.task_id !== taskId));
    message.success(t('unifiedBacktest.skillTestDeleted'));
  };

  // Skill 统计
  const skillStats = useMemo(() => {
    const total = skillTasks.length;
    const pending = skillTasks.filter(t => t.status === 'pending').length;
    const running = skillTasks.filter(t => t.status === 'running').length;
    const completed = skillTasks.filter(t => t.status === 'completed').length;
    return { total, pending, running, completed };
  }, [skillTasks]);

  // 过滤 Skill 任务
  const filteredSkillTasks = useMemo(() => {
    return skillTasks.filter(t => {
      if (skillKeyword && !t.skill_name.toLowerCase().includes(skillKeyword.toLowerCase())) return false;
      if (skillStatusFilter !== 'all' && t.status !== skillStatusFilter) return false;
      return true;
    });
  }, [skillTasks, skillKeyword, skillStatusFilter]);

  // 工作流回测列定义
  // @AI_GENERATED
  const workflowColumns: ColumnsType<BacktestTask> = [
    {
      title: td('任务名称'), dataIndex: 'name', key: 'name', width: 200,
      render: (name: string) => <span style={{ fontWeight: 500 }}>{td(name)}</span>,
    },
    {
      title: td('场景'), dataIndex: 'scenario_id', key: 'scenario', width: 100,
      render: (sid: string) => {
        const s = SCENARIOS.find(x => x.value === sid);
        return <Tag color="blue">{s ? td(s.label) : sid}</Tag>;
      },
    },
    { title: td('数据集'), key: 'ds', width: 80, render: (_: unknown, r: BacktestTask) => r.datasets.length },
    { title: td('算法'), key: 'alg', width: 80, render: (_: unknown, r: BacktestTask) => r.algorithms.length },
    {
      title: td('矩阵'), key: 'matrix', width: 90,
      render: (_: unknown, r: BacktestTask) => <Tag color="purple">{r.datasets.length}×{r.algorithms.length}</Tag>,
    },
    {
      title: td('进度'), key: 'progress', width: 120,
      render: (_: unknown, r: BacktestTask) => (
        <span>{r.completed_runs}/{r.total_runs}{r.failed_runs > 0 && <span style={{ color: '#f5222d' }}> ({r.failed_runs}{td('失败')})</span>}</span>
      ),
    },
    {
      title: td('状态'), dataIndex: 'status', key: 'status', width: 90,
      render: (status: string) => {
        const cfg = TASK_STATUS_CONFIG[status as keyof typeof TASK_STATUS_CONFIG];
        return <Badge status={cfg?.color as any} text={cfg ? td(cfg.label) : status} />;
      },
    },
    {
      title: td('创建时间'), dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: td('操作'), key: 'actions', width: 220,
      render: (_: unknown, r: BacktestTask) => (
        <Space size="small">
          {r.status === 'pending' && (
            <>
              <Tooltip title={t('unifiedBacktest.confirmDelete')}>
                <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => handleExecute(r.id)} />
              </Tooltip>
              {/* @AI_GENERATED: Kiro v1.0 */}
              <Tooltip title={td('加入调度')}>
                <Button type="link" size="small" icon={<CalendarOutlined />} onClick={() => handleOpenScheduleModal(r.id)} />
              </Tooltip>
              {/* @AI_GENERATED: end */}
            </>
          )}
          <Tooltip title={td('查看结果')}>
            <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => navigate('/backtest/unified/results')} />
          </Tooltip>
          <Tooltip title={td('克隆')}>
            <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => handleClone(r.id)} />
          </Tooltip>
          <Popconfirm title={td('确定删除？')} onConfirm={() => handleDelete(r.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];
  // @AI_GENERATED: end

  // @AI_GENERATED
  // Skill 测试列定义
  const skillColumns: ColumnsType<SkillTestTask> = [
    {
      title: td('任务 ID'), dataIndex: 'task_id', key: 'task_id', width: 120,
      render: (id) => <Text code>{id}</Text>,
    },
    {
      title: 'Skill', dataIndex: 'skill_name', key: 'skill_name', width: 220,
      render: (name, record) => (
        <Space>
          <ThunderboltOutlined style={{ color: '#722ed1' }} />
          <Text style={{ cursor: 'pointer', color: '#1890ff' }} onClick={() => navigate(`/skill-library/${record.skill_id}`)}>
            {td(name)}
          </Text>
        </Space>
      ),
    },
    {
      title: td('测试类型'), dataIndex: 'test_type', key: 'test_type', width: 100,
      render: (type) => {
        const typeMap: Record<string, { label: string; color: string }> = {
          training: { label: '训练测试', color: 'purple' },
          inference: { label: '推理测试', color: 'blue' },
          benchmark: { label: '基准测试', color: 'orange' },
        };
        const config = typeMap[type] || { label: type, color: 'default' };
        return <Tag color={config.color}>{td(config.label)}</Tag>;
      },
    },
    {
      title: td('状态'), dataIndex: 'status', key: 'status', width: 100,
      render: (status: SkillTaskStatus) => {
        const statusMap: Record<SkillTaskStatus, { label: string; color: string; icon: React.ReactNode }> = {
          pending: { label: '待执行', color: 'default', icon: <ClockCircleOutlined /> },
          running: { label: '执行中', color: 'processing', icon: <SyncOutlined spin /> },
          completed: { label: '已完成', color: 'success', icon: <CheckCircleOutlined /> },
          failed: { label: '失败', color: 'error', icon: <ClockCircleOutlined /> },
        };
        const config = statusMap[status];
        return <Tag color={config.color} icon={config.icon}>{td(config.label)}</Tag>;
      },
    },
    {
      title: td('配置'), key: 'config', width: 120,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          {record.config.epochs && <Text style={{ fontSize: 12 }}>Epochs: {record.config.epochs}</Text>}
          {record.config.batch_size && <Text style={{ fontSize: 12 }}>Batch: {record.config.batch_size}</Text>}
        </Space>
      ),
    },
    {
      title: td('测试指标'), key: 'metrics', width: 140,
      render: (_, record) => record.metrics ? (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>MAPE: {record.metrics.mape?.toFixed(2)}%</Text>
          <Text style={{ fontSize: 12 }}>RMSE: {record.metrics.rmse?.toFixed(2)}</Text>
        </Space>
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: td('创建时间'), dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (time) => new Date(time).toLocaleString(),
    },
    {
      title: td('操作'), key: 'actions', width: 150,
      render: (_, record) => (
        <Space size={4}>
          <Tooltip title={td('查看结果')}>
            <Button type="text" size="small" icon={<EyeOutlined />} onClick={() => navigate('/backtest/unified/results?type=skill')} />
          </Tooltip>
          {record.status === 'pending' && (
            <Tooltip title={td('执行')}>
              <Button type="text" size="small" icon={<PlayCircleOutlined />} onClick={() => handleRunSkillTask(record)} />
            </Tooltip>
          )}
          <Popconfirm title={td('确定删除？')} onConfirm={() => handleDeleteSkillTask(record.task_id)}>
            <Tooltip title={td('删除')}>
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];
  // @AI_GENERATED: end

  // @AI_GENERATED
  // 工作流创建步骤内容
  const stepItems = [
    { title: td('基本信息') },
    { title: td('选择数据集') },
    { title: td('选择算法') },
    { title: td('指标配置') },
    { title: td('确认预览') },
  ];
  // @AI_GENERATED: end

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <Form form={form} layout="vertical">
            <Form.Item name="name" label={t('unifiedBacktest.taskName')} rules={[{ required: true, message: t('unifiedBacktest.taskNameRequired') }]}>
              <Input placeholder={t('unifiedBacktest.taskNamePlaceholder')} />
            </Form.Item>
            <Form.Item name="description" label={t('unifiedBacktest.description')}>
              <TextArea rows={3} placeholder={t('unifiedBacktest.descPlaceholder')} />
            </Form.Item>
            <Form.Item name="scenario_id" label={t('unifiedBacktest.scenario')} rules={[{ required: true, message: t('unifiedBacktest.scenarioRequired') }]}>
              <Select options={SCENARIOS} placeholder={t('unifiedBacktest.selectScenario')} onChange={(v) => {
                const metrics = SCENARIO_METRICS[v] || ['rmse', 'mae', 'r2'];
                setSelectedMetrics(metrics);
                setPrimaryMetric(metrics[0]);
              }} />
            </Form.Item>
          </Form>
        );
      case 1:
        return (
          <Transfer
            dataSource={MOCK_DATASETS.map(d => ({ key: d.id, title: td(d.name) }))}
            titles={[td('可选数据集'), td('已选数据集')]}
            targetKeys={selectedDatasetKeys}
            onChange={setSelectedDatasetKeys}
            render={item => item.title || ''}
            listStyle={{ width: 280, height: 300 }}
            showSearch
            filterOption={(input, item) => (item.title || '').toLowerCase().includes(input.toLowerCase())}
          />
        );
      case 2:
        return (
          <Transfer
            dataSource={MOCK_ALGORITHMS.map(a => ({ key: a.id, title: `[${a.type === 'template' ? td('方案') : td('模板')}] ${td(a.name)}` }))}
            titles={[td('可选算法/模板'), td('已选算法/模板')]}
            targetKeys={selectedAlgorithmKeys}
            onChange={setSelectedAlgorithmKeys}
            render={item => item.title || ''}
            listStyle={{ width: 280, height: 300 }}
            showSearch
            filterOption={(input, item) => (item.title || '').toLowerCase().includes(input.toLowerCase())}
          />
        );
      case 3:
        return (
          <div>
            <div style={{ marginBottom: 16 }}>
              <span style={{ marginRight: 8 }}>{td('主要指标：')}</span>
              <Select value={primaryMetric} onChange={setPrimaryMetric} style={{ width: 150 }}
                options={METRIC_OPTIONS.filter(m => selectedMetrics.includes(m.value))} />
            </div>
            <div>
              <span style={{ marginRight: 8 }}>{td('评估指标：')}</span>
              <Checkbox.Group value={selectedMetrics} onChange={(v) => setSelectedMetrics(v as string[])}
                options={METRIC_OPTIONS} />
            </div>
          </div>
        );
      case 4: {
        const ds = MOCK_DATASETS.filter(d => selectedDatasetKeys.includes(d.id));
        const algs = MOCK_ALGORITHMS.filter(a => selectedAlgorithmKeys.includes(a.id));
        return (
          <div>
            <p><strong>{td('任务名称：')}</strong>{form.getFieldValue('name')}</p>
            <p><strong>{td('场景：')}</strong>{SCENARIOS.find(s => s.value === form.getFieldValue('scenario_id'))?.label}</p>
            <p><strong>{td('数据集')}（{ds.length}）：</strong>{ds.map(d => td(d.name)).join(', ')}</p>
            <p><strong>{td('算法')}/{td('模板')}（{algs.length}）：</strong>{algs.map(a => td(a.name)).join(', ')}</p>
            <p><strong>{td('回测矩阵：')}</strong><Tag color="purple">{ds.length} × {algs.length} = {ds.length * algs.length}{td('次运行')}</Tag></p>
          </div>
        );
      }
      default:
        return null;
    }
  };

  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <ExperimentOutlined style={{ fontSize: 24, color: '#1890ff' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>{t('unifiedBacktest.title')}</Typography.Title>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          {t('unifiedBacktest.subtitle')}
        </Paragraph>
      </div>

      {/* 类型切换 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Segmented
            value={testType}
            onChange={(v) => handleTypeChange(v as 'workflow' | 'skill')}
            options={[
              { value: 'workflow', label: <><ApartmentOutlined /> {t('unifiedBacktest.workflowBacktest')}</> },
              { value: 'skill', label: <><ThunderboltOutlined /> {t('unifiedBacktest.skillTest')}</> },
            ]}
          />
          {testType === 'workflow' ? (
            <>
              <Select allowClear placeholder={t('unifiedBacktest.scenarioFilter')} style={{ width: 130 }} options={SCENARIOS}
                value={filterScenario} onChange={setFilterScenario} />
              <Select allowClear placeholder={t('unifiedBacktest.statusFilter')} style={{ width: 110 }}
                options={Object.entries(TASK_STATUS_CONFIG).map(([k, v]) => ({ value: k, label: v.label }))}
                value={filterStatus} onChange={setFilterStatus} />
              <Button icon={<ReloadOutlined />} onClick={fetchWorkflowData}>{t('unifiedBacktest.refresh')}</Button>
              {/* @AI_GENERATED: Kiro v1.0 */}
              <Button icon={<ScheduleOutlined />} onClick={() => setSchedulePanelOpen(true)}>
                {t('unifiedBacktest.smartSchedule')}
              </Button>
              {/* @AI_GENERATED: end */}
              <Button type="primary" icon={<PlusOutlined />} onClick={() => { resetForm(); setModalOpen(true); }}>
                {t('unifiedBacktest.newBacktest')}
              </Button>
            </>
          ) : (
            <>
              <Input prefix={<SearchOutlined />} placeholder={t('unifiedBacktest.searchSkill')} allowClear style={{ width: 180 }}
                value={skillKeyword} onChange={e => setSkillKeyword(e.target.value)} />
              <Select allowClear placeholder={t('unifiedBacktest.statusFilter')} style={{ width: 110 }}
                value={skillStatusFilter === 'all' ? undefined : skillStatusFilter}
                onChange={v => setSkillStatusFilter(v || 'all')}
                options={[
                  { value: 'pending', label: '待执行' },
                  { value: 'running', label: '执行中' },
                  { value: 'completed', label: '已完成' },
                  { value: 'failed', label: '失败' },
                ]} />
              <Button icon={<ReloadOutlined />} onClick={loadSkills}>{t('unifiedBacktest.refresh')}</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setSkillModalOpen(true)}>
                {t('unifiedBacktest.createTest')}
              </Button>
            </>
          )}
        </Space>
      </Card>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {testType === 'workflow' ? (
          <>
            <Col span={6}>
              <Card size="small"><Statistic title={t('unifiedBacktest.totalTasks')} value={stats.total_tasks} prefix={<ExperimentOutlined />} /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title={t('unifiedBacktest.running')} value={stats.running_tasks} prefix={<RocketOutlined />} valueStyle={{ color: '#1890ff' }} /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title={t('unifiedBacktest.completed')} value={stats.completed_tasks} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title={t('unifiedBacktest.avgCompletion')} value={stats.avg_score * 100} suffix="%" prefix={<DatabaseOutlined />} precision={1} /></Card>
            </Col>
          </>
        ) : (
          <>
            <Col span={6}>
              <Card size="small"><Statistic title={t('unifiedBacktest.taskTotal')} value={skillStats.total} prefix={<ExperimentOutlined />} /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title={t('unifiedBacktest.pending')} value={skillStats.pending} prefix={<ClockCircleOutlined />} /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title={t('unifiedBacktest.executing')} value={skillStats.running} prefix={<SyncOutlined />} valueStyle={{ color: '#1890ff' }} /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title={t('unifiedBacktest.completed')} value={skillStats.completed} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
            </Col>
          </>
        )}
      </Row>

      {/* 任务列表 */}
      <Card title={testType === 'workflow' ? t('unifiedBacktest.workflowTasks') : t('unifiedBacktest.skillTasks')}>
        <Spin spinning={testType === 'workflow' ? loading : skillLoading}>
          {testType === 'workflow' ? (
            tasks.length > 0 ? (
              <Table<BacktestTask>
                columns={workflowColumns}
                dataSource={tasks}
                rowKey="id"
                pagination={{ pageSize: 10, showTotal: (total) => t('unifiedBacktest.totalCount', { count: total }) }}
                scroll={{ x: 1100 }}
                size="middle"
              />
            ) : <Empty description={t('unifiedBacktest.noBacktestTasks')} />
          ) : (
            filteredSkillTasks.length > 0 ? (
              <Table
                dataSource={filteredSkillTasks}
                columns={skillColumns}
                rowKey="task_id"
                size="small"
                pagination={{ pageSize: 10, showTotal: (total) => t('unifiedBacktest.totalTaskCount', { count: total }) }}
              />
            ) : <Empty description={t('unifiedBacktest.noTestTasks')} />
          )}
        </Spin>
      </Card>

      {/* 工作流回测创建弹窗 */}
      <Modal
        title={preselectedTemplateType === 'workflow' && preselectedTemplateId ? "新建工作流回测任务（已预选模板）" : "新建工作流回测任务"}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          // 清除预选状态
          if (preselectedTemplateType === 'workflow') {
            setPreselectedTemplateId(null);
            setPreselectedTemplateType(null);
          }
        }}
        width={700}
        footer={
          <Space>
            {currentStep > 0 && <Button onClick={() => setCurrentStep(s => s - 1)}>上一步</Button>}
            {currentStep < 4 && <Button type="primary" onClick={() => setCurrentStep(s => s + 1)}>下一步</Button>}
            {currentStep === 4 && <Button type="primary" onClick={handleCreate}>创建任务</Button>}
          </Space>
        }
        afterOpenChange={(open) => {
          // @AI_GENERATED: Kiro v1.0
          // 当弹窗打开且有预选的工作流模板时，预选算法
          if (open && preselectedTemplateType === 'workflow' && preselectedTemplateId) {
            // 预选该模板到算法列表
            if (!selectedAlgorithmKeys.includes(preselectedTemplateId)) {
              setSelectedAlgorithmKeys([preselectedTemplateId]);
            }
          }
          // @AI_GENERATED: end
        }}
      >
        {/* @AI_GENERATED: Kiro v1.0 */}
        {preselectedTemplateType === 'workflow' && preselectedTemplateId && (
          <div style={{ marginBottom: 16, padding: '8px 12px', background: '#e6f7ff', borderRadius: 4, border: '1px solid #91d5ff' }}>
            <Text type="secondary">📌 已从策划助手预选模板（ID: {preselectedTemplateId}），请继续配置回测参数</Text>
          </div>
        )}
        {/* @AI_GENERATED: end */}
        <Steps current={currentStep} items={stepItems} size="small" style={{ marginBottom: 24 }} />
        {renderStepContent()}
      </Modal>

      {/* Skill 测试创建弹窗 */}
      <Modal
        title={preselectedTemplateType === 'skill' && preselectedTemplateId ? "创建 Skill 测试任务（已预选模板）" : "创建 Skill 测试任务"}
        open={skillModalOpen}
        onCancel={() => {
          setSkillModalOpen(false);
          // 清除预选状态
          if (preselectedTemplateType === 'skill') {
            setPreselectedTemplateId(null);
            setPreselectedTemplateType(null);
          }
        }}
        onOk={() => skillForm.submit()}
        width={500}
        afterOpenChange={(open) => {
          // @AI_GENERATED: Kiro v1.0
          // 当弹窗打开且有预选的 Skill 时，自动设置表单值
          if (open && preselectedTemplateType === 'skill' && preselectedTemplateId) {
            skillForm.setFieldsValue({
              skill_id: preselectedTemplateId,
              test_type: 'training',
              epochs: 80,
              batch_size: 32,
            });
          }
          // @AI_GENERATED: end
        }}
      >
        <Form form={skillForm} layout="vertical" onFinish={handleCreateSkillTask}>
          {/* @AI_GENERATED: Kiro v1.0 */}
          {preselectedTemplateType === 'skill' && preselectedTemplateId && (
            <div style={{ marginBottom: 16, padding: '8px 12px', background: '#e6f7ff', borderRadius: 4, border: '1px solid #91d5ff' }}>
              <Text type="secondary">📌 已从策划助手预选模板，可直接配置测试参数</Text>
            </div>
          )}
          {/* @AI_GENERATED: end */}
          <Form.Item name="skill_id" label={t('unifiedBacktest.selectSkill')} rules={[{ required: true }]}>
            <Select placeholder={t('unifiedBacktest.selectSkill')}>
              {skills.map(s => (
                <Select.Option key={s.skill_id} value={s.skill_id}>{s.skill_name}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="test_type" label={t('unifiedBacktest.testType')} rules={[{ required: true }]}>
            <Select placeholder={t('unifiedBacktest.testType')}>
              <Select.Option value="training">{t('unifiedBacktest.trainingTest')}</Select.Option>
              <Select.Option value="inference">{t('unifiedBacktest.inferenceTest')}</Select.Option>
              <Select.Option value="benchmark">{t('unifiedBacktest.benchmarkTest')}</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="epochs" label={t('unifiedBacktest.epochs')} initialValue={80}>
            <InputNumber min={1} max={500} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="batch_size" label={t('unifiedBacktest.batchSize')} initialValue={32}>
            <InputNumber min={1} max={256} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* @AI_GENERATED: Kiro v1.0 */}
      {/* 添加到调度队列弹窗 */}
      <Modal
        title={t('unifiedBacktest.addToScheduleTitle')}
        open={scheduleModalOpen}
        onCancel={() => { setScheduleModalOpen(false); setSchedulingTaskId(null); }}
        onOk={handleAddToSchedule}
        width={550}
      >
        <Form form={scheduleForm} layout="vertical">
          <Form.Item name="priority" label={t('unifiedBacktest.priority')} rules={[{ required: true }]}>
            <Select>
              {Object.entries(PRIORITY_CONFIG).map(([key, config]) => (
                <Select.Option key={key} value={key}>
                  <Tag color={config.color}>{config.label}</Tag>
                  <span style={{ marginLeft: 8, color: '#8c8c8c', fontSize: 12 }}>权重: {config.weight}</span>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="deadline" label={t('unifiedBacktest.deadline')}>
            <DatePicker showTime style={{ width: '100%' }} placeholder={t('unifiedBacktest.deadlinePlaceholder')} />
          </Form.Item>
          <Form.Item name="estimated_duration_minutes" label={t('unifiedBacktest.estimatedDuration')} rules={[{ required: true }]}>
            <InputNumber min={1} max={1440} style={{ width: '100%' }} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="gpu_required" label="GPU 需求" rules={[{ required: true }]}>
                <InputNumber min={0} max={8} style={{ width: '100%' }} addonAfter="核" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="cpu_required" label="CPU 需求" rules={[{ required: true }]}>
                <InputNumber min={1} max={64} style={{ width: '100%' }} addonAfter="核" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="memory_required_gb" label={t('unifiedBacktest.memoryRequired')} rules={[{ required: true }]}>
                <InputNumber min={1} max={256} style={{ width: '100%' }} addonAfter="GB" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="allow_preemption" label={t('unifiedBacktest.allowPreemption')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 智能调度面板 */}
      <SchedulePanel
        visible={schedulePanelOpen}
        onClose={() => setSchedulePanelOpen(false)}
        onTaskStarted={fetchWorkflowData}
      />
      {/* @AI_GENERATED: end */}
    </div>
  );
};

export default UnifiedBacktestPage;
// @AI_GENERATED: end
