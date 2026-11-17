// @AI_GENERATED: Kiro v1.0
/**
 * 基础算法模块分类数据
 * 数据来源：docs/algorithm-library-split.md 第一部分
 * 763个基础模块，18个技术分类，6个技术层级
 */

export interface BasicModuleCategory {
  id: string;
  name: string;
  icon: string;
  description: string;
  layer: string;
  layerColor: string;
  functionCount: number;
  subCategories: string[];
}

export interface LayerInfo {
  name: string;
  color: string;
  functionCount: number;
}

export const LAYERS: LayerInfo[] = [
  { name: '数据管理层', color: '#1890ff', functionCount: 46 },
  { name: '数据处理层', color: '#52c41a', functionCount: 156 },
  { name: '算法模型层', color: '#722ed1', functionCount: 331 },
  { name: '基础计算层', color: '#fa8c16', functionCount: 45 },
  { name: 'MLOps层', color: '#eb2f96', functionCount: 120 },
  { name: '输出展示层', color: '#13c2c2', functionCount: 71 },
];

export const BASIC_MODULE_CATEGORIES: BasicModuleCategory[] = [
  {
    id: 'data_source',
    name: '数据源',
    icon: '📡',
    description: '通用数据接入能力，支持CSV/Excel/数据库/MQTT/OPC UA等多种数据源',
    layer: '数据管理层',
    layerColor: '#1890ff',
    functionCount: 40,
    subCategories: ['文件读取', '数据库连接', '实时数据订阅', '工业协议接入'],
  },
  {
    id: 'dataset_management',
    name: '数据集管理',
    icon: '📦',
    description: '数据集划分、版本管理、特征仓库等数据组织能力',
    layer: '数据管理层',
    layerColor: '#1890ff',
    functionCount: 6,
    subCategories: ['数据集划分', '版本管理', '特征仓库'],
  },
  {
    id: 'data_preprocessing',
    name: '数据预处理',
    icon: '🧹',
    description: '通用数据清洗/变换/质量评估能力',
    layer: '数据处理层',
    layerColor: '#52c41a',
    functionCount: 74,
    subCategories: ['缺失值处理', '异常值检测', '数据标准化', '标准化与缩放', '数据变换', '质量评估'],
  },
  {
    id: 'feature_engineering',
    name: '特征工程',
    icon: '🔧',
    description: '通用特征提取/选择/降维能力',
    layer: '数据处理层',
    layerColor: '#52c41a',
    functionCount: 82,
    subCategories: ['特征提取', '特征选择', '降维', '时序特征', '交叉特征'],
  },
  {
    id: 'ts_forecast',
    name: '时序预测',
    icon: '📈',
    description: '经典统计模型、机器学习、深度学习时序预测算法',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 54,
    subCategories: ['经典统计模型', '机器学习模型', '深度学习模型', '集成与专用模型'],
  },
  {
    id: 'anomaly_detection',
    name: '异常检测',
    icon: '🔍',
    description: '统计方法、机器学习、深度学习异常检测算法',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 32,
    subCategories: ['统计方法', '机器学习方法', '深度学习方法'],
  },
  {
    id: 'classification',
    name: '分类识别',
    icon: '🏷️',
    description: '经典分类算法与深度学习分类模型',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 28,
    subCategories: ['经典分类算法', '深度学习与特殊分类'],
  },
  {
    id: 'regression',
    name: '回归分析',
    icon: '📊',
    description: '通用回归建模能力，线性/非线性/正则化回归',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 35,
    subCategories: ['线性回归', '非线性回归', '正则化回归', '集成回归'],
  },
  {
    id: 'clustering',
    name: '聚类分析',
    icon: '🎯',
    description: '经典聚类与时序聚类/模式发现算法',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 22,
    subCategories: ['经典聚类', '时序聚类与模式发现'],
  },
  {
    id: 'deep_learning',
    name: '深度学习',
    icon: '🧠',
    description: '基础网络架构、生成模型、迁移学习、图神经网络、强化学习等',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 62,
    subCategories: ['基础网络架构', '生成模型', '迁移学习', '图神经网络', '强化学习', '模型解释', '训练技巧', 'NLP与文本模型'],
  },
  {
    id: 'industrial_vision',
    name: '工业视觉',
    icon: '👁️',
    description: '通用图像处理能力，图像增强/变换/滤波/形态学操作',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 24,
    subCategories: ['图像增强', '图像变换', '滤波处理', '形态学操作', '目标检测与分割'],
  },
  {
    id: 'signal_processing',
    name: '信号处理',
    icon: '📻',
    description: '频域分析、时频分析、滤波与信号处理、振动分析',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 43,
    subCategories: ['频域分析', '时频分析', '滤波与信号处理', '振动分析'],
  },
  {
    id: 'optimization',
    name: '优化算法',
    icon: '⚙️',
    description: '数学优化与智能优化算法',
    layer: '算法模型层',
    layerColor: '#722ed1',
    functionCount: 31,
    subCategories: ['数学优化', '智能优化算法', '工业控制与仿真'],
  },
  {
    id: 'math_statistics',
    name: '数学与统计',
    icon: '🔢',
    description: '基础数学/统计计算能力，概率分布、假设检验、矩阵运算',
    layer: '基础计算层',
    layerColor: '#fa8c16',
    functionCount: 45,
    subCategories: ['概率分布', '假设检验', '矩阵运算', '数值计算', '统计分析'],
  },
  {
    id: 'model_training',
    name: '模型训练',
    icon: '🏋️',
    description: '通用训练/调优/实验管理能力',
    layer: 'MLOps层',
    layerColor: '#eb2f96',
    functionCount: 40,
    subCategories: ['训练框架', '超参调优', '实验管理', '分布式训练'],
  },
  {
    id: 'model_deployment',
    name: '模型部署',
    icon: '🚀',
    description: '通用部署/监控/运维能力',
    layer: 'MLOps层',
    layerColor: '#eb2f96',
    functionCount: 32,
    subCategories: ['模型导出', '推理服务', '模型监控', '版本管理'],
  },
  {
    id: 'evaluation_metrics',
    name: '评估指标',
    icon: '📏',
    description: '通用评估/对比能力，回归/分类/聚类/时序评估指标',
    layer: 'MLOps层',
    layerColor: '#eb2f96',
    functionCount: 48,
    subCategories: ['回归指标', '分类指标', '聚类指标', '时序指标', '模型对比', '工业模板评估指标'],
  },
  {
    id: 'visualization',
    name: '可视化',
    icon: '📉',
    description: '基础图表与高级图表可视化能力',
    layer: '输出展示层',
    layerColor: '#13c2c2',
    functionCount: 34,
    subCategories: ['基础图表', '高级图表', '工业可视化', '仪表盘与报告'],
  },
  {
    id: 'data_output',
    name: '数据输出',
    icon: '💾',
    description: '通用数据输出能力，文件导出/数据库写入/API推送',
    layer: '输出展示层',
    layerColor: '#13c2c2',
    functionCount: 37,
    subCategories: ['文件导出', '数据库写入', 'API推送', '报告生成'],
  },
];
// @AI_GENERATED: end
