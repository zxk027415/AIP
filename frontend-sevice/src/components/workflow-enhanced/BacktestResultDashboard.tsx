// @AI_GENERATED
import React from 'react';
import { Card, Row, Col, Statistic, Button, Table, Tag, Alert, Typography, Image, Space } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useTranslation } from 'react-i18next';
import type { BacktestPipelineResult, BacktestDailyResult } from '../../types/pipeline';

interface BacktestResultDashboardProps {
  result: BacktestPipelineResult;
  onExport?: () => void;
  onApplyBestRecommendation?: (recommendation: any) => void;
  /** 打开「Baseline vs 当前模板」多窗比对（整模板上线路径） */
  onNavigateBaselineCompare?: () => void;
}

/** 对当日序列取均值，避免仅用 [0] 在多步预测下变成一条水平线 */
function seriesMean(values: number[] | undefined | null): number | null {
  if (!values || values.length === 0) return null;
  const nums = values.filter((v) => typeof v === 'number' && Number.isFinite(v));
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

const INTRADAY_MAX_POINTS = 1800;
const IMAGE_ARTIFACT_RE = /\.(png|jpg|jpeg|webp)$/i;

/** 跨成功日拼接日内点，抽样后用于折线图（按日均值在负荷量级下易呈「直线」） */
function buildIntradaySamplePoints(days: BacktestDailyResult[]): { tip: string; f: number; a: number }[] {
  const raw: { tip: string; f: number; a: number }[] = [];
  for (const d of days) {
    const fv = d.forecastValues || [];
    const av = d.actualValues || [];
    const n = Math.min(fv.length, av.length);
    if (n === 0) continue;
    const perDayBudget = Math.max(80, Math.floor(INTRADAY_MAX_POINTS / Math.max(1, days.length)));
    const stride = Math.max(1, Math.ceil(n / perDayBudget));
    for (let i = 0; i < n; i += stride) {
      const vf = fv[i];
      const va = av[i];
      if (typeof vf === 'number' && Number.isFinite(vf) && typeof va === 'number' && Number.isFinite(va)) {
        raw.push({ tip: `${d.date} · #${i}`, f: vf, a: va });
      }
    }
  }
  if (raw.length <= INTRADAY_MAX_POINTS) return raw;
  const s2 = Math.ceil(raw.length / INTRADAY_MAX_POINTS);
  return raw.filter((_, idx) => idx % s2 === 0);
}

function fileNameOf(path: string): string {
  const clean = String(path || '').split('?')[0].split('#')[0];
  return clean.split(/[\\/]/).filter(Boolean).pop() || clean;
}

function parentNameOf(path: string): string {
  const parts = String(path || '').split('?')[0].split('#')[0].split(/[\\/]/).filter(Boolean);
  return parts.length >= 2 ? parts[parts.length - 2] : '';
}

function artifactPathToUrl(path: string, outputDir?: string): string | null {
  const filename = fileNameOf(path);
  if (!filename || !IMAGE_ARTIFACT_RE.test(filename)) return null;
  const runId = parentNameOf(path) || (outputDir ? fileNameOf(outputDir) : '');
  if (!runId) return null;
  return `/api/workflows/enhanced/backtest-artifacts/${encodeURIComponent(runId)}/${encodeURIComponent(filename)}`;
}

const BacktestResultDashboard: React.FC<BacktestResultDashboardProps> = ({
  result,
  onExport,
  onApplyBestRecommendation,
  onNavigateBaselineCompare,
}) => {
  const { t } = useTranslation();
  const { Text } = Typography;
  const hasValidResults = result.successDays > 0;

  const STATUS_COLORS: Record<string, string> = { success: 'green', skipped: 'orange', failed: 'red' };
  const STATUS_LABELS: Record<string, string> = { success: t('backtest.statusSuccess'), skipped: t('backtest.statusSkipped'), failed: t('backtest.statusFailed') };

  // Daily comparison chart
  const successDays = result.dailyResults.filter((d) => d.status === 'success');
  const intradayPts = successDays.length > 0 ? buildIntradaySamplePoints(successDays) : [];

  const comparisonOption = successDays.length > 0 ? {
    tooltip: { trigger: 'axis' as const },
    legend: { data: [t('backtest.forecastValue'), t('backtest.actualValue')] },
    xAxis: { type: 'category' as const, data: successDays.map((d) => d.date) },
    yAxis: { type: 'value' as const, scale: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider' }],
    series: [
      {
        name: t('backtest.forecastValue'),
        type: 'line',
        data: successDays.map((d) => seriesMean(d.forecastValues)),
        smooth: true,
      },
      {
        name: t('backtest.actualValue'),
        type: 'line',
        data: successDays.map((d) => seriesMean(d.actualValues)),
        smooth: true,
        lineStyle: { type: 'dashed' as const },
      },
    ],
    grid: { left: 60, right: 30, bottom: 80, top: 40 },
  } : null;

  const intradayOption =
    intradayPts.length > 1
      ? {
          tooltip: {
            trigger: 'axis' as const,
            formatter: (params: unknown) => {
              const arr = params as { dataIndex: number; seriesName: string; value: number }[];
              if (!arr?.length) return '';
              const i = arr[0].dataIndex;
              const row = intradayPts[i];
              if (!row) return '';
              return `${row.tip}<br/>${arr.map((p) => `${p.seriesName}: ${p.value?.toFixed?.(4) ?? p.value}`).join('<br/>')}`;
            },
          },
          legend: { data: [t('backtest.forecastValue'), t('backtest.actualValue')] },
          xAxis: {
            type: 'category' as const,
            data: intradayPts.map((_, i) => String(i + 1)),
          },
          yAxis: { type: 'value' as const, scale: true },
          dataZoom: [{ type: 'inside' }, { type: 'slider' }],
          series: [
            {
              name: t('backtest.forecastValue'),
              type: 'line',
              data: intradayPts.map((p) => p.f),
              smooth: true,
              showSymbol: false,
            },
            {
              name: t('backtest.actualValue'),
              type: 'line',
              data: intradayPts.map((p) => p.a),
              smooth: true,
              lineStyle: { type: 'dashed' as const },
              showSymbol: false,
            },
          ],
          grid: { left: 60, right: 30, bottom: 80, top: 48 },
        }
      : null;

  // Point count bar chart
  const pointBarOption = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: result.dailyResults.map((d) => d.date), axisLabel: { rotate: 45 } },
    yAxis: { type: 'value' as const, name: t('backtest.pointCount') },
    series: [{
      type: 'bar',
      data: result.dailyResults.map((d) => d.pointCount ?? 0),
      itemStyle: { color: '#1890ff' },
    }],
    grid: { left: 60, right: 30, bottom: 80, top: 30 },
  };

  // Metrics trend charts
  const metricsOption = result.metrics ? {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['SMAPE', 'MAE', 'RMSE'] },
    xAxis: { type: 'category' as const, data: (result.metrics.dailySmape || []).map((d) => d.date) },
    yAxis: { type: 'value' as const, scale: true },
    series: [
      { name: 'SMAPE', type: 'line', data: (result.metrics.dailySmape || []).map((d) => d.value), smooth: true },
      { name: 'MAE', type: 'line', data: (result.metrics.dailyMae || []).map((d) => d.value), smooth: true },
      { name: 'RMSE', type: 'line', data: (result.metrics.dailyRmse || []).map((d) => d.value), smooth: true },
    ],
    grid: { left: 60, right: 30, bottom: 40, top: 40 },
  } : null;

  const columns = [
    { title: t('backtest.date'), dataIndex: 'date', key: 'date', sorter: (a: BacktestDailyResult, b: BacktestDailyResult) => a.date.localeCompare(b.date) },
    { title: t('backtest.status'), dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={STATUS_COLORS[s]}>{STATUS_LABELS[s] || s}</Tag>,
      filters: [{ text: t('backtest.statusSuccess'), value: 'success' }, { text: t('backtest.statusSkipped'), value: 'skipped' }, { text: t('backtest.statusFailed'), value: 'failed' }],
      onFilter: (v: any, r: BacktestDailyResult) => r.status === v,
    },
    { title: t('backtest.durationSec'), dataIndex: 'durationSeconds', key: 'duration', render: (v?: number) => v?.toFixed(2) ?? '-', sorter: (a: BacktestDailyResult, b: BacktestDailyResult) => (a.durationSeconds ?? 0) - (b.durationSeconds ?? 0) },
    { title: t('backtest.pointCount'), dataIndex: 'pointCount', key: 'pointCount', render: (v?: number) => v ?? '-' },
    { title: t('backtest.reason'), dataIndex: 'reason', key: 'reason', ellipsis: true },
  ];

  const artifactImageUrls = Array.from(new Set([
    ...((result.artifactUrls || []).filter((u) => IMAGE_ARTIFACT_RE.test(fileNameOf(u)))),
    ...((result.artifactPaths || [])
      .map((p) => artifactPathToUrl(p, result.outputDir))
      .filter((u): u is string => Boolean(u))),
  ]));

  const tuningColumns = [
    { title: 'Rank', dataIndex: 'rank', key: 'rank', width: 80, render: (v: number | null | undefined) => v ?? '-' },
    { title: '候选', dataIndex: 'name', key: 'name', width: 180 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (s: string) => <Tag color={s === 'success' ? 'green' : 'red'}>{s || '-'}</Tag>,
    },
    {
      title: 'Score',
      dataIndex: 'candidate_score',
      key: 'score',
      width: 100,
      render: (v: any) => (v?.score != null ? Number(v.score).toFixed(4) : '-'),
    },
    {
      title: 'avg_smape',
      dataIndex: 'avg_metrics',
      key: 'avg_smape',
      width: 120,
      render: (v: any) => (v?.avg_smape != null ? Number(v.avg_smape).toFixed(4) : '-'),
    },
    { title: '错误', dataIndex: 'error', key: 'error', ellipsis: true },
  ];

  return (
    <div style={{ padding: 16 }}>
      {!hasValidResults && result.mode !== 'tuning_batch' && (
        <Alert type="warning" message={t('backtest.noValidResults')} showIcon style={{ marginBottom: 16 }} />
      )}

      {result.mode === 'tuning_batch' && (
        <Card
          title="调优候选排名"
          size="small"
          style={{ marginBottom: 16 }}
          extra={
            (onApplyBestRecommendation && result.bestRecommendation) || onNavigateBaselineCompare ? (
              <Space wrap>
                {onApplyBestRecommendation && result.bestRecommendation ? (
                  <Button type="primary" onClick={() => onApplyBestRecommendation(result.bestRecommendation)}>
                    应用最佳候选到通用配置（参数回灌）
                  </Button>
                ) : null}
                {onNavigateBaselineCompare ? (
                  <Button onClick={onNavigateBaselineCompare}>与生产基线多窗比对…</Button>
                ) : null}
              </Space>
            ) : undefined
          }
        >
          {onNavigateBaselineCompare ? (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="若修改了节点结构或希望整模板上线，请使用「与生产基线多窗比对」；下方回灌仅覆盖白名单内的全局/回测参数。"
            />
          ) : null}
          {result.bestRecommendation ? (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 12 }}
              message={`最佳候选: ${result.bestRecommendation?.name || '-'} ${
                result.bestRecommendation?.candidate_score?.score != null
                  ? `(score=${Number(result.bestRecommendation.candidate_score.score).toFixed(4)})`
                  : ''
              }`}
            />
          ) : (
            <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="暂无可应用的最佳候选" />
          )}
          <Table
            columns={tuningColumns as any}
            dataSource={(result.rankedCandidates || []).map((item, idx) => ({ ...item, key: `${idx}` }))}
            size="small"
            pagination={{ pageSize: 10 }}
          />
        </Card>
      )}

      {result.mode !== 'tuning_batch' && (
        <Row gutter={[16, 16]}>
        <Col span={4}><Card size="small"><Statistic title={t('backtest.totalDays')} value={result.totalDays} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title={t('backtest.successDays')} value={result.successDays} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title={t('backtest.skippedDays')} value={result.skippedDays} valueStyle={{ color: '#faad14' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title={t('backtest.failedDays')} value={result.failedDays} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title={t('backtest.totalDuration')} value={result.totalDuration?.toFixed(1)} suffix={t('backtest.seconds')} /></Card></Col>
        {result.metrics && (
          <Col span={4}><Card size="small"><Statistic title={t('backtest.avgSmape')} value={result.metrics.avgSmape?.toFixed(2)} suffix="%" /></Card></Col>
        )}
        </Row>
      )}

      {result.mode !== 'tuning_batch' && comparisonOption && (
        <Card title={t('backtest.dailyComparison')} size="small" style={{ marginTop: 16 }}>
          <ReactECharts option={comparisonOption} style={{ height: 300 }} />
        </Card>
      )}

      {result.mode !== 'tuning_batch' && intradayOption && (
        <Card title={t('backtest.intradaySampleTitle')} size="small" style={{ marginTop: 16 }}>
          <ReactECharts option={intradayOption} style={{ height: 320 }} />
        </Card>
      )}

      {result.mode !== 'tuning_batch' && (
      <Card title={t('backtest.dailyPointCount')} size="small" style={{ marginTop: 16 }}>
        <ReactECharts option={pointBarOption} style={{ height: 250 }} />
      </Card>
      )}

      {result.mode !== 'tuning_batch' && metricsOption && (
        <Card title={t('backtest.metricsTrend')} size="small" style={{ marginTop: 16 }}>
          <ReactECharts option={metricsOption} style={{ height: 280 }} />
        </Card>
      )}

      {result.mode !== 'tuning_batch' && (
      <Card
        title={t('backtest.dailyDetails')}
        size="small"
        style={{ marginTop: 16 }}
        extra={onExport && <Button icon={<DownloadOutlined />} size="small" onClick={onExport}>{t('backtest.exportReport')}</Button>}
      >
        <Table
          columns={columns}
          dataSource={result.dailyResults.map((d, i) => ({ ...d, key: i }))}
          size="small"
          pagination={{ pageSize: 15 }}
          scroll={{ y: 400 }}
        />
      </Card>
      )}

      {result.mode !== 'tuning_batch' && result.artifactPaths && result.artifactPaths.length > 0 && (
        <Card title={t('backtest.artifactFiles')} size="small" style={{ marginTop: 16 }}>
          <Row gutter={[0, 8]}>
            {result.artifactPaths.map((p) => (
              <Col span={24} key={p}>
                <Text code>{p}</Text>
              </Col>
            ))}
          </Row>
          {result.outputDir && (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">{t('backtest.outputDirectory')}: </Text>
              <Text code>{result.outputDir}</Text>
            </div>
          )}
        </Card>
      )}

      {result.mode !== 'tuning_batch' && artifactImageUrls.length > 0 && (
        <Card title={t('backtest.artifactPreview')} size="small" style={{ marginTop: 16 }}>
          <Image.PreviewGroup>
            <Row gutter={[12, 12]}>
              {artifactImageUrls.map((url) => (
                <Col span={12} key={url}>
                  <Image src={url} style={{ width: '100%' }} />
                </Col>
              ))}
            </Row>
          </Image.PreviewGroup>
        </Card>
      )}
    </div>
  );
};

export default BacktestResultDashboard;
// @AI_GENERATED: end
