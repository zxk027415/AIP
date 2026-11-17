/**
 * SlotWaveformChart — 点路径电流曲线（实测 / 理论）。时间轴拉满，不截成几笔斜线。
 */
import React from 'react';
import ReactECharts from 'echarts-for-react';
import { Typography } from 'antd';

const { Text } = Typography;

export type WaveformPoint = {
  time: string;
  value?: number | null;
  i_cal?: number | null;
};

export type WaveformSeriesMap = Record<string, Array<number | null>>;

function tickLabel(stamp: string): string {
  const text = String(stamp || '');
  if (text.includes('T')) return text.slice(11, 16);
  if (text.includes(' ')) return text.split(' ')[1]?.slice(0, 5) || text;
  return text.slice(11, 16) || text;
}

interface Props {
  timestamps?: string[];
  series?: WaveformSeriesMap;
  points?: WaveformPoint[];
  height?: number;
  emptyText?: string;
}

const SlotWaveformChart: React.FC<Props> = ({
  timestamps,
  series,
  points,
  height = 220,
  emptyText = '没有可画的电流序列',
}) => {
  const axis = timestamps && timestamps.length
    ? timestamps
    : (points || []).map((item) => item.time);
  const seriesMap: WaveformSeriesMap = series && Object.keys(series).length
    ? series
    : {
        ...(points?.some((item) => item.value != null) ? { value: (points || []).map((item) => item.value ?? null) } : {}),
        ...(points?.some((item) => item.i_cal != null) ? { i_cal: (points || []).map((item) => item.i_cal ?? null) } : {}),
      };
  const usable = Object.values(seriesMap).some((vals) => (vals || []).filter((v) => v != null).length >= 2);
  if (!usable || axis.length < 2) {
    return <Text type="secondary">{emptyText}</Text>;
  }
  return (
    <ReactECharts
      style={{ height, width: '100%' }}
      option={{
        animation: false,
        tooltip: { trigger: 'axis' },
        legend: { bottom: 0, textStyle: { fontSize: 11 } },
        grid: { left: 48, right: 12, top: 12, bottom: 48 },
        xAxis: {
          type: 'category',
          data: axis.map(tickLabel),
          axisLabel: { fontSize: 10, rotate: 35 },
        },
        yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
        series: Object.entries(seriesMap).map(([name, values], index) => ({
          name: name === 'value' ? '实测电流' : name === 'i_cal' ? '理论电流' : name,
          type: 'line',
          data: values,
          smooth: true,
          showSymbol: axis.length <= 24,
          lineStyle: { width: 1.6 },
          itemStyle: { color: index === 0 ? '#1677ff' : '#fa8c16' },
        })),
      }}
    />
  );
};

export default SlotWaveformChart;
