// @AI_GENERATED: Kiro v1.0
/**
 * 方案精度管理页面
 * 按场景查看方案精度排名、趋势图表、新增精度记录
 */
import { useState, useEffect } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Table, Select, Space, Typography, Badge, Tag, Button, Modal, Form,
  Input, InputNumber, DatePicker, Row, Col, Statistic, Empty, Spin,
} from 'antd';
import {
  TrophyOutlined, ExperimentOutlined, PlusOutlined,
  ArrowUpOutlined, ArrowDownOutlined, MinusOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import {
  fetchAccuracyRanking, fetchAccuracyHistory, addAccuracyRecord, fetchTemplateStats,
} from '../services/algorithmSolutionApi';
import type { AccuracyRankingItem, AccuracyRecord, TemplateStats } from '../types/algorithm-solution';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { Text } = Typography;

const STATUS_KEYS: Record<string, { labelKey: string; color: string }> = {
  excellent: { labelKey: 'templateAccuracy.excellent', color: '#52c41a' },
  good: { labelKey: 'templateAccuracy.good', color: '#1890ff' },
  fair: { labelKey: 'templateAccuracy.fair', color: '#fa8c16' },
  needs_improvement: { labelKey: 'templateAccuracy.needsImprovement', color: '#f5222d' },
};

const TemplateAccuracyPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [stats, setStats] = useState<TemplateStats | null>(null);
  const [scenarioId, setScenarioId] = useState<string | undefined>(undefined);
  const [ranking, setRanking] = useState<AccuracyRankingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTpl, setSelectedTpl] = useState<string | null>(null);
  const [history, setHistory] = useState<AccuracyRecord[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => { fetchTemplateStats().then(setStats); }, []);

  useEffect(() => {
    setLoading(true);
    fetchAccuracyRanking(scenarioId).then(res => {
      setRanking(res.ranking);
      setLoading(false);
    });
  }, [scenarioId]);

  useEffect(() => {
    if (selectedTpl) {
      fetchAccuracyHistory(selectedTpl).then(res => setHistory(res.records));
    } else {
      setHistory([]);
    }
  }, [selectedTpl]);

  const handleAdd = async () => {
    if (!selectedTpl) return;
    const vals = await form.validateFields();
    const metrics: Record<string, number> = {};
    if (vals.rmse !== undefined) metrics.rmse = vals.rmse;
    if (vals.mae !== undefined) metrics.mae = vals.mae;
    if (vals.r2 !== undefined) metrics.r2 = vals.r2;
    if (vals.mape !== undefined) metrics.mape = vals.mape;
    if (vals.f1 !== undefined) metrics.f1 = vals.f1;
    await addAccuracyRecord(selectedTpl, {
      dataset_name: vals.dataset_name,
      test_date: vals.test_date?.format('YYYY-MM-DD'),
      metrics,
      tester: vals.tester,
      notes: vals.notes,
    });
    setModalOpen(false);
    form.resetFields();
    // refresh
    const res = await fetchAccuracyHistory(selectedTpl);
    setHistory(res.records);
    const rk = await fetchAccuracyRanking(scenarioId);
    setRanking(rk.ranking);
  };

  const excellentCount = ranking.filter(r => r.status === 'excellent').length;
  const goodCount = ranking.filter(r => r.status === 'good').length;

  const chartOption = history.length > 0 ? {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: history.map(h => h.test_date).reverse() },
    yAxis: { type: 'value' as const },
    series: Object.keys(history[0]?.metrics || {}).map(key => ({
      name: key.toUpperCase(),
      type: 'line' as const,
      data: [...history].reverse().map(h => h.metrics[key]),
      smooth: true,
    })),
    legend: { bottom: 0 },
  } : null;

  const columns = [
    {
      title: t('templateAccuracy.rank'), key: 'rank', width: 60,
      render: (_: unknown, __: unknown, i: number) => {
        if (i === 0) return <TrophyOutlined style={{ color: '#faad14', fontSize: 18 }} />;
        return <Text type="secondary">{i + 1}</Text>;
      },
    },
    {
      title: t('templateAccuracy.templateName'), dataIndex: 'template_name', key: 'name',
      render: (v: string, r: AccuracyRankingItem) => (
        <a onClick={() => setSelectedTpl(r.template_id)}>{td(v)}</a>
      ),
    },
    {
      title: t('templateAccuracy.accuracyStatus'), dataIndex: 'status', key: 'status', width: 100,
      render: (s: string) => <Badge color={STATUS_KEYS[s]?.color} text={t(STATUS_KEYS[s]?.labelKey || s)} />,
    },
    {
      title: t('templateAccuracy.coreMetrics'), dataIndex: 'metrics', key: 'metrics',
      render: (m: Record<string, number>) => (
        <Space size={8}>
          {Object.entries(m).slice(0, 3).map(([k, v]) => (
            <Tag key={k} style={{ fontSize: 11 }}>{k.toUpperCase()}: {typeof v === 'number' ? v.toFixed(4) : v}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: t('templateAccuracy.trend'), key: 'trend', width: 60,
      render: (_: unknown, r: AccuracyRankingItem) => {
        const prev = ranking.find(x => x.template_id === r.template_id);
        if (!prev) return <MinusOutlined />;
        const val = r.metrics.rmse ?? r.metrics.mae ?? 0;
        if (val < 0.03) return <ArrowUpOutlined style={{ color: '#52c41a' }} />;
        if (val > 0.08) return <ArrowDownOutlined style={{ color: '#f5222d' }} />;
        return <MinusOutlined style={{ color: '#999' }} />;
      },
    },
    { title: t('templateAccuracy.testDate'), dataIndex: 'test_date', key: 'date', width: 120 },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Space wrap style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Text strong style={{ fontSize: 16 }}>{t('templateAccuracy.title')}</Text>
          {stats && (
            <Select style={{ width: 200 }} placeholder={t('templateAccuracy.selectScenario')} allowClear
              value={scenarioId} onChange={v => { setScenarioId(v); setSelectedTpl(null); }}
              options={stats.by_scenario.map(s => ({ value: s.scenario_id, label: `${s.icon} ${td(s.name)}` }))}
            />
          )}
        </Space>
        <Button icon={<PlusOutlined />} disabled={!selectedTpl} onClick={() => setModalOpen(true)}>
          {t('templateAccuracy.addRecord')}
        </Button>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title={t('templateAccuracy.hasRecords')} value={ranking.length} prefix={<ExperimentOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title={t('templateAccuracy.excellentCount')} value={excellentCount} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title={t('templateAccuracy.goodCount')} value={goodCount} valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title={t('templateAccuracy.needsImprovementCount')} value={ranking.filter(r => r.status === 'needs_improvement').length} valueStyle={{ color: '#f5222d' }} /></Card></Col>
      </Row>

      <Row gutter={16}>
        <Col span={selectedTpl ? 14 : 24}>
          <Card title={t('templateAccuracy.accuracyRanking')} size="small">
            <Spin spinning={loading}>
              <Table dataSource={ranking} columns={columns} rowKey="template_id" size="small"
                pagination={false}
                onRow={r => ({ onClick: () => setSelectedTpl(r.template_id), style: { cursor: 'pointer', background: r.template_id === selectedTpl ? '#e6f7ff' : undefined } })}
              />
            </Spin>
          </Card>
        </Col>
        {selectedTpl && (
          <Col span={10}>
            <Card title={`${t('templateAccuracy.accuracyTrend')} - ${td(ranking.find(r => r.template_id === selectedTpl)?.template_name || selectedTpl)}`} size="small">
              {chartOption ? (
                <ReactECharts option={chartOption} style={{ height: 300 }} />
              ) : (
                <Empty description={t('templateAccuracy.noHistory')} />
              )}
            </Card>
          </Col>
        )}
      </Row>

      <Modal title={t('templateAccuracy.addRecordTitle')} open={modalOpen} onOk={handleAdd} onCancel={() => setModalOpen(false)} width={480}>
        <Form form={form} layout="vertical">
          <Form.Item name="dataset_name" label={t('templateAccuracy.datasetName')} rules={[{ required: true }]}><Input placeholder={t('templateAccuracy.datasetNamePlaceholder')} /></Form.Item>
          <Form.Item name="test_date" label={t('templateAccuracy.testDateLabel')} rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="rmse" label="RMSE"><InputNumber style={{ width: '100%' }} step={0.001} min={0} /></Form.Item></Col>
            <Col span={12}><Form.Item name="mae" label="MAE"><InputNumber style={{ width: '100%' }} step={0.001} min={0} /></Form.Item></Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="r2" label="R²"><InputNumber style={{ width: '100%' }} step={0.001} min={0} max={1} /></Form.Item></Col>
            <Col span={12}><Form.Item name="mape" label="MAPE (%)"><InputNumber style={{ width: '100%' }} step={0.1} min={0} /></Form.Item></Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="f1" label="F1-Score"><InputNumber style={{ width: '100%' }} step={0.01} min={0} max={1} /></Form.Item></Col>
            <Col span={12}><Form.Item name="tester" label={t('templateAccuracy.tester')}><Input /></Form.Item></Col>
          </Row>
          <Form.Item name="notes" label={t('templateAccuracy.notes')}><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TemplateAccuracyPage;
// @AI_GENERATED: end
