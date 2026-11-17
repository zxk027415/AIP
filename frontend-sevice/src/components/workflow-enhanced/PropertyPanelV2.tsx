// @AI_GENERATED: Kiro v1.0
/**
 * Property Panel V2
 * 增强版属性面板 - 为 WorkflowEditorPage 设计
 * 根据不同的 functionId 显示丰富的配置项
 */

import React from 'react';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Button,
  Divider,
  Empty,
  Space,
  Tag,
  Tooltip,
  Slider,
  Alert,
  Typography,
  Collapse,
} from 'antd';
import {
  DeleteOutlined,
  SaveOutlined,
  CloseOutlined,
  InfoCircleOutlined,
  DatabaseOutlined,
  FunctionOutlined,
  LineChartOutlined,
  ExperimentOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useWorkflowEditorStore } from '../../stores/workflowEditorStore';
import type { EnhancedWorkflowNode } from '../../types/workflow-enhanced';
import { td } from '../../utils/dataTranslation';
import { datasetApi, type TrainableDatasetsByKind } from '../../services/workflowEnhancedApi';
import './PropertyPanelEnhanced.css';

const { TextArea } = Input;
const { Option } = Select;
const { Text } = Typography;

interface PropertyPanelV2Props {
  nodeId: string | null;
  /** 当前工作流 slot；仅 pv_day / pv_point 时加载可训数据下拉 */
  workflowSlot?: string;
}

// 数据集元数据（与后端 /api/upload/demo/datasets 保持一致）
const DATASET_METADATA: Record<string, {
  name: string;
  time_column: string;
  features: string[];
  target: string;
  available: boolean;
}> = {
  'pv-power-yinchuan': {
    name: '光伏发电功率 - 宁夏银川',
    time_column: 'timestamp',
    features: ['irradiance', 'temperature', 'humidity', 'wind_speed', 'cloud_cover'],
    target: 'power_actual',
    available: true,
  },
  'kaggle-solar-india': {
    name: 'Kaggle太阳能发电 - 印度',
    time_column: 'DATE_TIME',
    features: ['IRRADIATION', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'HOUR_SIN', 'HOUR_COS', 'TEMP_DIFF'],
    target: 'DC_POWER',
    available: true,
  },
  'wind-power-neimeng': {
    name: '风力发电功率 - 内蒙古',
    time_column: 'timestamp',
    features: ['wind_speed', 'wind_direction', 'temperature', 'pressure'],
    target: 'power_actual',
    available: false,
  },
  'load-forecast-huadong': {
    name: '负荷预测 - 华东电网',
    time_column: 'timestamp',
    features: ['temperature', 'humidity', 'day_of_week', 'hour', 'is_holiday'],
    target: 'load',
    available: false,
  },
  'equipment-fault-industrial': {
    name: '设备故障预测 - 工业园区',
    time_column: 'timestamp',
    features: ['vibration', 'temperature', 'pressure', 'current', 'rpm'],
    target: 'fault_label',
    available: false,
  },
};

