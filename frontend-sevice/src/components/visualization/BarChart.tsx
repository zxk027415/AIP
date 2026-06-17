import React, { useEffect, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import type { ChartConfig } from './ChartContainer';

interface BarChartProps {
  data: number[] | number[][];
  categories: string[];
  config?: ChartConfig;
}

const BarChart: React.FC<BarChartProps> = ({
  data,
  categories,
  config = {},
}) => {
  const chartRef = useRef<any>(null);

  useEffect(() => {
    // 监听导出事件
    const handleExport = () => {
      if (chartRef.current) {
        const instance = chartRef.current.getEchartsInstance();
        const url = instance.getDataURL({
          type: 'png',
          pixelRatio: 2,
          backgroundColor: '#fff',
        });
        
        const link = document.createElement('a');
        link.href = url;
        link.download = `${config.title || 'bar-chart'}.png`;
        link.click();
      }
    };

    window.addEventListener('chart-export', handleExport);
    return () => window.removeEventListener('chart-export', handleExport);
  }, [config.title]);

  // 检查是否为多系列数据
  const isMultiSeries = Array.isArray(data[0]);

  const option: EChartsOption = {
    title: {
      text: config.title || '柱状图',
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: 'normal',
      },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
    },
    legend: config.showLegend !== false && isMultiSeries ? {
      top: 30,
      data: (data as number[][]).map((_, i) => `系列${i + 1}`),
    } : undefined,
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: config.showLegend !== false && isMultiSeries ? 80 : 60,
      containLabel: true,
      show: config.showGrid !== false,
    },
    xAxis: {
      type: 'category',
      name: config.xAxisLabel || '类别',
      nameLocation: 'middle',
      nameGap: 30,
      data: categories,
      axisLabel: {
        interval: 0,
        rotate: categories.length > 10 ? 45 : 0,
      },
    },
    yAxis: {
      type: 'value',
      name: config.yAxisLabel || '数值',
      nameLocation: 'middle',
      nameGap: 50,
    },
    series: isMultiSeries
      ? (data as number[][]).map((series, index) => ({
          name: `系列${index + 1}`,
          type: 'bar',
          data: series,
          emphasis: {
            focus: 'series',
          },
          barMaxWidth: 50,
        }))
      : [
          {
            type: 'bar',
            data: data as number[],
            itemStyle: {
              color: config.color || '#5470c6',
            },
            emphasis: {
              itemStyle: {
                color: config.color ? adjustColor(config.color, -20) : '#3d5aa6',
              },
            },
            barMaxWidth: 50,
          },
        ],
    toolbox: {
      feature: {
        saveAsImage: {
          title: '导出为PNG',
          pixelRatio: 2,
        },
        dataView: {
          title: '数据视图',
          readOnly: true,
        },
        restore: {
          title: '还原',
        },
      },
      right: 20,
    },
  };

  return (
    <ReactECharts
      ref={chartRef}
      option={option}
      style={{ height: '100%', minHeight: '350px' }}
      notMerge={true}
      lazyUpdate={true}
    />
  );
};

// 辅助函数：调整颜色亮度
function adjustColor(color: string, amount: number): string {
  const clamp = (val: number) => Math.min(Math.max(val, 0), 255);
  
  // 简单的颜色调整（假设输入为hex格式）
  if (color.startsWith('#')) {
    const hex = color.slice(1);
    const num = parseInt(hex, 16);
    const r = clamp((num >> 16) + amount);
    const g = clamp(((num >> 8) & 0x00ff) + amount);
    const b = clamp((num & 0x0000ff) + amount);
    return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
  }
  
  return color;
}

export default BarChart;
