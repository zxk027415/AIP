// @AI_GENERATED: Kiro v1.0
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card, Row, Col, Statistic, Table, Tag, Space, Input, Button, Tabs,
  Select, Typography, Tooltip, Progress, message, Spin, Modal, Form,
  InputNumber, Drawer, Badge,
} from 'antd';
import {
  ExperimentOutlined, SendOutlined, PlusOutlined,
  CheckCircleOutlined, CloseCircleOutlined, PauseCircleOutlined,
  PlayCircleOutlined, RobotOutlined, TrophyOutlined, LineChartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type {
  ABTestConfig, ABTestStats, QuickCommand,
} from '../types/algorithm-ops';
import { ABTEST_STATUS_CONFIG } from '../types/algorithm-ops';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
const { Text, Paragraph } = Typography;
const { TextArea } = Input;

// Mock 数据
const MOCK_STATS: ABTestStats = {
  total_tests: 22,
  running_count: 5,
  completed_count: 12,
  a_wins_count: 4,
  b_wins_count: 8,
};

const MOCK_TESTS: ABTestConfig[] = [
  { test_id: 'ab-001', test_name: '光伏预测 v2.1 vs v2.0', model_a_id: 'pv-v2.0', model_a_name: '光伏预测-LSTM v2.0', model_b_id: 'pv-v2.1', model_b_name: '光伏预测-LSTM v2.1', traffic_split: 30, start_time: '2026-03-18 10:00:00', status: 'running', result: 'pending', scenario_id: 'renewable-energy', scenario_name: '新能源发电' },
  { test_id: 'ab-002', test_name: '风电预测 v3.0 vs v2.5', model_a_id: 'wind-v2.5', model_a_name: '风电预测-XGBoost v2.5', model_b_id: 'wind-v3.0', model_b_name: '风电预测-XGBoost v3.0', traffic_split: 50, start_time: '2026-03-15 08:00:00', status: 'running', result: 'pending', scenario_id: 'renewable-energy', scenario_name: '新能源发电' },
  { test_id: 'ab-003', test_name: '负荷预测 Transformer vs LSTM', model_a_id: 'load-lstm', model_a_name: '负荷预测-LSTM', model_b_id: 'load-trans', model_b_name: '负荷预测-Transformer', traffic_split: 20, start_time: '2026-03-10 00:00:00', end_time: '2026-03-17 00:00:00', status: 'completed', result: 'b_wins', scenario_id: 'power-grid', scenario_name: '电网与微网' },
  { test_id: 'ab-004', test_name: '储能SOC v1.2 vs v1.1', model_a_id: 'soc-v1.1', model_a_name: '储能SOC-EKF v1.1', model_b_id: 'soc-v1.2', model_b_name: '储能SOC-EKF v1.2', traffic_split: 40, start_time: '2026-03-12 00:00:00', end_time: '2026-03-19 00:00:00', status: 'completed', result: 'a_wins', scenario_id: 'energy-storage', scenario_name: '储能管理' },
  { test_id: 'ab-005', test_name: '晶圆缺陷检测 YOLOv8 vs YOLOv5', model_a_id: 'defect-v5', model_a_name: '晶圆缺陷检测-YOLOv5', model_b_id: 'defect-v8', model_b_name: '晶圆缺陷检测-YOLOv8', traffic_split: 25, start_time: '2026-03-19 14:00:00', status: 'running', result: 'pending', scenario_id: 'semiconductor', scenario_name: '半导体制造' },
];



const QUICK_COMMANDS = [
  { labelKey: 'abTest.quickAnalyzeAll', prompt: '分析当前所有进行中的 A/B 测试，给出各测试的状态和建议' },
  { labelKey: 'abTest.quickFindEndable', prompt: '查找已达到统计显著性可以提前结束的 A/B 测试' },
  { labelKey: 'abTest.quickWeeklyReport', prompt: '生成本周 A/B 测试周报，包含完成的测试和关键发现' },
  { labelKey: 'abTest.quickRecommendConfig', prompt: '基于历史数据，推荐新 A/B 测试的最优配置' },
];
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
const ABTestPage: React.FC = () => {
  const { t } = useTranslation();
  const [stats] = useState<ABTestStats>(MOCK_STATS);
  const [tests] = useState<ABTestConfig[]>(MOCK_TESTS);
  const [loading, setLoading] = useState(false);
  const [promptText, setPromptText] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [selectedTest, setSelectedTest] = useState<ABTestConfig | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [form] = Form.useForm();

  useEffect(() => {
    setLoading(true);
    setTimeout(() => setLoading(false), 500);
  }, []);

  const handlePromptSubmit = async () => {
    if (!promptText.trim()) {
      message.warning(t('abTest.enterPrompt'));
      return;
    }
    setPromptLoading(true);
    setTimeout(() => {
      message.success(t('abTest.aiAnalysisDone'));
      setPromptLoading(false);
      setPromptText('');
    }, 2000);
  };

  const handleCreateTest = () => {
    form.validateFields().then(() => {
      message.success(t('abTest.testCreated'));
      setCreateModalVisible(false);
      form.resetFields();
    });
  };

  const handleViewDetail = (test: ABTestConfig) => {
    setSelectedTest(test);
    setDetailDrawerVisible(true);
  };

  const handlePauseTest = () => {
    message.loading(t('abTest.pausingTest'), 1);
    setTimeout(() => message.success(t('abTest.testPaused')), 1000);
  };

  const handleStopTest = () => {
    Modal.confirm({
      title: t('abTest.confirmEndTest'),
      content: t('abTest.confirmEndTestContent'),
      onOk: () => message.success(t('abTest.testEnded')),
    });
  };



  const columns = [
    {
      title: t('abTest.testName'),
      dataIndex: 'test_name',
      key: 'test_name',
      render: (text: string, record: ABTestConfig) => (
        <Space>
          <Text strong>{td(text)}</Text>
          {record.status === 'running' && <Badge status="processing" />}
        </Space>
      ),
    },
    { title: t('abTest.scenario'), dataIndex: 'scenario_name', key: 'scenario_name', render: (text: string) => <Tag>{td(text)}</Tag> },
    {
      title: t('abTest.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: keyof typeof ABTEST_STATUS_CONFIG) => (
        <Tag color={ABTEST_STATUS_CONFIG[status].color}>{td(ABTEST_STATUS_CONFIG[status].text)}</Tag>
      ),
    },
    {
      title: t('abTest.trafficSplit'),
      dataIndex: 'traffic_split',
      key: 'traffic_split',
      render: (split: number) => (
        <Tooltip title={`A: ${split}% / B: ${100 - split}%`}>
          <Progress percent={split} size="small" style={{ width: 80 }} format={p => `${p}%`} />
        </Tooltip>
      ),
    },
    {
      title: t('abTest.result'),
      dataIndex: 'result',
      key: 'result',
      render: (result: string) => {
        if (result === 'pending') return <Tag>{t('abTest.pending')}</Tag>;
        if (result === 'a_wins') return <Tag color="blue" icon={<TrophyOutlined />}>{t('abTest.aWinsResult')}</Tag>;
        if (result === 'b_wins') return <Tag color="green" icon={<TrophyOutlined />}>{t('abTest.bWinsResult')}</Tag>;
        return <Tag>{t('abTest.noDifference')}</Tag>;
      },
    },
    { title: t('abTest.startTime'), dataIndex: 'start_time', key: 'start_time', render: (t: string) => <Text type="secondary">{t.split(' ')[0]}</Text> },
    {
      title: t('abTest.action'),
      key: 'action',
      render: (_: unknown, record: ABTestConfig) => (
        <Space>
          <Button size="small" onClick={() => handleViewDetail(record)}>{t('abTest.detail')}</Button>
          {record.status === 'running' && (
            <>
              <Button size="small" icon={<PauseCircleOutlined />} onClick={() => handlePauseTest()} />
              <Button size="small" danger onClick={() => handleStopTest()}>{t('abTest.end')}</Button>
            </>
          )}
        </Space>
      ),
    },
  ];
// @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 指标对比图配置
  const metricsCompareOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['模型 A (v2.0)', '模型 B (v2.1)'] },
    xAxis: { type: 'category', data: ['精度 (%)', '延迟 P50 (ms)', '延迟 P99 (ms)', '错误率 (%)', '吞吐量 (qps)'] },
    yAxis: { type: 'value' },
    series: [
      { name: '模型 A (v2.0)', type: 'bar', data: [92.5, 45, 120, 0.5, 1200], itemStyle: { color: '#1890ff' } },
      { name: '模型 B (v2.1)', type: 'bar', data: [94.8, 42, 105, 0.3, 1350], itemStyle: { color: '#52c41a' } },
    ],
  };

  // 实时指标趋势图
  const realtimeTrendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['模型 A 精度', '模型 B 精度'] },
    xAxis: { type: 'category', data: ['3/18', '3/19', '3/20', '3/21'] },
    yAxis: { type: 'value', name: '精度 (%)', min: 88, max: 98 },
    series: [
      { name: '模型 A 精度', type: 'line', data: [92.1, 92.3, 92.5, 92.5], smooth: true },
      { name: '模型 B 精度', type: 'line', data: [94.2, 94.5, 94.7, 94.8], smooth: true },
    ],
  };

  // 样本量累积图
  const sampleSizeOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['模型 A 样本', '模型 B 样本'] },
    xAxis: { type: 'category', data: ['3/18', '3/19', '3/20', '3/21'] },
    yAxis: { type: 'value', name: '样本量' },
    series: [
      { name: '模型 A 样本', type: 'line', areaStyle: {}, data: [2000, 4500, 6800, 8500] },
      { name: '模型 B 样本', type: 'line', areaStyle: {}, data: [850, 1900, 2800, 3600] },
    ],
  };

  const tabItems = [
    {
      key: 'running',
      label: t('abTest.runningTests'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Table dataSource={tests.filter(t => t.status === 'running')} columns={columns} rowKey="test_id" size="small" pagination={false} />
          </Col>
          <Col span={12}>
            <Card title={t('abTest.realtimeTrend')} size="small">
              <ReactECharts option={realtimeTrendOption} style={{ height: 250 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title={t('abTest.sampleAccumulation')} size="small">
              <ReactECharts option={sampleSizeOption} style={{ height: 250 }} />
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'results',
      label: t('abTest.testResults'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Card title={t('abTest.metricsCompare')} size="small">
              <ReactECharts option={metricsCompareOption} style={{ height: 280 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title={t('abTest.statisticalSignificance')} size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={16}>
                  <Col span={12}><Statistic title={t('abTest.confidenceLevel')} value={95} suffix="%" valueStyle={{ color: '#52c41a' }} /></Col>
                  <Col span={12}><Statistic title="p-value" value={0.023} precision={3} valueStyle={{ color: '#52c41a' }} /></Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}><Statistic title={t('abTest.effectSize')} value={0.85} precision={2} /></Col>
                  <Col span={12}><Statistic title={t('abTest.statisticalPower')} value={92} suffix="%" /></Col>
                </Row>
              </Space>
            </Card>
          </Col>
          <Col span={12}>
            <Card title={t('abTest.aiDecisionAdvice')} size="small" extra={<RobotOutlined style={{ color: '#1890ff' }} />}>
              <Paragraph>
                <Text strong>{t('abTest.adviceAdoptB')}</Text>
              </Paragraph>
              <Paragraph type="secondary">
                模型 B 在精度上提升 2.3%，延迟降低 12.5%，错误率降低 40%。
                统计显著性达到 95% 置信水平 (p=0.023)，效应量为 0.85（大效应）。
                建议全量切换到模型 B。
              </Paragraph>
              <Space>
                <Button type="primary" icon={<CheckCircleOutlined />}>{t('abTest.adoptBModel')}</Button>
                <Button>{t('abTest.extendTest')}</Button>
              </Space>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'history',
      label: t('abTest.historyRecords'),
      children: (
        <Table
          dataSource={tests.filter(t => t.status === 'completed')}
          columns={columns}
          rowKey="test_id"
          size="small"
        />
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
            <Text strong>{t('abTest.aiAnalysisEntry')}</Text>
            <Text type="secondary">{t('abTest.aiAnalysisDesc')}</Text>
          </Space>
          <Space.Compact style={{ width: '100%' }}>
            <TextArea
              placeholder={t('abTest.placeholder')}
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
              <Button key={cmd.labelKey} size="small" onClick={() => setPromptText(cmd.prompt)}>
                {t(cmd.labelKey)}
              </Button>
            ))}
          </Space>
        </Space>
      </Card>

      {/* 测试概览 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('abTest.totalTests')} value={stats.total_tests} prefix={<ExperimentOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('abTest.running')} value={stats.running_count} valueStyle={{ color: '#1890ff' }} prefix={<PlayCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('abTest.completed')} value={stats.completed_count} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('abTest.aWins')} value={stats.a_wins_count} prefix={<TrophyOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title={t('abTest.bWins')} value={stats.b_wins_count} valueStyle={{ color: '#52c41a' }} prefix={<TrophyOutlined />} /></Card>
        </Col>
      </Row>

      {/* 测试列表和详情 */}
      <Card
        title={t('abTest.management')}
        size="small"
        extra={
          <Space>
            <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} size="small"
              options={[
                { value: 'all', label: t('abTest.allStatus') },
                { value: 'running', label: t('abTest.statusRunning') },
                { value: 'completed', label: t('abTest.statusCompleted') },
                { value: 'paused', label: t('abTest.statusPaused') },
              ]}
            />
            <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
              创建测试
            </Button>
          </Space>
        }
      >
        <Spin spinning={loading}>
          <Tabs items={tabItems} />
        </Spin>
      </Card>

      {/* 创建测试 Modal */}
      <Modal title={t('abTest.createABTest')} open={createModalVisible} onOk={handleCreateTest} onCancel={() => setCreateModalVisible(false)} width={600}>
        <Form form={form} layout="vertical">
          <Form.Item name="test_name" label={t('abTest.testNameLabel')} rules={[{ required: true }]}>
            <Input placeholder={t('abTest.testNamePlaceholder')} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="model_a" label={t('abTest.controlModel')} rules={[{ required: true }]}>
                <Select placeholder={t('abTest.selectModel')} options={[
                  { value: 'pv-v2.0', label: '光伏预测-LSTM v2.0' },
                  { value: 'wind-v2.5', label: '风电预测-XGBoost v2.5' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="model_b" label={t('abTest.experimentModel')} rules={[{ required: true }]}>
                <Select placeholder={t('abTest.selectModel')} options={[
                  { value: 'pv-v2.1', label: '光伏预测-LSTM v2.1' },
                  { value: 'wind-v3.0', label: '风电预测-XGBoost v3.0' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="traffic_split" label={t('abTest.trafficSplitLabel')} initialValue={30}>
            <InputNumber min={5} max={95} addonAfter="%" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="duration" label={t('abTest.testDuration')}>
            <InputNumber min={1} max={30} addonAfter={t('abTest.days')} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 测试详情 Drawer */}
      <Drawer title={selectedTest?.test_name || t('abTest.testDetail')} open={detailDrawerVisible} onClose={() => setDetailDrawerVisible(false)} width={600}>
        {selectedTest && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Card size="small" title={t('abTest.basicInfo')}>
              <Row gutter={[16, 8]}>
                <Col span={12}><Text type="secondary">{t('abTest.testId')}</Text>{selectedTest.test_id}</Col>
                <Col span={12}><Text type="secondary">{t('abTest.scenarioLabel')}</Text>{selectedTest.scenario_name}</Col>
                <Col span={12}><Text type="secondary">{t('abTest.modelA')}</Text>{selectedTest.model_a_name}</Col>
                <Col span={12}><Text type="secondary">{t('abTest.modelB')}</Text>{selectedTest.model_b_name}</Col>
                <Col span={12}><Text type="secondary">{t('abTest.trafficLabel')}</Text>A {selectedTest.traffic_split}% / B {100 - selectedTest.traffic_split}%</Col>
                <Col span={12}><Text type="secondary">{t('abTest.statusLabel')}</Text><Tag color={ABTEST_STATUS_CONFIG[selectedTest.status].color}>{ABTEST_STATUS_CONFIG[selectedTest.status].text}</Tag></Col>
              </Row>
            </Card>
            <Card size="small" title={t('abTest.metricsCompare')}>
              <ReactECharts option={metricsCompareOption} style={{ height: 200 }} />
            </Card>
            <Card size="small" title={t('abTest.quickActions')}>
              <Space wrap>
                <Button icon={<LineChartOutlined />}>{t('abTest.viewDetailReport')}</Button>
                {selectedTest.status === 'running' && (
                  <>
                    <Button icon={<PauseCircleOutlined />}>{t('abTest.pauseTest')}</Button>
                    <Button danger icon={<CloseCircleOutlined />}>{t('abTest.endTest')}</Button>
                  </>
                )}
                {selectedTest.status === 'completed' && selectedTest.result === 'b_wins' && (
                  <Button type="primary" icon={<CheckCircleOutlined />}>{t('abTest.adoptBModel')}</Button>
                )}
              </Space>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default ABTestPage;
// @AI_GENERATED: end