// 函数配置元数据
const FUNCTION_CONFIGS: Record<string, {
  name: string;
  category: string;
  icon: React.ReactNode;
  description: string;
  params: Array<{
    key: string;
    label: string;
    type: 'string' | 'number' | 'select' | 'switch' | 'slider' | 'multiselect' | 'dynamic' | 'trainable_file_path';
    default?: any;
    options?: { label: string; value: any }[];
    min?: number;
    max?: number;
    step?: number;
    tooltip?: string;
    required?: boolean;
    dependsOn?: string; // 依赖的字段
  }>;
}> = {
  // 数据加载函数
  load_csv: {
    name: '加载CSV文件',
    category: '数据加载',
    icon: <DatabaseOutlined />,
    description: '从CSV文件加载数据，支持自定义分隔符和编码',
    params: [
      { key: 'file_path', label: '文件路径', type: 'trainable_file_path', tooltip: '从当前 slot 确认箱/累计版本选择，或手动填写相对路径' },
      { key: 'delimiter', label: '分隔符', type: 'select', default: ',', options: [
        { label: '逗号 (,)', value: ',' },
        { label: '制表符 (\\t)', value: '\t' },
        { label: '分号 (;)', value: ';' },
        { label: '空格', value: ' ' },
      ]},
      { key: 'encoding', label: '编码', type: 'select', default: 'utf-8', options: [
        { label: 'UTF-8', value: 'utf-8' },
        { label: 'GBK', value: 'gbk' },
        { label: 'GB2312', value: 'gb2312' },
        { label: 'ISO-8859-1', value: 'iso-8859-1' },
      ]},
    ],
  },
  load_labeled_dataset: {
    name: '加载确认箱/累计冻结版',
    category: '数据加载',
    icon: <DatabaseOutlined />,
    description: '按 dataset_id 加载 curated 确认箱或累计快照',
    params: [
      { key: 'dataset_id', label: '训练数据', type: 'trainable_file_path', tooltip: '优先选累计冻结版本' },
    ],
  },
  load_dataset: {
    name: '加载数据集',
    category: '数据加载',
    icon: <DatabaseOutlined />,
    description: '从系统数据集中选择并加载数据，自动推荐时间列，支持多选特征列',
    params: [
      // @AI_GENERATED: Kiro v1.0
      { key: 'dataset_id', label: '数据集', type: 'select', default: 'pv-power-yinchuan', required: true, options: [
        { label: '🟢 光伏发电功率 - 宁夏银川', value: 'pv-power-yinchuan' },
        { label: '🟢 Kaggle太阳能发电 - 印度', value: 'kaggle-solar-india' },
        { label: '⚪ 风力发电功率 - 内蒙古 (即将上线)', value: 'wind-power-neimeng' },
        { label: '⚪ 负荷预测 - 华东电网 (即将上线)', value: 'load-forecast-huadong' },
        { label: '⚪ 设备故障预测 - 工业园区 (即将上线)', value: 'equipment-fault-industrial' },
      ], tooltip: '选择要加载的数据集' },
      // @AI_GENERATED: end
      { key: 'time_column', label: '时间列', type: 'dynamic', dependsOn: 'dataset_id', tooltip: '根据数据集自动推荐' },
      { key: 'feature_columns', label: '特征列', type: 'dynamic', dependsOn: 'dataset_id', tooltip: '选择用于预测的特征列（可多选）' },
      { key: 'target_column', label: '目标列', type: 'dynamic', dependsOn: 'dataset_id', tooltip: '选择预测目标列' },
      { key: 'sample_rows', label: '采样行数', type: 'number', default: 0, min: 0, max: 100000, tooltip: '0表示加载全部数据' },
    ],
  },
  load_pv_demo: {
    name: '加载光伏示例数据',
    category: '数据加载',
    icon: <DatabaseOutlined />,
    description: '加载宁夏银川光伏电站示例数据（96条记录，15分钟间隔）',
    params: [],
  },
  
  // 数据处理函数
  handle_missing: {
    name: '缺失值处理',
    category: '数据处理',
    icon: <FunctionOutlined />,
    description: '处理数据中的缺失值，支持多种填充方法',
    params: [
      { key: 'method', label: '填充方法', type: 'select', default: 'interpolate', options: [
        { label: '插值法', value: 'interpolate' },
        { label: '前向填充', value: 'ffill' },
        { label: '后向填充', value: 'bfill' },
        { label: '均值填充', value: 'mean' },
        { label: '中位数填充', value: 'median' },
        { label: '零值填充', value: 'zero' },
      ], tooltip: '选择如何填充缺失值' },
    ],
  },
  resample_timeseries: {
    name: '时序重采样',
    category: '数据处理',
    icon: <FunctionOutlined />,
    description: '对时间序列数据进行重采样',
    params: [
      { key: 'frequency', label: '采样频率', type: 'select', default: '15min', options: [
        { label: '1分钟', value: '1min' },
        { label: '5分钟', value: '5min' },
        { label: '15分钟', value: '15min' },
        { label: '30分钟', value: '30min' },
        { label: '1小时', value: '1h' },
        { label: '1天', value: '1d' },
      ]},
      { key: 'aggregation', label: '聚合方式', type: 'select', default: 'mean', options: [
        { label: '平均值', value: 'mean' },
        { label: '求和', value: 'sum' },
        { label: '最大值', value: 'max' },
        { label: '最小值', value: 'min' },
        { label: '首值', value: 'first' },
        { label: '末值', value: 'last' },
      ]},
    ],
  },
  min_max_scale: {
    name: 'Min-Max归一化',
    category: '数据处理',
    icon: <FunctionOutlined />,
    description: '将数据缩放到指定范围（默认0-1）',
    params: [
      { key: 'feature_min', label: '最小值', type: 'number', default: 0, min: -100, max: 100, tooltip: '归一化后的最小值' },
      { key: 'feature_max', label: '最大值', type: 'number', default: 1, min: -100, max: 100, tooltip: '归一化后的最大值' },
    ],
  },
  z_score_scale: {
    name: 'Z-Score标准化',
    category: '数据处理',
    icon: <FunctionOutlined />,
    description: '使用Z-Score方法标准化数据（均值为0，标准差为1）',
    params: [],
  },
  train_test_split: {
    name: '训练测试集划分',
    category: '数据处理',
    icon: <FunctionOutlined />,
    description: '将数据划分为训练集和测试集',
    params: [
      { key: 'test_ratio', label: '测试集比例', type: 'slider', default: 0.2, min: 0.1, max: 0.5, step: 0.05, tooltip: '测试集占总数据的比例' },
      { key: 'shuffle', label: '随机打乱', type: 'switch', default: false, tooltip: '是否随机打乱数据（时序数据建议关闭）' },
    ],
  },
  
  // 预测模型函数
  xgboost_forecast: {
    name: 'XGBoost预测',
    category: '预测模型',
    icon: <ExperimentOutlined />,
    description: '使用XGBoost算法进行时序预测',
    params: [
      { key: 'n_estimators', label: '树的数量', type: 'number', default: 100, min: 10, max: 1000, tooltip: '集成的决策树数量' },
      { key: 'max_depth', label: '最大深度', type: 'number', default: 6, min: 1, max: 20, tooltip: '每棵树的最大深度' },
      { key: 'learning_rate', label: '学习率', type: 'slider', default: 0.1, min: 0.01, max: 1, step: 0.01, tooltip: '模型学习率' },
      { key: 'forecast_horizon', label: '预测步长', type: 'number', default: 4, min: 1, max: 96, tooltip: '向前预测的时间步数' },
    ],
  },
  linear_regression: {
    name: '线性回归',
    category: '预测模型',
    icon: <ExperimentOutlined />,
    description: '使用线性回归进行预测',
    params: [
      { key: 'fit_intercept', label: '拟合截距', type: 'switch', default: true, tooltip: '是否计算截距项' },
      { key: 'forecast_horizon', label: '预测步长', type: 'number', default: 4, min: 1, max: 96, tooltip: '向前预测的时间步数' },
    ],
  },
  
  // 评估函数
  mape_metric: {
    name: 'MAPE评估',
    category: '模型评估',
    icon: <BarChartOutlined />,
    description: '计算平均绝对百分比误差（MAPE）',
    params: [
      { key: 'ignore_zero', label: '忽略零值', type: 'switch', default: true, tooltip: '计算时忽略实际值为零的数据点' },
    ],
  },
  rmse_metric: {
    name: 'RMSE评估',
    category: '模型评估',
    icon: <BarChartOutlined />,
    description: '计算均方根误差（RMSE）',
    params: [],
  },
  r2_metric: {
    name: 'R²评估',
    category: '模型评估',
    icon: <BarChartOutlined />,
    description: '计算决定系数R²',
    params: [],
  },
  
  // 可视化函数
  forecast_plot: {
    name: '预测结果可视化',
    category: '可视化',
    icon: <LineChartOutlined />,
    description: '绘制实际值与预测值对比图',
    params: [
      { key: 'title', label: '图表标题', type: 'string', default: '预测结果对比', tooltip: '图表的标题' },
      { key: 'show_legend', label: '显示图例', type: 'switch', default: true },
      { key: 'smooth', label: '平滑曲线', type: 'switch', default: true, tooltip: '是否使用平滑曲线' },
      { key: 'line_width', label: '线条宽度', type: 'slider', default: 2, min: 1, max: 5, step: 0.5 },
    ],
  },
  line_chart: {
    name: '折线图',
    category: '可视化',
    icon: <LineChartOutlined />,
    description: '绘制折线图',
    params: [
      { key: 'title', label: '图表标题', type: 'string' },
      { key: 'x_label', label: 'X轴标签', type: 'string' },
      { key: 'y_label', label: 'Y轴标签', type: 'string' },
      { key: 'show_legend', label: '显示图例', type: 'switch', default: true },
      { key: 'smooth', label: '平滑曲线', type: 'switch', default: false },
    ],
  },
  scatter_plot: {
    name: '散点图',
    category: '可视化',
    icon: <LineChartOutlined />,
    description: '绘制散点图',
    params: [
      { key: 'title', label: '图表标题', type: 'string' },
      { key: 'x_column', label: 'X轴列', type: 'string' },
      { key: 'y_column', label: 'Y轴列', type: 'string' },
      { key: 'point_size', label: '点大小', type: 'slider', default: 5, min: 1, max: 20, step: 1 },
    ],
  },
  heatmap: {
    name: '热力图',
    category: '可视化',
    icon: <LineChartOutlined />,
    description: '绘制热力图（相关性矩阵等）',
    params: [
      { key: 'title', label: '图表标题', type: 'string' },
      { key: 'color_scheme', label: '配色方案', type: 'select', default: 'RdYlBu', options: [
        { label: '红黄蓝', value: 'RdYlBu' },
        { label: '蓝色', value: 'Blues' },
        { label: '红色', value: 'Reds' },
        { label: '绿色', value: 'Greens' },
      ]},
      { key: 'show_values', label: '显示数值', type: 'switch', default: true },
    ],
  },
  
  // 额外的预测模型
  random_forest: {
    name: '随机森林',
    category: '预测模型',
    icon: <ExperimentOutlined />,
    description: '使用随机森林进行预测',
    params: [
      { key: 'n_estimators', label: '树的数量', type: 'number', default: 100, min: 10, max: 500 },
      { key: 'max_depth', label: '最大深度', type: 'number', default: 10, min: 1, max: 30 },
      { key: 'min_samples_split', label: '最小分裂样本数', type: 'number', default: 2, min: 2, max: 20 },
      { key: 'forecast_horizon', label: '预测步长', type: 'number', default: 4, min: 1, max: 96 },
    ],
  },
  lstm_forecast: {
    name: 'LSTM预测',
    category: '预测模型',
    icon: <ExperimentOutlined />,
    description: '使用LSTM神经网络进行时序预测',
    params: [
      { key: 'hidden_size', label: '隐藏层大小', type: 'number', default: 64, min: 16, max: 512 },
      { key: 'num_layers', label: '层数', type: 'number', default: 2, min: 1, max: 5 },
      { key: 'dropout', label: 'Dropout比例', type: 'slider', default: 0.2, min: 0, max: 0.5, step: 0.05 },
      { key: 'epochs', label: '训练轮数', type: 'number', default: 100, min: 10, max: 1000 },
      { key: 'batch_size', label: '批次大小', type: 'number', default: 32, min: 8, max: 256 },
      { key: 'learning_rate', label: '学习率', type: 'slider', default: 0.001, min: 0.0001, max: 0.1, step: 0.0001 },
    ],
  },
  arima_forecast: {
    name: 'ARIMA预测',
    category: '预测模型',
    icon: <ExperimentOutlined />,
    description: '使用ARIMA模型进行时序预测',
    params: [
      { key: 'p', label: 'AR阶数(p)', type: 'number', default: 1, min: 0, max: 10, tooltip: '自回归阶数' },
      { key: 'd', label: '差分阶数(d)', type: 'number', default: 1, min: 0, max: 3, tooltip: '差分阶数' },
      { key: 'q', label: 'MA阶数(q)', type: 'number', default: 1, min: 0, max: 10, tooltip: '移动平均阶数' },
      { key: 'seasonal', label: '季节性', type: 'switch', default: false },
      { key: 'forecast_horizon', label: '预测步长', type: 'number', default: 4, min: 1, max: 96 },
    ],
  },
  
  // 额外的评估指标
  mae_metric: {
    name: 'MAE评估',
    category: '模型评估',
    icon: <BarChartOutlined />,
    description: '计算平均绝对误差（MAE）',
    params: [],
  },
  
  // 特征工程
  feature_select: {
    name: '特征选择',
    category: '特征工程',
    icon: <FunctionOutlined />,
    description: '选择最重要的特征',
    params: [
      { key: 'method', label: '选择方法', type: 'select', default: 'correlation', options: [
        { label: '相关性分析', value: 'correlation' },
        { label: '方差阈值', value: 'variance' },
        { label: '互信息', value: 'mutual_info' },
      ]},
      { key: 'n_features', label: '选择特征数', type: 'number', default: 10, min: 1, max: 100 },
      { key: 'threshold', label: '阈值', type: 'slider', default: 0.5, min: 0, max: 1, step: 0.05 },
    ],
  },
  pca_reduce: {
    name: 'PCA降维',
    category: '特征工程',
    icon: <FunctionOutlined />,
    description: '使用主成分分析进行降维',
    params: [
      { key: 'n_components', label: '主成分数量', type: 'number', default: 5, min: 1, max: 100, tooltip: '保留的主成分数量' },
      { key: 'variance_ratio', label: '方差解释比例', type: 'slider', default: 0.95, min: 0.5, max: 0.99, step: 0.01, tooltip: '保留的方差比例' },
    ],
  },
  lag_features: {
    name: '滞后特征',
    category: '特征工程',
    icon: <FunctionOutlined />,
    description: '创建时序滞后特征',
    params: [
      { key: 'lag_periods', label: '滞后期数', type: 'string', default: '1,2,3,4', tooltip: '逗号分隔的滞后期数' },
    ],
  },
  rolling_features: {
    name: '滚动窗口特征',
    category: '特征工程',
    icon: <FunctionOutlined />,
    description: '创建滚动窗口统计特征',
    params: [
      { key: 'window_size', label: '窗口大小', type: 'number', default: 4, min: 2, max: 100 },
      { key: 'statistics', label: '统计量', type: 'select', default: 'mean', options: [
        { label: '均值', value: 'mean' },
        { label: '标准差', value: 'std' },
        { label: '最大值', value: 'max' },
        { label: '最小值', value: 'min' },
      ]},
    ],
  },
  outlier_detection: {
    name: '异常值检测',
    category: '数据处理',
    icon: <FunctionOutlined />,
    description: '检测并处理数据中的异常值',
    params: [
      { key: 'method', label: '检测方法', type: 'select', default: 'zscore', options: [
        { label: 'Z-Score', value: 'zscore' },
        { label: 'IQR (四分位距)', value: 'iqr' },
        { label: 'Isolation Forest', value: 'iforest' },
      ]},
      { key: 'threshold', label: '阈值', type: 'number', default: 3, min: 1, max: 10, step: 0.5 },
      { key: 'action', label: '处理方式', type: 'select', default: 'clip', options: [
        { label: '截断', value: 'clip' },
        { label: '删除', value: 'remove' },
        { label: '替换为均值', value: 'mean' },
      ]},
    ],
  },
  
  // @AI_GENERATED: Kiro v1.0
  // ==================== 通用算法库函数（支持 Kaggle Solar 等场景）====================
  // 描述性统计 - 通用 descriptive_stats
  descriptive_stats: {
    name: '描述性统计',
    category: '数据处理',
    icon: <BarChartOutlined />,
    description: '计算数据的统计特征（均值、标准差、最大最小值等）',
    params: [],
  },
  // 相关性矩阵 - 通用 correlation_matrix
  correlation_matrix: {
    name: '相关系数矩阵',
    category: '数据处理',
    icon: <BarChartOutlined />,
    description: '计算变量间的相关系数矩阵',
    params: [],
  },
  // 时间特征提取 - 通用 extract_time_features
  extract_time_features: {
    name: '时间特征提取',
    category: '特征工程',
    icon: <FunctionOutlined />,
    description: '从时间列提取小时、星期、月份等时间特征',
    params: [
      { key: 'time_column', label: '时间列', type: 'string', default: 'DATE_TIME', tooltip: '时间戳列名' },
      { key: 'add_time_features', label: '添加时间特征', type: 'switch', default: true, tooltip: '添加小时、星期、月份等时间特征' },
      { key: 'add_cyclic_features', label: '添加周期特征', type: 'switch', default: true, tooltip: '添加正弦/余弦周期编码特征' },
    ],
  },
  // 周期编码 - 通用 cyclical_encode
  cyclical_encode: {
    name: '周期性编码',
    category: '特征工程',
    icon: <FunctionOutlined />,
    description: '使用sin/cos对周期性特征进行编码',
    params: [
      { key: 'column', label: '编码列', type: 'string', default: 'HOUR', tooltip: '需要周期编码的列名' },
      { key: 'period', label: '周期', type: 'number', default: 24, min: 1, max: 365, tooltip: '周期长度（如小时=24，月份=12）' },
    ],
  },
  // 随机森林回归 - 通用 random_forest_regression
  random_forest_regression: {
    name: '随机森林回归',
    category: '预测模型',
    icon: <ExperimentOutlined />,
    description: '训练随机森林回归模型',
    params: [
      { key: 'n_estimators', label: '树的数量', type: 'number', default: 20, min: 5, max: 100, tooltip: '集成的决策树数量' },
      { key: 'max_depth', label: '最大深度', type: 'number', default: 8, min: 2, max: 20, tooltip: '每棵树的最大深度' },
    ],
  },
  // XGBoost回归 - 通用 xgboost_regression
  xgboost_regression: {
    name: 'XGBoost回归',
    category: '预测模型',
    icon: <ExperimentOutlined />,
    description: '训练XGBoost梯度提升回归模型',
    params: [
      { key: 'n_estimators', label: '迭代次数', type: 'number', default: 100, min: 10, max: 500, tooltip: '弱学习器数量' },
      { key: 'learning_rate', label: '学习率', type: 'slider', default: 0.1, min: 0.01, max: 0.5, step: 0.01, tooltip: '每次迭代的步长' },
      { key: 'max_depth', label: '最大深度', type: 'number', default: 5, min: 1, max: 10, tooltip: '弱学习器的最大深度' },
    ],
  },
  // 回归评估指标 - 通用 regression_metrics
  regression_metrics: {
    name: '回归评估指标',
    category: '模型评估',
    icon: <BarChartOutlined />,
    description: '计算 RMSE, MAE, R², MAPE 等回归评估指标',
    params: [],
  },
  // @AI_GENERATED: end
};

