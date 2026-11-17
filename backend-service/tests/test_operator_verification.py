# @AI_GENERATED
"""六重测试门禁：已验证登记必须 ⊆ L1∩L2∩L3∩L4∩L5∩L6。"""
from services.operator_test_coverage import (
    LAYER1_META,
    coverage_report_for_batch,
    missing_layers,
    six_layer_passed,
)
from services.operator_verification import VERIFIED_OPERATOR_IDS, filter_verified_registered


def test_verified_equals_six_layer_intersection():
    passed = six_layer_passed()
    assert VERIFIED_OPERATOR_IDS == passed, (
        f"VERIFIED 与六重交集不一致。"
        f" verified-only={sorted(VERIFIED_OPERATOR_IDS - passed)}"
        f" six-only={sorted(passed - VERIFIED_OPERATOR_IDS)}"
    )


def test_every_verified_has_no_missing_layer():
    for op_id in sorted(VERIFIED_OPERATOR_IDS):
        miss = missing_layers(op_id)
        assert not miss, f"{op_id} 登记为已验证但仍缺: {miss}"


def test_filter_verified_registered_intersection():
    registered = ["isolation_forest", "ghost_op", "min_max_scale"]
    out = filter_verified_registered(registered)
    # min_max_scale 目前缺 L4 等，不应出现在六重交集
    assert "ghost_op" not in out
    assert all(op in VERIFIED_OPERATOR_IDS for op in out)


def test_batch_coverage_report_exposes_gap():
    report = coverage_report_for_batch(LAYER1_META)
    assert report["batch_size"] == len(LAYER1_META)
    assert report["six_layer_passed_count"] == len(six_layer_passed() & LAYER1_META)
    # 明确：绝大多数新增算子尚未六重全过
    assert report["six_layer_passed_count"] < report["batch_size"]


def test_isolation_forest_is_fully_covered():
    """已知样例，防止覆盖表被误删。"""
    assert "isolation_forest" in six_layer_passed()


def test_p3_w1_batch_is_fully_covered():
    """方案1：P3 W1 十个算子必须六重全过。"""
    w1 = {
        "autocorrelation_features", "spectral_features", "shape_features",
        "chi2_select", "quantile_transform",
        "zscore_anomaly", "iqr_anomaly", "mad_anomaly", "ewma_anomaly", "knn_anomaly",
    }
    passed = six_layer_passed()
    missing = sorted(w1 - passed)
    assert not missing, f"P3 W1 尚未六重全过: {missing}"


def test_p3_w2_batch_is_fully_covered():
    """P3 W2：时序预测 4 + 分类 4 必须六重全过。"""
    w2 = {
        "random_forest_forecast", "quantile_regression_forecast",
        "knn_forecast", "exponential_smoothing",
        "calibrated_classifier", "extra_trees_classifier",
        "adaboost_classifier", "lightgbm_classifier",
    }
    passed = six_layer_passed()
    missing = sorted(w2 - passed)
    assert not missing, f"P3 W2 尚未六重全过: {missing}"


def test_p3_w3_batch_is_fully_covered():
    """P3 W3：聚类 3 + 采样/评估 5 必须六重全过。"""
    w3 = {
        "hdbscan_cluster", "gmm_cluster", "optics_cluster",
        "adasyn_oversample", "stratified_sample", "class_imbalance_check",
        "balanced_accuracy", "pinball_loss",
    }
    passed = six_layer_passed()
    missing = sorted(w3 - passed)
    assert not missing, f"P3 W3 尚未六重全过: {missing}"


def test_soft_batch67_with_l2_l6_is_fully_covered():
    """方案1续：已有 L2+L6 的上一批软目标必须六重全过。"""
    soft = {
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
    passed = six_layer_passed()
    missing = sorted(soft - passed)
    assert not missing, f"软目标尚未六重全过({len(missing)}): {missing}"


def test_p4_wave_l1_and_ks_fully_covered():
    """P4α：Legacy L1 波 11 个 + ks_test 必须六重全过。"""
    from services.operator_test_coverage import P4_ALPHA, six_layer_passed

    passed = six_layer_passed()
    missing = sorted(P4_ALPHA - passed)
    assert not missing, f"P4α 尚未六重全过: {missing}"


def test_p4_beta_feature_engineering_fully_covered():
    """P4-β：特征工程 9 个算子必须六重全过。"""
    from services.operator_test_coverage import P4_BETA_FE, six_layer_passed

    passed = six_layer_passed()
    missing = sorted(P4_BETA_FE - passed)
    assert not missing, f"P4-β 特征工程尚未六重全过: {missing}"


def test_p4_beta_eval_sampling_fully_covered():
    """P4-β：评估/采样 8 个算子必须六重全过。"""
    from services.operator_test_coverage import P4_BETA_EVAL, six_layer_passed

    passed = six_layer_passed()
    missing = sorted(P4_BETA_EVAL - passed)
    assert not missing, f"P4-β 评估/采样尚未六重全过: {missing}"


def test_p4_gamma_remaining_fully_covered():
    """P4-γ：剩余 16 个算子必须六重全过（不含 hdf5/mongodb）。"""
    from services.operator_test_coverage import P4_GAMMA, six_layer_passed

    passed = six_layer_passed()
    missing = sorted(P4_GAMMA - passed)
    assert not missing, f"P4-γ 尚未六重全过: {missing}"


def test_all_backend_operators_verified_except_env_deps():
    """除 load_hdf5/load_mongodb 外，全部 backend 算子应已六重验证。"""
    import os

    from services.operator_execution.router import OperatorRouter
    from services.operator_test_coverage import six_layer_passed

    r = OperatorRouter()
    r.auto_discover(os.path.join(os.path.dirname(__file__), "..", "services", "operator_backends"))
    skip = {"load_hdf5", "load_mongodb"}
    all_ops = set(r.list_operators()) - skip
    passed = six_layer_passed()
    missing = sorted(all_ops - passed)
    assert not missing, f"仍有未六重验证 backend({len(missing)}): {missing}"
# @AI_GENERATED: end
