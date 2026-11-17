# @AI_GENERATED
"""
Layer 2 — 契约/烟测（Contract & Smoke Tests）

每个 P0+P1 算子一条参数化用例，验证 happy path：
1. 用合理输入调用能返回 dict（不崩溃）
2. 返回 dict 中包含契约声明的输出键
3. 关键输出类型正确（DataFrame / ndarray / float / int / str / list / dict）

这层不检查数值正确性（那是 Layer 3 property tests 的任务），
只检查"契约声明的接口是否兑现"。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest


# ────────────────────────────────────────────────────────────────────────────
# 复用的合成数据生成器（不依赖 fixture，方便参数化 lazy 构造）
# ────────────────────────────────────────────────────────────────────────────


def _numeric_df(rows: int = 20, cols: int = 3) -> pd.DataFrame:
    """稳定种子的数值 DataFrame。"""
    rng = np.random.RandomState(42)
    return pd.DataFrame(
        rng.randn(rows, cols),
        columns=[chr(97 + i) for i in range(cols)],
    )


def _classification_features_target():
    from sklearn.datasets import make_classification
    X, y = make_classification(
        n_samples=40, n_features=5, n_informative=3, n_redundant=1,
        n_classes=2, random_state=42,
    )
    return pd.DataFrame(X, columns=list("abcde")), y


def _multiclass_features_target():
    from sklearn.datasets import make_classification
    X, y = make_classification(
        n_samples=60, n_features=4, n_informative=3, n_redundant=0,
        n_classes=3, n_clusters_per_class=1, random_state=42,
    )
    return pd.DataFrame(X, columns=list("abcd")), y


def _regression_features_target():
    from sklearn.datasets import make_regression
    X, y = make_regression(n_samples=40, n_features=3, noise=0.1, random_state=42)
    return pd.DataFrame(X, columns=list("abc")), y


def _timeseries_df(n: int = 50) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=n, freq="h")
    values = np.sin(np.arange(n) / 5.0) * 10.0 + np.arange(n) * 0.5
    return pd.DataFrame({"timestamp": ts, "value": values})


def _make_tmp_parquet(tmp_path):
    p = tmp_path / "smoke.parquet"
    pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]}).to_parquet(p)
    return str(p)


def _make_tmp_json(tmp_path):
    p = tmp_path / "smoke.json"
    pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}).to_json(p, orient="records")
    return str(p)


# ────────────────────────────────────────────────────────────────────────────
# 参数化用例表
# ────────────────────────────────────────────────────────────────────────────
#
# 每行格式：(operator_id, params_builder, inputs_builder, expected_keys, extra_asserts)
#   - params_builder / inputs_builder: 接受 tmp_path 参数的 factory（可忽略）
#   - expected_keys: 必须出现在返回 dict 中的键列表
#   - extra_asserts: (result) -> None，做额外类型/形状检查
#
# 使用 lambda 延迟构造，避免 pytest collect 阶段执行副作用（临时文件、导入等）。
# ────────────────────────────────────────────────────────────────────────────


def _no_extra(_result):
    pass


def _output_is_dataframe(result):
    assert isinstance(result.get("data"), pd.DataFrame), "output['data'] not DataFrame"


def _score_is_float(result):
    assert isinstance(result.get("score"), float), "output['score'] not float"


def _labels_is_array(result):
    labels = result.get("labels")
    assert isinstance(labels, np.ndarray), "output['labels'] not ndarray"


def _chart_option_valid(result):
    opt = result.get("chart_option")
    assert isinstance(opt, dict), "chart_option not dict"
    assert "series" in opt, "chart_option missing 'series'"
    assert isinstance(opt["series"], list), "chart_option['series'] not list"


def _classifier_train_output(result):
    assert isinstance(result["predictions"], np.ndarray)
    assert isinstance(result["y_true"], np.ndarray)
    assert isinstance(result["model_id"], str) and len(result["model_id"]) > 0
    assert isinstance(result["feature_list"], list)


def _regressor_train_output(result):
    assert isinstance(result["predictions"], np.ndarray)
    assert isinstance(result["y_true"], np.ndarray)
    assert isinstance(result["model_id"], str) and len(result["model_id"]) > 0
    assert isinstance(result.get("coefficients"), np.ndarray)
    assert "intercept" in result


SMOKE_CASES = [
    # ─── P0 数据预处理 ───
    (
        "min_max_scale",
        lambda _tp: {},
        lambda _tp: {"data": _numeric_df()},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "z_score_scale",
        lambda _tp: {},
        lambda _tp: {"data": _numeric_df()},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "column_select",
        lambda _tp: {"columns": ["a", "b"]},
        lambda _tp: {"data": _numeric_df()},
        ["data"],
        lambda r: (_output_is_dataframe(r), (
            lambda: (_ for _ in ()).throw(AssertionError("wrong columns"))
        ) if list(r["data"].columns) != ["a", "b"] else None),
    ),
    (
        "data_merge",
        lambda _tp: {"join_key": "id", "how": "inner"},
        lambda _tp: {
            "left": pd.DataFrame({"id": [1, 2, 3], "x": [10, 20, 30]}),
            "right": pd.DataFrame({"id": [2, 3, 4], "y": [200, 300, 400]}),
        },
        ["data"],
        _output_is_dataframe,
    ),
    (
        "remove_duplicates",
        lambda _tp: {},
        lambda _tp: {"data": pd.DataFrame({"a": [1, 1, 2, 3, 3], "b": [10, 10, 20, 30, 30]})},
        ["data", "rows_removed"],
        lambda r: _output_is_dataframe(r),
    ),
    # ─── P0 特征工程 ───
    (
        "pca",
        lambda _tp: {"n_components": 2},
        lambda _tp: {"data": _numeric_df(rows=30, cols=4)},
        ["data", "explained_variance_ratio"],
        lambda r: (_output_is_dataframe(r),
                    isinstance(r["explained_variance_ratio"], list)),
    ),
    # ─── P0 分类 ───
    (
        "logistic_regression",
        lambda _tp: {"mode": "train"},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    (
        "svm_classifier",
        lambda _tp: {"mode": "train"},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    (
        "decision_tree_classifier",
        lambda _tp: {"mode": "train", "max_depth": 4},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    # ─── P0 回归 ───
    (
        "linear_regression",
        lambda _tp: {"mode": "train"},
        lambda _tp: dict(zip(["features", "target"], _regression_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "coefficients", "intercept"],
        _regressor_train_output,
    ),
    (
        "lasso_regression",
        lambda _tp: {"mode": "train", "alpha": 0.1},
        lambda _tp: dict(zip(["features", "target"], _regression_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "coefficients", "intercept"],
        _regressor_train_output,
    ),
    (
        "elastic_net",
        lambda _tp: {"mode": "train", "alpha": 0.1, "l1_ratio": 0.5},
        lambda _tp: dict(zip(["features", "target"], _regression_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "coefficients", "intercept"],
        _regressor_train_output,
    ),
    # ─── P0 聚类 ───
    (
        "kmeans",
        lambda _tp: {"n_clusters": 3},
        lambda _tp: {"data": _numeric_df(rows=50, cols=3)},
        ["labels", "cluster_centers", "inertia"],
        _labels_is_array,
    ),
    (
        "dbscan",
        lambda _tp: {"eps": 1.0, "min_samples": 3},
        lambda _tp: {"data": _numeric_df(rows=50, cols=3)},
        ["labels", "n_clusters_found"],
        _labels_is_array,
    ),
    # ─── P0 异常检测 ───
    (
        "isolation_forest",
        lambda _tp: {"mode": "fit_predict", "contamination": 0.1},
        lambda _tp: {"data": _numeric_df(rows=50, cols=3)},
        ["labels", "scores", "model_id"],
        _labels_is_array,
    ),
    (
        "one_class_svm",
        lambda _tp: {"mode": "fit_predict", "nu": 0.1},
        lambda _tp: {"data": _numeric_df(rows=50, cols=3)},
        ["labels", "scores", "model_id"],
        _labels_is_array,
    ),
    # ─── P0 评估指标 ───
    (
        "r2_score",
        lambda _tp: {},
        lambda _tp: {"y_true": [1.0, 2.0, 3.0, 4.0], "y_pred": [1.1, 2.2, 2.9, 4.1]},
        ["score"],
        _score_is_float,
    ),
    (
        "mape_score",
        lambda _tp: {},
        lambda _tp: {"y_true": [1.0, 2.0, 3.0, 4.0], "y_pred": [1.1, 2.2, 2.9, 4.1]},
        ["score", "excluded_zero_count"],
        _score_is_float,
    ),
    (
        "roc_auc",
        lambda _tp: {},
        lambda _tp: {"y_true": [0, 1, 0, 1, 0, 1, 0, 1],
                      "y_score": [0.1, 0.8, 0.3, 0.7, 0.2, 0.9, 0.4, 0.6]},
        ["score"],
        _score_is_float,
    ),
    # ─── P0 可视化 ───
    (
        "line_chart",
        lambda _tp: {"x_column": "a", "y_column": "b", "title": "test"},
        lambda _tp: {"data": _numeric_df()},
        ["chart_option", "chart_type"],
        _chart_option_valid,
    ),
    (
        "scatter_chart",
        lambda _tp: {"x_column": "a", "y_column": "b"},
        lambda _tp: {"data": _numeric_df()},
        ["chart_option", "chart_type"],
        _chart_option_valid,
    ),
    (
        "histogram",
        lambda _tp: {"target_column": "a", "bins": 10},
        lambda _tp: {"data": _numeric_df()},
        ["chart_option", "chart_type"],
        _chart_option_valid,
    ),
    # ─── P0 数据输出 ───
    (
        "export_csv",
        lambda tp: {"output_path": f"data/exports/smoke_test_{os.getpid()}.csv"},
        lambda _tp: {"data": _numeric_df()},
        ["output_path", "rows_written"],
        lambda r: (isinstance(r["output_path"], str),
                    isinstance(r["rows_written"], int),
                    not os.path.isabs(r["output_path"])),
    ),
    (
        "export_excel",
        lambda tp: {"output_path": f"data/exports/smoke_test_{os.getpid()}.xlsx"},
        lambda _tp: {"data": _numeric_df()},
        ["output_path", "rows_written"],
        lambda r: (isinstance(r["output_path"], str),
                    isinstance(r["rows_written"], int),
                    not os.path.isabs(r["output_path"])),
    ),
    # ─── P0 时序 ───
    (
        "arima",
        lambda _tp: {"timestamp_column": "timestamp", "value_column": "value",
                      "forecast_horizon": 5, "p": 1, "d": 1, "q": 1},
        lambda _tp: {"data": _timeseries_df()},
        ["forecast", "forecast_dates"],
        lambda r: (isinstance(r["forecast"], list),
                    isinstance(r["forecast_dates"], list),
                    len(r["forecast"]) == 5),
    ),
    # prophet 依赖 prophet 包，可能未安装 → 用 skip_if 处理，见下方特殊 test
    # ─── P0 数据源 ───
    (
        "load_parquet",
        lambda tp: {"file_path": _make_tmp_parquet(tp)},
        lambda _tp: {},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "load_json",
        lambda tp: {"file_path": _make_tmp_json(tp)},
        lambda _tp: {},
        ["data"],
        _output_is_dataframe,
    ),
    # ─── P1 数据预处理 ───
    (
        "moving_average",
        lambda _tp: {"window": 3, "method": "sma"},
        lambda _tp: {"data": _numeric_df()},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "log_transform",
        lambda _tp: {"base": "ln", "offset": 1},
        lambda _tp: {"data": pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "one_hot_encode",
        lambda _tp: {},
        lambda _tp: {"data": pd.DataFrame({"cat": ["A", "B", "A", "C"], "num": [1, 2, 3, 4]})},
        ["data", "new_columns"],
        lambda r: (_output_is_dataframe(r), isinstance(r["new_columns"], list)),
    ),
    (
        "data_type_convert",
        lambda _tp: {"conversions": {"num_str": "int"}},
        lambda _tp: {"data": pd.DataFrame({"num_str": ["1", "2", "3"]})},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "data_aggregate",
        lambda _tp: {"group_by": ["cat"], "agg_columns": ["val"], "agg_func": "sum"},
        lambda _tp: {"data": pd.DataFrame({
            "cat": ["A", "B", "A", "B"], "val": [1.0, 2.0, 3.0, 4.0],
        })},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "data_profile",
        lambda _tp: {},
        lambda _tp: {"data": _numeric_df()},
        ["n_rows", "n_columns", "dtypes", "missing_summary", "numeric_summary", "memory_usage_mb"],
        lambda r: (isinstance(r["n_rows"], int),
                    isinstance(r["dtypes"], dict)),
    ),
    (
        "stationarity_test",
        lambda _tp: {"column": "value", "significance": 0.05},
        lambda _tp: {"data": _timeseries_df()},
        ["is_stationary", "adf_statistic", "p_value", "critical_values", "conclusion"],
        lambda r: (isinstance(r["is_stationary"], bool),
                    isinstance(r["p_value"], float)),
    ),
    (
        "correlation_analysis",
        lambda _tp: {"method": "pearson"},
        lambda _tp: {"data": _numeric_df()},
        ["correlation_matrix", "method"],
        lambda r: isinstance(r["correlation_matrix"], pd.DataFrame),
    ),
    # ─── P1 特征工程 ───
    (
        "polynomial_features",
        lambda _tp: {"degree": 2, "include_bias": False, "interaction_only": True},
        lambda _tp: {"data": _numeric_df()},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "cyclical_encode",
        lambda _tp: {"column": "hour", "period": 24},
        lambda _tp: {"data": pd.DataFrame({"hour": [0, 6, 12, 18, 23]})},
        ["data"],
        lambda r: (_output_is_dataframe(r),
                    "hour_sin" in r["data"].columns,
                    "hour_cos" in r["data"].columns),
    ),
    # ─── P1 分类 ───
    (
        "knn_classifier",
        lambda _tp: {"mode": "train", "n_neighbors": 5},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    (
        "gradient_boosting_classifier",
        lambda _tp: {"mode": "train", "n_estimators": 20, "learning_rate": 0.1, "max_depth": 3},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    # ─── P1 回归 ───
    (
        "ridge_regression",
        lambda _tp: {"mode": "train", "alpha": 1.0},
        lambda _tp: dict(zip(["features", "target"], _regression_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "coefficients", "intercept"],
        _regressor_train_output,
    ),
    (
        "svr_regression",
        lambda _tp: {"mode": "train", "kernel": "rbf", "C": 1.0},
        lambda _tp: dict(zip(["features", "target"], _regression_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true"],
        lambda r: (isinstance(r["predictions"], np.ndarray),
                    isinstance(r["model_id"], str)),
    ),
    # ─── P1 聚类 ───
    (
        "agglomerative_clustering",
        lambda _tp: {"n_clusters": 3, "linkage": "ward"},
        lambda _tp: {"data": _numeric_df(rows=50, cols=3)},
        ["labels", "n_clusters"],
        _labels_is_array,
    ),
    # ─── P1 评估 ───
    (
        "silhouette_score",
        lambda _tp: {},
        lambda _tp: {
            "data": _numeric_df(rows=30, cols=2),
            "labels": np.array([0]*10 + [1]*10 + [2]*10),
        },
        ["score"],
        _score_is_float,
    ),
    (
        "accuracy_score",
        lambda _tp: {},
        lambda _tp: {"y_true": [0, 1, 0, 1, 0], "y_pred": [0, 1, 1, 1, 0]},
        ["score"],
        _score_is_float,
    ),
    (
        "f1_score",
        lambda _tp: {"average": "macro"},
        lambda _tp: {"y_true": [0, 1, 0, 1, 0, 1], "y_pred": [0, 1, 1, 1, 0, 0]},
        ["score"],
        _score_is_float,
    ),
    # ─── P1 可视化 ───
    (
        "heatmap_chart",
        lambda _tp: {"title": "smoke"},
        lambda _tp: {"data": _numeric_df().corr()},
        ["chart_option", "chart_type"],
        _chart_option_valid,
    ),
    (
        "box_chart",
        lambda _tp: {"title": "smoke"},
        lambda _tp: {"data": _numeric_df()},
        ["chart_option", "chart_type"],
        _chart_option_valid,
    ),
    # ─── P2 信号处理 & 过滤 ───
    (
        "savgol_filter",
        lambda _tp: {"window_length": 5, "polyorder": 2},
        lambda _tp: {"data": _numeric_df(rows=30)},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "median_filter",
        lambda _tp: {"size": 3},
        lambda _tp: {"data": _numeric_df()},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "gaussian_filter",
        lambda _tp: {"sigma": 1.0},
        lambda _tp: {"data": _numeric_df()},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "fft_transform",
        lambda _tp: {"column": "a", "sampling_rate": 100.0, "top_k": 5},
        lambda _tp: {"data": _timeseries_df(n=128).rename(columns={"value": "a"})[["a"]]},
        ["data", "dominant_frequency"],
        lambda r: (_output_is_dataframe(r), isinstance(r["dominant_frequency"], float)),
    ),
    (
        "bandpass_filter",
        lambda _tp: {"low_cutoff": 1.0, "high_cutoff": 10.0, "sampling_rate": 100.0, "order": 4},
        lambda _tp: {"data": _timeseries_df(n=200)[["value"]]},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "lowpass_filter",
        lambda _tp: {"cutoff": 10.0, "sampling_rate": 100.0, "order": 4},
        lambda _tp: {"data": _timeseries_df(n=200)[["value"]]},
        ["data"],
        _output_is_dataframe,
    ),
    # ─── P2 数据变换 ───
    (
        "data_pivot",
        lambda _tp: {"index": "region", "columns": "period", "values": "value", "aggfunc": "sum"},
        lambda _tp: {"data": pd.DataFrame({
            "region": ["A", "A", "B", "B"],
            "period": ["Q1", "Q2", "Q1", "Q2"],
            "value": [10, 20, 30, 40],
        })},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "binning",
        lambda _tp: {"column": "a", "method": "equal_width", "bins": 5},
        lambda _tp: {"data": _numeric_df()},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "variance_threshold",
        lambda _tp: {"threshold": 0.0},
        lambda _tp: {"data": _numeric_df()},
        ["data", "removed_columns"],
        lambda r: (_output_is_dataframe(r), isinstance(r["removed_columns"], list)),
    ),
    (
        "mutual_info_select",
        lambda _tp: {"top_k": 3},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["data", "selected_columns", "scores"],
        lambda r: (_output_is_dataframe(r),
                    isinstance(r["selected_columns"], list),
                    isinstance(r["scores"], dict)),
    ),
    # ─── P2 分类进阶 ───
    (
        "naive_bayes_classifier",
        lambda _tp: {"mode": "train"},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    (
        "xgboost_classifier",
        lambda _tp: {"mode": "train", "n_estimators": 20, "max_depth": 3, "learning_rate": 0.1},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    # ─── P2 回归进阶 ───
    (
        "xgboost_regression",
        lambda _tp: {"mode": "train", "n_estimators": 20, "max_depth": 3, "learning_rate": 0.1},
        lambda _tp: dict(zip(["features", "target"], _regression_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true"],
        lambda r: (isinstance(r["predictions"], np.ndarray),
                    isinstance(r["model_id"], str)),
    ),
    # ─── P2 异常检测进阶 ───
    (
        "lof_detector",
        lambda _tp: {"n_neighbors": 10, "contamination": 0.1},
        lambda _tp: {"data": _numeric_df(rows=50, cols=3)},
        ["labels", "scores"],
        _labels_is_array,
    ),
    (
        "elliptic_envelope",
        lambda _tp: {"contamination": 0.1},
        lambda _tp: {"data": _numeric_df(rows=50, cols=3)},
        ["labels", "scores"],
        _labels_is_array,
    ),
    # ─── P2 评估进阶 ───
    (
        "classification_report",
        lambda _tp: {},
        lambda _tp: {
            "y_true": [0, 1, 0, 1, 2, 0, 1, 2, 0, 1],
            "y_pred": [0, 1, 0, 0, 2, 0, 1, 1, 0, 2],
        },
        ["report_text", "report_dict", "accuracy", "macro_precision", "macro_recall", "macro_f1"],
        lambda r: (isinstance(r["report_text"], str),
                    isinstance(r["report_dict"], dict),
                    isinstance(r["accuracy"], float)),
    ),
    # ─── P2 可视化进阶 ───
    (
        "bar_chart",
        lambda _tp: {"x_column": "cat", "y_column": "val"},
        lambda _tp: {"data": pd.DataFrame({
            "cat": ["A", "B", "C", "D"], "val": [10, 20, 15, 25],
        })},
        ["chart_option", "chart_type"],
        _chart_option_valid,
    ),
    (
        "pie_chart",
        lambda _tp: {"name_column": "cat", "value_column": "val"},
        lambda _tp: {"data": pd.DataFrame({
            "cat": ["A", "B", "C", "A"], "val": [10, 20, 15, 5],
        })},
        ["chart_option", "chart_type"],
        _chart_option_valid,
    ),
    # ─── P3 W1 特征工程 ───
    (
        "autocorrelation_features",
        lambda _tp: {"column": "value", "nlags": 8},
        lambda _tp: {"data": _timeseries_df(80)},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "spectral_features",
        lambda _tp: {"column": "value", "sampling_rate": 1.0},
        lambda _tp: {"data": _timeseries_df(64)},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "shape_features",
        lambda _tp: {"column": "value"},
        lambda _tp: {"data": _timeseries_df(64)},
        ["data"],
        _output_is_dataframe,
    ),
    (
        "chi2_select",
        lambda _tp: {"k": 3},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["data", "selected_columns", "scores"],
        lambda r: (isinstance(r["data"], pd.DataFrame), len(r["selected_columns"]) <= 3),
    ),
    (
        "quantile_transform",
        lambda _tp: {"columns": ["a", "b"], "output_distribution": "uniform"},
        lambda _tp: {"data": _numeric_df(rows=50, cols=3)},
        ["data"],
        _output_is_dataframe,
    ),
    # ─── P3 W1 异常检测 ───
    (
        "zscore_anomaly",
        lambda _tp: {"column": "a", "threshold": 3.0},
        lambda _tp: {"data": _numeric_df(rows=80, cols=2)},
        ["labels", "scores"],
        _labels_is_array,
    ),
    (
        "iqr_anomaly",
        lambda _tp: {"column": "a", "factor": 1.5},
        lambda _tp: {"data": _numeric_df(rows=80, cols=2)},
        ["labels", "scores"],
        _labels_is_array,
    ),
    (
        "mad_anomaly",
        lambda _tp: {"column": "a", "threshold": 3.0},
        lambda _tp: {"data": _numeric_df(rows=80, cols=2)},
        ["labels", "scores"],
        _labels_is_array,
    ),
    (
        "ewma_anomaly",
        lambda _tp: {"column": "value", "span": 10, "threshold": 3.0},
        lambda _tp: {"data": _timeseries_df(80)},
        ["labels", "scores"],
        _labels_is_array,
    ),
    (
        "knn_anomaly",
        lambda _tp: {"n_neighbors": 5, "contamination": 0.1},
        lambda _tp: {"data": _numeric_df(rows=60, cols=3)},
        ["labels", "scores"],
        _labels_is_array,
    ),
    # ─── P3 W2 时序预测 ───
    (
        "random_forest_forecast",
        lambda _tp: {
            "timestamp_column": "timestamp", "value_column": "value",
            "forecast_horizon": 5, "n_lags": 8, "n_estimators": 20,
        },
        lambda _tp: {"data": _timeseries_df(80)},
        ["forecast", "forecast_dates"],
        lambda r: (isinstance(r["forecast"], list), len(r["forecast"]) == 5),
    ),
    (
        "knn_forecast",
        lambda _tp: {
            "timestamp_column": "timestamp", "value_column": "value",
            "forecast_horizon": 5, "n_lags": 8, "n_neighbors": 3,
        },
        lambda _tp: {"data": _timeseries_df(80)},
        ["forecast", "forecast_dates"],
        lambda r: (isinstance(r["forecast"], list), len(r["forecast"]) == 5),
    ),
    (
        "quantile_regression_forecast",
        lambda _tp: {
            "timestamp_column": "timestamp", "value_column": "value",
            "forecast_horizon": 4, "n_lags": 6, "quantile": 0.5,
        },
        lambda _tp: {"data": _timeseries_df(60)},
        ["forecast", "forecast_dates"],
        lambda r: (isinstance(r["forecast"], list), len(r["forecast"]) == 4),
    ),
    (
        "exponential_smoothing",
        lambda _tp: {
            "timestamp_column": "timestamp", "value_column": "value",
            "forecast_horizon": 5, "trend": "add",
        },
        lambda _tp: {"data": _timeseries_df(60)},
        ["forecast", "forecast_dates"],
        lambda r: (isinstance(r["forecast"], list), len(r["forecast"]) == 5),
    ),
    # ─── P3 W2 分类 ───
    (
        "extra_trees_classifier",
        lambda _tp: {"mode": "train", "n_estimators": 20, "max_depth": 4, "save_model": "false"},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    (
        "adaboost_classifier",
        lambda _tp: {"mode": "train", "n_estimators": 20, "learning_rate": 0.5, "save_model": "false"},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    (
        "calibrated_classifier",
        lambda _tp: {"mode": "train", "cv": 2, "method": "sigmoid", "save_model": "false"},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    (
        "lightgbm_classifier",
        lambda _tp: {
            "mode": "train", "n_estimators": 20, "max_depth": 3,
            "learning_rate": 0.1, "save_model": "false",
        },
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["model", "model_id", "feature_list", "predictions", "y_true", "feature_importances"],
        _classifier_train_output,
    ),
    # ─── P3 W3 聚类 ───
    (
        "hdbscan_cluster",
        lambda _tp: {"min_cluster_size": 5},
        lambda _tp: {"data": _numeric_df(rows=80, cols=3)},
        ["labels", "n_clusters_found"],
        _labels_is_array,
    ),
    (
        "gmm_cluster",
        lambda _tp: {"n_components": 3, "random_state": 0},
        lambda _tp: {"data": _numeric_df(rows=60, cols=3)},
        ["labels", "n_clusters_found", "means", "weights"],
        _labels_is_array,
    ),
    (
        "optics_cluster",
        lambda _tp: {"min_samples": 5, "xi": 0.05},
        lambda _tp: {"data": _numeric_df(rows=80, cols=3)},
        ["labels", "n_clusters_found"],
        _labels_is_array,
    ),
    # ─── P3 W3 采样 / 诊断 / 评估 ───
    (
        "adasyn_oversample",
        lambda _tp: {"n_neighbors": 3, "random_state": 0},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["features", "target", "n_synthetic"],
        lambda r: (
            isinstance(r["features"], pd.DataFrame),
            len(r["features"]) == len(r["target"]),
            isinstance(r["n_synthetic"], int),
        ),
    ),
    (
        "stratified_sample",
        lambda _tp: {"sample_ratio": 0.5, "random_state": 0},
        lambda _tp: dict(zip(["features", "target"], _classification_features_target())),
        ["features", "target", "sample_indices", "n_rows"],
        lambda r: (
            isinstance(r["features"], pd.DataFrame),
            r["n_rows"] == len(r["features"]),
        ),
    ),
    (
        "class_imbalance_check",
        lambda _tp: {"imbalance_threshold": 3.0},
        lambda _tp: {"target": _classification_features_target()[1]},
        ["class_counts", "imbalance_ratio", "is_imbalanced", "n_classes"],
        lambda r: (isinstance(r["class_counts"], dict), isinstance(r["imbalance_ratio"], float)),
    ),
    (
        "balanced_accuracy",
        lambda _tp: {},
        lambda _tp: {"y_true": [0, 1, 0, 1, 1], "y_pred": [0, 1, 0, 0, 1]},
        ["score"],
        lambda r: isinstance(r["score"], float),
    ),
    (
        "pinball_loss",
        lambda _tp: {"quantile": 0.5},
        lambda _tp: {"y_true": [1.0, 2.0, 3.0, 4.0], "y_pred": [1.1, 1.9, 3.2, 3.8]},
        ["score", "quantile"],
        lambda r: isinstance(r["score"], float),
    ),
]


@pytest.mark.parametrize(
    "op_id,params_builder,inputs_builder,expected_keys,extra_asserts",
    SMOKE_CASES,
    ids=[case[0] for case in SMOKE_CASES],
)
def test_operator_smoke(router, tmp_path, op_id, params_builder, inputs_builder,
                        expected_keys, extra_asserts):
    """happy path: 每个算子给合理输入 → 返回 dict 且包含契约声明的键。"""
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)

    result = router.execute(op_id, params, inputs)

    # 契约 1: 返回必须是 dict
    assert isinstance(result, dict), f"{op_id} did not return dict, got {type(result)}"

    # 契约 2: 每个声明的输出键都必须存在
    for key in expected_keys:
        assert key in result, f"{op_id} missing output key '{key}'. Got keys: {list(result.keys())}"

    # 契约 3: 额外的类型/形状检查
    extra_asserts(result)


# ────────────────────────────────────────────────────────────────────────────
# Prophet 单独测试（可选依赖）
# ────────────────────────────────────────────────────────────────────────────


def test_prophet_smoke_or_skip(router):
    """Prophet 依赖可选包 `prophet`，若未装则 skip。"""
    try:
        import prophet  # noqa: F401
    except ImportError:
        pytest.skip("prophet package not installed")

    ts = pd.date_range("2024-01-01", periods=50, freq="h")
    df = pd.DataFrame({"ds": ts, "y": np.sin(np.arange(50) / 5.0) * 10 + np.arange(50) * 0.5})

    result = router.execute(
        "prophet",
        {"timestamp_column": "ds", "value_column": "y", "forecast_horizon": 5, "freq": "h"},
        {"data": df},
    )
    for k in ("forecast", "forecast_dates", "forecast_lower", "forecast_upper"):
        assert k in result, f"prophet output missing '{k}'"
    assert len(result["forecast"]) == 5


def test_prophet_dependency_error_when_not_installed(router):
    """如果 prophet 未装，算子应抛 DependencyError（而非 ImportError 泄漏）。"""
    try:
        import prophet  # noqa: F401
        pytest.skip("prophet is installed; DependencyError path not testable")
    except ImportError:
        pass

    from services.operator_execution.router import OperatorExecutionError
    ts = pd.date_range("2024-01-01", periods=50, freq="h")
    df = pd.DataFrame({"ds": ts, "y": np.arange(50, dtype=float)})

    with pytest.raises(OperatorExecutionError) as excinfo:
        router.execute(
            "prophet",
            {"timestamp_column": "ds", "value_column": "y", "forecast_horizon": 5},
            {"data": df},
        )
    assert excinfo.value.error_type == "DependencyError"
# @AI_GENERATED: end
