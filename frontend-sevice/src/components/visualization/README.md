# 数据可视化组件

本目录包含基于ECharts的数据可视化组件，用于算法模板执行结果的可视化展示。

## 组件列表

### ChartContainer
图表容器组件，提供图表类型选择、配置和导出功能。

### LineChart
折线图组件，支持单系列和多系列数据。

### ScatterPlot
散点图组件，支持2D散点数据可视化。

### BarChart
柱状图组件，支持分类数据的柱状展示。

## 使用示例

### 基本用法

```tsx
import { ChartContainer, LineChart, ScatterPlot, BarChart } from '@/components/visualization';

// 折线图
<ChartContainer data={[1, 2, 3, 4, 5]}>
  <LineChart 
    data={[1, 2, 3, 4, 5]}
    config={{
      title: '温度变化',
      xAxisLabel: '时间',
      yAxisLabel: '温度(°C)',
      color: '#ff6b6b'
    }}
  />
</ChartContainer>

// 散点图
<ChartContainer data={[[1, 2], [3, 4], [5, 6]]}>
  <ScatterPlot 
    data={[[1, 2], [3, 4], [5, 6]]}
    config={{
      title: '数据分布',
      xAxisLabel: 'X',
      yAxisLabel: 'Y',
      pointSize: 12,
      color: '#4ecdc4'
    }}
  />
</ChartContainer>

// 柱状图
<ChartContainer data={[10, 20, 30, 40]}>
  <BarChart 
    data={[10, 20, 30, 40]}
    categories={['A', 'B', 'C', 'D']}
    config={{
      title: '销售数据',
      xAxisLabel: '产品',
      yAxisLabel: '销量',
      color: '#95e1d3'
    }}
  />
</ChartContainer>
```

### 多系列数据

```tsx
// 多系列折线图
<LineChart 
  data={[
    [1, 2, 3, 4, 5],
    [2, 4, 6, 8, 10],
    [1, 3, 5, 7, 9]
  ]}
  config={{
    title: '多组数据对比',
    showLegend: true
  }}
/>

// 多系列散点图
<ScatterPlot 
  data={[
    [[1, 2], [3, 4], [5, 6]],
    [[2, 3], [4, 5], [6, 7]]
  ]}
  config={{
    title: '分组散点',
    showLegend: true
  }}
/>

// 多系列柱状图
<BarChart 
  data={[
    [10, 20, 30],
    [15, 25, 35],
    [12, 22, 32]
  ]}
  categories={['Q1', 'Q2', 'Q3']}
  config={{
    title: '季度对比',
    showLegend: true
  }}
/>
```

## 配置选项

### ChartConfig

```typescript
interface ChartConfig {
  title?: string;          // 图表标题
  xAxisLabel?: string;     // X轴标签
  yAxisLabel?: string;     // Y轴标签
  color?: string;          // 主色调（单系列）
  pointSize?: number;      // 点大小（散点图）
  showLegend?: boolean;    // 显示图例
  showGrid?: boolean;      // 显示网格
}
```

## 功能特性

### 交互功能
- ✅ 缩放和平移
- ✅ 数据点悬停提示
- ✅ 区域缩放
- ✅ 数据视图
- ✅ 导出为PNG

### 响应式设计
- 自适应容器大小
- 最小高度350px
- 标签自动旋转（柱状图）

### 性能优化
- 懒加载更新
- 非合并模式渲染
- 高分辨率导出（2x）

## 在算法模板中使用

可视化节点会生成图表配置，前端接收后使用对应的图表组件渲染：

```tsx
// 算法模板执行结果
const executionResult = {
  nodeId: 'viz-1',
  output: {
    type: 'line',
    data: [1, 2, 3, 4, 5],
    config: {
      title: '结果可视化',
      xAxisLabel: 'Index',
      yAxisLabel: 'Value'
    }
  }
};

// 渲染
{executionResult.output.type === 'line' && (
  <LineChart 
    data={executionResult.output.data}
    config={executionResult.output.config}
  />
)}
```

## 依赖

- echarts: ^5.4.3
- echarts-for-react: ^3.0.2
- antd: ^5.12.0

## 注意事项

1. 确保数据格式正确，避免渲染错误
2. 大数据集可能影响性能，建议采样或分页
3. 导出功能依赖浏览器支持
4. 多系列数据需要保证每个系列长度一致（柱状图）
