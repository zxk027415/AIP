import React, { useMemo } from 'react';
import { Col, Empty, Row, Statistic, Typography } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import './pvFaultClassificationMetrics.css';

const { Text } = Typography;

export interface PvClassMetric {
  label: string;
  label_name?: string;
  precision?: number | null;
  recall?: number | null;
  f1?: number | null;
  support?: number | null;
}

export interface PvClassificationMetrics {
  accuracy?: number | null;
  accuracy_mean?: number | null;
  accuracy_std?: number | null;
  precision?: number | null;
  macro_precision?: number | null;
  macro_precision_mean?: number | null;
  recall?: number | null;
  macro_recall?: number | null;
  macro_recall_mean?: number | null;
  f1?: number | null;
  macro_f1?: number | null;
  macro_f1_mean?: number | null;
  macro_f1_std?: number | null;
  counted_units?: number | null;
  n_samples?: number | null;
  n_repeats?: number | null;
  per_repeat_macro_f1?: number[];
  per_class_metrics?: PvClassMetric[];
  per_class_recall_mean?: Record<string, number | null>;
  confusion_matrix?: {
    labels?: Array<string | number>;
    label_names?: string[];
    data?: number[][];
    matrix?: number[][];
    note?: string;
  };
}

interface Props {
  metrics?: PvClassificationMetrics | null;
  labelNames?: Record<string, string>;
  emptyText: string;
}

const asPercent = (value?: number | null) => (
  value === null || value === undefined || Number.isNaN(value) ? undefined : value * 100
);

