# @AI_GENERATED
"""
Layer 1 — 元测试（Meta Tests）

一次覆盖所有算子的**通用规范性检查**：
- 每个模块能否被 auto_discover 发现
- OPERATOR_ID 是否合法（非空、小写、合法标识符）
- execute 是否是可调用对象
- 所有算子 ID 唯一（无重复注册）
- Backend Status API 能列出全部算子

这一层不需要任何业务知识，纯粹检查"契约的元数据"。
"""
import inspect
import os

import pytest

from services.operator_execution.router import OperatorRouter


# ────────────────────────────────────────────────────────────────────────────
# auto_discover / OPERATOR_ID / execute 规范性
# ────────────────────────────────────────────────────────────────────────────


class TestAutoDiscovery:
    """自动发现层规范检查。"""

    def test_router_discovers_at_least_60_operators(self, router):
        """经过 auto_discover，router 至少注册 60 个算子（当前应为 92 个左右）。"""
        ops = router.list_operators()
        assert len(ops) >= 60, f"Only {len(ops)} operators discovered, expected >= 60"

    def test_no_duplicate_operator_ids(self, router):
        """算子 ID 无重复（set 大小等于 list 大小）。"""
        ops = router.list_operators()
        assert len(ops) == len(set(ops)), "Duplicate OPERATOR_IDs detected"

    def test_every_operator_id_is_lowercase_identifier(self, router):
        """每个 OPERATOR_ID 都是小写合法 Python 标识符。"""
        for op_id in router.list_operators():
            assert isinstance(op_id, str), f"{op_id!r} is not str"
            assert op_id.isidentifier(), f"{op_id!r} is not a valid identifier"
            assert op_id == op_id.lower(), f"{op_id!r} contains uppercase letters"

    def test_every_operator_has_callable_execute(self, router):
        """每个已注册算子的执行函数都是可调用对象。"""
        for op_id in router.list_operators():
            fn = router._registry[op_id]
            assert callable(fn), f"execute for {op_id} is not callable"

    def test_every_execute_signature_has_two_positional_params(self, router):
        """
        每个 execute 函数必须接受 (params, inputs) 两个参数。

        用 inspect 检查签名，容错 *args / **kwargs 但至少需要 2 个位置形参名。
        """
        for op_id in router.list_operators():
            fn = router._registry[op_id]
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())
            positional = [
                p for p in params
                if p.kind in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            assert len(positional) >= 2, (
                f"{op_id} execute() has only {len(positional)} positional params, "
                f"expected >= 2 (params, inputs). Sig: {sig}"
            )


# ────────────────────────────────────────────────────────────────────────────
# 未注册算子的错误处理
# ────────────────────────────────────────────────────────────────────────────


class TestRouterErrorHandling:
    """router 未知算子的错误路径。"""

    def test_execute_unknown_operator_raises(self, router):
        """调用未注册的 operator_id 抛 OperatorExecutionError。"""
        from services.operator_execution.router import OperatorExecutionError
        with pytest.raises(OperatorExecutionError) as excinfo:
            router.execute("__definitely_not_registered__", {}, {})
        assert excinfo.value.error_type == "OperatorNotFoundError"


# ────────────────────────────────────────────────────────────────────────────
# 期望包含的 P0 / P1 关键算子（回归防护）
# ────────────────────────────────────────────────────────────────────────────


EXPECTED_P2_OPERATORS = [
    "savgol_filter", "median_filter", "gaussian_filter", "data_pivot",
    "fft_transform", "bandpass_filter", "lowpass_filter",
    "naive_bayes_classifier", "xgboost_classifier", "xgboost_regression",
    "variance_threshold", "mutual_info_select", "binning",
    "lof_detector", "elliptic_envelope", "classification_report",
    "bar_chart", "pie_chart",
    "load_hdf5", "load_mongodb",
]

EXPECTED_P3_W1_OPERATORS = [
    # 特征工程
    "autocorrelation_features", "spectral_features", "shape_features",
    "chi2_select", "quantile_transform",
    # 异常检测
    "zscore_anomaly", "iqr_anomaly", "mad_anomaly", "ewma_anomaly", "knn_anomaly",
]

EXPECTED_P3_W2_OPERATORS = [
    # 时序预测
    "random_forest_forecast", "quantile_regression_forecast",
    "knn_forecast", "exponential_smoothing",
    # 分类
    "calibrated_classifier", "extra_trees_classifier",
    "adaboost_classifier", "lightgbm_classifier",
]

EXPECTED_P3_W3_OPERATORS = [
    "hdbscan_cluster", "gmm_cluster", "optics_cluster",
    "adasyn_oversample", "stratified_sample", "class_imbalance_check",
    "balanced_accuracy", "pinball_loss",
]


@pytest.mark.parametrize("op_id", EXPECTED_P3_W3_OPERATORS)
def test_expected_p3_w3_operator_is_registered(router, op_id):
    """P3 W3 算子必须全部注册成功。"""
    assert router.has_operator(op_id), f"Expected P3 W3 operator '{op_id}' is not registered"


@pytest.mark.parametrize("op_id", EXPECTED_P3_W2_OPERATORS)
def test_expected_p3_w2_operator_is_registered(router, op_id):
    """P3 W2 算子必须全部注册成功。"""
    assert router.has_operator(op_id), f"Expected P3 W2 operator '{op_id}' is not registered"


@pytest.mark.parametrize("op_id", EXPECTED_P3_W1_OPERATORS)
def test_expected_p3_w1_operator_is_registered(router, op_id):
    """P3 W1 算子必须全部注册成功。"""
    assert router.has_operator(op_id), f"Expected P3 W1 operator '{op_id}' is not registered"


@pytest.mark.parametrize("op_id", EXPECTED_P2_OPERATORS)
def test_expected_p2_operator_is_registered(router, op_id):
    """P2 关键算子必须全部注册成功。"""
    assert router.has_operator(op_id), f"Expected P2 operator '{op_id}' is not registered"


EXPECTED_P0_P1_OPERATORS = [
    # P0 数据预处理
    "min_max_scale", "z_score_scale", "column_select", "data_merge", "remove_duplicates",
    # P0 特征工程
    "pca",
    # P0 分类
    "logistic_regression", "svm_classifier", "decision_tree_classifier",
    # P0 回归
    "linear_regression", "lasso_regression", "elastic_net",
    # P0 聚类
    "kmeans", "dbscan",
    # P0 异常检测
    "isolation_forest", "one_class_svm",
    # P0 评估
    "r2_score", "mape_score", "roc_auc",
    # P0 可视化
    "line_chart", "scatter_chart", "histogram",
    # P0 数据输出
    "export_csv", "export_excel",
    # P0 时序
    "arima", "prophet",
    # P0 数据源
    "load_parquet", "load_json",
    # P1 追加
    "moving_average", "log_transform", "one_hot_encode", "data_type_convert",
    "data_aggregate", "data_profile", "stationarity_test", "correlation_analysis",
    "polynomial_features", "cyclical_encode",
    "knn_classifier", "gradient_boosting_classifier",
    "ridge_regression", "svr_regression",
    "agglomerative_clustering",
    "silhouette_score", "accuracy_score", "f1_score",
    "heatmap_chart", "box_chart",
]


@pytest.mark.parametrize("op_id", EXPECTED_P0_P1_OPERATORS)
def test_expected_operator_is_registered(router, op_id):
    """P0/P1 关键算子必须全部注册成功（防止后续误删）。"""
    assert router.has_operator(op_id), f"Expected operator '{op_id}' is not registered"
# @AI_GENERATED: end
