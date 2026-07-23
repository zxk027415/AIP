// @AI_GENERATED
/**
 * AccuracyTrendChart.tsx — 精度对比 + 预测/真值曲线
 *
 * - 上：各形态滚动 MAPE 快照对比（monitoringSnapshot）
 * - 下：PredictionResult 时序（pred vs actual）；无点时提示需先跑 gap-1 日滚+回填
 * 防穿越：曲线只读已落库预测与回填真值，不直读 CSV。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Card,
  Statistic,
  Row,
  Col,
  Spin,
  Alert,
  Empty,
  Tag,
  Typography,
  Table,
} from 'antd';
import { LineChartOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import useAccuracyOperationsStore from '../../stores/accuracyOperationsStore';
import { accuracyOperationsApi } from '../../services/accuracyOperationsApi';
import type { MonitoringMetrics } from '../../types/accuracy-operations';

const { Text } = Typography;

interface AccuracyTrendChartProps {
  slot: string;
}

function formatMape(value: number | null): string {
  if (value === null || value === undefined) return '—';
  // 后端滚动 MAPE 已是百分比数值（如 5.66），不是 0~1 比例
  const pct = value > 0 && value < 1 ? value * 100 : value;
  return `${pct.toFixed(2)}%`;
}

function mapeColor(value: number | null): string {
  if (value === null) return '#8c8c8c';
  const pct = value > 0 && value < 1 ? value * 100 : value;
  if (pct < 5) return '#52c41a';
  if (pct < 10) return '#faad14';
  return '#f5222d';
}

interface BarRow {
  key: string;
  label: string;
  form: string;
  mape: number | null;
  mae: number | null;
  cycles: number | null;
  status: string | null;
}

const MapeBar: React.FC<{ value: number | null; maxValue: number }> = ({ value, maxValue }) => {
  if (value === null) return <Text type="secondary">—</Text>;
  const pct = value > 0 && value < 1 ? value * 100 : value;
  const maxPct = maxValue > 0 && maxValue < 1 ? maxValue * 100 : maxValue;
  const barWidth = maxPct > 0 ? Math.min((pct / maxPct) * 100, 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div
        style={{
          width: `${Math.max(barWidth, 2)}%`,
          minWidth: 4,
          maxWidth: 160,
          height: 14,
          backgroundColor: mapeColor(value),
          borderRadius: 2,
        }}
      />
      <Text style={{ color: mapeColor(value), fontWeight: 600 }}>{formatMape(value)}</Text>
    </div>
  );
};

function toRow(form: string, label: string, m: MonitoringMetrics | null | undefined): BarRow | null {
  if (!m) return null;
  return {
    key: `${form}-${m.workflow_id}-${m.version_tag}`,
    label,
    form,
    mape: m.rolling_mape ?? m.rolling_wmape ?? null,
    mae: m.rolling_mae ?? null,
    cycles: m.valid_cycle_count ?? null,
    status: m.status ?? null,
  };
}

const AccuracyTrendChart: React.FC<AccuracyTrendChartProps> = ({ slot }) => {
  const { monitoringSnapshot, fetchMonitoringSnapshot, loading, error } = useAccuracyOperationsStore();
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [seriesMeta, setSeriesMeta] = useState<{ workflow_id?: string; version_tag?: string; point_count?: number }>({});
  const [points, setPoints] = useState<
    Array<{ timestamp: string | null; predicted: number | null; actual: number | null }>
  >([]);

  useEffect(() => {
    void fetchMonitoringSnapshot(slot);
  }, [slot, fetchMonitoringSnapshot]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setSeriesLoading(true);
      setSeriesError(null);
      try {
        const res = await accuracyOperationsApi.getPredictionSeries({ slot, days: 7 });
        if (cancelled) return;
        setPoints(res.points || []);
        setSeriesMeta({
          workflow_id: res.workflow_id,
          version_tag: res.version_tag,
          point_count: res.point_count,
        });
      } catch (err) {
        if (!cancelled) {
          setSeriesError((err as Error).message || '时序读取失败');
          setPoints([]);
        }
      } finally {
        if (!cancelled) setSeriesLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [slot]);

  const rows = useMemo(() => {
    const list: BarRow[] = [];
    const prod = toRow('production', '生产', monitoringSnapshot?.production ?? null);
    if (prod) list.push(prod);
    (monitoringSnapshot?.shadows || []).forEach((s, idx) => {
      const row = toRow('shadow', `影子#${idx + 1}`, s);
      if (row) list.push(row);
    });
    (monitoringSnapshot?.prelaunches || []).forEach((s, idx) => {
      const row = toRow('prelaunch', `预上线#${idx + 1}`, s);
      if (row) list.push(row);
    });
    return list;
  }, [monitoringSnapshot]);

  const maxMape = Math.max(...rows.map((r) => r.mape ?? 0), 1);

  const chartOption = useMemo(() => {
    const times = points.map((p) => p.timestamp || '');
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['预测', '真值'] },
      grid: { left: 48, right: 24, top: 40, bottom: 40 },
      xAxis: { type: 'category', data: times, axisLabel: { hideOverlap: true } },
      yAxis: { type: 'value', name: '负荷' },
      series: [
        {
          name: '预测',
          type: 'line',
          showSymbol: false,
          data: points.map((p) => p.predicted),
        },
        {
          name: '真值',
          type: 'line',
          showSymbol: false,
          data: points.map((p) => p.actual),
        },
      ],
    };
  }, [points]);

  const columns = [
    { title: '形态', dataIndex: 'label', key: 'label', width: 100 },
    {
      title: '滚动 MAPE',
      dataIndex: 'mape',
      key: 'mape',
      render: (v: number | null) => <MapeBar value={v} maxValue={maxMape} />,
    },
    {
      title: '周期',
      dataIndex: 'cycles',
      key: 'cycles',
      width: 80,
      render: (v: number | null) => v ?? '—',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (v: string | null) => <Tag>{v || '—'}</Tag>,
    },
  ];

  return (
    <Card
      size="small"
      title={
        <span>
          <LineChartOutlined style={{ marginRight: 8 }} />
          精度对比与预测曲线
        </span>
      }
    >
      {error.monitoring ? (
        <Alert type="error" showIcon message={error.monitoring} style={{ marginBottom: 12 }} />
      ) : null}

      <Spin spinning={Boolean(loading.monitoring)}>
        <Row gutter={16} style={{ marginBottom: 12 }}>
          <Col span={8}>
            <Statistic
              title="生产滚动 MAPE"
              value={formatMape(monitoringSnapshot?.production?.rolling_mape ?? null)}
            />
          </Col>
          <Col span={8}>
            <Statistic title="形态数" value={rows.length} />
          </Col>
          <Col span={8}>
            <Statistic title="曲线点数" value={seriesMeta.point_count ?? 0} />
          </Col>
        </Row>

        {rows.length === 0 ? (
          <Empty description="暂无模型监控数据" />
        ) : (
          <Table<BarRow>
            dataSource={rows}
            columns={columns}
            pagination={false}
            size="small"
            rowKey="key"
          />
        )}
      </Spin>

      <div style={{ marginTop: 16 }}>
        <Text strong>
          预测 vs 真值
          {seriesMeta.workflow_id
            ? `（${seriesMeta.workflow_id}@${seriesMeta.version_tag}）`
            : ''}
        </Text>
        <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
          仅展示已落库 PredictionResult；真值来自回填后的 actual，不直读威海 CSV（防穿越）。
        </Text>
        {seriesError ? <Alert type="warning" showIcon message={seriesError} style={{ marginBottom: 8 }} /> : null}
        <Spin spinning={seriesLoading}>
          {points.length === 0 ? (
            <Empty description="暂无预测时序。请先按日 mock 喂数 → pull → gap-1 日滚 → 回填。" />
          ) : (
            <ReactECharts option={chartOption} style={{ height: 320 }} />
          )}
        </Spin>
      </div>
    </Card>
  );
};

export default AccuracyTrendChart;
// @AI_GENERATED: end
