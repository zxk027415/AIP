import React from 'react';
import ReactECharts from 'echarts-for-react';

interface ScatterPlotProps {
  data: [number, number][];
  title?: string;
  xAxisLabel?: string;
  yAxisLabel?: string;
  pointSize?: number;
  color?: string;
}

const ScatterPlot: React.FC<ScatterPlotProps> = ({
  data,
  title = '散点图',
  xAxisLabel = 'X轴',
  yAxisLabel = 'Y轴',
  pointSize = 10,
  color = '#5470c6',
}) => {
  const option = {
    title: {
      text: title,
      left: 'center',
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        return `(${params.value[0]}, ${params.value[1]})`;
      },
    },
    xAxis: {
      type: 'value',
      name: xAxisLabel,
      nameLocation: 'middle',
      nameGap: 30,
    },
    yAxis: {
      type: 'value',
      name: yAxisLabel,
      nameLocation: 'middle',
      nameGap: 40,
    },
    series: [
      {
        type: 'scatter',
        data: data,
        symbolSize: pointSize,
        itemStyle: {
          color: color,
          opacity: 0.8,
        },
        emphasis: {
          itemStyle: {
            opacity: 1,
            borderColor: '#333',
            borderWidth: 2,
          },
        },
      },
    ],
    toolbox: {
      feature: {
        saveAsImage: {
          title: '导出为PNG',
        },
        dataZoom: {
          title: {
            zoom: '区域缩放',
            back: '还原',
          },
        },
      },
    },
    grid: {
      left: '10%',
      right: '10%',
      bottom: '15%',
      top: '15%',
    },
  };

  return <ReactECharts option={option} style={{ height: '400px', width: '100%' }} />;
};

export default ScatterPlot;
