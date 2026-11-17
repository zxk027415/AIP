// @AI_GENERATED
/**
 * badge-verify.test.ts — 纯 Node 端跑的验证脚本（不依赖 vitest）。
 *
 * 目的：模拟 useBackendReadyOperators hook 的 buildReadySet 逻辑，
 * 对照 basicModuleFunctions.ts 的静态目录，输出：
 *   - 哪些前端卡片会显示"可执行"徽标
 *   - 哪些 P0/P1/P2 关键算子成功匹配（回归防护）
 *
 * 运行：node --experimental-vm-modules tests/badge-verify.test.ts（或复制到浏览器 console）
 */
export {};

const BACKEND_URL = 'http://127.0.0.1:8080/api/functions/backend-status';

const FRONTEND_TO_BACKEND_ALIASES: Record<string, string> = {
  arima_forecast: 'arima',
  prophet_forecast: 'prophet',
  elastic_net_forecast: 'elastic_net',
  pca_reduce: 'pca',
  pca_reduction: 'pca',
  kmeans_cluster: 'kmeans',
  dbscan_cluster: 'dbscan',
  agglomerative_cluster: 'agglomerative_clustering',
  ocsvm_anomaly: 'one_class_svm',
  dbscan_anomaly: 'dbscan',
  elliptic_envelope_anomaly: 'elliptic_envelope',
  isolation_forest_anomaly: 'isolation_forest',
  lof_anomaly: 'lof_detector',
  elastic_net_regression: 'elastic_net',
  roc_auc_score: 'roc_auc',
  confusion_matrix_eval: 'confusion_matrix',
  f1_metric: 'f1_score',
  accuracy_metric: 'accuracy_score',
  r2_metric: 'r2_score',
  histogram_chart: 'histogram',
  train_test_split: 'train_test_split_ts',
  save_model: 'save_model_artifact',
  load_model: 'load_model_artifact',
};

// 关键算子：验证它们的前端目录 ID 能命中徽标
const CRITICAL_FRONTEND_IDS = [
  // P0 数据源
  'load_csv', 'load_parquet', 'load_json',
  // P0 数据预处理
  'min_max_scale', 'z_score_scale', 'column_select', 'data_merge', 'remove_duplicates',
  // P0 特征
  'pca_reduce', 'pca_reduction',
  // P0 分类（前端目录里的分类算法）
  // P0 回归
  'ridge_regression', 'lasso_regression', 'elastic_net_regression',
  // P0 聚类
  'kmeans_cluster', 'dbscan_cluster',
  // P0 异常检测
  'ocsvm_anomaly',
  // P0 评估
  'r2_score', 'mse_rmse_mae', 'roc_auc_score',
  // P0 可视化
  'line_chart', 'scatter_chart', 'histogram_chart',
  // P0 数据输出
  'export_csv', 'export_excel',
  // P0 时序
  'arima_forecast', 'prophet_forecast',
  // P1 追加
  'moving_average', 'one_hot_encode', 'label_encode',
  'accuracy_metric', 'f1_metric', 'r2_metric',
  'polynomial_features', 'variance_threshold',
  'agglomerative_cluster',
  // P2 追加
  'savgol_filter', 'median_filter', 'gaussian_filter',
  'fft_transform', 'bandpass_filter', 'lowpass_filter',
  'data_pivot', 'binning',
  'mutual_info_select',
  'elliptic_envelope_anomaly',
  'bar_chart', 'pie_chart', 'box_chart', 'heatmap_chart',
  'load_hdf5', 'load_mongodb',
  'classification_report',
];

async function main() {
  const res = await fetch(BACKEND_URL);
  const body = (await res.json()) as { total_registered: number; registered_operators: string[] };
  const registered = body.registered_operators;
  const backendSet = new Set(registered);

  // 复现 useBackendReadyOperators.buildReadySet 逻辑
  const readySet = new Set(registered);
  for (const [frontendId, backendId] of Object.entries(FRONTEND_TO_BACKEND_ALIASES)) {
    if (backendSet.has(backendId)) readySet.add(frontendId);
  }

  console.log(`Backend registered: ${registered.length}`);
  console.log(`readySet size (含别名): ${readySet.size}`);

  const misses: string[] = [];
  for (const id of CRITICAL_FRONTEND_IDS) {
    if (!readySet.has(id)) misses.push(id);
  }

  if (misses.length === 0) {
    console.log(`✓ All ${CRITICAL_FRONTEND_IDS.length} critical operators map to backend`);
  } else {
    console.log(`✗ ${misses.length} critical ops MISSING from readySet:`);
    for (const m of misses) console.log(`  - ${m}`);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error('Failed:', e);
  process.exit(1);
});
// @AI_GENERATED: end