const PvFaultClassificationMetrics: React.FC<Props> = ({ metrics, labelNames = {}, emptyText }) => {
  const normalized = useMemo(() => {
    if (!metrics) return null;
    const accuracy = metrics.accuracy_mean ?? metrics.accuracy;
    const precision = metrics.macro_precision_mean ?? metrics.macro_precision ?? metrics.precision;
    const recall = metrics.macro_recall_mean ?? metrics.macro_recall ?? metrics.recall;
    const f1 = metrics.macro_f1_mean ?? metrics.macro_f1 ?? metrics.f1;
    const cm = metrics.confusion_matrix;
    const labels = (cm?.labels ?? []).map(String);
    const matrix = cm?.data ?? cm?.matrix ?? [];
    const displayNames = labels.map((label, index) => cm?.label_names?.[index] ?? labelNames[label] ?? `类别 ${label}`);
    const matrixDerived = labels.map((label, index) => {
      const tp = Number(matrix[index]?.[index] ?? 0);
      const support = (matrix[index] ?? []).reduce((sum, value) => sum + Number(value || 0), 0);
      const predicted = matrix.reduce((sum, row) => sum + Number(row[index] || 0), 0);
      const precision = predicted > 0 ? tp / predicted : 0;
      const recall = support > 0 ? tp / support : 0;
      return {
        label,
        label_name: displayNames[index],
        precision,
        recall,
        f1: precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0,
        support,
      };
    });
    const perClass = metrics.per_class_metrics?.length
      ? metrics.per_class_metrics.map(item => ({
        ...item,
        label_name: item.label_name ?? labelNames[String(item.label)] ?? `类别 ${item.label}`,
      }))
      : Object.keys(metrics.per_class_recall_mean ?? {}).length
        ? Object.entries(metrics.per_class_recall_mean ?? {}).map(([label, value]) => ({
          label,
          label_name: labelNames[label] ?? `类别 ${label}`,
          recall: value,
        }))
        : matrixDerived;
    return { accuracy, precision, recall, f1, labels, matrix, displayNames, perClass };
  }, [metrics, labelNames]);

  if (!normalized) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />;
  }

  const heatmapData = normalized.matrix.flatMap((row, rowIndex) => (
    row.map((value, colIndex) => [colIndex, rowIndex, value])
  ));
  const maxCell = Math.max(1, ...heatmapData.map(item => Number(item[2]) || 0));
  const confusionOption: EChartsOption = {
    animationDuration: 200,
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const [col, row, value] = params.value;
        return `真值：${normalized.displayNames[row]}<br/>预测：${normalized.displayNames[col]}<br/>数量：${value}`;
      },
    },
    grid: { left: 92, right: 28, top: 18, bottom: 72 },
    xAxis: { type: 'category', data: normalized.displayNames, name: '预测', axisLabel: { rotate: 25 } },
    yAxis: { type: 'category', data: normalized.displayNames, name: '真值' },
    visualMap: {
      min: 0,
      max: maxCell,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      inRange: { color: ['#f3f7fc', '#9ec5f8', '#1668dc'] },
    },
    series: [{
      type: 'heatmap',
      data: heatmapData,
      label: { show: true },
      emphasis: { itemStyle: { borderColor: '#0f172a', borderWidth: 1 } },
    }],
  };
  const classOption: EChartsOption = {
    animationDuration: 200,
    tooltip: { trigger: 'axis' },
    legend: { data: ['Precision', 'Recall', 'F1'] },
    grid: { left: 52, right: 20, top: 42, bottom: 72 },
    xAxis: {
      type: 'category',
      data: normalized.perClass.map(item => item.label_name),
      axisLabel: { rotate: 25 },
    },
    yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` } },
    series: [
      { name: 'Precision', type: 'bar', data: normalized.perClass.map(item => item.precision ?? null), itemStyle: { color: '#1677ff' } },
      { name: 'Recall', type: 'bar', data: normalized.perClass.map(item => item.recall ?? null), itemStyle: { color: '#13a8a8' } },
      { name: 'F1', type: 'bar', data: normalized.perClass.map(item => item.f1 ?? null), itemStyle: { color: '#722ed1' } },
    ],
  };
  const repeatOption: EChartsOption = {
    animationDuration: 200,
    tooltip: { trigger: 'axis' },
    grid: { left: 52, right: 20, top: 24, bottom: 42 },
    xAxis: {
      type: 'category',
      data: (metrics.per_repeat_macro_f1 ?? []).map((_, index) => `第 ${index + 1} 次`),
    },
    yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` } },
    series: [{
      name: 'Macro-F1',
      type: 'line',
      smooth: false,
      symbolSize: 7,
      data: metrics.per_repeat_macro_f1 ?? [],
      lineStyle: { color: '#1677ff', width: 2 },
      itemStyle: { color: '#1677ff' },
    }],
  };

  return (
    <div className="pv-classification-metrics">
      <Row gutter={[12, 12]}>
        {[
          ['Accuracy', normalized.accuracy, metrics.accuracy_std],
          ['Macro Precision', normalized.precision, null],
          ['Macro Recall', normalized.recall, null],
          ['Macro F1', normalized.f1, metrics.macro_f1_std],
        ].map(([label, value, std]) => (
          <Col xs={12} md={6} key={String(label)}>
            <div className="pv-metric-number">
              <Statistic title={String(label)} value={asPercent(value as number | null)} precision={1} suffix="%" />
              {typeof std === 'number' && <Text type="secondary">± {(std * 100).toFixed(1)}%</Text>}
            </div>
          </Col>
        ))}
      </Row>
      <Text type="secondary" className="pv-metric-evidence">
        证据样本：{metrics.n_samples ?? metrics.counted_units ?? '—'}
        {metrics.n_repeats ? ` · 重复评估 ${metrics.n_repeats} 次` : ''}
      </Text>
      <Row gutter={[16, 16]} style={{ marginTop: 12 }}>
        <Col xs={24} xl={12}>
          <div className="pv-metric-chart-title">混淆矩阵</div>
          {normalized.labels.length && normalized.matrix.length
            ? <ReactECharts option={confusionOption} style={{ height: Math.max(300, normalized.labels.length * 38 + 130) }} />
            : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该记录没有混淆矩阵" />}
        </Col>
        <Col xs={24} xl={12}>
          <div className="pv-metric-chart-title">各类别指标</div>
          {normalized.perClass.length
            ? <ReactECharts option={classOption} style={{ height: 320 }} />
            : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该记录没有类别级指标" />}
        </Col>
        {!!metrics.per_repeat_macro_f1?.length && (
          <Col span={24}>
            <div className="pv-metric-chart-title">重复评估稳定性</div>
            <ReactECharts option={repeatOption} style={{ height: 260 }} />
          </Col>
        )}
      </Row>
    </div>
  );
};

export default PvFaultClassificationMetrics;
