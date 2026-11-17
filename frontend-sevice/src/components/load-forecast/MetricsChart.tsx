// @AI_GENERATED
/**
 * 指标可视化图表组件
 *
 * 使用 echarts-for-react 渲染四种图表：
 * - step-duration-bar: 水平条形图展示各步骤耗时
 * - step-duration-pie: 饼图/环形图展示各步骤耗时占比
 * - backtest-line: 折线图展示每日预测值与实际值对比
 * - backtest-bar: 柱状图展示每日回测预测点数量分布
 */
import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { TRAINING_STEPS } from '../../types/load-forecast';
import type { BacktestDailyResult } from '../../types/load-forecast';

export interface MetricsChartProps {
  type: 'step-duration-bar' | 'step-duration-pie' | 'backtest-line' | 'backtest-bar';
  data: any;
  title?: string;
}

/** 构建步骤耗时水平条形图配置 */
function buildStepDurationBarOption(
  stepDurations: Record<string, number>,
  title: string | undefined,
  stepLabels: Record<string, string>,
): any {
  const entries = TRAINING_STEPS.filter((s) => stepDurations[s.name] != null).map((s) => ({
    label: stepLabels[s.name] || s.name,
    value: stepDurations[s.name],
  }));

  if (entries.length === 0) return null;

  return {
    title: title ? { text: title, textStyle: { fontSize: 14 } } : undefined,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: any) => {
        const p = params[0];
        return `${p.name}: ${p.value.toFixed(2)}s`;
      },
    },
    grid: { left: 100, right: 40, top: title ? 40 : 10, bottom: 10 },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}s' },
    },
    yAxis: {
      type: 'category',
      data: entries.map((e) => e.label),
      inverse: true,
    },
    series: [
      {
        type: 'bar',
        data: entries.map((e) => e.value),
        barWidth: 20,
        itemStyle: { borderRadius: [0, 4, 4, 0] },
        colorBy: 'data',
      },
    ],
  };
}

/** 构建步骤耗时饼图配置 */
function buildStepDurationPieOption(
  stepDurations: Record<string, number>,
  title: string | undefined,
  stepLabels: Record<string, string>,
): any {
  const entries = TRAINING_STEPS.filter((s) => stepDurations[s.name] != null).map((s) => ({
    name: stepLabels[s.name] || s.name,
    value: stepDurations[s.name],
  }));

  if (entries.length === 0) return null;

  return {
    title: title ? { text: title, textStyle: { fontSize: 14 } } : undefined,
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        return `${params.name}: ${params.value.toFixed(2)}s (${params.percent}%)`;
      },
    },
    legend: {
      orient: 'vertical',
      right: 10,
      top: 'center',
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 14, fontWeight: 'bold' },
        },
        data: entries,
      },
    ],
  };
}

/** 构建回测折线图配置 — 每日预测值统计 */
function buildBacktestLineOption(
  dailyResults: BacktestDailyResult[],
  title: string | undefined,
  legendNames: [string, string, string],
  yAxisName: string,
): any {
  const successResults = dailyResults.filter((r) => r.status === 'success');
  if (successResults.length === 0) return null;

  const dates = successResults.map((r) => r.date);

  const avgValues = successResults.map((r) => {
    const vals = r.forecast_values || [];
    if (vals.length === 0) return 0;
    return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length);
  });
  const maxValues = successResults.map((r) => {
    const vals = r.forecast_values || [];
    return vals.length > 0 ? Math.round(Math.max(...vals)) : 0;
  });
  const minValues = successResults.map((r) => {
    const vals = r.forecast_values || [];
    return vals.length > 0 ? Math.round(Math.min(...vals)) : 0;
  });

  return {
    title: title ? { text: title, textStyle: { fontSize: 14 } } : undefined,
    tooltip: { trigger: 'axis' },
    legend: { data: legendNames, top: title ? 30 : 0 },
    grid: { left: 80, right: 20, top: title ? 60 : 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      name: yAxisName,
    },
    series: [
      {
        name: legendNames[0],
        type: 'line',
        data: avgValues,
        smooth: true,
        lineStyle: { width: 2 },
      },
      {
        name: legendNames[1],
        type: 'line',
        data: maxValues,
        smooth: true,
        lineStyle: { width: 1, type: 'dashed' },
        itemStyle: { color: '#ff7875' },
      },
      {
        name: legendNames[2],
        type: 'line',
        data: minValues,
        smooth: true,
        lineStyle: { width: 1, type: 'dashed' },
        itemStyle: { color: '#95de64' },
        areaStyle: { opacity: 0 },
      },
    ],
  };
}

