// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useCallback, useRef } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Select, Table, Tabs, Tag, Button, Space, message, Spin, Radio, Tooltip,
} from 'antd';
import { DownloadOutlined, TrophyOutlined, ReloadOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import { backtestApi } from '../services/backtestApi';
import type { BacktestTask, BacktestResult } from '../types/backtest';
import { METRIC_OPTIONS } from '../types/backtest';

const MEDAL = ['🥇', '🥈', '🥉'];

function metricColor(metric: string, value: number): string {
  const lower = ['rmse', 'mae', 'mape'];
  if (lower.includes(metric)) {
    if (value < 0.03) return '#52c41a';
    if (value < 0.06) return '#1890ff';
    if (value < 0.10) return '#fa8c16';
    return '#f5222d';
  }
  // higher is better
  if (value > 0.95) return '#52c41a';
  if (value > 0.90) return '#1890ff';
  if (value > 0.85) return '#fa8c16';
  return '#f5222d';
}

const BacktestResultPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>();
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [metric, setMetric] = useState('rmse');
  const radarRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const heatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    backtestApi.listTasks({ status: 'completed', page_size: 100 }).then(res => {
      const completed = res.items.filter(t => t.status === 'completed' || t.status === 'failed');
      setTasks(completed);
      if (completed.length > 0) setSelectedTaskId(completed[0].id);
    }).catch(() => message.error('加载任务列表失败'));
  }, []);

  const fetchResults = useCallback(async () => {
    if (!selectedTaskId) return;
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
        message.warning(t('backtestResult.noResultData'));
      }
    } catch {
      message.error(t('backtestResult.loadResultsFailed'));
    } finally {
      setLoading(false);
    }
  }, [selectedTaskId, tasks]);

  useEffect(() => { fetchResults(); }, [fetchResults]);

  // Radar chart
  useEffect(() => {
    if (!radarRef.current || !result?.matrix) return;
    const chart = echarts.init(radarRef.current);
    const m = result.matrix;
    const metrics = Object.keys(result.statistics[m.algorithms[0]] || {});
    if (metrics.length === 0) { chart.dispose(); return; }
    const ds0 = m.datasets[0];
    const indicator = metrics.map(mt => {
      const lower = ['rmse', 'mae', 'mape'].includes(mt);
      const vals = m.algorithms.map(a => m.results[ds0]?.[a]?.[mt] || 0);
      return { name: mt.toUpperCase(), max: lower ? Math.max(...vals) * 1.3 : 1 };
    });
    chart.setOption({
      title: { text: `${m.dataset_names[ds0]} - 多指标对比`, left: 'center', textStyle: { fontSize: 13 } },
      tooltip: {},
      legend: { bottom: 0, data: m.algorithms.map(a => m.algorithm_names[a]) },
      radar: { indicator, radius: '60%' },
      series: [{
        type: 'radar',
        data: m.algorithms.map(a => ({
          name: m.algorithm_names[a],
          value: metrics.map(mt => m.results[ds0]?.[a]?.[mt] || 0),
        })),
      }],
    });
    return () => chart.dispose();
  }, [result, metric]);

  // Bar chart
  useEffect(() => {
    if (!barRef.current || !result?.matrix) return;
    const chart = echarts.init(barRef.current);
    const m = result.matrix;
    chart.setOption({
      title: { text: `${METRIC_OPTIONS.find(o => o.value === metric)?.label || metric} 对比`, left: 'center', textStyle: { fontSize: 13 } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, data: m.algorithms.map(a => m.algorithm_names[a]) },
      xAxis: { type: 'category', data: m.datasets.map(d => m.dataset_names[d]), axisLabel: { fontSize: 11, rotate: 15 } },
      yAxis: { type: 'value', name: metric.toUpperCase() },
      series: m.algorithms.map(a => ({
        name: m.algorithm_names[a],
        type: 'bar',
        data: m.datasets.map(d => m.results[d]?.[a]?.[metric] ?? null),
      })),
    });
    return () => chart.dispose();
  }, [result, metric]);

  // Heatmap
  useEffect(() => {
    if (!heatRef.current || !result?.matrix) return;
    const chart = echarts.init(heatRef.current);
    const m = result.matrix;
    const data: [number, number, number][] = [];
    let min = Infinity, max = -Infinity;
    m.datasets.forEach((d, di) => {
      m.algorithms.forEach((a, ai) => {
        const v = m.results[d]?.[a]?.[metric];
        if (v != null) {
          data.push([ai, di, v]);
          if (v < min) min = v;
          if (v > max) max = v;
        }
      });
    });
    chart.setOption({
      title: { text: `${metric.toUpperCase()} 热力图`, left: 'center', textStyle: { fontSize: 13 } },
      tooltip: { formatter: (p: any) => `${m.dataset_names[m.datasets[p.value[1]]]} × ${m.algorithm_names[m.algorithms[p.value[0]]]}: ${p.value[2]}` },
      xAxis: { type: 'category', data: m.algorithms.map(a => m.algorithm_names[a]), axisLabel: { fontSize: 11 } },
      yAxis: { type: 'category', data: m.datasets.map(d => m.dataset_names[d]), axisLabel: { fontSize: 11 } },
      visualMap: { min, max, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#52c41a', '#faad14', '#f5222d'] } },
      series: [{ type: 'heatmap', data, label: { show: true, fontSize: 11 } }],
    });
    return () => chart.dispose();
  }, [result, metric]);

  const m = result?.matrix;
  const ranking = result?.ranking?.overall || [];
  const stats = result?.statistics || {};

  // Pivot table columns
  const pivotColumns = m ? [
    { title: '数据集', dataIndex: 'dataset', key: 'dataset', fixed: 'left' as const, width: 180 },
    ...m.algorithms.map(aid => ({
      title: m.algorithm_names[aid],
      dataIndex: aid,
      key: aid,
      width: 140,
      render: (cell: any) => {
        if (!cell) return '-';
        const val = cell[metric];
        if (val == null) return '-';
        const rank = cell.rank;
        return (
          <Tooltip title={Object.entries(cell).filter(([k]) => k !== 'rank').map(([k, v]) => `${k}: ${v}`).join(', ')}>
            <span style={{ color: metricColor(metric, val), fontWeight: rank === 1 ? 700 : 400 }}>
              {val.toFixed(4)} {rank && rank <= 3 ? MEDAL[rank - 1] : ''}
            </span>
          </Tooltip>
        );
      },
    })),
  ] : [];

  const pivotData = m ? [
    ...m.datasets.map(did => {
      const row: any = { key: did, dataset: m.dataset_names[did] };
      m.algorithms.forEach(aid => { row[aid] = m.results[did]?.[aid] || null; });
      return row;
    }),
    // Average row
    (() => {
      const row: any = { key: '_avg', dataset: '📊 平均值' };
      m.algorithms.forEach(aid => {
        const vals = m.datasets.map(d => m.results[d]?.[aid]?.[metric]).filter((v): v is number => v != null);
        if (vals.length > 0) {
          const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
          const r = ranking.find(x => x.algorithm_id === aid);
          row[aid] = { [metric]: avg, rank: r?.rank };
        }
      });
      return row;
    })(),
  ] : [];

  // Statistics table
  const statsColumns = [
    { title: t('backtestResult.algorithm'), dataIndex: 'name', key: 'name', width: 180 },
    { title: t('backtestResult.mean'), dataIndex: 'mean', key: 'mean', render: (v: number) => v?.toFixed(4) },
    { title: t('backtestResult.std'), dataIndex: 'std', key: 'std', render: (v: number) => v?.toFixed(4) },
    { title: t('backtestResult.min'), dataIndex: 'min', key: 'min', render: (v: number) => v?.toFixed(4) },
    { title: t('backtestResult.max'), dataIndex: 'max', key: 'max', render: (v: number) => v?.toFixed(4) },
    { title: t('backtestResult.median'), dataIndex: 'median', key: 'median', render: (v: number) => v?.toFixed(4) },
    { title: t('backtestResult.rank'), dataIndex: 'rank', key: 'rank', render: (v: number) => v <= 3 ? `${MEDAL[v - 1]} #${v}` : `#${v}` },
  ];

  const statsData = m ? m.algorithms.map(aid => {
    const s = stats[aid]?.[metric] || {};
    const r = ranking.find(x => x.algorithm_id === aid);
    return { key: aid, name: m.algorithm_names[aid], ...s, rank: r?.rank || 0 };
  }) : [];

  return (
    <div style={{ padding: 24 }}>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <span>{t('backtestResult.selectTask')}</span>
          <Select value={selectedTaskId} onChange={setSelectedTaskId} style={{ width: 350 }}
            options={tasks.map(t => ({ value: t.id, label: t.name }))} />
          <span>{t('backtestResult.evalMetric')}</span>
          <Radio.Group value={metric} onChange={e => setMetric(e.target.value)} optionType="button" size="small"
            options={METRIC_OPTIONS.filter(o => {
              const task = tasks.find(t => t.id === selectedTaskId);
              return task?.metrics_config?.metrics?.includes(o.value);
            })} />
          <Button icon={<ReloadOutlined />} onClick={fetchResults}>{t('backtestResult.refresh')}</Button>
          <Button icon={<DownloadOutlined />} onClick={() => selectedTaskId && backtestApi.exportResults(selectedTaskId)}>{t('backtestResult.exportCsv')}</Button>
        </Space>
      </Card>

      <Spin spinning={loading}>
        {/* Ranking */}
        {ranking.length > 0 && (
          <Card size="small" style={{ marginBottom: 16 }} title={<><TrophyOutlined /> {t('backtestResult.overallRanking')}</>}>
            <Space size={24}>
              {ranking.map((r, i) => (
                <Tag key={r.algorithm_id} color={i === 0 ? 'gold' : i === 1 ? 'default' : i === 2 ? 'orange' : undefined}
                  style={{ fontSize: 14, padding: '4px 12px' }}>
                  {i < 3 ? MEDAL[i] : `#${r.rank}`} {r.algorithm_name} ({metric}: {r.avg_value.toFixed(4)})
                </Tag>
              ))}
            </Space>
          </Card>
        )}

        {/* Pivot table */}
        <Card size="small" style={{ marginBottom: 16 }} title={t('backtestResult.resultMatrix')}>
          <Table columns={pivotColumns} dataSource={pivotData} pagination={false} scroll={{ x: 800 }} size="small"
            rowClassName={(r) => r.key === '_avg' ? 'ant-table-row-selected' : ''} />
        </Card>

        {/* Charts */}
        <Card size="small">
          <Tabs items={[
            { key: 'radar', label: t('backtestResult.radarChart'), children: <div ref={radarRef} style={{ height: 400 }} /> },
            { key: 'bar', label: t('backtestResult.barChart'), children: <div ref={barRef} style={{ height: 400 }} /> },
            { key: 'heatmap', label: t('backtestResult.heatmap'), children: <div ref={heatRef} style={{ height: 400 }} /> },
            {
              key: 'stats', label: t('backtestResult.statsSummary'),
              children: <Table columns={statsColumns} dataSource={statsData} pagination={false} size="small" />,
            },
          ]} />
        </Card>
      </Spin>
    </div>
  );
};

export default BacktestResultPage;
// @AI_GENERATED: end