// 获取分类颜色
const getCategoryColor = (category: string): string => {
  const colors: Record<string, string> = {
    '数据加载': 'blue',
    '数据处理': 'green',
    '特征工程': 'geekblue',
    '预测模型': 'purple',
    '模型评估': 'orange',
    '可视化': 'cyan',
  };
  return colors[category] || 'default';
};

// @AI_GENERATED: pv_tsc 作为第三个可训产品槽，纳入编辑器可训数据集选择白名单。
const PV_TRAINABLE_SLOTS = new Set(['pv_day', 'pv_point', 'pv_tsc']);
// @AI_GENERATED: end

const PropertyPanelV2: React.FC<PropertyPanelV2Props> = ({ nodeId, workflowSlot }) => {
  const { t } = useTranslation();
  const { nodes, updateNode, deleteNode } = useWorkflowEditorStore();
  const [form] = Form.useForm();
  const [hasChanges, setHasChanges] = React.useState(false);
  const [trainableDatasets, setTrainableDatasets] = React.useState<TrainableDatasetsByKind | null>(null);
  const [trainableLoading, setTrainableLoading] = React.useState(false);
  const [trainableError, setTrainableError] = React.useState<string | null>(null);

  const normalizedWorkflowSlot = React.useMemo(() => {
    const raw = String(workflowSlot || '').trim();
    return PV_TRAINABLE_SLOTS.has(raw) ? raw : '';
  }, [workflowSlot]);

  // 查找选中的节点
  const selectedNode = nodes.find((n) => n.id === nodeId) as EnhancedWorkflowNode | undefined;

  // 使用 ref 跟踪上一次的 nodeId 和原始数据
  const prevNodeIdRef = React.useRef<string | null>(null);
  const originalDataRef = React.useRef<any>(null);

  // 节点切换时重填表单；同一节点被 URL 预填改写 file_path/dataset_id 时也要同步
  React.useEffect(() => {
    if (!selectedNode) return;
    const formData = {
      label: selectedNode.data.label,
      description: selectedNode.data.description,
      ...selectedNode.data.config,
    };
    if (nodeId !== prevNodeIdRef.current) {
      prevNodeIdRef.current = nodeId;
      setHasChanges(false);
      form.setFieldsValue(formData);
      originalDataRef.current = formData;
      return;
    }
    const storePath = String(selectedNode.data.config?.file_path || '');
    const storeDatasetId = String(selectedNode.data.config?.dataset_id || '');
    const formPath = String(form.getFieldValue('file_path') || '');
    const formDatasetId = String(form.getFieldValue('dataset_id') || '');
    if ((storePath && storePath !== formPath) || (storeDatasetId && storeDatasetId !== formDatasetId)) {
      form.setFieldsValue({
        file_path: storePath || formPath,
        dataset_id: storeDatasetId || formDatasetId,
        trainable_file_path: storePath || formPath,
      });
    }
  }, [nodeId, selectedNode, form]);

  React.useEffect(() => {
    const functionId = selectedNode?.data?.config?.functionId;
    if ((functionId !== 'load_csv' && functionId !== 'load_labeled_dataset') || !normalizedWorkflowSlot) {
      setTrainableDatasets(null);
      setTrainableError(null);
      setTrainableLoading(false);
      return;
    }

    let cancelled = false;
    setTrainableLoading(true);
    setTrainableError(null);
    datasetApi
      .listTrainable(normalizedWorkflowSlot)
      .then((resp) => {
        if (cancelled) return;
        if (resp?.success && resp.data) {
          setTrainableDatasets(resp.data);
        } else {
          setTrainableDatasets({ labeled_versions: [], cumulative_snapshots: [] });
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTrainableDatasets({ labeled_versions: [], cumulative_snapshots: [] });
        setTrainableError(err instanceof Error ? err.message : '加载可训练数据失败');
      })
      .finally(() => {
        if (!cancelled) setTrainableLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedNode?.data?.config?.functionId, normalizedWorkflowSlot]);

  const handleTrainableDatasetPick = (datasetId: string) => {
    if (!trainableDatasets) return;
    const allRows = [
      ...trainableDatasets.labeled_versions,
      ...trainableDatasets.cumulative_snapshots,
    ];
    const row = allRows.find((item) => item.dataset_id === datasetId);
    if (!row) return;
    form.setFieldsValue({
      file_path: row.file_path,
      dataset_id: row.dataset_id,
    });
    setHasChanges(true);
  };

  const renderTrainableFilePathField = (param: typeof FUNCTION_CONFIGS[string]['params'][0]) => {
    const labeled = trainableDatasets?.labeled_versions || [];
    const cumulative = trainableDatasets?.cumulative_snapshots || [];
    const formatLabel = (row: { dataset_id: string; name?: string; is_latest?: boolean }) => {
      const base = row.name || row.dataset_id;
      return row.is_latest ? `${base}（最新）` : base;
    };

    return (
      <React.Fragment key={param.key}>
        {!normalizedWorkflowSlot ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="当前工作流未设置 pv_day / pv_point slot"
            description="请使用带 slot 的 PV 训练/评估模板，或先在模板元数据中指定 slot，再从此处选择确认箱或累计训练数据。"
          />
        ) : (
          <>
            {trainableError && (
              <Alert type="warning" showIcon message={trainableError} style={{ marginBottom: 12 }} />
            )}
            <Form.Item name="dataset_id" label="训练数据">
              <Select
                allowClear
                showSearch
                loading={trainableLoading}
                placeholder="优先选择累计训练冻结版本"
                optionFilterProp="label"
                onChange={(value) => {
                  if (value) handleTrainableDatasetPick(String(value));
                }}
                options={[
                  ...(cumulative.length > 0
                    ? [{
                        label: '累计训练（优先）',
                        options: cumulative.map((row) => ({
                          label: formatLabel(row),
                          value: row.dataset_id,
                        })),
                      }]
                    : []),
                  ...(labeled.length > 0
                    ? [{
                        label: '确认箱（单批，不优先）',
                        options: labeled.map((row) => ({
                          label: formatLabel(row),
                          value: row.dataset_id,
                        })),
                      }]
                    : []),
                ]}
              />
            </Form.Item>
          </>
        )}
        <Form.Item
          name="file_path"
          label={
            <Space>
              {td(param.label)}
              {param.tooltip && (
                <Tooltip title={td(param.tooltip)}>
                  <InfoCircleOutlined style={{ color: '#999' }} />
                </Tooltip>
              )}
            </Space>
          }
        >
          <Input placeholder="相对 backend-service/ 或项目根路径" />
        </Form.Item>
      </React.Fragment>
    );
  };

  // 处理表单值变化
  const handleValuesChange = () => {
    setHasChanges(true);
  };

  // 保存修改
  const handleSave = () => {
    if (!selectedNode) return;

    const allValues = form.getFieldsValue();
    const { label, description, ...config } = allValues;
    
    updateNode(selectedNode.id, {
      label: label || selectedNode.data.label,
      description: description || selectedNode.data.description,
      config: { ...selectedNode.data.config, ...config },
    });

    originalDataRef.current = allValues;
    setHasChanges(false);
  };

  // 取消修改
  const handleCancel = () => {
    if (originalDataRef.current) {
      form.setFieldsValue(originalDataRef.current);
      setHasChanges(false);
    }
  };

  // 处理删除节点
  const handleDelete = () => {
    if (selectedNode) {
      deleteNode(selectedNode.id);
    }
  };

  // 如果没有选中节点
  if (!selectedNode) {
    return (
      <Card title={t('workflowEditor.property.nodeAttributes')} className="property-panel-enhanced">
        <Empty 
          description={t('workflowEditor.property.selectNodeHint')} 
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ padding: '40px 0' }}
        />
      </Card>
    );
  }

  // 获取函数配置
  const functionId = selectedNode.data.config?.functionId;
  const funcConfig = functionId ? FUNCTION_CONFIGS[functionId] : null;
  
  // 获取当前选中的数据集ID
  const currentDatasetId = Form.useWatch('dataset_id', form) || selectedNode.data.config?.dataset_id || 'pv-power-yinchuan';
  const datasetMeta = DATASET_METADATA[currentDatasetId];

  // 渲染参数表单项
  const renderParamField = (param: typeof FUNCTION_CONFIGS[string]['params'][0]) => {
    const commonProps = {
      key: param.key,
      name: param.key,
      label: (
        <Space>
          {td(param.label)}
          {param.tooltip && (
            <Tooltip title={td(param.tooltip)}>
              <InfoCircleOutlined style={{ color: '#999' }} />
            </Tooltip>
          )}
        </Space>
      ),
      rules: param.required ? [{ required: true, message: t('workflowEditor.property.pleaseEnter', { field: td(param.label) }) }] : undefined,
    };

    // 处理动态字段（依赖数据集选择）
    if (param.type === 'dynamic' && param.dependsOn === 'dataset_id') {
      if (param.key === 'time_column') {
        // 时间列：自动推荐，显示为带推荐标记的选择框
        return (
          <Form.Item {...commonProps}>
            <Select 
              placeholder={t('workflowEditor.property.selectTimeColumn')}
              suffixIcon={datasetMeta ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : undefined}
            >
              <Option value={datasetMeta?.time_column || 'timestamp'}>
                <Space>
                  {datasetMeta?.time_column || 'timestamp'}
                  <Tag color="green" style={{ marginLeft: 4 }}>{t('workflowEditor.property.recommendedTag')}</Tag>
                </Space>
              </Option>
            </Select>
          </Form.Item>
        );
      }
      
      if (param.key === 'feature_columns') {
        // 特征列：多选
        const featureOptions = datasetMeta?.features || [];
        return (
          <Form.Item {...commonProps}>
            <Select
              mode="multiple"
              placeholder={t('workflowEditor.property.selectFeatureColumns')}
              maxTagCount={3}
              allowClear
              defaultValue={featureOptions}
            >
              {featureOptions.map((feat) => (
                <Option key={feat} value={feat}>{feat}</Option>
              ))}
            </Select>
          </Form.Item>
        );
      }
      
      if (param.key === 'target_column') {
        // 目标列：单选，从数据集元数据获取推荐值
        return (
          <Form.Item {...commonProps}>
            <Select placeholder={t('workflowEditor.property.selectTargetColumn')}>
              {datasetMeta && (
                <Option value={datasetMeta.target}>
                  <Space>
                    {datasetMeta.target}
                    <Tag color="blue" style={{ marginLeft: 4 }}>{t('workflowEditor.property.recommendedTag')}</Tag>
                  </Space>
                </Option>
              )}
              {datasetMeta?.features.map((feat) => (
                <Option key={feat} value={feat}>{feat}</Option>
              ))}
            </Select>
          </Form.Item>
        );
      }
    }

    switch (param.type) {
      case 'trainable_file_path':
        return renderTrainableFilePathField(param);
      case 'string':
        return (
          <Form.Item {...commonProps}>
            <Input placeholder={t('workflowEditor.property.pleaseEnter', { field: td(param.label) })} />
          </Form.Item>
        );
      case 'number':
        return (
          <Form.Item {...commonProps}>
            <InputNumber
              style={{ width: '100%' }}
              min={param.min}
              max={param.max}
              step={param.step || 1}
              placeholder={param.default?.toString()}
            />
          </Form.Item>
        );
      case 'select':
        return (
          <Form.Item {...commonProps}>
            <Select placeholder={t('workflowEditor.property.pleaseSelect', { field: td(param.label) })}>
              {param.options?.map((opt) => (
                <Option key={opt.value} value={opt.value}>
                  {td(opt.label)}
                </Option>
              ))}
            </Select>
          </Form.Item>
        );
      case 'switch':
        return (
          <Form.Item {...commonProps} valuePropName="checked">
            <Switch />
          </Form.Item>
        );
      case 'slider':
        return (
          <Form.Item {...commonProps}>
            <Slider
              min={param.min}
              max={param.max}
              step={param.step}
              marks={{
                [param.min || 0]: param.min?.toString(),
                [param.max || 1]: param.max?.toString(),
              }}
            />
          </Form.Item>
        );
      default:
        return null;
    }
  };

  // 渲染配置表单
  const renderConfigForm = () => {
    if (!funcConfig) {
      return (
        <Alert
          message={t('workflowEditor.property.unknownFunction')}
          description={t('workflowEditor.property.unknownFunctionDesc', { id: functionId || t('workflowEditor.property.notSet') })}
          type="warning"
          showIcon
        />
      );
    }

    if (funcConfig.params.length === 0) {
      return (
        <Alert
          message={t('workflowEditor.property.noConfigNeeded')}
          description={t('workflowEditor.property.noConfigDesc')}
          type="info"
          showIcon
        />
      );
    }

    // 对于 load_dataset，显示数据集可用性提示
    if (functionId === 'load_dataset' && datasetMeta && !datasetMeta.available) {
      return (
        <>
          <Alert
            message={t('workflowEditor.property.datasetOffline')}
            description={t('workflowEditor.property.datasetOfflineDesc')}
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
          />
          {funcConfig.params.map(renderParamField)}
        </>
      );
    }

    return funcConfig.params.map(renderParamField);
  };

  return (
    <Card 
      title={
        <Space>
          <span>{t('workflowEditor.property.nodeConfig')}</span>
          {funcConfig && (
            <Tag color={getCategoryColor(funcConfig.category)}>
              {td(funcConfig.category)}
            </Tag>
          )}
        </Space>
      }
      className="property-panel-enhanced"
      extra={
        <Button 
          type="text" 
          danger 
          size="small"
          icon={<DeleteOutlined />}
          onClick={handleDelete}
        >
          {t('workflowEditor.property.delete')}
        </Button>
      }
    >
      <div className="property-panel-content">
        <Form
          form={form}
          layout="vertical"
          onValuesChange={handleValuesChange}
          size="small"
        >
          {/* 函数信息 */}
          {funcConfig && (
            <div className="property-section" style={{ marginBottom: 16 }}>
              <Space align="start">
                <span style={{ fontSize: 20 }}>{funcConfig.icon}</span>
                <div>
                  <Text strong>{td(funcConfig.name)}</Text>
                  <br />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {td(funcConfig.description)}
                  </Text>
                </div>
              </Space>
            </div>
          )}

          <Divider style={{ margin: '12px 0' }} />

          {/* 基本信息 */}
          <Collapse
            defaultActiveKey={['basic', 'config']}
            ghost
            items={[
              {
                key: 'basic',
                label: t('workflowEditor.property.basicInfo'),
                children: (
                  <>
                    <Form.Item label={t('workflowEditor.property.nodeName')} name="label">
                      <Input placeholder={t('workflowEditor.property.nodeName')} />
                    </Form.Item>
                    <Form.Item label={t('workflowEditor.property.nodeDesc')} name="description">
                      <TextArea 
                        rows={2} 
                        placeholder={t('workflowEditor.property.nodeDesc')}
                      />
                    </Form.Item>
                    <Form.Item label={t('workflowEditor.property.functionId')}>
                      <Input value={functionId || t('workflowEditor.property.notSet')} disabled />
                    </Form.Item>
                  </>
                ),
              },
              {
                key: 'config',
                label: t('workflowEditor.property.paramConfig'),
                children: renderConfigForm(),
              },
              {
                key: 'ports',
                label: t('workflowEditor.property.portsInfo', { in: selectedNode.data.inputs.length, out: selectedNode.data.outputs.length }),
                children: (
                  <div className="property-ports">
                    {selectedNode.data.inputs.length > 0 && (
                      <div className="property-ports-group">
                        <div className="property-ports-label">
                          <Tag color="blue">{t('workflowEditor.property.inputPorts')}</Tag>
                        </div>
                        {selectedNode.data.inputs.map((input: any) => (
                          <div key={input.id} className="property-port-item">
                            <span className="property-port-name">{td(input.name)}</span>
                            <Tag>{input.dataType}</Tag>
                            {input.required && <Tag color="red">{t('workflowEditor.property.required')}</Tag>}
                          </div>
                        ))}
                      </div>
                    )}
                    {selectedNode.data.outputs.length > 0 && (
                      <div className="property-ports-group" style={{ marginTop: 8 }}>
                        <div className="property-ports-label">
                          <Tag color="green">{t('workflowEditor.property.outputPorts')}</Tag>
                        </div>
                        {selectedNode.data.outputs.map((output: any) => (
                          <div key={output.id} className="property-port-item">
                            <span className="property-port-name">{td(output.name)}</span>
                            <Tag>{output.dataType}</Tag>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </Form>
      </div>

      {/* 保存/取消按钮 */}
      {hasChanges && (
        <div className="property-actions-footer">
          <Space>
            <Button 
              icon={<CloseOutlined />}
              onClick={handleCancel}
              size="small"
            >
              {t('workflowEditor.property.cancel')}
            </Button>
            <Button 
              type="primary" 
              icon={<SaveOutlined />}
              onClick={handleSave}
              size="small"
            >
              {t('workflowEditor.property.save')}
            </Button>
          </Space>
        </div>
      )}
    </Card>
  );
};

export default PropertyPanelV2;
// @AI_GENERATED: end
