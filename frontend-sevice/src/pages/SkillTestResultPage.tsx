// @AI_GENERATED: Kiro v1.0
/**
 * Skill 测试结果页面
 * 展示 Skill 测试结果，包括精度指标、对比分析、实验历史
 */
import { useState, useMemo } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Space, Typography, Tag, Row, Col, Table, Statistic,
  Tabs, Progress, Descriptions,
} from 'antd';
import {
  ThunderboltOutlined, CheckCircleOutlined, TrophyOutlined,
  LineChartOutlined, HistoryOutlined, ExperimentOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

const { Text, Paragraph } = Typography;

// 测试结果类型
interface TestResult {
  result_id: string;
  skill_id: string;
  skill_name: string;
  test_type: string;
  version: string;
  metrics: {
    mape: number;
    rmse: number;
    mae: number;
    r2: number;
  };
  baseline_metrics?: {
    mape: number;
    rmse: number;
  };
  improvement?: number;
  status: 'pass' | 'fail' | 'warning';
  tested_at: string;
  duration_seconds: number;
}

// 实验历史类型
interface ExperimentRecord {
  id: number;
  commit: string;
  description: string;
  mape: number;
  rmse: number;
  status: 'keep' | 'discard';
  time: string;
}

// 模拟测试结果
const MOCK_RESULTS: TestResult[] = [
  {
    result_id: 'result-001',
    skill_id: 'skill-2365da5d',
    skill_name: '光伏发电功率预测 Skill',
    test_type: 'training',
    version: 'v1.0.0',
    metrics: { mape: 6.95, rmse: 105.23, mae: 78.45, r2: 0.92 },
    baseline_metrics: { mape: 12.34, rmse: 156.78 },
    improvement: 43.7,
    status: 'pass',
    tested_at: '2026-03-23T10:04:10',
    duration_seconds: 245,
  },
  {
    result_id: 'result-002',
    skill_id: 'skill-8f4a2b1c',
    skill_name: '电网负荷预测 Skill',
    test_type: 'benchmark',
    version: 'v1.0.0',
    metrics: { mape: 4.56, rmse: 89.12, mae: 65.34, r2: 0.95 },
    baseline_metrics: { mape: 5.23, rmse: 98.45 },
    improvement: 12.8,
    status: 'pass',
    tested_at: '2026-03-23T11:30:00',
    duration_seconds: 1800,
  },
  {
    result_id: 'result-003',
    skill_id: 'skill-3c7d9e2f',
    skill_name: '设备振动故障诊断 Skill',
    test_type: 'inference',
    version: 'v1.0.0',
    metrics: { mape: 8.12, rmse: 0.045, mae: 0.032, r2: 0.88 },
    status: 'warning',
    tested_at: '2026-03-23T12:15:00',
    duration_seconds: 120,
  },
];

// 模拟实验历史
const MOCK_EXPERIMENTS: ExperimentRecord[] = [
  { id: 1, commit: 'a1b2c3d', description: 'baseline - 线性回归', mape: 12.34, rmse: 156.78, status: 'keep', time: '2026-03-23 10:00' },
  { id: 2, commit: 'b2c3d4e', description: 'LSTM 2层 hidden=64', mape: 8.54, rmse: 125.67, status: 'keep', time: '2026-03-23 10:05' },
  { id: 3, commit: 'c3d4e5f', description: 'GRU 效果更差', mape: 15.00, rmse: 200.00, status: 'discard', time: '2026-03-23 10:10' },
  { id: 4, commit: 'd4e5f6g', description: 'LSTM + 时间特征', mape: 7.82, rmse: 118.45, status: 'keep', time: '2026-03-23 10:15' },
  { id: 5, commit: 'e5f6g7h', description: 'LSTM + 气象特征', mape: 6.95, rmse: 105.23, status: 'keep', time: '2026-03-23 10:20' },
];

const SkillTestResultPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [results] = useState<TestResult[]>(MOCK_RESULTS);
  const [selectedResult, setSelectedResult] = useState<TestResult | null>(MOCK_RESULTS[0]);
  const [experiments] = useState<ExperimentRecord[]>(MOCK_EXPERIMENTS);

  // 统计数据
  const stats = useMemo(() => {
    const total = results.length;
    const passed = results.filter(r => r.status === 'pass').length;
    const avgMape = results.reduce((sum, r) => sum + r.metrics.mape, 0) / total;
    const bestMape = Math.min(...results.map(r => r.metrics.mape));
    return { total, passed, avgMape, bestMape };
  }, [results]);

  const resultColumns: ColumnsType<TestResult> = [
    {
      title: t('skillTestResult.skillName'),
      dataIndex: 'skill_name',
      key: 'skill_name',
      render: (name) => (
        <Space>
          <ThunderboltOutlined style={{ color: '#722ed1' }} />
          <Text>{name}</Text>
        </Space>
      ),
    },
    {
      title: t('skillTestResult.testType'),
      dataIndex: 'test_type',
      key: 'test_type',
      render: (type) => {
        const typeMap: Record<string, string> = {
          training: t('skillTestResult.trainingTest'),
          inference: t('skillTestResult.inferenceTest'),
          benchmark: t('skillTestResult.benchmarkTest'),
        };
        return <Tag>{typeMap[type] || type}</Tag>;
      },
    },
    {
      title: 'MAPE',
      dataIndex: ['metrics', 'mape'],
      key: 'mape',
      render: (mape, record) => (
        <Space>
          <Text strong style={{ color: mape < 10 ? '#52c41a' : '#faad14' }}>{mape.toFixed(2)}%</Text>
          {record.improvement && (
            <Tag color="green" icon={<ArrowDownOutlined />}>↓{record.improvement.toFixed(1)}%</Tag>
          )}
        </Space>
      ),
    },
    {
      title: 'RMSE',
      dataIndex: ['metrics', 'rmse'],
      key: 'rmse',
      render: (rmse) => <Text>{rmse.toFixed(2)}</Text>,
    },
    {
      title: 'R²',
      dataIndex: ['metrics', 'r2'],
      key: 'r2',
      render: (r2) => <Text>{r2.toFixed(2)}</Text>,
    },
    {
      title: t('skillTestResult.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const config: Record<string, { label: string; color: string }> = {
          pass: { label: t('skillTestResult.pass'), color: 'success' },
          fail: { label: t('skillTestResult.fail'), color: 'error' },
          warning: { label: t('skillTestResult.warning'), color: 'warning' },
        };
        return <Tag color={config[status]?.color}>{config[status]?.label}</Tag>;
      },
    },
    {
      title: t('skillTestResult.testTime'),
      dataIndex: 'tested_at',
      key: 'tested_at',
      render: (time) => new Date(time).toLocaleString('zh-CN'),
    },
  ];

  const experimentColumns: ColumnsType<ExperimentRecord> = [
    {
      title: t('skillTestResult.commit'),
      dataIndex: 'commit',
      key: 'commit',
      render: (commit) => <Text code>{commit}</Text>,
    },
    {
      title: t('skillTestResult.experimentDesc'),
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: 'MAPE',
      dataIndex: 'mape',
      key: 'mape',
      render: (mape, record) => (
        <Text strong style={{ color: record.status === 'keep' ? '#52c41a' : '#ff4d4f' }}>
          {mape.toFixed(2)}%
        </Text>
      ),
    },
    {
      title: 'RMSE',
      dataIndex: 'rmse',
      key: 'rmse',
      render: (rmse) => rmse.toFixed(2),
    },
    {
      title: t('skillTestResult.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'keep' ? 'green' : 'red'}>
          {status === 'keep' ? t('skillTestResult.keep') : t('skillTestResult.discard')}
        </Tag>
      ),
    },
    {
      title: t('skillTestResult.time'),
      dataIndex: 'time',
      key: 'time',
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <TrophyOutlined style={{ fontSize: 24, color: '#faad14' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>{t('skillTestResult.title')}</Typography.Title>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          查看 Skill 测试结果、精度指标和实验历史
        </Paragraph>
      </div>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title={t('skillTestResult.totalTests')} value={stats.total} prefix={<ExperimentOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic 
              title={t('skillTestResult.passRate')} 
              value={(stats.passed / stats.total * 100).toFixed(0)} 
              suffix="%" 
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic 
              title={t('skillTestResult.avgMape')} 
              value={stats.avgMape.toFixed(2)} 
              suffix="%" 
              prefix={<LineChartOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic 
              title={t('skillTestResult.bestMape')} 
              value={stats.bestMape.toFixed(2)} 
              suffix="%" 
              prefix={<TrophyOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 主内容 */}
      <Tabs defaultActiveKey="results">
        {/* 测试结果 Tab */}
        <Tabs.TabPane tab={<><CheckCircleOutlined /> {t('skillTestResult.testResults')}</>} key="results">
          <Card>
            <Table
              dataSource={results}
              columns={resultColumns}
              rowKey="result_id"
              size="small"
              onRow={(record) => ({
                onClick: () => setSelectedResult(record),
                style: { cursor: 'pointer', background: selectedResult?.result_id === record.result_id ? '#e6f7ff' : undefined },
              })}
            />
          </Card>

          {/* 选中结果详情 */}
          {selectedResult && (
            <Card title={t('skillTestResult.resultDetail')} style={{ marginTop: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Descriptions bordered size="small" column={1}>
                    <Descriptions.Item label={t('skillTestResult.skillNameLabel')}>{selectedResult.skill_name}</Descriptions.Item>
                    <Descriptions.Item label={t('skillTestResult.versionLabel')}>{selectedResult.version}</Descriptions.Item>
                    <Descriptions.Item label={t('skillTestResult.testTypeLabel')}>{selectedResult.test_type}</Descriptions.Item>
                    <Descriptions.Item label={t('skillTestResult.testTimeLabel')}>{new Date(selectedResult.tested_at).toLocaleString()}</Descriptions.Item>
                    <Descriptions.Item label={t('skillTestResult.duration')}>{selectedResult.duration_seconds} {t('common.seconds')}</Descriptions.Item>
                  </Descriptions>
                </Col>
                <Col span={12}>
                  <Card size="small" title={t('skillTestResult.accuracyMetrics')}>
                    <Row gutter={16}>
                      <Col span={12}>
                        <Statistic title="MAPE" value={selectedResult.metrics.mape} suffix="%" precision={2} />
                      </Col>
                      <Col span={12}>
                        <Statistic title="RMSE" value={selectedResult.metrics.rmse} precision={2} />
                      </Col>
                      <Col span={12}>
                        <Statistic title="MAE" value={selectedResult.metrics.mae} precision={2} />
                      </Col>
                      <Col span={12}>
                        <Statistic title="R²" value={selectedResult.metrics.r2} precision={2} />
                      </Col>
                    </Row>
                    {selectedResult.improvement && (
                      <div style={{ marginTop: 16 }}>
                        <Tag color="green" icon={<ArrowUpOutlined />}>
                          相比基线提升 {selectedResult.improvement.toFixed(1)}%
                        </Tag>
                      </div>
                    )}
                  </Card>
                </Col>
              </Row>
            </Card>
          )}
        </Tabs.TabPane>

        {/* 实验历史 Tab */}
        <Tabs.TabPane tab={<><HistoryOutlined /> {t('skillTestResult.experimentHistory')}</>} key="history">
          <Card>
            <Table
              dataSource={experiments}
              columns={experimentColumns}
              rowKey="id"
              size="small"
              pagination={false}
            />
          </Card>

          {/* 实验进度可视化 */}
          <Card title={t('skillTestResult.mapeProgress')} style={{ marginTop: 16 }}>
            <div style={{ padding: 16 }}>
              {experiments.filter(e => e.status === 'keep').map((exp) => (
                <div key={exp.id} style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
                  <Text style={{ width: 200 }}>{exp.description}</Text>
                  <Progress 
                    percent={100 - exp.mape * 3} 
                    size="small" 
                    style={{ flex: 1, marginRight: 16 }}
                    strokeColor={exp.mape < 8 ? '#52c41a' : exp.mape < 10 ? '#1890ff' : '#faad14'}
                    format={() => `${exp.mape}%`}
                  />
                </div>
              ))}
            </div>
          </Card>
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default SkillTestResultPage;
// @AI_GENERATED: end
