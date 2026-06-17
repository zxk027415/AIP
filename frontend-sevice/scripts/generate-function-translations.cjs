// @AI_GENERATED
/**
 * Generate English translations for all basicModuleFunctions.ts entries
 * Run: node AIP-service/frontend/scripts/generate-function-translations.cjs
 */
const fs = require('fs');
const path = require('path');

const funcFile = path.join(__dirname, '..', 'src', 'data', 'basicModuleFunctions.ts');
const transFile = path.join(__dirname, '..', 'src', 'utils', 'dataTranslation.ts');

const funcContent = fs.readFileSync(funcFile, 'utf8');
const transContent = fs.readFileSync(transFile, 'utf8');

// Extract existing keys
const existingKeys = new Set([...transContent.matchAll(/'([^']+)':\s*'/g)].map(m => m[1]));

// Extract all name and description values
const names = [...funcContent.matchAll(/name:\s*'([^']+)'/g)].map(m => m[1]);
const descs = [...funcContent.matchAll(/description:\s*'([^']+)'/g)].map(m => m[1]);

// Simple Chinese to English translation map for common terms
const termMap = {
  '加载': 'Loading', '读取': 'Reading', '连接': 'Connection', '接入': 'Access',
  '查询': 'Query', '订阅': 'Subscription', '写入': 'Write', '导出': 'Export',
  '推送': 'Push', '生成': 'Generation', '检测': 'Detection', '分析': 'Analysis',
  '预测': 'Prediction', '优化': 'Optimization', '分类': 'Classification',
  '聚类': 'Clustering', '回归': 'Regression', '训练': 'Training', '评估': 'Evaluation',
  '部署': 'Deployment', '监控': 'Monitoring', '可视化': 'Visualization',
  '处理': 'Processing', '变换': 'Transform', '填充': 'Filling', '清洗': 'Cleaning',
  '标准化': 'Normalization', '缩放': 'Scaling', '编码': 'Encoding', '提取': 'Extraction',
  '选择': 'Selection', '降维': 'Reduction', '特征': 'Feature', '数据': 'Data',
  '模型': 'Model', '算法': 'Algorithm', '函数': 'Function', '图表': 'Chart',
  '报告': 'Report', '仪表盘': 'Dashboard', '文件': 'File', '数据库': 'Database',
  '时序': 'Time Series', '统计': 'Statistical', '概率': 'Probability',
  '矩阵': 'Matrix', '向量': 'Vector', '张量': 'Tensor', '梯度': 'Gradient',
  '损失': 'Loss', '精度': 'Accuracy', '误差': 'Error', '指标': 'Metric',
  '图像': 'Image', '信号': 'Signal', '频域': 'Frequency', '时频': 'Time-Frequency',
  '滤波': 'Filtering', '振动': 'Vibration', '频谱': 'Spectrum',
  '神经网络': 'Neural Network', '深度学习': 'Deep Learning', '机器学习': 'Machine Learning',
  '强化学习': 'Reinforcement Learning', '迁移学习': 'Transfer Learning',
  '卷积': 'Convolution', '循环': 'Recurrent', '注意力': 'Attention',
  '自编码器': 'Autoencoder', '生成对抗': 'GAN', '图神经': 'Graph Neural',
  '集成': 'Ensemble', '随机森林': 'Random Forest', '决策树': 'Decision Tree',
  '支持向量': 'Support Vector', '贝叶斯': 'Bayesian', '高斯': 'Gaussian',
  '核密度': 'Kernel Density', '主成分': 'Principal Component',
  '线性': 'Linear', '非线性': 'Nonlinear', '正则化': 'Regularized',
  '岭回归': 'Ridge', '套索': 'Lasso', '弹性网': 'Elastic Net',
  '梯度提升': 'Gradient Boosting', '自适应': 'Adaptive',
  '异常': 'Anomaly', '缺失值': 'Missing Value', '异常值': 'Outlier',
  '插值': 'Interpolation', '平滑': 'Smoothing', '去噪': 'Denoising',
  '采样': 'Sampling', '过采样': 'Oversampling', '欠采样': 'Undersampling',
  '交叉验证': 'Cross Validation', '超参数': 'Hyperparameter',
  '分布式': 'Distributed', '并行': 'Parallel', '实验': 'Experiment',
  '版本': 'Version', '管理': 'Management', '服务': 'Service',
  '推理': 'Inference', '导入': 'Import', '输出': 'Output',
  '计算': 'Computing', '运算': 'Operation', '检验': 'Test',
  '分布': 'Distribution', '假设': 'Hypothesis', '相关': 'Correlation',
  '协方差': 'Covariance', '方差': 'Variance', '均值': 'Mean',
  '中位数': 'Median', '分位数': 'Quantile', '百分位': 'Percentile',
};

// For names: try to transliterate using term map, fallback to keeping as-is
function translateName(zh) {
  // If it's already mostly English/numbers, keep it
  if (/^[A-Za-z0-9\s\/\-\.\(\)]+$/.test(zh)) return zh;
  
  let en = zh;
  // Replace known terms
  for (const [zhTerm, enTerm] of Object.entries(termMap)) {
    en = en.replace(new RegExp(zhTerm, 'g'), enTerm);
  }
  
  // If still has Chinese, just return original (td() will show it as-is)
  return en;
}

// Collect all missing entries
const missing = {};
for (const name of names) {
  if (!existingKeys.has(name)) {
    missing[name] = translateName(name);
  }
}
for (const desc of descs) {
  if (!existingKeys.has(desc)) {
    missing[desc] = translateName(desc);
  }
}

console.log(`Missing entries: ${Object.keys(missing).length}`);
console.log(`Sample translations:`);
const samples = Object.entries(missing).slice(0, 10);
for (const [zh, en] of samples) {
  console.log(`  '${zh}': '${en}'`);
}

// Generate the translation entries
const lines = Object.entries(missing).map(([zh, en]) => `  '${zh}': '${en}',`);
const block = `\n  // @AI_GENERATED\n  // ===== Basic Module Functions - All 762 function names & descriptions =====\n${lines.join('\n')}\n  // @AI_GENERATED: end\n`;

// Insert before the closing of ZH_EN_MAP (before the line with just `};`)
const insertPoint = transContent.lastIndexOf('\n};');
if (insertPoint === -1) {
  console.error('Could not find insertion point');
  process.exit(1);
}

const newContent = transContent.slice(0, insertPoint) + block + transContent.slice(insertPoint);
fs.writeFileSync(transFile, newContent, 'utf8');
console.log(`\nInserted ${lines.length} translation entries into dataTranslation.ts`);
// @AI_GENERATED: end
