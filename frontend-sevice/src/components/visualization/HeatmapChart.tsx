import React from 'react';
import ReactECharts from 'echarts-for-react';

interface HeatmapChartProps {
  data: number[][];
  xLabels?: string[];
  yLabels?: string[];
  title?: string;
  colorRange?: [string, string];
}

const HeatmapChart: React.FC<HeatmapChartProps> = ({
  data,
  xLabels,
  yLabels,
  title = '热力图',
  colorRange = ['#313695', '#a50026'],
}) => {
  // 转换数据格式为 ECharts 需要的格式 [x, y, value]
  const formattedData: [number, number, number][] = [];
  data.forEach((row, y) => {
    row.forEach((value, x) => {
      formattedData.push([x, y, value]);
    });
  });

  // 计算最小值和最大值
  const values = formattedData.map(item => item[2]);
  const min = Math.min(...values);
  const max = Math.max(...values);

  const option = {
    title: {
      text: title,
      left: 'center',
    },
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const [x, y, value] = params.value;
        const xLabel = xLabels ? xLabels[x] : x;
        const yLabel = yLabels ? yLabels[y] : y;
        return `${yLabel} - ${xLabel}: ${value.toFixed(2)}`;
      },
    },
    grid: {
      left: '10%',
      right: '10%',
      bottom: '15%',
      top: '15%',
    },
    xAxis: {
      type: 'category',
      data: xLabels || Array.from({ length: data[0]?.length || 0 }, (_, i) => i),
      splitArea: {
        show: true,
      },
    },
    yAxis: {
      type: 'category',
      data: yLabels || Array.from({ length: data.length }, (_, i) => i),
      splitArea: {
        show: true,
      },
    },
    visualMap: {
      min: min,
      max: max,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '5%',
      inRange: {
        color: [colorRange[0], '#ffffbf', colorRange[1]],
      },
    },
    series: [
      {
        name: '热力值',
        type: 'heatmap',
        data: formattedData,
        label: {
          show: false,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
    toolbox: {
      feature: {
        saveAsImage: {
          title: '导出为PNG',
        },
      },
    },
  };

  return <ReactECharts option={option} style={{ height: '500px', width: '100%' }} />;
};

export default HeatmapChart;