/** 构建回测柱状图配置 */
function buildBacktestBarOption(
  dailyResults: BacktestDailyResult[],
  title: string | undefined,
  labels: { points: string; status: string; duration: string; yAxis: string },
  statusLabel: (s: string) => string,
): any {
  if (dailyResults.length === 0) return null;

  const dates = dailyResults.map((r) => r.date);
  const pointCounts = dailyResults.map((r) => r.point_count ?? 0);
  const colors = dailyResults.map((r) => {
    switch (r.status) {
      case 'success':
        return '#52c41a';
      case 'skipped':
        return '#faad14';
      case 'failed':
        return '#ff4d4f';
      default:
        return '#d9d9d9';
    }
  });

  return {
    title: title ? { text: title, textStyle: { fontSize: 14 } } : undefined,
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = params[0];
        const result = dailyResults[p.dataIndex];
        let tip = `${p.name}<br/>${labels.points}: ${p.value}`;
        tip += `<br/>${labels.status}: ${statusLabel(result.status)}`;
        if (result.duration_seconds != null) {
          tip += `<br/>${labels.duration}: ${result.duration_seconds.toFixed(1)}s`;
        }
        return tip;
      },
    },
    grid: { left: 60, right: 20, top: title ? 40 : 10, bottom: 30 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      name: labels.yAxis,
    },
    series: [
      {
        type: 'bar',
        data: pointCounts.map((val, idx) => ({
          value: val,
          itemStyle: { color: colors[idx] },
        })),
        barWidth: '60%',
      },
    ],
  };
}

const MetricsChart: React.FC<MetricsChartProps> = ({ type, data, title }) => {
  const { t } = useTranslation();

  const stepLabels = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of TRAINING_STEPS) {
      m[s.name] = t(`loadForecast.steps.${s.name}`);
    }
    return m;
  }, [t]);

  const option = useMemo(() => {
    try {
      switch (type) {
        case 'step-duration-bar':
          return buildStepDurationBarOption(data, title, stepLabels);
        case 'step-duration-pie':
          return buildStepDurationPieOption(data, title, stepLabels);
        case 'backtest-line':
          return buildBacktestLineOption(data, title, [
            t('loadForecast.metrics.legendAvg'),
            t('loadForecast.metrics.legendMax'),
            t('loadForecast.metrics.legendMin'),
          ], t('loadForecast.metrics.yAxisLoad'));
        case 'backtest-bar':
          return buildBacktestBarOption(data, title, {
            points: t('loadForecast.metrics.tooltipPoints'),
            status: t('loadForecast.metrics.tooltipStatus'),
            duration: t('loadForecast.metrics.tooltipDuration'),
            yAxis: t('loadForecast.metrics.yAxisPointCount'),
          }, (s) => t(`loadForecast.metrics.backtestStatus.${s}`));
        default:
          return null;
      }
    } catch {
      return null;
    }
  }, [type, data, title, t, stepLabels]);

  if (!option) {
    return <Empty description={t('loadForecast.metrics.empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <ReactECharts
      option={option}
      style={{ height: 260, width: '100%' }}
      notMerge
      lazyUpdate
    />
  );
};

export default MetricsChart;
// @AI_GENERATED: end
