# @AI_GENERATED
"""
算子六重测试覆盖登记 — 「已验证 / 已通过测试」的硬门禁。

六重定义
--------
L1 元测试     tests/operators/test_operator_meta.py（期望列表 / 自动发现）
L2 契约烟测   tests/operators/test_operators_smoke.py（SMOKE_CASES）
              tests/operators/test_legacy_operators_smoke.py
              tests/operators/test_feature_operators_smoke.py
              tests/operators/test_eval_operators_smoke.py
              tests/operators/test_p4_gamma_operators_smoke.py
L3 性质测试   tests/operators/test_operator_properties.py
              tests/operators/test_batch67_coverage.py（L3 契约性质）
              tests/operators/test_legacy_batch_coverage.py
              tests/operators/test_feature_batch_coverage.py
              tests/operators/test_eval_batch_coverage.py
              tests/operators/test_p4_gamma_batch_coverage.py
L4 往返/重放  tests/operators/test_model_roundtrip.py
              tests/operators/test_stateless_replay.py
              tests/operators/test_batch67_coverage.py（L4 确定性重放）
              - 有 train/predict 或 fit_predict/predict：模型往返
              - 无状态算子：deterministic replay（同输入两次输出一致）
L5 合成端到端 tests/operators/test_end_to_end.py（多算子链路 / 软目标巡检）
L6 真实数据   tests/test_e2e_accuracy_comparison.py
              tests/test_e2e_new_operators_realdata.py
              tests/test_e2e_p3_w1_realdata.py
              tests/test_e2e_remaining_realdata.py
              tests/test_e2e_p3_w2_realdata.py
              tests/test_e2e_p3_w3_realdata.py
              tests/test_e2e_legacy_realdata.py
              tests/test_e2e_feature_realdata.py
              tests/test_e2e_eval_realdata.py
              tests/test_e2e_p4_gamma_realdata.py

规则：只有同时出现在 L1∩L2∩L3∩L4∩L5∩L6 的算子，才允许写入
services.operator_verification.VERIFIED_OPERATOR_IDS。

维护：补测通过后，把算子 ID 加入下方对应集合；门禁测试会拦截「登记了但缺层」的情况。
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List

# ── P4α：Legacy L1 波 + 新算子 ks_test ─────────────────────────────────────
P4_ALPHA_LEGACY: FrozenSet[str] = frozenset({
    "load_csv", "handle_missing", "detect_outliers", "row_filter",
    "label_encode", "merge_label", "time_window_split",
    "create_lag_features", "extract_time_features", "rolling_statistics", "diff_features",
})
P4_ALPHA_NEW: FrozenSet[str] = frozenset({"ks_test"})
P4_ALPHA: FrozenSet[str] = P4_ALPHA_LEGACY | P4_ALPHA_NEW

# ── P4-β：特征工程波（L2 文档 Wave L2 剩余 9 个）──────────────────────────
P4_BETA_FE: FrozenSet[str] = frozenset({
    "shift_features",
    "pct_change_features",
    "peak_valley_features",
    "workday_features",
    "holiday_features",
    "extract_statistical_features",
    "ts_comparison_features",
    "sliding_window",
    "feature_select",
})

P4_BETA: FrozenSet[str] = P4_BETA_FE | frozenset({
    "confusion_matrix",
    "mse_rmse_mae",
    "smape_score",
    "precision_recall_f1",
    "stratified_cv_eval",
    "random_forest_classifier",
    "smote_oversample",
    "tsfresh_extract",
})

P4_BETA_EVAL: FrozenSet[str] = frozenset({
    "confusion_matrix",
    "mse_rmse_mae",
    "smape_score",
    "precision_recall_f1",
    "stratified_cv_eval",
    "random_forest_classifier",
    "smote_oversample",
    "tsfresh_extract",
})

P4_GAMMA: FrozenSet[str] = frozenset({
    "train_test_split_ts",
    "resample_timeseries",
    "multi_step_forecast",
    "ridge_forecast",
    "xgboost_forecast",
    "lightgbm_forecast",
    "catboost_forecast",
    "ensemble_forecast",
    "save_model_artifact",
    "load_model_artifact",
    "batch_predict_classifier",
    "load_database",
    "load_api",
    "auto_tune_xgboost",
    "auto_tune_lightgbm",
    "auto_tune_catboost",
})

P4_REMAINING: FrozenSet[str] = P4_GAMMA

# ── L1：P0/P1/P2/P3 期望注册（与 test_operator_meta 对齐）──────────────────
LAYER1_META: FrozenSet[str] = frozenset(
    {
        # P0+P1
        "min_max_scale", "z_score_scale", "column_select", "data_merge", "remove_duplicates",
        "pca",
        "logistic_regression", "svm_classifier", "decision_tree_classifier",
        "linear_regression", "lasso_regression", "elastic_net",
        "kmeans", "dbscan",
        "isolation_forest", "one_class_svm",
        "r2_score", "mape_score", "roc_auc",
        "line_chart", "scatter_chart", "histogram",
        "export_csv", "export_excel",
        "arima", "prophet",
        "load_parquet", "load_json",
        "moving_average", "log_transform", "one_hot_encode", "data_type_convert",
        "data_aggregate", "data_profile", "stationarity_test", "correlation_analysis",
        "polynomial_features", "cyclical_encode",
        "knn_classifier", "gradient_boosting_classifier",
        "ridge_regression", "svr_regression",
        "agglomerative_clustering",
        "silhouette_score", "accuracy_score", "f1_score",
        "heatmap_chart", "box_chart",
        # P2
        "savgol_filter", "median_filter", "gaussian_filter", "data_pivot",
        "fft_transform", "bandpass_filter", "lowpass_filter",
        "naive_bayes_classifier", "xgboost_classifier", "xgboost_regression",
        "variance_threshold", "mutual_info_select", "binning",
        "lof_detector", "elliptic_envelope", "classification_report",
        "bar_chart", "pie_chart",
        "load_hdf5", "load_mongodb",
        # P3 W1
        "autocorrelation_features", "spectral_features", "shape_features",
        "chi2_select", "quantile_transform",
        "zscore_anomaly", "iqr_anomaly", "mad_anomaly", "ewma_anomaly", "knn_anomaly",
        # P3 W2
        "random_forest_forecast", "quantile_regression_forecast",
        "knn_forecast", "exponential_smoothing",
        "calibrated_classifier", "extra_trees_classifier",
        "adaboost_classifier", "lightgbm_classifier",
        # P3 W3
        "hdbscan_cluster", "gmm_cluster", "optics_cluster",
        "adasyn_oversample", "stratified_sample", "class_imbalance_check",
        "balanced_accuracy", "pinball_loss",
    }
    | P4_ALPHA
    | P4_BETA
    | P4_GAMMA
)

# ── L2：烟测（SMOKE_CASES + legacy_smoke + prophet；缺 hdf5/mongodb）──────
LAYER2_SMOKE: FrozenSet[str] = frozenset(
    (LAYER1_META - {"load_hdf5", "load_mongodb"}) | {"prophet"} | P4_ALPHA | P4_BETA | P4_GAMMA
)

# ── L3：性质测试（hypothesis + batch67 契约性质）──────────────────────────
_SOFT_BATCH67 = {
    "accuracy_score", "arima", "bandpass_filter", "bar_chart", "binning",
    "classification_report", "column_select", "correlation_analysis",
    "data_aggregate", "dbscan", "decision_tree_classifier", "elastic_net",
    "export_csv", "f1_score", "fft_transform", "gaussian_filter",
    "gradient_boosting_classifier", "histogram", "kmeans", "knn_classifier",
    "lasso_regression", "line_chart", "linear_regression", "load_json",
    "load_parquet", "log_transform", "logistic_regression", "lowpass_filter",
    "mape_score", "median_filter", "min_max_scale", "moving_average",
    "mutual_info_select", "naive_bayes_classifier", "one_hot_encode", "pca",
    "pie_chart", "polynomial_features", "r2_score", "remove_duplicates",
    "ridge_regression", "savgol_filter", "scatter_chart", "stationarity_test",
    "svm_classifier", "svr_regression", "variance_threshold",
    "xgboost_classifier", "xgboost_regression", "z_score_scale",
    "agglomerative_clustering", "box_chart", "cyclical_encode", "data_merge",
    "data_pivot", "data_profile", "data_type_convert", "elliptic_envelope",
    "export_excel", "heatmap_chart", "lof_detector", "one_class_svm",
    "prophet", "roc_auc", "silhouette_score",
}

LAYER3_PROPERTY: FrozenSet[str] = frozenset(
    {
        "min_max_scale", "z_score_scale", "remove_duplicates", "column_select",
        "pca", "kmeans", "dbscan",
        "isolation_forest", "one_class_svm",
        "r2_score", "mape_score", "roc_auc",
        "accuracy_score", "f1_score",
        "line_chart", "scatter_chart", "histogram",
        "export_csv", "load_parquet", "load_json",
        # P3 W1
        "autocorrelation_features", "spectral_features", "shape_features",
        "chi2_select", "quantile_transform",
        "zscore_anomaly", "iqr_anomaly", "mad_anomaly", "ewma_anomaly", "knn_anomaly",
        # P3 W2
        "random_forest_forecast", "quantile_regression_forecast",
        "knn_forecast", "exponential_smoothing",
        "calibrated_classifier", "extra_trees_classifier",
        "adaboost_classifier", "lightgbm_classifier",
        # P3 W3
        "hdbscan_cluster", "gmm_cluster", "optics_cluster",
        "adasyn_oversample", "stratified_sample", "class_imbalance_check",
        "balanced_accuracy", "pinball_loss",
    }
    | _SOFT_BATCH67
    | P4_ALPHA
    | P4_BETA
    | P4_GAMMA
)

# ── L4：模型往返 / 异常往返 / 无状态重放 / batch67 重放 ───────────────────
LAYER4_ROUNDTRIP: FrozenSet[str] = frozenset(
    {
        "logistic_regression", "svm_classifier", "decision_tree_classifier",
        "random_forest_classifier", "knn_classifier", "gradient_boosting_classifier",
        "naive_bayes_classifier", "xgboost_classifier",
        "linear_regression", "lasso_regression", "ridge_regression",
        "elastic_net", "svr_regression", "xgboost_regression",
        "isolation_forest", "one_class_svm",
        # P3 W1 stateless replay
        "autocorrelation_features", "spectral_features", "shape_features",
        "chi2_select", "quantile_transform",
        "zscore_anomaly", "iqr_anomaly", "mad_anomaly", "ewma_anomaly", "knn_anomaly",
        # P3 W2
        "random_forest_forecast", "quantile_regression_forecast",
        "knn_forecast", "exponential_smoothing",
        "calibrated_classifier", "extra_trees_classifier",
        "adaboost_classifier", "lightgbm_classifier",
        # P3 W3
        "hdbscan_cluster", "gmm_cluster", "optics_cluster",
        "adasyn_oversample", "stratified_sample", "class_imbalance_check",
        "balanced_accuracy", "pinball_loss",
    }
    | _SOFT_BATCH67
    | P4_ALPHA
    | P4_BETA
    | P4_GAMMA
)

# ── L5：合成工作流端到端命中（test_end_to_end.py）──────────────────────────
LAYER5_SYNTHETIC_E2E: FrozenSet[str] = frozenset(
    {
        "remove_duplicates", "min_max_scale", "kmeans", "silhouette_score",
        "column_select", "z_score_scale", "logistic_regression",
        "accuracy_score", "f1_score",
        "linear_regression", "r2_score",
        "load_parquet", "data_profile", "correlation_analysis",
        "heatmap_chart", "line_chart", "export_csv",
        "isolation_forest",
        # P3 W1 pipeline
        "autocorrelation_features", "spectral_features", "shape_features",
        "chi2_select", "quantile_transform",
        "zscore_anomaly", "iqr_anomaly", "mad_anomaly", "ewma_anomaly", "knn_anomaly",
        # P3 W2 pipeline
        "random_forest_forecast", "quantile_regression_forecast",
        "knn_forecast", "exponential_smoothing",
        "calibrated_classifier", "extra_trees_classifier",
        "adaboost_classifier", "lightgbm_classifier",
        # P3 W3
        "hdbscan_cluster", "gmm_cluster", "optics_cluster",
        "adasyn_oversample", "stratified_sample", "class_imbalance_check",
        "balanced_accuracy", "pinball_loss",
    }
    | _SOFT_BATCH67
    | P4_ALPHA
    | P4_BETA
    | P4_GAMMA
)

# ── L6：真实业务数据 e2e（accuracy/realdata + legacy 文件并集）────────────
LAYER6_REALDATA_E2E: FrozenSet[str] = frozenset(
    {
        # accuracy_comparison + new_operators_realdata + p3_w1
        "accuracy_score", "arima", "bandpass_filter", "bar_chart", "binning",
        "classification_report", "column_select", "confusion_matrix",
        "correlation_analysis", "data_aggregate", "dbscan",
        "decision_tree_classifier", "elastic_net", "export_csv",
        "extract_statistical_features", "f1_score", "fft_transform",
        "gaussian_filter", "gradient_boosting_classifier", "histogram",
        "isolation_forest", "kmeans", "knn_classifier", "lasso_regression",
        "line_chart", "linear_regression", "load_csv", "load_json",
        "load_parquet", "log_transform", "logistic_regression", "lowpass_filter",
        "mape_score", "median_filter", "merge_label", "min_max_scale",
        "moving_average", "mse_rmse_mae", "mutual_info_select",
        "naive_bayes_classifier", "one_hot_encode", "pca", "pie_chart",
        "polynomial_features", "precision_recall_f1", "prophet", "r2_score",
        "remove_duplicates", "ridge_regression", "savgol_filter", "scatter_chart",
        "smape_score", "stationarity_test", "stratified_cv_eval",
        "svm_classifier", "svr_regression", "variance_threshold",
        "xgboost_classifier", "xgboost_regression", "z_score_scale",
        # P3 W1
        "autocorrelation_features", "spectral_features", "shape_features",
        "chi2_select", "quantile_transform",
        "zscore_anomaly", "iqr_anomaly", "mad_anomaly", "ewma_anomaly", "knn_anomaly",
        # remaining fill-batch（test_e2e_remaining_realdata）
        "agglomerative_clustering", "box_chart", "cyclical_encode", "data_merge",
        "data_pivot", "data_profile", "data_type_convert", "elliptic_envelope",
        "export_excel", "heatmap_chart", "lof_detector", "one_class_svm",
        "roc_auc", "silhouette_score",
        # P3 W2（test_e2e_p3_w2_realdata）
        "random_forest_forecast", "quantile_regression_forecast",
        "knn_forecast", "exponential_smoothing",
        "calibrated_classifier", "extra_trees_classifier",
        "adaboost_classifier", "lightgbm_classifier",
        # P3 W3
        "hdbscan_cluster", "gmm_cluster", "optics_cluster",
        "adasyn_oversample", "stratified_sample", "class_imbalance_check",
        "balanced_accuracy", "pinball_loss",
    }
    | P4_ALPHA
    | P4_BETA
    | P4_GAMMA
)


def layer_sets() -> Dict[str, FrozenSet[str]]:
    return {
        "L1_meta": LAYER1_META,
        "L2_smoke": LAYER2_SMOKE,
        "L3_property": LAYER3_PROPERTY,
        "L4_roundtrip": LAYER4_ROUNDTRIP,
        "L5_synthetic_e2e": LAYER5_SYNTHETIC_E2E,
        "L6_realdata_e2e": LAYER6_REALDATA_E2E,
    }


def six_layer_passed() -> FrozenSet[str]:
    """严格六重交集。"""
    sets = list(layer_sets().values())
    out = sets[0]
    for s in sets[1:]:
        out = out & s
    return frozenset(out)


def missing_layers(op_id: str) -> List[str]:
    return [name for name, s in layer_sets().items() if op_id not in s]


def coverage_report_for_batch(batch: FrozenSet[str]) -> Dict[str, object]:
    passed = six_layer_passed() & batch
    return {
        "batch_size": len(batch),
        "six_layer_passed": sorted(passed),
        "six_layer_passed_count": len(passed),
        "not_fully_passed": sorted(batch - passed),
        "missing_by_op": {op: missing_layers(op) for op in sorted(batch - passed)},
    }
# @AI_GENERATED: end
