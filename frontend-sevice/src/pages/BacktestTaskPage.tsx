// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useCallback } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Table, Button, Space, Tag, Badge, Modal, Steps, Form, Input,
  Select, Transfer, Checkbox, message, Popconfirm, Row, Col, Statistic, Tooltip,
} from 'antd';
import {
  PlusOutlined, PlayCircleOutlined, DeleteOutlined, CopyOutlined,
  ExperimentOutlined, DatabaseOutlined, RocketOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { backtestApi } from '../services/backtestApi';
import type { BacktestTask, BacktestStats, BacktestDatasetRef, BacktestAlgorithmRef } from '../types/backtest';
import { TASK_STATUS_CONFIG, METRIC_OPTIONS, SCENARIO_METRICS } from '../types/backtest';
import { td } from '../utils/dataTranslation';

const { TextArea } = Input;

const SCENARIOS = [
  { value: 'renewable-energy', label: '新能源' },
  { value: 'industrial-manufacturing', label: '工业制造' },
  { value: 'grid-load-storage', label: '源网荷储' },
  { value: 'carbon-management', label: '碳管理' },
  { value: 'building-park', label: '楼宇园区' },
  { value: 'port-transport', label: '港口运输' },
  { value: 'general-industry', label: '通用工业' },
];

// Mock datasets for transfer picker
const MOCK_DATASETS: BacktestDatasetRef[] = [
  { id: 'ds-001', name: '光伏电站A-2025年数据' },
  { id: 'ds-002', name: '光伏电站B-2025年数据' },
  { id: 'ds-003', name: '光伏电站C-2024年数据' },
  { id: 'ds-004', name: '光伏电站D-2025年数据' },
  { id: 'ds-005', name: '光伏电站E-2024年数据' },
  { id: 'ds-101', name: '华东电网-2025Q1' },
  { id: 'ds-102', name: '华南电网-2025Q1' },
  { id: 'ds-103', name: '华北电网-2024Q4' },
  { id: 'ds-201', name: '电机振动数据集' },
  { id: 'ds-202', name: '轴承温度数据集' },
  { id: 'ds-301', name: '工业园区A碳排放' },
  { id: 'ds-302', name: '工业园区B碳排放' },
  { id: 'ds-303', name: '商业园区C碳排放' },
];

const MOCK_ALGORITHMS: BacktestAlgorithmRef[] = [
  { type: 'template', id: 'pv_power_forecast', name: '光伏发电功率预测' },
  { type: 'template', id: 'lstm_forecast', name: 'LSTM时序预测' },
  { type: 'template', id: 'load_forecast_lstm', name: 'LSTM负荷预测' },
  { type: 'template', id: 'load_forecast_xgb', name: 'XGBoost负荷预测' },
  { type: 'template', id: 'load_forecast_transformer', name: 'Transformer负荷预测' },
  { type: 'template', id: 'fault_svm', name: 'SVM故障分类' },
  { type: 'template', id: 'fault_rf', name: '随机森林故障诊断' },
  { type: 'template', id: 'carbon_predict_lr', name: '线性回归碳预测' },
  { type: 'template', id: 'carbon_predict_nn', name: '神经网络碳预测' },
  { type: 'workflow', id: 'wf-001', name: '集成预测模板' },
  { type: 'workflow', id: 'wf-load-ensemble', name: '集成负荷预测模板' },
  { type: 'workflow', id: 'wf-carbon', name: '碳排放综合预测模板' },
];

const BacktestTaskPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [stats, setStats] = useState<BacktestStats>({ total_tasks: 0, running_tasks: 0, completed_tasks: 0, avg_score: 0 });
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [filterScenario, setFilterScenario] = useState<string | undefined>();
  const [filterStatus, setFilterStatus] = useState<string | undefined>();

  // Create form state
  const [form] = Form.useForm();
  const [selectedDatasetKeys, setSelectedDatasetKeys] = useState<string[]>([]);
  const [selectedAlgorithmKeys, setSelectedAlgorithmKeys] = useState<string[]>([]);
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(['rmse', 'mae', 'r2']);
  const [primaryMetric, setPrimaryMetric] = useState('rmse');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [taskRes, statsRes] = await Promise.all([
        backtestApi.listTasks({ scenario: filterScenario, status: filterStatus }),
        backtestApi.getStats(),
      ]);
      setTasks(taskRes.items);
      setStats(statsRes);
    } catch {
      message.error(t('backtestTask.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [filterScenario, filterStatus]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleExecute = async (id: string) => {
    try {
      await backtestApi.executeTask(id);
      message.success(t('backtestTask.executeSuccess'));
      fetchData();
    } catch {
      message.error(t('backtestTask.executeFailed'));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await backtestApi.deleteTask(id);
      message.success(t('backtestTask.deleted'));
      fetchData();
    } catch {
      message.error(t('backtestTask.deleteFailed'));
    }
  };

  const handleClone = async (id: string) => {
    try {
      await backtestApi.cloneTask(id);
      message.success(t('backtestTask.cloned'));
      fetchData();
    } catch {
      message.error(t('backtestTask.cloneFailed'));
    }
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      const datasets = MOCK_DATASETS.filter(d => selectedDatasetKeys.includes(d.id));
      const algorithms = MOCK_ALGORITHMS.filter(a => selectedAlgorithmKeys.includes(a.id));
      if (datasets.length === 0 || algorithms.length === 0) {
        message.warning(t('backtestTask.selectDatasetAndAlgo'));
        return;
      }
      await backtestApi.createTask({
        name: values.name,
        description: values.description || '',
        scenario_id: values.scenario_id,
        datasets,
        algorithms,
        metrics_config: {
          primary_metric: primaryMetric,
          metrics: selectedMetrics,
          thresholds: {},
        },
      });
      message.success(t('backtestTask.createSuccess'));
      setModalOpen(false);
      resetForm();
      fetchData();
    } catch {
      message.error(t('backtestTask.createFailed'));
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

  const columns: ColumnsType<BacktestTask> = [
    {
      title: t('backtestTask.taskName'), dataIndex: 'name', key: 'name', width: 200,
      render: (name: string) => <span style={{ fontWeight: 500 }}>{td(name)}</span>,
    },
    {
      title: t('backtestTask.scenario'), dataIndex: 'scenario_id', key: 'scenario', width: 100,
      render: (sid: string) => {
        const s = SCENARIOS.find(x => x.value === sid);
        return <Tag color="blue">{td(s?.label || sid)}</Tag>;
      },
    },
    { title: t('backtestTask.datasets'), key: 'ds', width: 80, render: (_: unknown, r: BacktestTask) => r.datasets.length },
    { title: t('backtestTask.algorithms'), key: 'alg', width: 80, render: (_: unknown, r: BacktestTask) => r.algorithms.length },
    {
      title: t('backtestTask.matrix'), key: 'matrix', width: 90,
      render: (_: unknown, r: BacktestTask) => (
        <Tag color="purple">{r.datasets.length}×{r.algorithms.length}</Tag>
      ),
    },
    {
      title: t('backtestTask.progress'), key: 'progress', width: 120,
      render: (_: unknown, r: BacktestTask) => (
        <span>{r.completed_runs}/{r.total_runs}{r.failed_runs > 0 && <span style={{ color: '#f5222d' }}> ({r.failed_runs}失败)</span>}</span>
      ),
    },
    {
      title: t('backtestTask.status'), dataIndex: 'status', key: 'status', width: 90,
      render: (status: string) => {
        const cfg = TASK_STATUS_CONFIG[status as keyof typeof TASK_STATUS_CONFIG];
        return <Badge status={cfg?.color as any} text={cfg?.label || status} />;
      },
    },
    {
      title: t('backtestTask.createdAt'), dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: t('backtestTask.actions'), key: 'actions', width: 200, fixed: 'right',
      render: (_: unknown, r: BacktestTask) => (
        <Space size="small">
          {r.status === 'pending' && (
            <Tooltip title={t('backtestTask.startExecution')}>
              <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => handleExecute(r.id)} />
            </Tooltip>
          )}
          <Tooltip title={t('backtestTask.clone')}>
            <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => handleClone(r.id)} />
          </Tooltip>
          <Popconfirm title={t('backtestTask.confirmDelete')} onConfirm={() => handleDelete(r.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const stepItems = [
    { title: t('backtestTask.stepBasicInfo') },
    { title: t('backtestTask.stepSelectDataset') },
    { title: t('backtestTask.stepSelectAlgo') },
    { title: t('backtestTask.stepMetrics') },
    { title: t('backtestTask.stepPreview') },
  ];

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <Form form={form} layout="vertical">
            <Form.Item name="name" label={t('backtestTask.taskNameLabel')} rules={[{ required: true, message: t('backtestTask.taskNameRequired') }]}>
              <Input placeholder={t('backtestTask.taskNamePlaceholder')} />
            </Form.Item>
            <Form.Item name="description" label={t('backtestTask.description')}>
              <TextArea rows={3} placeholder={t('backtestTask.descPlaceholder')} />
            </Form.Item>
            <Form.Item name="scenario_id" label={t('backtestTask.scenarioLabel')} rules={[{ required: true, message: t('backtestTask.scenarioRequired') }]}>
              <Select options={SCENARIOS} placeholder={t('backtestTask.selectScenario')} onChange={(v) => {
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
            dataSource={MOCK_DATASETS.map(d => ({ key: d.id, title: d.name }))}
            titles={[t('backtestTask.availableDatasets'), t('backtestTask.selectedDatasets')]}
            targetKeys={selectedDatasetKeys}
            onChange={setSelectedDatasetKeys}
            render={item => item.title || ''}
            listStyle={{ width: 280, height: 350 }}
            showSearch
            filterOption={(input, item) => (item.title || '').toLowerCase().includes(input.toLowerCase())}
          />
        );
      case 2:
        return (
          <Transfer
            dataSource={MOCK_ALGORITHMS.map(a => ({ key: a.id, title: `[${a.type === 'template' ? '方案' : '模板'}] ${a.name}` }))}
            titles={[t('backtestTask.availableAlgos'), t('backtestTask.selectedAlgos')]}
            targetKeys={selectedAlgorithmKeys}
            onChange={setSelectedAlgorithmKeys}
            render={item => item.title || ''}
            listStyle={{ width: 280, height: 350 }}
            showSearch
            filterOption={(input, item) => (item.title || '').toLowerCase().includes(input.toLowerCase())}
          />
        );
      case 3:
        return (
          <div>
            <div style={{ marginBottom: 16 }}>
              <span style={{ marginRight: 8 }}>{t('backtestTask.primaryMetric')}</span>
              <Select value={primaryMetric} onChange={setPrimaryMetric} style={{ width: 150 }}
                options={METRIC_OPTIONS.filter(m => selectedMetrics.includes(m.value))} />
            </div>
            <div>
              <span style={{ marginRight: 8 }}>{t('backtestTask.evalMetrics')}</span>
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
            <p><strong>{t('backtestTask.taskNameLabel')}</strong>{form.getFieldValue('name')}</p>
            <p><strong>{t('backtestTask.scenarioLabel')}</strong>{SCENARIOS.find(s => s.value === form.getFieldValue('scenario_id'))?.label}</p>
            <p><strong>数据集（{ds.length}个）：</strong>{ds.map(d => d.name).join('、')}</p>
            <p><strong>算法/模板（{algs.length}个）：</strong>{algs.map(a => a.name).join('、')}</p>
            <p><strong>回测矩阵：</strong><Tag color="purple">{ds.length} × {algs.length} = {ds.length * algs.length} 次运行</Tag></p>
            <p><strong>主要指标：</strong>{METRIC_OPTIONS.find(m => m.value === primaryMetric)?.label}</p>
            <p><strong>评估指标：</strong>{selectedMetrics.map(m => METRIC_OPTIONS.find(o => o.value === m)?.label).join('、')}</p>
          </div>
        );
      }
      default:
        return null;
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title={t('backtestTask.totalTasks')} value={stats.total_tasks} prefix={<ExperimentOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title={t('backtestTask.running')} value={stats.running_tasks} prefix={<RocketOutlined />} valueStyle={{ color: '#1890ff' }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title={t('backtestTask.completed')} value={stats.completed_tasks} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title={t('backtestTask.avgCompletion')} value={stats.avg_score * 100} suffix="%" prefix={<DatabaseOutlined />} precision={1} /></Card>
        </Col>
      </Row>

      <Card
        title={t('backtestTask.taskList')}
        extra={
          <Space>
            <Select allowClear placeholder={t('backtestTask.scenarioFilter')} style={{ width: 130 }} options={SCENARIOS}
              value={filterScenario} onChange={setFilterScenario} />
            <Select allowClear placeholder={t('backtestTask.statusFilter')} style={{ width: 110 }}
              options={Object.entries(TASK_STATUS_CONFIG).map(([k, v]) => ({ value: k, label: v.label }))}
              value={filterStatus} onChange={setFilterStatus} />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { resetForm(); setModalOpen(true); }}>
              新建回测
            </Button>
          </Space>
        }
      >
        <Table<BacktestTask>
          columns={columns}
          dataSource={tasks}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, showTotal: (total) => t('backtestTask.totalCount', { count: total }) }}
          scroll={{ x: 1100 }}
          size="middle"
        />
      </Card>

      <Modal
        title={t('backtestTask.newBacktestTask')}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        width={700}
        footer={
          <Space>
            {currentStep > 0 && <Button onClick={() => setCurrentStep(s => s - 1)}>{t('backtestTask.prevStep')}</Button>}
            {currentStep < 4 && <Button type="primary" onClick={() => setCurrentStep(s => s + 1)}>{t('backtestTask.nextStep')}</Button>}
            {currentStep === 4 && <Button type="primary" onClick={handleCreate}>{t('backtestTask.createTask')}</Button>}
          </Space>
        }
      >
        <Steps current={currentStep} items={stepItems} size="small" style={{ marginBottom: 24 }} />
        {renderStepContent()}
      </Modal>
    </div>
  );
};

export default BacktestTaskPage;
// @AI_GENERATED: end
