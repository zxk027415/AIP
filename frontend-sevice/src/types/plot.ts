/**
 * 图表类型枚举
 */
export enum PlotType {
  LINE = 'LINE',
  SCATTER = 'SCATTER',
  SURFACE = 'SURFACE',
  HEATMAP = 'HEATMAP',
  BAR = 'BAR',
  HISTOGRAM = 'HISTOGRAM',
}

/**
 * 线条样式
 */
export enum LineStyle {
  SOLID = 'SOLID',
  DASHED = 'DASHED',
  DOTTED = 'DOTTED',
}

/**
 * 图表数据
 */
export interface PlotData {
  type: PlotType;
  x?: number[] | number[][];
  y?: number[] | number[][];
  z?: number[][];
  labels?: string[];
  series?: PlotSeries[];
}

/**
 * 图表系列数据
 */
export interface PlotSeries {
  name: string;
  data: number[] | number[][];
  type?: string;
  color?: string;
}

/**
 * 图表配置
 */
export interface PlotConfig {
  title?: string;
  xLabel?: string;
  yLabel?: string;
  zLabel?: string;
  colors?: string[];
  lineStyle?: LineStyle;
  width?: number;
  height?: number;
  legend?: boolean;
  grid?: boolean;
  tooltip?: boolean;
  animation?: boolean;
}

/**
 * 图表实例
 */
export interface Plot {
  id: string;
  data: PlotData;
  config: PlotConfig;
}

/**
 * ECharts选项类型（用于可视化节点）
 */
export interface ChartOptions {
  title?: {
    text?: string;
    subtext?: string;
  };
  tooltip?: any;
  legend?: any;
  xAxis?: any;
  yAxis?: any;
  series?: any[];
  grid?: any;
  color?: string[];
}
