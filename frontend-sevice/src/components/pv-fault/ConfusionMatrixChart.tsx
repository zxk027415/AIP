// @AI_GENERATED
/**
 * ConfusionMatrixChart — ECharts 热力图展示混淆矩阵。
 *
 * 接收 matrix(二维数组) + labels(类别名)，渲染带数值标注的混淆矩阵。
 * 支持归一化切换（原始计数 / 按行归一化）。
 */
import React, { useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Radio } from 'antd';

interface ConfusionMatrixChartProps {
  matrix: number[][];
  labels: string[];
  title?: string;
}

const ConfusionMatrixChart: React.FC<ConfusionMatrixChartProps> = ({
  matrix,
  labels,
  title = '混淆矩阵',
}) => {
  const [normalize, setNormalize] = useState<'raw' | 'row'>('raw');

  const displayMatrix = useMemo(() => {
    if (normalize === 'row') {
      return matrix.map(row => {
        const sum = row.reduce((a, b) => a + b, 0);
        return sum > 0 ? row.map(v => +(v / sum).toFixed(3)) : row;
      });
    }
    return matrix;
  }, [matrix, normalize]);

  const option = useMemo(() => {
    const data: Array<[number, number, number]> = [];
    for (let i = 0; i < displayMatrix.length; i++) {
      for (let j = 0; j < displayMatrix[i].length; j++) {
        data.push([j, i, displayMatrix[i][j]]);
      }
    }
    const maxVal = Math.max(...data.map(d => d[2]), 1);

    return {
      title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
      tooltip: {
        formatter: (params: any) => {
          const [x, y, val] = params.data;
          return `真实: ${labels[y]}<br/>预测: ${labels[x]}<br/>值: ${val}`;
        },
      },
      xAxis: {
        type: 'category',
        data: labels,
        name: '预测',
        nameLocation: 'center',
        nameGap: 30,
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: {
        type: 'category',
        data: labels,
        name: '真实',
        nameLocation: 'center',
        nameGap: 50,
        axisLabel: { fontSize: 10 },
      },
      visualMap: {
        min: 0,
        max: maxVal,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        inRange: { color: ['#f7f7f7', '#67a9cf', '#2166ac'] },
      },
      series: [{
        type: 'heatmap',
        data,
        label: {
          show: true,
          fontSize: 10,
          formatter: (params: any) => {
            const val = params.data[2];
            return normalize === 'row' ? `${(val * 100).toFixed(0)}%` : String(val);
          },
        },
      }],
      grid: { top: 40, bottom: 80, left: 80, right: 20 },
    };
  }, [displayMatrix, labels, title, normalize]);

  if (!matrix || matrix.length === 0) {
    return <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>无混淆矩阵数据</div>;
  }

  return (
    <div>
      <div style={{ textAlign: 'center', marginBottom: 8 }}>
        <Radio.Group size="small" value={normalize} onChange={e => setNormalize(e.target.value)}>
          <Radio.Button value="raw">原始计数</Radio.Button>
          <Radio.Button value="row">按行归一化</Radio.Button>
        </Radio.Group>
      </div>
      <ReactECharts option={option} style={{ height: 320 }} />
    </div>
  );
};

export default ConfusionMatrixChart;
// @AI_GENERATED: end
