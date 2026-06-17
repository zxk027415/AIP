// @AI_GENERATED: Kiro v1.0
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card, Row, Col, Statistic, Table, Tag, Space, Input, Button, Tabs,
  Select, Typography, Tooltip, Progress, message, Spin, Badge, Drawer,
} from 'antd';
import {
  LineChartOutlined, SendOutlined, ThunderboltOutlined, ReloadOutlined,
  WarningOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  RobotOutlined, DownOutlined, QuestionCircleOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { ModelDriftInfo, DriftMonitorStats, FeatureDriftDetail, QuickCommand } from '../types/algorithm-ops';
import { DRIFT_STATUS_CONFIG } from '../types/algorithm-ops';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
const { Text, Paragraph } = Typography;
const { TextArea } = Input;

// Mock 数据
const MOCK_STATS: DriftMonitorStats = {
  total_models: 45,
  normal_count: 32,
  mild_drift_count: 8,
  severe_drift_count: 5,
  retrain_triggered: 3,
};

const MOCK_MODELS: ModelDriftInfo[] = [
  { model_id: 'pv-power-001', model_name: '光伏功率预测-LSTM', scenario_id: 'renewable-energy', scenario_name: '新能源发电', status: 'severe', drift_type: 'both', psi_score: 0.35, accuracy_change: -12.5, last_check_time: '2026-03-21 10:30:00', alert_triggered: true },
  { model_id: 'wind-power-001', model_name: '风电功率预测-XGBoost', scenario_id: 'renewable-energy', scenario_name: '新能源发电', status: 'mild', drift_type: 'data', psi_score: 0.18, accuracy_change: -5.2, last_check_time: '2026-03-21 10:25:00', alert_triggered: false },
  { model_id: 'soc-est-001', model_name: '储能SOC估计-EKF', scenario_id: 'energy-storage', scenario_name: '储能管理', status: 'normal', drift_type: 'data', psi_score: 0.08, accuracy_change: -1.2, last_check_time: '2026-03-21 10:20:00', alert_triggered: false },
  { model_id: 'load-forecast-001', model_name: '负荷预测-Transformer', scenario_id: 'power-grid', scenario_name: '电网与微网', status: 'severe', drift_type: 'concept', psi_score: 0.28, accuracy_change: -15.8, last_check_time: '2026-03-21 10:15:00', alert_triggered: true },
  { model_id: 'defect-detect-001', model_name: '晶圆缺陷检测-YOLO', scenario_id: 'semiconductor', scenario_name: '半导体制造', status: 'mild', drift_type: 'data', psi_score: 0.15, accuracy_change: -3.8, last_check_time: '2026-03-21 10:10:00', alert_triggered: false },
  { model_id: 'quality-pred-001', model_name: '质量预测-RF', scenario_id: 'steel-manufacturing', scenario_name: '钢铁制造', status: 'normal', drift_type: 'data', psi_score: 0.05, accuracy_change: 0.5, last_check_time: '2026-03-21 10:05:00', alert_triggered: false },
];

const MOCK_FEATURE_DRIFT: FeatureDriftDetail[] = [
  { feature_name: '辐照度', psi_value: 0.42, ks_statistic: 0.18, js_divergence: 0.15, drift_status: 'severe', train_mean: 650, train_std: 180, prod_mean: 520, prod_std: 210 },
  { feature_name: '温度', psi_value: 0.25, ks_statistic: 0.12, js_divergence: 0.09, drift_status: 'mild', train_mean: 25.5, train_std: 8.2, prod_mean: 18.3, prod_std: 10.5 },
  { feature_name: '湿度', psi_value: 0.08, ks_statistic: 0.05, js_divergence: 0.03, drift_status: 'normal', train_mean: 65, train_std: 15, prod_mean: 62, prod_std: 18 },
  { feature_name: '风速', psi_value: 0.12, ks_statistic: 0.08, js_divergence: 0.05, drift_status: 'normal', train_mean: 3.2, train_std: 1.5, prod_mean: 3.8, prod_std: 1.8 },
  { feature_name: '云量', psi_value: 0.32, ks_statistic: 0.15, js_divergence: 0.12, drift_status: 'severe', train_mean: 0.3, train_std: 0.2, prod_mean: 0.55, prod_std: 0.25 },
];

const QUICK_COMMANDS: QuickCommand[] = [
  { labelKey: 'driftMonitor.quickDiagnoseAll', prompt: '诊断当前所有已部署模型的漂移状态，按严重程度排序' },
  { labelKey: 'driftMonitor.quickAnalyzeWeek', prompt: '分析本周精度下降超过5%的模型，给出根因分析' },
  { labelKey: 'driftMonitor.quickWeeklyReport', prompt: '生成本周的模型漂移监控周报，包含趋势分析和建议' },
  { labelKey: 'driftMonitor.quickPredictRisk', prompt: '基于历史数据预测下周可能出现漂移的模型' },
];
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
const DriftMonitorPage: React.FC = () => {
  const { t } = useTranslation();
  const [stats, setStats] = useState<DriftMonitorStats>(MOCK_STATS);
  const [models, setModels] = useState<ModelDriftInfo[]>(MOCK_MODELS);
  const [loading, setLoading] = useState(false);
  const [promptText, setPromptText] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<ModelDriftInfo | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // 模拟加载数据
  useEffect(() => {
    setLoading(true);
    setTimeout(() => setLoading(false), 500);
  }, []);

  // 执行 Prompt
  const handlePromptSubmit = async () => {
    if (!promptText.trim()) {
      message.warning(t('driftMonitor.enterPrompt'));
      return;
    }
    setPromptLoading(true);
    // 模拟 AI 分析
    setTimeout(() => {
      message.success(t('driftMonitor.aiAnalysisDone'));
      setPromptLoading(false);
      setPromptText('');
    }, 2000);
  };

  // 触发漂移检测
  const handleTriggerDetection = (modelId: string) => {
    message.loading(t('driftMonitor.detecting'), 1.5);
    setTimeout(() => message.success(t('driftMonitor.detectDone')), 1500);
  };

  // 查看模型详情
  const handleViewDetail = (model: ModelDriftInfo) => {
    setSelectedModel(model);
    setDetailDrawerVisible(true);
  };

  // 过滤模型
  const filteredModels = statusFilter === 'all' 
    ? models 
    : models.filter(m => m.status === statusFilter);

  // 模型列表列定义
  const columns = [
    {
      title: t('driftMonitor.modelName'),
      dataIndex: 'model_name',
      key: 'model_name',
      render: (text: string, record: ModelDriftInfo) => (
        <Space>
          <Text strong>{td(text)}</Text>
          {record.alert_triggered && <Badge status="error" />}
        </Space>
      ),
    },
    {
      title: t('driftMonitor.scenario'),
      dataIndex: 'scenario_name',
      key: 'scenario_name',
      render: (text: string) => <Tag>{td(text)}</Tag>,
    },
    {
      title: t('driftMonitor.driftStatus'),
      dataIndex: 'status',
      key: 'status',
      render: (status: keyof typeof DRIFT_STATUS_CONFIG) => (
        <Tag color={DRIFT_STATUS_CONFIG[status].color}>
          {td(DRIFT_STATUS_CONFIG[status].text)}
        </Tag>
      ),
    },
    {
      title: t('driftMonitor.driftType'),
      dataIndex: 'drift_type',
      key: 'drift_type',
      render: (type: string) => (
        <Tag color={type === 'both' ? 'red' : type === 'concept' ? 'orange' : 'blue'}>
          {type === 'both' ? t('driftMonitor.driftBoth') : type === 'concept' ? t('driftMonitor.driftConcept') : t('driftMonitor.driftData')}
        </Tag>
      ),
    },
    {
      title: 'PSI',
      dataIndex: 'psi_score',
      key: 'psi_score',
      render: (psi: number) => (
        <Tooltip title={t('driftMonitor.psiTooltip')}>
          <Text type={psi > 0.2 ? 'danger' : psi > 0.1 ? 'warning' : undefined}>
            {psi.toFixed(2)}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: t('driftMonitor.accuracyChange'),
      dataIndex: 'accuracy_change',
      key: 'accuracy_change',
      render: (change: number) => (
        <Text type={change < -5 ? 'danger' : change < 0 ? 'warning' : 'success'}>
          {change > 0 ? '+' : ''}{change.toFixed(1)}%
        </Text>
      ),
    },
    {
      title: t('driftMonitor.lastCheck'),
      dataIndex: 'last_check_time',
      key: 'last_check_time',
      render: (time: string) => <Text type="secondary">{time.split(' ')[1]}</Text>,
    },
    {
      title: t('driftMonitor.action'),
      key: 'action',
      render: (_: any, record: ModelDriftInfo) => (
        <Space>
          <Button size="small" onClick={() => handleViewDetail(record)}>{t('driftMonitor.detail')}</Button>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => handleTriggerDetection(record.model_id)}>{t('driftMonitor.detect')}</Button>
        </Space>
      ),
    },
  ];
// @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 特征漂移热力图配置
  const featureHeatmapOption = {
    tooltip: { trigger: 'item' },
    xAxis: { type: 'category', data: MOCK_FEATURE_DRIFT.map(f => f.feature_name) },
    yAxis: { type: 'category', data: ['PSI', 'KS', 'JS'] },
    visualMap: { min: 0, max: 0.5, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#52c41a', '#faad14', '#f5222d'] } },
    series: [{
      type: 'heatmap',
      data: MOCK_FEATURE_DRIFT.flatMap((f, i) => [
        [i, 0, f.psi_value],
        [i, 1, f.ks_statistic],
        [i, 2, f.js_divergence],
      ]),
      label: { show: true, formatter: (p: any) => p.value[2].toFixed(2) },
    }],
  };

  // 精度趋势图配置
  const accuracyTrendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['RMSE', 'MAE', 'MAPE'] },
    xAxis: { type: 'category', data: ['3/15', '3/16', '3/17', '3/18', '3/19', '3/20', '3/21'] },
    yAxis: { type: 'value', name: '误差' },
    series: [
      { name: 'RMSE', type: 'line', data: [2.1, 2.3, 2.5, 2.8, 3.2, 3.5, 3.8], smooth: true },
      { name: 'MAE', type: 'line', data: [1.5, 1.6, 1.8, 2.0, 2.3, 2.5, 2.8], smooth: true },
      { name: 'MAPE', type: 'line', data: [5.2, 5.5, 6.0, 6.8, 7.5, 8.2, 9.0], smooth: true },
    ],
  };

  // 贡献因子瀑布图配置
  const contributionOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', name: '贡献度 (%)' },
    yAxis: { type: 'category', data: ['辐照度漂移', '云量漂移', '季节变化', '数据延迟', '其他'] },
    series: [{
      type: 'bar',
      data: [35, 28, 18, 12, 7],
      itemStyle: { color: (p: any) => ['#f5222d', '#fa541c', '#faad14', '#1890ff', '#d9d9d9'][p.dataIndex] },
      label: { show: true, position: 'right', formatter: '{c}%' },
    }],
  };
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // Tab 内容
  const tabItems = [
    {
      key: 'data-drift',
      label: t('driftMonitor.driftData'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Card title={t('driftMonitor.featureHeatmap')} size="small">
              <ReactECharts option={featureHeatmapOption} style={{ height: 250 }} />
            </Card>
          </Col>
          <Col span={24}>
            <Card title={t('driftMonitor.featureDetail')} size="small">
              <Table
                dataSource={MOCK_FEATURE_DRIFT}
                rowKey="feature_name"
                size="small"
                pagination={false}
                columns={[
                  { title: t('driftMonitor.feature'), dataIndex: 'feature_name', key: 'feature_name' },
                  { title: 'PSI', dataIndex: 'psi_value', key: 'psi_value', render: (v: number) => <Text type={v > 0.2 ? 'danger' : undefined}>{v.toFixed(2)}</Text> },
                  { title: t('driftMonitor.ksStatistic'), dataIndex: 'ks_statistic', key: 'ks_statistic', render: (v: number) => v.toFixed(2) },
                  { title: t('driftMonitor.driftStatus'), dataIndex: 'drift_status', key: 'drift_status', render: (s: keyof typeof DRIFT_STATUS_CONFIG) => <Tag color={DRIFT_STATUS_CONFIG[s].color}>{DRIFT_STATUS_CONFIG[s].text}</Tag> },
                  { title: t('driftMonitor.trainMean'), dataIndex: 'train_mean', key: 'train_mean', render: (v: number) => v.toFixed(1) },
                  { title: t('driftMonitor.prodMean'), dataIndex: 'prod_mean', key: 'prod_mean', render: (v: number) => v.toFixed(1) },
                ]}
              />
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'concept-drift',
      label: t('driftMonitor.driftConcept'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Card title={t('driftMonitor.accuracyMetricsTrend')} size="small">
              <ReactECharts option={accuracyTrendOption} style={{ height: 300 }} />
            </Card>
          </Col>
          <Col span={24}>
            <Card title={t('driftMonitor.aiInterpretation')} size="small" extra={<RobotOutlined style={{ color: '#1890ff' }} />}>
              <Paragraph>
                <Text strong>{t('driftMonitor.conceptDriftAnalysis')}</Text>
              </Paragraph>
              <Paragraph>
                模型在过去7天内出现明显的概念漂移，RMSE从2.1上升至3.8（+81%），MAPE从5.2%上升至9.0%（+73%）。
                主要原因是春季气象模式变化导致辐照度-功率关系发生改变。建议触发增量重训练以适应新的数据分布。
              </Paragraph>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'accuracy-trend',
      label: t('driftMonitor.accuracyTrend'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Card title={t('driftMonitor.multiModelCompare')} size="small">
              <ReactECharts
                option={{
                  tooltip: { trigger: 'axis' },
                  legend: { data: ['光伏预测-LSTM', '风电预测-XGBoost', '负荷预测-Transformer'] },
                  xAxis: { type: 'category', data: ['3/15', '3/16', '3/17', '3/18', '3/19', '3/20', '3/21'] },
                  yAxis: { type: 'value', name: 'MAPE (%)', min: 0, max: 15 },
                  series: [
                    { name: '光伏预测-LSTM', type: 'line', data: [5.2, 5.5, 6.0, 6.8, 7.5, 8.2, 9.0], smooth: true, markLine: { data: [{ type: 'average', name: '平均' }] } },
                    { name: '风电预测-XGBoost', type: 'line', data: [4.8, 4.9, 5.1, 5.3, 5.5, 5.8, 6.0], smooth: true },
                    { name: '负荷预测-Transformer', type: 'line', data: [3.2, 3.5, 4.0, 5.5, 7.2, 9.5, 12.0], smooth: true },
                  ],
                }}
                style={{ height: 350 }}
              />
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'root-cause',
      label: t('driftMonitor.rootCause'),
      children: (
        <Row gutter={[16, 16]}>
          <Col span={12}>
            <Card title={t('driftMonitor.contributionAnalysis')} size="small">
              <ReactECharts option={contributionOption} style={{ height: 280 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title={t('driftMonitor.fixSuggestions')} size="small" extra={<RobotOutlined style={{ color: '#1890ff' }} />}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Card size="small" style={{ background: '#fff7e6', borderColor: '#ffd591' }}>
                  <Space>
                    <ExclamationCircleOutlined style={{ color: '#fa8c16' }} />
                    <Text strong>{t('driftMonitor.priority1')}</Text>
                  </Space>
                  <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                    辐照度和云量特征漂移严重，建议使用最近30天数据进行增量训练。
                  </Paragraph>
                </Card>
                <Card size="small" style={{ background: '#e6f7ff', borderColor: '#91d5ff' }}>
                  <Space>
                    <QuestionCircleOutlined style={{ color: '#1890ff' }} />
                    <Text strong>{t('driftMonitor.priority2')}</Text>
                  </Space>
                  <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                    数据延迟贡献12%，建议检查气象数据接口的时效性。
                  </Paragraph>
                </Card>
                <Button type="primary" block icon={<ThunderboltOutlined />}>
                  一键执行修复方案
                </Button>
              </Space>
            </Card>
          </Col>
        </Row>
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
            <Text strong>{t('driftMonitor.aiAnalysisEntry')}</Text>
            <Text type="secondary">{t('driftMonitor.aiAnalysisDesc')}</Text>
          </Space>
          <Space.Compact style={{ width: '100%' }}>
            <TextArea
              placeholder={t('driftMonitor.placeholder')}
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

      {/* 监控概览 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8} md={4}>
          <Card size="small">
            <Statistic title={t('driftMonitor.monitorModels')} value={stats.total_models} prefix={<LineChartOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small">
            <Statistic title={t('driftMonitor.normal')} value={stats.normal_count} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small">
            <Statistic title={t('driftMonitor.mildDrift')} value={stats.mild_drift_count} valueStyle={{ color: '#faad14' }} prefix={<ExclamationCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small">
            <Statistic title={t('driftMonitor.severeDrift')} value={stats.severe_drift_count} valueStyle={{ color: '#f5222d' }} prefix={<WarningOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small">
            <Statistic title={t('driftMonitor.retrainTriggered')} value={stats.retrain_triggered} valueStyle={{ color: '#722ed1' }} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
      </Row>

      {/* 模型列表和详情 */}
      <Card
        title={t('driftMonitor.modelDriftStatus')}
        size="small"
        extra={
          <Space>
            <Select
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ width: 120 }}
              size="small"
              options={[
                { value: 'all', label: t('driftMonitor.allStatus') },
                { value: 'normal', label: t('driftMonitor.statusNormal') },
                { value: 'mild', label: '轻度漂移' },
                { value: 'severe', label: '严重漂移' },
              ]}
            />
            <Button size="small" icon={<ReloadOutlined />} onClick={() => message.info(t('driftMonitor.refreshing'))}>
              刷新
            </Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Spin spinning={loading}>
          <Table
            dataSource={filteredModels}
            columns={columns}
            rowKey="model_id"
            size="small"
            pagination={{ pageSize: 5 }}
          />
        </Spin>
      </Card>

      {/* 详细分析 Tabs */}
      <Card size="small">
        <Tabs items={tabItems} />
      </Card>

      {/* 模型详情抽屉 */}
      <Drawer
        title={selectedModel?.model_name || t('driftMonitor.modelDetail')}
        open={detailDrawerVisible}
        onClose={() => setDetailDrawerVisible(false)}
        width={600}
      >
        {selectedModel && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Card size="small" title={t('driftMonitor.basicInfo')}>
              <Row gutter={[16, 8]}>
                <Col span={12}><Text type="secondary">{t('driftMonitor.modelId')}</Text>{selectedModel.model_id}</Col>
                <Col span={12}><Text type="secondary">{t('driftMonitor.scenarioLabel')}</Text>{td(selectedModel.scenario_name)}</Col>
                <Col span={12}><Text type="secondary">{t('driftMonitor.driftStatusLabel')}</Text><Tag color={DRIFT_STATUS_CONFIG[selectedModel.status].color}>{td(DRIFT_STATUS_CONFIG[selectedModel.status].text)}</Tag></Col>
                <Col span={12}><Text type="secondary">{t('driftMonitor.psiLabel')}</Text>{selectedModel.psi_score.toFixed(2)}</Col>
                <Col span={12}><Text type="secondary">{t('driftMonitor.accuracyChangeLabel')}</Text><Text type={selectedModel.accuracy_change < -5 ? 'danger' : undefined}>{selectedModel.accuracy_change}%</Text></Col>
                <Col span={12}><Text type="secondary">{t('driftMonitor.lastCheckLabel')}</Text>{selectedModel.last_check_time}</Col>
              </Row>
            </Card>
            <Card size="small" title={t('driftMonitor.quickActions')}>
              <Space wrap>
                <Button icon={<ReloadOutlined />} onClick={() => handleTriggerDetection(selectedModel.model_id)}>{t('driftMonitor.reDetect')}</Button>
                <Button icon={<ThunderboltOutlined />} type="primary">{t('driftMonitor.triggerRetrain')}</Button>
                <Button>{t('driftMonitor.createABTest')}</Button>
                <Button>{t('driftMonitor.viewHistory')}</Button>
              </Space>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default DriftMonitorPage;
// @AI_GENERATED: end
