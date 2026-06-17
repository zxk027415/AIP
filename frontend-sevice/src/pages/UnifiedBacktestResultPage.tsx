// @AI_GENERATED: Kiro v1.0
/**
 * 统一回测结果页面
 * 整合工作流回测结果和 Skill 测试结果
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Card, Select, Table, Tabs, Tag, Button, Space, message, Spin,
  Segmented, Row, Col, Statistic, Typography, Empty,
} from 'antd';
import {
  TrophyOutlined, ReloadOutlined, ApartmentOutlined,
  ThunderboltOutlined, ExperimentOutlined, LineChartOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import * as echarts from 'echarts';
import { backtestApi } from '../services/backtestApi';
import type { BacktestTask, BacktestResult } from '../types/backtest';
import { METRIC_OPTIONS } from '../types/backtest';
import { td } from '../utils/dataTranslation';

const { Text, Paragraph } = Typography;

const MEDAL = ['🥇', '🥈', '🥉'];

const toSafeNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
};

const formatFixed = (value: unknown, digits: number): string => {
  const n = toSafeNumber(value);
  return n === null ? '-' : n.toFixed(digits);
};

function metricColor(metric: string, value: number): string {
  const lower = ['rmse', 'mae', 'mape'];
  if (lower.includes(metric)) {
    if (value < 0.03) return '#52c41a';
    if (value < 0.06) return '#1890ff';
    if (value < 0.10) return '#fa8c16';
    return '#f5222d';
  }
  if (value > 0.95) return '#52c41a';
  if (value > 0.90) return '#1890ff';
  if (value > 0.85) return '#fa8c16';
  return '#f5222d';
}

// Skill 测试结果类型
interface SkillTestResult {
  task_id: string;
  skill_id: string;
  skill_name: string;
  test_type: string;
  status: 'completed' | 'failed';
  metrics: {
    mape: number;
    rmse: number;
    mae: number;
    r2: number;
    duration_seconds: number;
  };
  created_at: string;
  completed_at: string;
}

interface RankingRow {
  algorithm_id: string;
  algorithm_name: string;
  avg_score: number | null;
  best_dataset: string;
}

// 模拟 Skill 测试结果
const MOCK_SKILL_RESULTS: SkillTestResult[] = [
  {
    task_id: 'test-001',
    skill_id: 'skill-2365da5d',
    skill_name: '光伏发电功率预测 Skill',
    test_type: 'training',
    status: 'completed',
    metrics: { mape: 6.95, rmse: 105.23, mae: 82.15, r2: 0.923, duration_seconds: 245 },
    created_at: '2026-03-23T10:00:00',
    completed_at: '2026-03-23T10:04:10',
  },
  {
    task_id: 'test-004',
    skill_id: 'skill-8f4a2b1c',
    skill_name: '电网负荷预测 Skill',
    test_type: 'benchmark',
    status: 'completed',
    metrics: { mape: 4.32, rmse: 78.56, mae: 61.23, r2: 0.956, duration_seconds: 312 },
    created_at: '2026-03-22T14:00:00',
    completed_at: '2026-03-22T14:05:12',
  },
  {
    task_id: 'test-005',
    skill_id: 'skill-3c7d9e2f',
    skill_name: '设备振动故障诊断 Skill',
    test_type: 'inference',
    status: 'completed',
    metrics: { mape: 2.15, rmse: 0.023, mae: 0.018, r2: 0.987, duration_seconds: 45 },
    created_at: '2026-03-21T09:00:00',
    completed_at: '2026-03-21T09:00:45',
  },
];

const UnifiedBacktestResultPage: React.FC = () => {
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialType = searchParams.get('type') === 'skill' ? 'skill' : 'workflow';
  
  const [resultType, setResultType] = useState<'workflow' | 'skill'>(initialType);
  
  // 工作流回测结果状态
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>();
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [metric, setMetric] = useState('rmse');
  const barRef = useRef<HTMLDivElement>(null);

  // Skill 测试结果状态
  const [skillResults] = useState<SkillTestResult[]>(MOCK_SKILL_RESULTS);
  const dateLocale = (i18n.language || '').toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN';

  const rankingRows = useMemo<RankingRow[]>(() => {
    const raw = result?.ranking?.overall;
    if (!Array.isArray(raw)) return [];
    return raw.map((item: any, idx: number) => ({
      algorithm_id: String(item?.algorithm_id ?? item?.algorithm_name ?? `alg-${idx}`),
      algorithm_name: typeof item?.algorithm_name === 'string' ? item.algorithm_name : '-',
      avg_score: toSafeNumber(item?.avg_score),
      best_dataset: typeof item?.best_dataset === 'string' ? item.best_dataset : '-',
    }));
  }, [result]);

  const handleTypeChange = (type: 'workflow' | 'skill') => {
    setResultType(type);
    setSearchParams({ type });
  };

  // 加载工作流回测任务列表
  useEffect(() => {
    if (resultType === 'workflow') {
      backtestApi.listTasks({ status: 'completed', page_size: 100 }).then(res => {
        const completed = res.items.filter(t => t.status === 'completed' || t.status === 'failed');
        setTasks(completed);
        if (completed.length > 0) setSelectedTaskId(completed[0].id);
      }).catch(() => message.error(t('unifiedBacktestResult.loadFailed')));
    }
  }, [resultType, t]);

  // 加载工作流回测结果
  const fetchResults = useCallback(async () => {
    if (!selectedTaskId || resultType !== 'workflow') return;
    setLoading(true);
    try {
      const r = await backtestApi.getResults(selectedTaskId);
      if (r.matrix) {
        setResult(r);
        const task = tasks.find(t => t.id === selectedTaskId);
        if (task) {
          const pm = task.metrics_config?.primary_metric || 'rmse';
          setMetric(pm);
        }
      } else {
        setResult(null);
        message.warning(t('unifiedBacktestResult.noResultData'));
      }
    } catch {
      message.error(t('unifiedBacktestResult.loadResultsFailed'));
    } finally {
      setLoading(false);
    }
  }, [selectedTaskId, tasks, resultType]);

  useEffect(() => { fetchResults(); }, [fetchResults]);

  // 柱状图
  useEffect(() => {
    if (!barRef.current || !result?.matrix || resultType !== 'workflow') return;
    const chart = echarts.init(barRef.current);
    const m = result.matrix;
    const algorithmLabels = m.algorithms.map(a => td(m.algorithm_names[a]));
    const labelCount = algorithmLabels.length;
    const longestLabelLen = algorithmLabels.reduce((max, label) => Math.max(max, label.length), 0);
    let labelRotate = 0;
    let labelInterval: number | 'auto' = 0;
    if (labelCount > 16) {
      labelRotate = 28;
      labelInterval = 1; // 标签非常多时隔一个显示，避免重叠
    } else if (labelCount > 12) {
      labelRotate = 16;
    } else if (labelCount > 8) {
      labelRotate = 8;
    }
    if (longestLabelLen > 30 && labelCount > 8) {
      labelRotate = Math.max(labelRotate, 20);
    }
    const truncateLabel = (label: string, maxLen: number) => (
      label.length > maxLen ? `${label.slice(0, maxLen)}...` : label
    );
    const avgData = m.algorithms.map(a => {
      const vals = m.datasets.map(d => m.results[d]?.[a]?.[metric] || 0);
      return vals.reduce((s, v) => s + v, 0) / vals.length;
    });
    chart.setOption({
      title: { text: `${t('unifiedBacktestResult.algorithm')} ${metric.toUpperCase()} (${t('unifiedBacktestResult.chartAnalysis')})`, left: 'center', textStyle: { fontSize: 13 } },
      tooltip: { trigger: 'axis', confine: true },
      grid: { left: 48, right: 24, top: 56, bottom: labelRotate > 0 ? 96 : 62, containLabel: true },
      xAxis: {
        type: 'category',
        data: algorithmLabels,
        axisLabel: {
          rotate: labelRotate,
          interval: labelInterval,
          hideOverlap: true,
          margin: labelRotate > 0 ? 14 : 10,
          formatter: (value: string) => truncateLabel(value, labelRotate > 0 ? 18 : 24),
        },
      },
      yAxis: { type: 'value', name: metric.toUpperCase() },
      series: [{ type: 'bar', data: avgData, itemStyle: { color: '#1890ff' } }],
    });
    return () => chart.dispose();
  }, [result, metric, resultType, t]);

  // Skill 统计
  const skillStats = useMemo(() => {
    const total = skillResults.length;
    if (total === 0) return { total: 0, avgMape: 0, avgR2: 0, bestMape: 0 };
    const avgMape = skillResults.reduce((s, r) => s + (toSafeNumber(r.metrics.mape) ?? 0), 0) / total;
    const avgR2 = skillResults.reduce((s, r) => s + (toSafeNumber(r.metrics.r2) ?? 0), 0) / total;
    const bestMape = Math.min(...skillResults.map(r => toSafeNumber(r.metrics.mape) ?? Number.MAX_SAFE_INTEGER));
    return { total, avgMape, avgR2, bestMape };
  }, [skillResults]);

  // Skill 结果列定义
  const skillColumns = [
    {
      title: t('unifiedBacktestResult.skillName'), dataIndex: 'skill_name', key: 'skill_name', width: 220,
      render: (name: string, record: SkillTestResult) => (
        <Space>
          <ThunderboltOutlined style={{ color: '#722ed1' }} />
          <Text style={{ cursor: 'pointer', color: '#1890ff' }} onClick={() => navigate(`/skill-library/${record.skill_id}`)}>
            {td(name)}
          </Text>
        </Space>
      ),
    },
    {
      title: t('unifiedBacktestResult.testType'), dataIndex: 'test_type', key: 'test_type', width: 100,
      render: (type: string) => {
        const typeMap: Record<string, { label: string; color: string }> = {
          training: { label: t('unifiedBacktestResult.trainingTest'), color: 'purple' },
          inference: { label: t('unifiedBacktestResult.inferenceTest'), color: 'blue' },
          benchmark: { label: t('unifiedBacktestResult.benchmarkTest'), color: 'orange' },
        };
        const config = typeMap[type] || { label: type, color: 'default' };
        return <Tag color={config.color}>{config.label}</Tag>;
      },
    },
    {
      title: 'MAPE', key: 'mape', width: 100,
      render: (_: unknown, r: SkillTestResult) => (
        <Text style={{ color: metricColor('mape', toSafeNumber(r.metrics.mape) ?? 0) }}>
          {formatFixed(r.metrics.mape, 2)}%
        </Text>
      ),
    },
    {
      title: 'RMSE', key: 'rmse', width: 100,
      render: (_: unknown, r: SkillTestResult) => <Text>{formatFixed(r.metrics.rmse, 2)}</Text>,
    },
    {
      title: 'R²', key: 'r2', width: 100,
      render: (_: unknown, r: SkillTestResult) => (
        <Text style={{ color: metricColor('r2', toSafeNumber(r.metrics.r2) ?? 0) }}>
          {formatFixed(r.metrics.r2, 3)}
        </Text>
      ),
    },
    {
      title: t('unifiedBacktestResult.duration'), key: 'duration', width: 100,
      render: (_: unknown, r: SkillTestResult) => <Text>{r.metrics.duration_seconds}s</Text>,
    },
    {
      title: t('unifiedBacktestResult.completedAt'), dataIndex: 'completed_at', key: 'completed_at', width: 160,
      render: (time: string) => new Date(time).toLocaleString(dateLocale),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <LineChartOutlined style={{ fontSize: 24, color: '#1890ff' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>{t('unifiedBacktestResult.title')}</Typography.Title>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          {t('unifiedBacktestResult.subtitle')}
        </Paragraph>
      </div>

      {/* 类型切换 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Segmented
            value={resultType}
            onChange={(v) => handleTypeChange(v as 'workflow' | 'skill')}
            options={[
              { value: 'workflow', label: <><ApartmentOutlined /> {t('unifiedBacktestResult.workflowResults')}</> },
              { value: 'skill', label: <><ThunderboltOutlined /> {t('unifiedBacktestResult.skillResults')}</> },
            ]}
          />
          {resultType === 'workflow' && (
            <>
              <Select
                style={{ width: 280 }}
                placeholder={t('unifiedBacktestResult.selectTask')}
                value={selectedTaskId}
                onChange={setSelectedTaskId}
                options={tasks.map(t => ({ value: t.id, label: `${td(t.name)} (${t.completed_runs}/${t.total_runs})` }))}
              />
              <Select
                style={{ width: 120 }}
                value={metric}
                onChange={setMetric}
                options={METRIC_OPTIONS}
              />
              <Button icon={<ReloadOutlined />} onClick={fetchResults}>{t('unifiedBacktestResult.refresh')}</Button>
            </>
          )}
        </Space>
      </Card>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {resultType === 'workflow' ? (
          result?.statistics ? (
            <>
              <Col span={6}>
                <Card size="small">
                  <Statistic title={t('unifiedBacktestResult.algorithmCount')} value={result.matrix?.algorithms.length || 0} prefix={<ExperimentOutlined />} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title={t('unifiedBacktestResult.datasetCount')} value={result.matrix?.datasets.length || 0} prefix={<TrophyOutlined />} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title={t('unifiedBacktestResult.bestAlgorithm')} value={td(rankingRows[0]?.algorithm_name || '-')} prefix={<TrophyOutlined />} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title={t('unifiedBacktestResult.bestScore')} value={rankingRows[0]?.avg_score ?? 0} precision={4} prefix={<CheckCircleOutlined />} />
                </Card>
              </Col>
            </>
          ) : (
            <Col span={24}><Card size="small"><Empty description={t('unifiedBacktestResult.selectTaskToView')} /></Card></Col>
          )
        ) : (
          <>
            <Col span={6}>
              <Card size="small">
                <Statistic title={t('unifiedBacktestResult.testResultCount')} value={skillStats.total} prefix={<ExperimentOutlined />} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title={t('unifiedBacktestResult.avgMape')} value={skillStats.avgMape} suffix="%" precision={2} prefix={<LineChartOutlined />} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title={t('unifiedBacktestResult.avgR2')} value={skillStats.avgR2} precision={3} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title={t('unifiedBacktestResult.bestMape')} value={skillStats.bestMape} suffix="%" precision={2} prefix={<TrophyOutlined />} valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
          </>
        )}
      </Row>

      {/* 结果内容 */}
      <Spin spinning={loading}>
        {resultType === 'workflow' ? (
          result?.matrix ? (
            <Card>
              <Tabs items={[
                {
                  key: 'chart',
                  label: t('unifiedBacktestResult.chartAnalysis'),
                  children: (
                    <div ref={barRef} style={{ height: 350 }} />
                  ),
                },
                {
                  key: 'ranking',
                  label: t('unifiedBacktestResult.algorithmRanking'),
                  children: (
                    <Table
                      dataSource={rankingRows}
                      rowKey="algorithm_id"
                      size="small"
                      pagination={false}
                      columns={[
                        {
                          title: t('unifiedBacktestResult.rank'), key: 'rank', width: 80,
                          render: (_: unknown, __: unknown, idx: number) => (
                            <span style={{ fontSize: 18 }}>{MEDAL[idx] || idx + 1}</span>
                          ),
                        },
                        { title: t('unifiedBacktestResult.algorithm'), dataIndex: 'algorithm_name', key: 'name', render: (v: string) => td(v) },
                        {
                          title: `${t('unifiedBacktestResult.avgMape').replace('MAPE', metric.toUpperCase())}`, dataIndex: 'avg_score', key: 'score',
                          render: (v: number | null) => {
                            const score = toSafeNumber(v);
                            return (
                              <Text style={{ color: metricColor(metric, score ?? 0) }}>
                                {formatFixed(v, 4)}
                              </Text>
                            );
                          },
                        },
                        { title: t('unifiedBacktestResult.bestDataset'), dataIndex: 'best_dataset', key: 'best', render: (v: string) => td(v) },
                      ]}
                    />
                  ),
                },
              ]} />
            </Card>
          ) : (
            <Card><Empty description={t('unifiedBacktestResult.noResults')} /></Card>
          )
        ) : (
          <Card title={t('unifiedBacktestResult.skillResultList')}>
            <Table
              dataSource={skillResults}
              columns={skillColumns}
              rowKey="task_id"
              size="small"
              pagination={{ pageSize: 10, showTotal: total => t('unifiedBacktestResult.totalResults', { count: total }) }}
            />
          </Card>
        )}
      </Spin>
    </div>
  );
};

export default UnifiedBacktestResultPage;
// @AI_GENERATED: end
