import React, { useEffect, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import type { ChartConfig } from './ChartContainer';

interface LineChartProps {
  data: number[] | number[][];
  categories?: string[];
  config?: ChartConfig;
}

const LineChart: React.FC<LineChartProps> = ({
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
        
        // 创建下载链接
        const link = document.createElement('a');
        link.href = url;
        link.download = `${config.title || 'chart'}.png`;
        link.click();
      }
    };

    window.addEventListener('chart-export', handleExport);
    return () => window.removeEventListener('chart-export', handleExport);
  }, [config.title]);

  // 处理数据格式
  const isMultiSeries = Array.isArray(data[0]);
  
  const option: EChartsOption = {
    title: {
      text: config.title || '折线图',
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: 'normal',
      },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
      },
    },
    legend: config.showLegend !== false ? {
      top: 30,
      data: isMultiSeries ? (data as number[][]).map((_, i) => `系列${i + 1}`) : undefined,
    } : undefined,
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: config.showLegend !== false ? 80 : 60,
      containLabel: true,
      show: config.showGrid !== false,
    },
    xAxis: {
      type: 'category',
      name: config.xAxisLabel || 'X轴',
      nameLocation: 'middle',
      nameGap: 30,
      data: categories || (isMultiSeries 
        ? (data as number[][])[0].map((_, i) => i.toString())
        : (data as number[]).map((_, i) => i.toString())
      ),
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      name: config.yAxisLabel || 'Y轴',
      nameLocation: 'middle',
      nameGap: 50,
    },
    series: isMultiSeries
      ? (data as number[][]).map((series, index) => ({
          name: `系列${index + 1}`,
          type: 'line',
          data: series,
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: {
            width: 2,
          },
        }))
      : [
          {
            type: 'line',
            data: data as number[],
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            lineStyle: {
              width: 2,
              color: config.color || '#5470c6',
            },
            itemStyle: {
              color: config.color || '#5470c6',
            },
            areaStyle: {
              opacity: 0.1,
            },
          },
        ],
    toolbox: {
      feature: {
        saveAsImage: {
          title: '导出为PNG',
          pixelRatio: 2,
        },
        dataZoom: {
          title: {
            zoom: '区域缩放',
            back: '还原',
          },
        },
        restore: {
          title: '还原',
        },
      },
      right: 20,
    },
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
      },
      {
        start: 0,
        end: 100,
        height: 20,
        bottom: 10,
      },
    ],
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

export default LineChart;
