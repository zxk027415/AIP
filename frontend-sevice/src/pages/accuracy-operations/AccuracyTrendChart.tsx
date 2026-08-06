// @AI_GENERATED
/**
 * AccuracyTrendChart.tsx — 精度对比 + 预测/真值曲线
 *
 * - 上：各形态滚动 MAPE 快照对比（monitoringSnapshot）
 * - 下：按业务日展示约 96 个 15 分钟点；可前后翻日
 * 防穿越：曲线只读已落库预测与回填真值，不直读 CSV。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
  Button,
  Space,
  DatePicker,
  Select,
} from 'antd';
import { LeftOutlined, LineChartOutlined, RightOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';
import useAccuracyOperationsStore from '../../stores/accuracyOperationsStore';
import { accuracyOperationsApi } from '../../services/accuracyOperationsApi';
import type { DailyMapePoint, MonitoringMetrics, MonitoringSnapshot } from '../../types/accuracy-operations';

const { Text } = Typography;

interface AccuracyTrendChartProps {
  slot: string;
}

function formatMape(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  // 运营侧滚动 MAPE/WMAPE 后端已是百分点（如 1.18 = 1.18%），禁止再 ×100
  return `${Number(value).toFixed(2)}%`;
}

function mapeColor(value: number | null): string {
  if (value === null || value === undefined) return '#8c8c8c';
  const pct = Number(value);
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
  const pct = Number(value);
  const maxPct = Math.max(Number(maxValue) || 1, 0.01);
  const barWidth = Math.min((pct / maxPct) * 100, 100);
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

interface VersionOption {
  key: string;
  label: string;
  form: 'production' | 'shadow' | 'prelaunch';
  workflow_id: string;
  version_tag: string;
}

function buildVersionOptions(snapshot: MonitoringSnapshot | null): VersionOption[] {
  if (!snapshot) return [];
  const list: VersionOption[] = [];
  if (snapshot.production?.workflow_id && snapshot.production.version_tag) {
    list.push({
      key: `production-${snapshot.production.workflow_id}-${snapshot.production.version_tag}`,
      label: `生产 · ${snapshot.production.version_tag}`,
      form: 'production',
      workflow_id: snapshot.production.workflow_id,
      version_tag: snapshot.production.version_tag,
    });
  }
  (snapshot.shadows || []).forEach((s, idx) => {
    if (!s.workflow_id || !s.version_tag) return;
    list.push({
      key: `shadow-${s.workflow_id}-${s.version_tag}`,
      label: `影子#${idx + 1} · ${s.version_tag}`,
      form: 'shadow',
      workflow_id: s.workflow_id,
      version_tag: s.version_tag,
    });
  });
  (snapshot.prelaunches || []).forEach((s, idx) => {
    if (!s.workflow_id || !s.version_tag) return;
    list.push({
      key: `prelaunch-${s.workflow_id}-${s.version_tag}`,
      label: `预上线#${idx + 1} · ${s.version_tag}`,
      form: 'prelaunch',
      workflow_id: s.workflow_id,
      version_tag: s.version_tag,
    });
  });
  return list;
}

function findMetricsForVersion(
  snapshot: MonitoringSnapshot | null,
  version: VersionOption | null,
): MonitoringMetrics | null {
  if (!snapshot || !version) return null;
  if (
    snapshot.production?.workflow_id === version.workflow_id
    && snapshot.production.version_tag === version.version_tag
  ) {
    return snapshot.production;
  }
  const shadow = (snapshot.shadows || []).find(
    (s) => s.workflow_id === version.workflow_id && s.version_tag === version.version_tag,
  );
  if (shadow) return shadow;
  const pre = (snapshot.prelaunches || []).find(
    (s) => s.workflow_id === version.workflow_id && s.version_tag === version.version_tag,
  );
  return pre ?? null;
}

const AccuracyTrendChart: React.FC<AccuracyTrendChartProps> = ({ slot }) => {
  const { monitoringSnapshot, fetchMonitoringSnapshot, loading, error } = useAccuracyOperationsStore();
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [seriesMeta, setSeriesMeta] = useState<{
    workflow_id?: string;
    version_tag?: string;
    point_count?: number;
    business_day?: string | null;
  }>({});
  const [availableDays, setAvailableDays] = useState<string[]>([]);
  const [businessDay, setBusinessDay] = useState<string | null>(null);
  const [selectedVersionKey, setSelectedVersionKey] = useState<string | null>(null);
  const [points, setPoints] = useState<
    Array<{ timestamp: string | null; predicted: number | null; actual: number | null }>
  >([]);

  const versionOptions = useMemo(() => buildVersionOptions(monitoringSnapshot), [monitoringSnapshot]);

  const selectedVersion = useMemo(
    () => versionOptions.find((v) => v.key === selectedVersionKey) ?? versionOptions[0] ?? null,
    [versionOptions, selectedVersionKey],
  );

  const selectedMetrics = useMemo(
    () => findMetricsForVersion(monitoringSnapshot, selectedVersion),
    [monitoringSnapshot, selectedVersion],
  );

  const dailyMapeRows = useMemo(() => {
    const series = selectedMetrics?.daily_mape_series || [];
    return [...series]
      .filter((d) => d.business_day)
      .sort((a, b) => String(a.business_day).localeCompare(String(b.business_day)))
      .slice(-7);
  }, [selectedMetrics]);

  useEffect(() => {
    void fetchMonitoringSnapshot(slot);
  }, [slot, fetchMonitoringSnapshot]);

  // 槽位或快照变化时，默认选中生产
  useEffect(() => {
    if (versionOptions.length === 0) {
      setSelectedVersionKey(null);
      return;
    }
    setSelectedVersionKey((prev) => {
      if (prev && versionOptions.some((v) => v.key === prev)) return prev;
      return versionOptions[0].key;
    });
  }, [slot, versionOptions]);

  const loadSeries = useCallback(
    async (version: VersionOption | null, day: string | null) => {
      if (!version) return;
      setSeriesLoading(true);
      setSeriesError(null);
      try {
        const res = await accuracyOperationsApi.getPredictionSeries({
          slot,
          days: 1,
          workflow_id: version.workflow_id,
          version_tag: version.version_tag,
          ...(day ? { business_day: day } : {}),
        });
        setPoints(res.points || []);
        const daysList = res.available_days || [];
        setAvailableDays(daysList);
        const resolvedDay = res.business_day || day || (daysList.length ? daysList[daysList.length - 1] : null);
        setBusinessDay(resolvedDay);
        setSeriesMeta({
          workflow_id: res.workflow_id,
          version_tag: res.version_tag,
          point_count: res.point_count,
          business_day: resolvedDay,
        });
      } catch (err) {
        setSeriesError((err as Error).message || '时序读取失败');
        setPoints([]);
      } finally {
        setSeriesLoading(false);
      }
    },
    [slot],
  );

  useEffect(() => {
    if (!selectedVersion) return;
    setBusinessDay(null);
    void loadSeries(selectedVersion, null);
  }, [slot, selectedVersion, loadSeries]);

  const dayIndex = useMemo(() => {
    if (!businessDay || availableDays.length === 0) return -1;
    return availableDays.indexOf(businessDay);
  }, [availableDays, businessDay]);

  const goPrevDay = () => {
    if (!selectedVersion || dayIndex <= 0) return;
    void loadSeries(selectedVersion, availableDays[dayIndex - 1]);
  };

  const goNextDay = () => {
    if (!selectedVersion || dayIndex < 0 || dayIndex >= availableDays.length - 1) return;
    void loadSeries(selectedVersion, availableDays[dayIndex + 1]);
  };

  const onPickDay = (value: Dayjs | null) => {
    if (!value || !selectedVersion) return;
    const key = value.format('YYYY-MM-DD');
    if (availableDays.length && !availableDays.includes(key)) {
      setSeriesError(`该日无预测点：${key}`);
      return;
    }
    void loadSeries(selectedVersion, key);
  };

  const onVersionChange = (key: string) => {
    setSelectedVersionKey(key);
  };

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
    const times = points.map((p) => {
      const ts = p.timestamp || '';
      // 单日视图：只显示时分，减少横轴拥挤
      if (ts.length >= 16) return ts.slice(11, 16);
      return ts;
    });
    // 纵轴贴合数据范围（不要从 0 起），才能看出日内波动
    const vals = points
      .flatMap((p) => [p.predicted, p.actual])
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
    let yMin: number | undefined;
    let yMax: number | undefined;
    if (vals.length > 0) {
      const lo = Math.min(...vals);
      const hi = Math.max(...vals);
      const span = Math.max(hi - lo, 1);
      const pad = Math.max(span * 0.15, 20);
      yMin = Math.floor(lo - pad);
      yMax = Math.ceil(hi + pad);
      if (yMin < 0 && lo >= 0) yMin = 0;
    }
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['预测', '真值'] },
      grid: { left: 56, right: 24, top: 40, bottom: 40 },
      xAxis: { type: 'category', data: times, axisLabel: { hideOverlap: true } },
      yAxis: {
        type: 'value',
        name: '负荷',
        scale: true,
        min: yMin,
        max: yMax,
        splitNumber: 5,
      },
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
      title: '滚动 MAPE (7d median)',
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
              title="生产滚动 MAPE (7d median)"
              value={monitoringSnapshot?.production?.rolling_mape ?? undefined}
              precision={2}
              suffix="%"
              valueStyle={{
                color: mapeColor(monitoringSnapshot?.production?.rolling_mape ?? null),
              }}
            />
          </Col>
          <Col span={8}>
            <Statistic title="形态数" value={rows.length} />
          </Col>
          <Col span={8}>
            <Statistic title="当日点数" value={seriesMeta.point_count ?? 0} />
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
        <Space wrap style={{ marginBottom: 8, width: '100%', justifyContent: 'space-between' }}>
          <div>
            <Text strong>
              预测 vs 真值
              {seriesMeta.workflow_id
                ? `（${seriesMeta.workflow_id}@${seriesMeta.version_tag}）`
                : ''}
            </Text>
            <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
              单日约 96 点（15 分钟）；切换版本可看各 patch 预测分叉；真值来自回填 actual。
            </Text>
          </div>
          <Space wrap>
            <Select
              size="small"
              style={{ minWidth: 260 }}
              placeholder="选择版本"
              value={selectedVersion?.key}
              onChange={onVersionChange}
              options={versionOptions.map((v) => ({
                value: v.key,
                label: v.label,
              }))}
              disabled={versionOptions.length === 0 || seriesLoading}
            />
            <Button
              size="small"
              icon={<LeftOutlined />}
              disabled={dayIndex <= 0 || seriesLoading}
              onClick={goPrevDay}
            >
              前一天
            </Button>
            <DatePicker
              size="small"
              value={businessDay ? dayjs(businessDay) : null}
              onChange={onPickDay}
              allowClear={false}
              disabledDate={(current) =>
                availableDays.length > 0
                  ? !availableDays.includes(current.format('YYYY-MM-DD'))
                  : false
              }
            />
            <Button
              size="small"
              icon={<RightOutlined />}
              disabled={dayIndex < 0 || dayIndex >= availableDays.length - 1 || seriesLoading}
              onClick={goNextDay}
            >
              后一天
            </Button>
          </Space>
        </Space>
        {seriesError ? <Alert type="warning" showIcon message={seriesError} style={{ marginBottom: 8 }} /> : null}
        <Spin spinning={seriesLoading}>
          {points.length === 0 ? (
            <Empty description="暂无预测时序。请先按日 mock 喂数 → pull → gap-1 日滚 → 回填。" />
          ) : (
            <ReactECharts option={chartOption} style={{ height: 320 }} />
          )}
        </Spin>

        {selectedMetrics ? (
          <div style={{ marginTop: 12 }}>
            <Text strong>日 MAPE（最近 7 个业务日）</Text>
            <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 8 }}>
              滚动 MAPE = 下列日 MAPE 的中位数
              {selectedMetrics.rolling_mape_pooled != null
                ? `；pooled 参考 ${Number(selectedMetrics.rolling_mape_pooled).toFixed(2)}%`
                : ''}
            </Text>
            {dailyMapeRows.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无日 MAPE，请先完成回填" />
            ) : (
              <Table<DailyMapePoint>
                size="small"
                pagination={false}
                rowKey={(r) => `${r.business_day}-${r.prediction_cycle_id}`}
                dataSource={dailyMapeRows}
                columns={[
                  { title: '业务日', dataIndex: 'business_day', key: 'business_day', width: 120 },
                  {
                    title: '日 MAPE',
                    dataIndex: 'daily_mape',
                    key: 'daily_mape',
                    render: (v: number | null) => (v == null ? '—' : `${Number(v).toFixed(2)}%`),
                  },
                  {
                    title: '日 WMAPE',
                    dataIndex: 'daily_wmape',
                    key: 'daily_wmape',
                    render: (v: number | null) => (v == null ? '—' : `${Number(v).toFixed(2)}%`),
                  },
                  { title: '点数', dataIndex: 'point_count', key: 'point_count', width: 72 },
                ]}
              />
            )}
          </div>
        ) : null}
      </div>
    </Card>
  );
};

export default AccuracyTrendChart;
// @AI_GENERATED: end
