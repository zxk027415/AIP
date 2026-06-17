// @AI_GENERATED
/**
 * Fix auto-generated translations that still contain Chinese characters
 * Replaces remaining Chinese with reasonable English equivalents
 */
const fs = require('fs');
const path = require('path');

const transFile = path.join(__dirname, '..', 'src', 'utils', 'dataTranslation.ts');
let content = fs.readFileSync(transFile, 'utf8');

// Find all entries that have Chinese in the VALUE (right side)
const hasChinese = /[\u4e00-\u9fff]/;
const entryRegex = /  '([^']+)':\s*'([^']+)',/g;
let match;
let fixes = 0;
const replacements = [];

while ((match = entryRegex.exec(content)) !== null) {
  const [fullMatch, key, value] = match;
  if (hasChinese.test(value) && key !== value) {
    // Value still has Chinese - needs fixing
    // For these, just use the key as-is (td() will return the Chinese in zh mode)
    // In English mode, showing the function ID is better than broken translation
    replacements.push({ from: fullMatch, key, value });
    fixes++;
  }
}

console.log(`Found ${fixes} entries with Chinese in values that need fixing`);

// Better translation approach: word-by-word replacement with comprehensive dictionary
const dict = {
  // Protocols & Standards
  '协议': ' Protocol', '总线': ' Bus', '接口': ' Interface', '通信': ' Communication',
  '串口': 'Serial', '以太网': 'Ethernet', '无线': 'Wireless', '蓝牙': 'Bluetooth',
  
  // Data operations
  '加载': 'Loading', '读取': 'Reading', '写入': 'Writing', '导入': 'Import', '导出': 'Export',
  '连接': 'Connection', '接入': 'Access', '查询': 'Query', '订阅': 'Subscription',
  '推送': 'Push', '存储': 'Storage', '缓存': 'Cache', '索引': 'Index',
  '解析': 'Parsing', '序列化': 'Serialization', '反序列化': 'Deserialization',
  
  // Data processing
  '处理': 'Processing', '变换': 'Transform', '转换': 'Conversion', '映射': 'Mapping',
  '填充': 'Filling', '清洗': 'Cleaning', '去重': 'Deduplication', '合并': 'Merging',
  '拆分': 'Splitting', '排序': 'Sorting', '过滤': 'Filtering', '聚合': 'Aggregation',
  '分组': 'Grouping', '透视': 'Pivot', '重塑': 'Reshaping', '展平': 'Flattening',
  '标准化': 'Normalization', '归一化': 'Normalization', '缩放': 'Scaling',
  '编码': 'Encoding', '解码': 'Decoding', '哈希': 'Hashing',
  '插值': 'Interpolation', '外推': 'Extrapolation', '拟合': 'Fitting',
  '平滑': 'Smoothing', '去噪': 'Denoising', '降噪': 'Noise Reduction',
  '采样': 'Sampling', '重采样': 'Resampling', '过采样': 'Oversampling', '欠采样': 'Undersampling',
  '补全': 'Completion', '修复': 'Repair', '校正': 'Correction', '对齐': 'Alignment',
  
  // Feature engineering
  '特征': 'Feature', '提取': 'Extraction', '选择': 'Selection', '降维': 'Reduction',
  '嵌入': 'Embedding', '表示': 'Representation', '编码器': 'Encoder',
  '滞后': 'Lag', '差分': 'Differencing', '滚动': 'Rolling', '窗口': 'Window',
  '移动平均': 'Moving Average', '指数平滑': 'Exponential Smoothing',
  '傅里叶': 'Fourier', '小波': 'Wavelet', '频谱': 'Spectrum', '频域': 'Frequency Domain',
  '时频': 'Time-Frequency', '包络': 'Envelope', '倒谱': 'Cepstrum',
  '自相关': 'Autocorrelation', '互相关': 'Cross-correlation',
  '峰值': 'Peak', '谷值': 'Valley', '峰谷': 'Peak-Valley',
  '趋势': 'Trend', '季节性': 'Seasonality', '周期': 'Periodicity',
  '交叉': 'Cross', '组合': 'Combined', '多项式': 'Polynomial',
  '独热': 'One-Hot', '标签': 'Label', '目标': 'Target', '序数': 'Ordinal',
  '分箱': 'Binning', '离散化': 'Discretization', '二值化': 'Binarization',
  
  // Statistics
  '统计': 'Statistical', '概率': 'Probability', '分布': 'Distribution',
  '假设检验': 'Hypothesis Test', '显著性': 'Significance',
  '相关性': 'Correlation', '协方差': 'Covariance', '方差': 'Variance',
  '均值': 'Mean', '中位数': 'Median', '众数': 'Mode',
  '分位数': 'Quantile', '百分位': 'Percentile', '偏度': 'Skewness', '峰度': 'Kurtosis',
  '正态': 'Normal', '泊松': 'Poisson', '指数': 'Exponential', '均匀': 'Uniform',
  '卡方': 'Chi-Square', 'T检验': 'T-Test', 'F检验': 'F-Test', 'Z检验': 'Z-Test',
  'KS检验': 'KS Test', 'ANOVA': 'ANOVA',
  '矩阵': 'Matrix', '向量': 'Vector', '张量': 'Tensor',
  '特征值': 'Eigenvalue', '特征向量': 'Eigenvector', '奇异值': 'Singular Value',
  '逆矩阵': 'Inverse Matrix', '行列式': 'Determinant', '秩': 'Rank',
  '范数': 'Norm', '内积': 'Inner Product', '外积': 'Outer Product',
  '分解': 'Decomposition', '因式': 'Factorization',
  '积分': 'Integration', '微分': 'Differentiation', '求解': 'Solving',
  '最优化': 'Optimization', '梯度': 'Gradient', '海森': 'Hessian',
  '雅可比': 'Jacobian', '拉格朗日': 'Lagrange', '牛顿': 'Newton',
  '蒙特卡洛': 'Monte Carlo', '马尔可夫': 'Markov',
  '随机': 'Random', '伪随机': 'Pseudo-random', '种子': 'Seed',
  
  // ML/DL models
  '模型': 'Model', '算法': 'Algorithm', '网络': 'Network', '架构': 'Architecture',
  '层': 'Layer', '节点': 'Node', '权重': 'Weight', '偏置': 'Bias',
  '激活': 'Activation', '损失': 'Loss', '优化器': 'Optimizer',
  '学习率': 'Learning Rate', '批量': 'Batch', '轮次': 'Epoch',
  '过拟合': 'Overfitting', '欠拟合': 'Underfitting', '正则化': 'Regularization',
  '丢弃': 'Dropout', '批归一化': 'Batch Normalization',
  '卷积': 'Convolution', '池化': 'Pooling', '全连接': 'Fully Connected',
  '循环': 'Recurrent', '注意力': 'Attention', '自注意力': 'Self-Attention',
  '变换器': 'Transformer', '编码器': 'Encoder', '解码器': 'Decoder',
  '生成': 'Generation', '判别': 'Discriminator', '对抗': 'Adversarial',
  '自编码器': 'Autoencoder', '变分': 'Variational',
  '图神经': 'Graph Neural', '图卷积': 'Graph Convolution',
  '强化': 'Reinforcement', '策略': 'Policy', '价值': 'Value', '奖励': 'Reward',
  '迁移': 'Transfer', '微调': 'Fine-tuning', '预训练': 'Pre-training',
  '蒸馏': 'Distillation', '剪枝': 'Pruning', '量化': 'Quantization',
  '集成': 'Ensemble', '堆叠': 'Stacking', '投票': 'Voting', '装袋': 'Bagging',
  '提升': 'Boosting', '梯度提升': 'Gradient Boosting',
  '随机森林': 'Random Forest', '决策树': 'Decision Tree',
  '支持向量机': 'SVM', '支持向量': 'Support Vector',
  '贝叶斯': 'Bayesian', '朴素贝叶斯': 'Naive Bayes',
  '高斯': 'Gaussian', '核密度': 'Kernel Density', '核函数': 'Kernel',
  '主成分': 'PCA', '独立成分': 'ICA', '线性判别': 'LDA',
  '聚类': 'Clustering', '分类': 'Classification', '回归': 'Regression',
  '预测': 'Prediction', '推理': 'Inference', '检测': 'Detection',
  '分割': 'Segmentation', '识别': 'Recognition', '跟踪': 'Tracking',
  '异常': 'Anomaly', '离群': 'Outlier', '新奇': 'Novelty',
  
  // Time series
  '时序': 'Time Series', '序列': 'Sequence', '时间': 'Time',
  'ARIMA': 'ARIMA', 'SARIMA': 'SARIMA', 'LSTM': 'LSTM', 'GRU': 'GRU',
  'Prophet': 'Prophet', 'N-BEATS': 'N-BEATS', 'DeepAR': 'DeepAR',
  'Informer': 'Informer', 'Autoformer': 'Autoformer',
  
  // Image processing
  '图像': 'Image', '视觉': 'Vision', '像素': 'Pixel',
  '增强': 'Enhancement', '锐化': 'Sharpening', '模糊': 'Blurring',
  '边缘': 'Edge', '轮廓': 'Contour', '形态学': 'Morphological',
  '腐蚀': 'Erosion', '膨胀': 'Dilation', '开运算': 'Opening', '闭运算': 'Closing',
  '直方图': 'Histogram', '均衡化': 'Equalization', '阈值': 'Threshold',
  '仿射': 'Affine', '透视': 'Perspective', '旋转': 'Rotation',
  '翻转': 'Flip', '裁剪': 'Crop', '缩放': 'Resize', '填充': 'Padding',
  '目标检测': 'Object Detection', '语义分割': 'Semantic Segmentation',
  '实例分割': 'Instance Segmentation', '全景分割': 'Panoptic Segmentation',
  
  // Signal processing
  '信号': 'Signal', '振动': 'Vibration', '声学': 'Acoustic', '声音': 'Sound',
  '带通': 'Bandpass', '低通': 'Lowpass', '高通': 'Highpass', '带阻': 'Bandstop',
  '巴特沃斯': 'Butterworth', '切比雪夫': 'Chebyshev', '椭圆': 'Elliptic',
  '希尔伯特': 'Hilbert', '短时': 'Short-Time',
  
  // Optimization
  '优化': 'Optimization', '搜索': 'Search', '进化': 'Evolutionary',
  '遗传': 'Genetic', '粒子群': 'Particle Swarm', '蚁群': 'Ant Colony',
  '模拟退火': 'Simulated Annealing', '禁忌': 'Tabu',
  '线性规划': 'Linear Programming', '整数规划': 'Integer Programming',
  '二次规划': 'Quadratic Programming', '凸优化': 'Convex Optimization',
  '约束': 'Constraint', '目标函数': 'Objective Function',
  '仿真': 'Simulation', '控制': 'Control', 'PID': 'PID', 'MPC': 'MPC',
  
  // MLOps
  '训练': 'Training', '验证': 'Validation', '测试': 'Testing',
  '评估': 'Evaluation', '指标': 'Metric', '精度': 'Accuracy',
  '召回': 'Recall', '准确': 'Precision', '混淆矩阵': 'Confusion Matrix',
  'ROC': 'ROC', 'AUC': 'AUC', 'F1': 'F1',
  '均方误差': 'MSE', '均方根误差': 'RMSE', '平均绝对误差': 'MAE',
  '对称平均': 'Symmetric Mean', '百分比': 'Percentage',
  '部署': 'Deployment', '监控': 'Monitoring', '运维': 'Operations',
  '版本': 'Version', '管理': 'Management', '注册': 'Registry',
  '容器': 'Container', '微服务': 'Microservice', '负载均衡': 'Load Balancing',
  '扩缩容': 'Scaling', '灰度': 'Canary', '蓝绿': 'Blue-Green',
  '回滚': 'Rollback', '健康检查': 'Health Check',
  '日志': 'Logging', '告警': 'Alerting', '追踪': 'Tracing',
  '漂移': 'Drift', '衰退': 'Degradation',
  
  // Visualization
  '可视化': 'Visualization', '图表': 'Chart', '仪表盘': 'Dashboard',
  '折线图': 'Line Chart', '柱状图': 'Bar Chart', '饼图': 'Pie Chart',
  '散点图': 'Scatter Plot', '热力图': 'Heatmap', '箱线图': 'Box Plot',
  '雷达图': 'Radar Chart', '桑基图': 'Sankey Diagram', '树图': 'Treemap',
  '瀑布图': 'Waterfall Chart', '漏斗图': 'Funnel Chart',
  '甘特图': 'Gantt Chart', '地图': 'Map', '拓扑图': 'Topology',
  '报告': 'Report', '报表': 'Report', '模板': 'Template',
  
  // Output
  '文件': 'File', '数据库': 'Database', '消息队列': 'Message Queue',
  'Kafka': 'Kafka', 'RabbitMQ': 'RabbitMQ', 'Redis': 'Redis',
  'API': 'API', 'REST': 'REST', 'gRPC': 'gRPC', 'WebSocket': 'WebSocket',
  'PDF': 'PDF', 'Excel': 'Excel', 'CSV': 'CSV', 'JSON': 'JSON',
  'HTML': 'HTML', 'Markdown': 'Markdown',
  
  // General
  '自动': 'Auto', '智能': 'Intelligent', '高级': 'Advanced', '基础': 'Basic',
  '通用': 'General', '自定义': 'Custom', '配置': 'Configuration',
  '参数': 'Parameter', '设置': 'Settings', '选项': 'Options',
  '输入': 'Input', '输出': 'Output', '结果': 'Result',
  '工业': 'Industrial', '电力': 'Power', '能源': 'Energy',
  '质量': 'Quality', '效率': 'Efficiency', '性能': 'Performance',
  '安全': 'Safety', '可靠': 'Reliability', '稳定': 'Stability',
  '实时': 'Real-time', '批量': 'Batch', '流式': 'Streaming',
  '在线': 'Online', '离线': 'Offline', '增量': 'Incremental',
  '全量': 'Full', '混合': 'Hybrid', '多模态': 'Multimodal',
  '跨域': 'Cross-domain', '端到端': 'End-to-End',
  '基于': 'Based on', '支持': 'Supports', '适用于': 'Suitable for',
  '包含': 'Contains', '提供': 'Provides', '实现': 'Implements',
  '使用': 'Uses', '利用': 'Utilizes', '通过': 'Through',
  '用于': 'For', '针对': 'For', '面向': 'For',
  '以及': 'and', '或者': 'or', '等': 'etc.',
  '多种': 'Multiple', '各种': 'Various', '常见': 'Common',
  '典型': 'Typical', '经典': 'Classic', '现代': 'Modern',
  '传统': 'Traditional', '新型': 'Novel', '改进': 'Improved',
  '增强': 'Enhanced', '扩展': 'Extended', '简化': 'Simplified',
  '快速': 'Fast', '高效': 'Efficient', '轻量': 'Lightweight',
  '鲁棒': 'Robust', '稳健': 'Robust', '灵活': 'Flexible',
  '可扩展': 'Scalable', '可配置': 'Configurable',
  '方法': 'Method', '技术': 'Technique', '方案': 'Solution',
  '框架': 'Framework', '工具': 'Tool', '库': 'Library',
  '系统': 'System', '平台': 'Platform', '引擎': 'Engine',
  '组件': 'Component', '模块': 'Module', '插件': 'Plugin',
  '接口': 'Interface', '协议': 'Protocol', '规范': 'Specification',
  '标记': 'Mark', '标注': 'Annotation', '注释': 'Comment',
  '节假日': 'Holiday', '工作日': 'Workday', '休息日': 'Rest Day',
  '班次': 'Shift', '早班': 'Morning Shift', '中班': 'Afternoon Shift', '晚班': 'Night Shift',
  '峰时段': 'Peak Period', '谷时段': 'Valley Period', '平时段': 'Flat Period',
  '电价': 'Electricity Price', '用电': 'Electricity Usage',
  '负荷': 'Load', '功率': 'Power', '电压': 'Voltage', '电流': 'Current',
  '频率': 'Frequency', '相位': 'Phase', '阻抗': 'Impedance',
  '谐波': 'Harmonic', '暂态': 'Transient', '稳态': 'Steady State',
};

// Better translation function
function betterTranslate(zh) {
  if (!hasChinese.test(zh)) return zh;
  
  let en = zh;
  // Sort by length descending to match longer terms first
  const sorted = Object.entries(dict).sort((a, b) => b[0].length - a[0].length);
  for (const [zhTerm, enTerm] of sorted) {
    en = en.replace(new RegExp(zhTerm, 'g'), enTerm);
  }
  
  // Clean up: remove double spaces, trim
  en = en.replace(/\s+/g, ' ').trim();
  
  return en;
}

// Re-process all entries
let newContent = content;
for (const r of replacements) {
  const newValue = betterTranslate(r.value);
  const newEntry = `  '${r.key}': '${newValue}',`;
  newContent = newContent.replace(r.from, newEntry);
}

fs.writeFileSync(transFile, newContent, 'utf8');
console.log(`Fixed ${fixes} entries`);

// Verify: count remaining Chinese in values
const remaining = [...newContent.matchAll(/  '([^']+)':\s*'([^']+)',/g)]
  .filter(m => hasChinese.test(m[2]) && m[1] !== m[2])
  .length;
console.log(`Remaining entries with Chinese in values: ${remaining}`);
// @AI_GENERATED: end
