// @AI_GENERATED: Kiro v1.0
import { useState, useEffect } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Row, Col, Statistic, Table, Tag, Space, Input, Button, Tabs,
  Select, Typography, Progress, message, Spin, Modal, Form,
  InputNumber, Switch, Drawer, Badge, Timeline,
} from 'antd';
import {
  SyncOutlined, SendOutlined, PlusOutlined,
  CheckCircleOutlined, CloseCircleOutlined, PauseCircleOutlined,
  PlayCircleOutlined, RobotOutlined, ThunderboltOutlined, SettingOutlined,
  ClockCircleOutlined, ExperimentOutlined, RocketOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type {
  RetrainTask, RetrainStrategy, RetrainStats, QuickCommand,
} from '../types/algorithm-ops';
import { RETRAIN_STATUS_CONFIG } from '../types/algorithm-ops';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
const { Text, Paragraph } = Typography;
const { TextArea } = Input;

// Mock 数据
const MOCK_STATS: RetrainStats = {
  total_tasks: 29,
  queued_count: 8,
  training_count: 2,
  completed_count: 15,
  failed_count: 1,
  avg_improvement: 3.2,
};

const MOCK_TASKS: RetrainTask[] = [
  { task_id: 'rt-001', model_id: 'pv-power-001', model_name: '光伏功率预测-LSTM', scenario_id: 'renewable-energy', scenario_name: '新能源发电', retrain_type: 'incremental', trigger: 'drift_detected', status: 'training', created_at: '2026-03-21 09:00:00', started_at: '2026-03-21 09:05:00', progress: 65, old_accuracy: 92.5 },
  { task_id: 'rt-002', model_id: 'load-forecast-001', model_name: '负荷预测-Transformer', scenario_id: 'power-grid', scenario_name: '电网与微网', retrain_type: 'full', trigger: 'drift_detected', status: 'validating', created_at: '2026-03-21 08:00:00', started_at: '2026-03-21 08:10:00', progress: 90, old_accuracy: 88.2, new_accuracy: 93.5, improvement: 5.3 },
  { task_id: 'rt-003', model_id: 'wind-power-001', model_name: '风电功率预测-XGBoost', scenario_id: 'renewable-energy', scenario_name: '新能源发电', retrain_type: 'incremental', trigger: 'scheduled', status: 'queued', created_at: '2026-03-21 10:00:00', progress: 0, old_accuracy: 91.8 },
  { task_id: 'rt-004', model_id: 'soc-est-001', model_name: '储能SOC估计-EKF', scenario_id: 'energy-storage', scenario_name: '储能管理', retrain_type: 'incremental', trigger: 'manual', status: 'queued', created_at: '2026-03-21 10:30:00', progress: 0, old_accuracy: 95.2 },
  { task_id: 'rt-005', model_id: 'defect-detect-001', model_name: '晶圆缺陷检测-YOLO', scenario_id: 'semiconductor', scenario_name: '半导体制造', retrain_type: 'full', trigger: 'ab_test_result', status: 'completed', created_at: '2026-03-20 14:00:00', started_at: '2026-03-20 14:10:00', completed_at: '2026-03-20 16:30:00', progress: 100, old_accuracy: 89.5, new_accuracy: 94.2, improvement: 4.7 },
  { task_id: 'rt-006', model_id: 'quality-pred-001', model_name: '质量预测-RF', scenario_id: 'steel-manufacturing', scenario_name: '钢铁制造', retrain_type: 'incremental', trigger: 'drift_detected', status: 'failed', created_at: '2026-03-19 10:00:00', started_at: '2026-03-19 10:05:00', progress: 45, old_accuracy: 87.3 },
];

const MOCK_STRATEGIES: RetrainStrategy[] = [
  { strategy_id: 'str-001', model_id: 'pv-power-001', model_name: '光伏功率预测-LSTM', enabled: true, drift_threshold: 0.2, accuracy_drop_threshold: 5, min_retrain_interval_hours: 24, prefer_incremental: true, auto_deploy: false, require_ab_test: true },
  { strategy_id: 'str-002', model_id: 'load-forecast-001', model_name: '负荷预测-Transformer', enabled: true, drift_threshold: 0.15, accuracy_drop_threshold: 3, min_retrain_interval_hours: 12, prefer_incremental: false, auto_deploy: true, require_ab_test: false },
  { strategy_id: 'str-003', model_id: 'wind-power-001', model_name: '风电功率预测-XGBoost', enabled: true, drift_threshold: 0.2, accuracy_drop_threshold: 5, min_retrain_interval_hours: 48, prefer_incremental: true, auto_deploy: false, require_ab_test: true },
];

const QUICK_COMMANDS: QuickCommand[] = [
  { labelKey: 'autoRetrain.quickEvaluateAll', prompt: '评估当前所有已部署模型是否需要重训，按紧急程度排序' },
  { labelKey: 'autoRetrain.quickAutoRetrain', prompt: '对所有检测到漂移的模型自动执行重训' },
  { labelKey: 'autoRetrain.quickRetrainPlan', prompt: '为本周需要重训的模型生成详细的重训计划' },
  { labelKey: 'autoRetrain.quickAnalyzeEffect', prompt: '分析最近完成的重训任务的效果，总结成功和失败原因' },
];
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
const AutoRetrainPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [stats] = useState<RetrainStats>(MOCK_STATS);
  const [tasks] = useState<RetrainTask[]>(MOCK_TASKS);
  const [strategies] = useState<RetrainStrategy[]>(MOCK_STRATEGIES);
  const [loading, setLoading] = useState(false);
  const [promptText, setPromptText] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [selectedTask, setSelectedTask] = useState<RetrainTask | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [form] = Form.useForm();

  useEffect(() => {
    setLoading(true);
    setTimeout(() => setLoading(false), 500);
  }, []);

  const handlePromptSubmit = async () => {
    if (!promptText.trim()) {
      message.warning(t('autoRetrain.enterPrompt'));
      return;
    }
    setPromptLoading(true);
    setTimeout(() => {
      message.success(t('autoRetrain.aiAnalysisDone'));
      setPromptLoading(false);
      setPromptText('');
    }, 2000);
  };

  const handleCreateTask = () => {
    form.validateFields().then(() => {
      message.success(t('autoRetrain.taskCreated'));
      setCreateModalVisible(false);
      form.resetFields();
    });
  };

  const handleViewDetail = (task: RetrainTask) => {
    setSelectedTask(task);
    setDetailDrawerVisible(true);
  };

  const handleCancelTask = () => {
    Modal.confirm({
      title: t('autoRetrain.confirmCancelTask'),
      content: t('autoRetrain.confirmCancelContent'),
      onOk: () => message.success(t('autoRetrain.taskCancelled')),
    });
  };

  const filteredTasks = statusFilter === 'all'
    ? tasks
    : tasks.filter(t => t.status === statusFilter);

  const taskColumns = [
    {
      title: t('autoRetrain.modelName'),
      dataIndex: 'model_name',
      key: 'model_name',
      render: (text: string, record: RetrainTask) => (
        <Space>
          <Text strong>{td(text)}</Text>
          {record.status === 'training' && <Badge status="processing" />}
        </Space>
      ),
    },
    { title: t('autoRetrain.scenario'), dataIndex: 'scenario_name', key: 'scenario_name', render: (text: string) => <Tag>{td(text)}</Tag> },
    {
      title: t('autoRetrain.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: keyof typeof RETRAIN_STATUS_CONFIG) => (
        <Tag color={RETRAIN_STATUS_CONFIG[status].color}>{td(RETRAIN_STATUS_CONFIG[status].text)}</Tag>
      ),
    },
    {
      title: t('autoRetrain.type'),
      dataIndex: 'retrain_type',
      key: 'retrain_type',
      render: (type: string) => <Tag color={type === 'full' ? 'orange' : 'blue'}>{type === 'full' ? t('autoRetrain.fullTrain') : t('autoRetrain.incrementalTrain')}</Tag>,
    },
    {
      title: t('autoRetrain.triggerReason'),
      dataIndex: 'trigger',
      key: 'trigger',
      render: (trigger: string) => {
        const map: Record<string, string> = { drift_detected: t('autoRetrain.triggerDrift'), scheduled: t('autoRetrain.triggerScheduled'), manual: t('autoRetrain.triggerManual'), ab_test_result: t('autoRetrain.triggerABTest') };
        return <Text type="secondary">{map[trigger] || trigger}</Text>;
      },
    },
    {
      title: t('autoRetrain.progress'),
      dataIndex: 'progress',
      key: 'progress',
      render: (progress: number, record: RetrainTask) => (
        <Progress
          percent={progress}
          size="small"
          status={record.status === 'failed' ? 'exception' : record.status === 'completed' ? 'success' : 'active'}
          style={{ width: 100 }}
        />
      ),
    },
    {
      title: t('autoRetrain.accuracyImprovement'),
      key: 'improvement',
      render: (_: unknown, record: RetrainTask) => (
        record.improvement ? (
          <Text type="success">+{record.improvement.toFixed(1)}%</Text>
        ) : (
          <Text type="secondary">-</Text>
        )
      ),
    },
    {
      title: t('autoRetrain.action'),
      key: 'action',
      render: (_: unknown, record: RetrainTask) => (
        <Space>
          <Button size="small" onClick={() => handleViewDetail(record)}>{t('autoRetrain.detail')}</Button>
          {(record.status === 'queued' || record.status === 'training') && (
            <Button size="small" danger onClick={() => handleCancelTask()}>{t('autoRetrain.cancel')}</Button>
          )}
          {record.status === 'validating' && (
            <Button size="small" type="primary">{t('autoRetrain.deploy')}</Button>
          )}
        </Space>
      ),
    },
  ];
// @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 训练 Loss 曲线
  const lossChartOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['训练 Loss', '验证 Loss'] },
    xAxis: { type: 'category', data: Array.from({ length: 50 }, (_, i) => `${i + 1}`) },
    yAxis: { type: 'value', name: 'Loss' },
    series: [
      { name: '训练 Loss', type: 'line', data: Array.from({ length: 50 }, (_, i) => 0.5 * Math.exp(-i / 15) + 0.02 + Math.random() * 0.01), smooth: true },
      { name: '验证 Loss', type: 'line', data: Array.from({ length: 50 }, (_, i) => 0.55 * Math.exp(-i / 18) + 0.025 + Math.random() * 0.015), smooth: true },
    ],
  };

  // 精度对比图
  const accuracyCompareOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['旧模型', '新模型'] },
    xAxis: { type: 'category', data: ['RMSE', 'MAE', 'MAPE (%)', 'R²'] },
    yAxis: { type: 'value' },
    series: [
      { name: '旧模型', type: 'bar', data: [3.8, 2.8, 9.0, 0.85], itemStyle: { color: '#ff7875' } },
      { name: '新模型', type: 'bar', data: [2.5, 1.8, 5.5, 0.93], itemStyle: { color: '#52c41a' } },
    ],
  };

  // 资源使用图
  const resourceOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['GPU 使用率', 'CPU 使用率', '内存使用率'] },
    xAxis: { type: 'category', data: ['09:05', '09:10', '09:15', '09:20', '09:25', '09:30'] },
    yAxis: { type: 'value', name: '%', max: 100 },
    series: [
      { name: 'GPU 使用率', type: 'line', data: [85, 92, 88, 95, 90, 87], areaStyle: { opacity: 0.3 } },
      { name: 'CPU 使用率', type: 'line', data: [45, 52, 48, 55, 50, 47] },
      { name: '内存使用率', type: 'line', data: [62, 65, 68, 70, 72, 71] },
    ],
  };

  const strategyColumns = [
    { title: t('autoRetrain.modelName'), dataIndex: 'model_name', key: 'model_name' },
    {
      title: t('autoRetrain.enabled'),
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => <Switch checked={enabled} size="small" />,
    },
    { title: t('autoRetrain.driftThreshold'), dataIndex: 'drift_threshold', key: 'drift_threshold', render: (v: number) => `PSI > ${v}` },
    { title: t('autoRetrain.accuracyDropThreshold'), dataIndex: 'accuracy_drop_threshold', key: 'accuracy_drop_threshold', render: (v: number) => `> ${v}%` },
    { title: t('autoRetrain.minInterval'), dataIndex: 'min_retrain_interval_hours', key: 'min_retrain_interval_hours', render: (v: number) => `${v}h` },
    { title: t('autoRetrain.preferIncremental'), dataIndex: 'prefer_incremental', key: 'prefer_incremental', render: (v: boolean) => v ? <Tag color="blue">{t('autoRetrain.yes')}</Tag> : <Tag>{t('autoRetrain.no')}</Tag> },
    { title: t('autoRetrain.autoDeploy'), dataIndex: 'auto_deploy', key: 'auto_deploy', render: (v: boolean) => v ? <Tag color="green">{t('autoRetrain.yes')}</Tag> : <Tag>{t('autoRetrain.no')}</Tag> },
    { title: t('autoRetrain.requireABTest'), dataIndex: 'require_ab_test', key: 'require_ab_test', render: (v: boolean) => v ? <Tag color="orange">{t('autoRetrain.yes')}</Tag> : <Tag>{t('autoRetrain.no')}</Tag> },
    {
      title: t('autoRetrain.action'),
      key: 'action',
      render: () => <Button size="small" icon={<SettingOutlined />}>{t('autoRetrain.configure')}</Button>,
    },
  ];

  const tabItems = [
    {
      key: 'queue',
      label: t('autoRetrain.retrainQueue'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Table dataSource={filteredTasks} columns={taskColumns} rowKey="task_id" size="small" pagination={{ pageSize: 5 }} />
          </Col>
          <Col span={24}>
            <Card title={t('autoRetrain.aiRetrainAdvice')} size="small" extra={<RobotOutlined style={{ color: '#1890ff' }} />}>
              <Paragraph>
                <Text strong>{t('autoRetrain.currentAdvice')}</Text>
              </Paragraph>
              <Paragraph type="secondary">
                1. 光伏功率预测模型正在增量训练中，预计30分钟后完成，建议等待验证结果。<br />
                2. 负荷预测模型已完成训练，精度提升5.3%，建议创建A/B测试验证后部署。<br />
                3. 风电功率预测模型排队中，可考虑提高优先级以尽快处理漂移问题。
              </Paragraph>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'monitor',
      label: t('autoRetrain.trainingMonitor'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={12}>
            <Card title={t('autoRetrain.trainingLoss')} size="small">
              <ReactECharts option={lossChartOption} style={{ height: 250 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title={t('autoRetrain.resourceUsage')} size="small">
              <ReactECharts option={resourceOption} style={{ height: 250 }} />
            </Card>
          </Col>
          <Col span={24}>
            <Card title={t('autoRetrain.trainingLog')} size="small" style={{ maxHeight: 200, overflow: 'auto' }}>
              <Timeline
                items={[
                  { color: 'green', children: '[09:05:00] 开始训练任务 rt-001' },
                  { color: 'blue', children: '[09:05:02] 加载训练数据: 15,000 样本' },
                  { color: 'blue', children: '[09:05:10] 数据预处理完成' },
                  { color: 'blue', children: '[09:10:00] Epoch 10/50, Loss: 0.125, Val Loss: 0.138' },
                  { color: 'blue', children: '[09:20:00] Epoch 30/50, Loss: 0.052, Val Loss: 0.068' },
                  { color: 'gray', children: '[09:30:00] 训练进行中... Epoch 45/50' },
                ]}
              />
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'validation',
      label: t('autoRetrain.effectValidation'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={12}>
            <Card title={t('autoRetrain.oldNewCompare')} size="small">
              <ReactECharts option={accuracyCompareOption} style={{ height: 280 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title={t('autoRetrain.validationResult')} size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={16}>
                  <Col span={12}><Statistic title={t('autoRetrain.oldAccuracy')} value={88.2} suffix="%" /></Col>
                  <Col span={12}><Statistic title={t('autoRetrain.newAccuracy')} value={93.5} suffix="%" valueStyle={{ color: '#52c41a' }} /></Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}><Statistic title={t('autoRetrain.accuracyUp')} value={5.3} suffix="%" valueStyle={{ color: '#52c41a' }} prefix="+" /></Col>
                  <Col span={12}><Statistic title={t('autoRetrain.statisticalSignificance')} value={98.5} suffix="%" /></Col>
                </Row>
                <Space style={{ marginTop: 16 }}>
                  <Button type="primary" icon={<RocketOutlined />}>{t('autoRetrain.directDeploy')}</Button>
                  <Button icon={<ExperimentOutlined />}>{t('autoRetrain.createABTest')}</Button>
                  <Button danger icon={<CloseCircleOutlined />}>{t('autoRetrain.discard')}</Button>
                </Space>
              </Space>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'strategy',
      label: t('autoRetrain.strategyConfig'),
      children: (
        <Table dataSource={strategies} columns={strategyColumns} rowKey="strategy_id" size="small" />
      ),
    },
  ];
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  return (
    <div style={{ padding: 16, height: '100%', overflow: 'auto' }}>
      {/* AI 分析入口 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <RobotOutlined style={{ fontSize: 18, color: '#1890ff' }} />
            <Text strong>{t('autoRetrain.aiAnalysisEntry')}</Text>
            <Text type="secondary">{t('autoRetrain.aiAnalysisDesc')}</Text>
          </Space>
          <Space.Compact style={{ width: '100%' }}>
            <TextArea
              placeholder={t('autoRetrain.placeholder')}
              value={promptText}
              onChange={e => setPromptText(e.target.value)}
              autoSize={{ minRows: 1, maxRows: 3 }}
              style={{ flex: 1 }}
            />
            <Button type="primary" icon={<SendOutlined />} loading={promptLoading} onClick={handlePromptSubmit}>
              发送
            </Button>
          </Space.Compact>
          <Space wrap>
            {QUICK_COMMANDS.map(cmd => (
              <Button key={cmd.labelKey || cmd.label} size="small" onClick={() => setPromptText(cmd.prompt)}>
                {cmd.label}
              </Button>
            ))}
          </Space>
        </Space>
      </Card>

      {/* 重训概览 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('autoRetrain.totalTasks')} value={stats.total_tasks} prefix={<SyncOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('autoRetrain.queued')} value={stats.queued_count} prefix={<ClockCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('autoRetrain.training')} value={stats.training_count} valueStyle={{ color: '#1890ff' }} prefix={<PlayCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('autoRetrain.completed')} value={stats.completed_count} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('autoRetrain.avgImprovement')} value={stats.avg_improvement} suffix="%" valueStyle={{ color: '#52c41a' }} prefix={<ThunderboltOutlined />} /></Card>
        </Col>
      </Row>

      {/* 任务列表和详情 */}
      <Card
        title={t('autoRetrain.management')}
        size="small"
        extra={
          <Space>
            <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} size="small"
              options={[
                { value: 'all', label: t('autoRetrain.allStatus') },
                { value: 'queued', label: t('autoRetrain.statusQueued') },
                { value: 'training', label: t('autoRetrain.statusTraining') },
                { value: 'validating', label: t('autoRetrain.statusValidating') },
                { value: 'completed', label: t('autoRetrain.statusCompleted') },
                { value: 'failed', label: t('autoRetrain.statusFailed') },
              ]}
            />
            <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
              创建任务
            </Button>
          </Space>
        }
      >
        <Spin spinning={loading}>
          <Tabs items={tabItems} />
        </Spin>
      </Card>

      {/* 创建任务 Modal */}
      <Modal title={t('autoRetrain.createRetrainTask')} open={createModalVisible} onOk={handleCreateTask} onCancel={() => setCreateModalVisible(false)} width={500}>
        <Form form={form} layout="vertical">
          <Form.Item name="model_id" label={t('autoRetrain.selectModel')} rules={[{ required: true }]}>
            <Select placeholder={t('autoRetrain.selectModelPlaceholder')} options={[
              { value: 'pv-power-001', label: '光伏功率预测-LSTM' },
              { value: 'wind-power-001', label: '风电功率预测-XGBoost' },
              { value: 'load-forecast-001', label: '负荷预测-Transformer' },
            ]} />
          </Form.Item>
          <Form.Item name="retrain_type" label={t('autoRetrain.trainType')} initialValue="incremental">
            <Select options={[
              { value: 'incremental', label: t('autoRetrain.incrementalRecommended') },
              { value: 'full', label: t('autoRetrain.fullTrain') },
            ]} />
          </Form.Item>
          <Form.Item name="data_range" label={t('autoRetrain.dataRange')} initialValue={30}>
            <InputNumber min={7} max={365} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="auto_deploy" label={t('autoRetrain.autoDeployAfter')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 任务详情 Drawer */}
      <Drawer title={selectedTask?.model_name || t('autoRetrain.taskDetail')} open={detailDrawerVisible} onClose={() => setDetailDrawerVisible(false)} width={600}>
        {selectedTask && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Card size="small" title={t('autoRetrain.basicInfo')}>
              <Row gutter={[16, 8]}>
                <Col span={12}><Text type="secondary">{t('autoRetrain.taskId')}</Text>{selectedTask.task_id}</Col>
                <Col span={12}><Text type="secondary">{t('autoRetrain.scenarioLabel')}</Text>{td(selectedTask.scenario_name)}</Col>
                <Col span={12}><Text type="secondary">{t('autoRetrain.trainTypeLabel')}</Text><Tag color={selectedTask.retrain_type === 'full' ? 'orange' : 'blue'}>{selectedTask.retrain_type === 'full' ? t('autoRetrain.fullTrain') : t('autoRetrain.incrementalTrain')}</Tag></Col>
                <Col span={12}><Text type="secondary">{t('autoRetrain.statusLabel')}</Text><Tag color={RETRAIN_STATUS_CONFIG[selectedTask.status].color}>{td(RETRAIN_STATUS_CONFIG[selectedTask.status].text)}</Tag></Col>
                <Col span={12}><Text type="secondary">{t('autoRetrain.oldAccuracyLabel')}</Text>{selectedTask.old_accuracy}%</Col>
                <Col span={12}><Text type="secondary">{t('autoRetrain.newAccuracyLabel')}</Text>{selectedTask.new_accuracy ? `${selectedTask.new_accuracy}%` : '-'}</Col>
                <Col span={24}><Text type="secondary">{t('autoRetrain.progressLabel')}</Text><Progress percent={selectedTask.progress} status={selectedTask.status === 'failed' ? 'exception' : 'active'} /></Col>
              </Row>
            </Card>
            <Card size="small" title={t('autoRetrain.trainingCurve')}>
              <ReactECharts option={lossChartOption} style={{ height: 200 }} />
            </Card>
            <Card size="small" title={t('autoRetrain.quickActions')}>
              <Space wrap>
                {selectedTask.status === 'training' && <Button icon={<PauseCircleOutlined />}>{t('autoRetrain.pause')}</Button>}
                {selectedTask.status === 'validating' && <Button type="primary" icon={<RocketOutlined />}>{t('autoRetrain.deploy')}</Button>}
                {selectedTask.status === 'completed' && <Button icon={<ExperimentOutlined />}>{t('autoRetrain.createABTest')}</Button>}
                <Button>{t('autoRetrain.viewLog')}</Button>
              </Space>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default AutoRetrainPage;
// @AI_GENERATED: end
