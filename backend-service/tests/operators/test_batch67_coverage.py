# @AI_GENERATED
"""
上一批 P0/P1/P2 算子六重补测（方案1续）— L3 性质 + L4 确定性重放。

从 SMOKE_CASES 复用入参，对「已有 L2+L6、尚未六重全过」的算子补齐：
- L3：可执行且契约键存在、关键数值有限
- L4：同输入连续两次执行，关键输出一致（无状态 / 评估 / 滤波 / 图表等）

模型 train/predict 往返仍由 test_model_roundtrip.py 覆盖，不在此重复。
"""
from __future__ import annotations

import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

_SMOKE_PATH = os.path.join(os.path.dirname(__file__), "test_operators_smoke.py")
_spec = importlib.util.spec_from_file_location("op_smoke_cases", _SMOKE_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
SMOKE_CASES = _mod.SMOKE_CASES

# 已有 L2+L6、待补六重的软目标（与 operator_test_coverage 审计一致）
SOFT_BATCH67 = frozenset(
    {
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
        # 续：原先缺 L6/L3/L4/L5 的一批
        "agglomerative_clustering", "box_chart", "cyclical_encode", "data_merge",
        "data_pivot", "data_profile", "data_type_convert", "elliptic_envelope",
        "export_excel", "heatmap_chart", "lof_detector", "one_class_svm",
        "roc_auc", "silhouette_score",
    }
)

# 已有模型往返的算子：L4 不在此文件重复
MODEL_ROUNDTRIP_OPS = frozenset(
    {
        "logistic_regression", "svm_classifier", "decision_tree_classifier",
        "knn_classifier", "gradient_boosting_classifier", "naive_bayes_classifier",
        "xgboost_classifier", "linear_regression", "lasso_regression",
        "ridge_regression", "elastic_net", "svr_regression", "xgboost_regression",
        "isolation_forest", "one_class_svm",
    }
)

_SMOKE_BY_ID = {case[0]: case for case in SMOKE_CASES}


def _cases_for(op_ids):
    missing = sorted(op_ids - set(_SMOKE_BY_ID))
    if missing:
        raise RuntimeError(f"SMOKE_CASES 缺少: {missing}")
    return [(_SMOKE_BY_ID[op],) for op in sorted(op_ids)]


def _assert_replay_equal(op_id: str, r1: dict, r2: dict):
    """按输出类型做确定性比较。"""
    if "data" in r1 and isinstance(r1["data"], pd.DataFrame):
        pd.testing.assert_frame_equal(
            r1["data"].reset_index(drop=True),
            r2["data"].reset_index(drop=True),
            check_dtype=False,
            rtol=1e-8,
            atol=1e-8,
        )
    if "labels" in r1:
        np.testing.assert_array_equal(r1["labels"], r2["labels"])
    if "scores" in r1 and isinstance(r1["scores"], dict):
        assert r1["scores"].keys() == r2["scores"].keys()
        for k in r1["scores"]:
            assert float(r1["scores"][k]) == pytest.approx(float(r2["scores"][k]), rel=1e-8, abs=1e-8)
    elif "scores" in r1 and isinstance(r1["scores"], (int, float, np.floating)):
        assert r1["scores"] == pytest.approx(r2["scores"], rel=1e-9, abs=1e-9)
    elif "scores" in r1:
        np.testing.assert_allclose(r1["scores"], r2["scores"], rtol=1e-8, atol=1e-8)
    if "score" in r1:
        assert float(r1["score"]) == pytest.approx(float(r2["score"]), rel=1e-9, abs=1e-9)
    if "forecast" in r1:
        np.testing.assert_allclose(r1["forecast"], r2["forecast"], rtol=1e-6, atol=1e-6)
    if "forecast_dates" in r1:
        assert r1["forecast_dates"] == r2["forecast_dates"]
    if "chart_option" in r1:
        assert r1["chart_type"] == r2["chart_type"]
        assert r1["chart_option"].keys() == r2["chart_option"].keys()
    if "selected_columns" in r1:
        assert r1["selected_columns"] == r2["selected_columns"]
    if "correlation_matrix" in r1 and isinstance(r1["correlation_matrix"], pd.DataFrame):
        pd.testing.assert_frame_equal(r1["correlation_matrix"], r2["correlation_matrix"], rtol=1e-8, atol=1e-8)
    if "report_text" in r1:
        assert r1["report_text"] == r2["report_text"]
        assert r1["accuracy"] == pytest.approx(r2["accuracy"])
    if "output_path" in r1:
        assert r1["output_path"] == r2["output_path"]
        assert r1["rows_written"] == r2["rows_written"]
    if "n_rows" in r1:
        assert r1["n_rows"] == r2["n_rows"]
    if "removed_columns" in r1:
        assert r1["removed_columns"] == r2["removed_columns"]
    if "explained_variance_ratio" in r1:
        np.testing.assert_allclose(
            r1["explained_variance_ratio"], r2["explained_variance_ratio"], rtol=1e-8, atol=1e-8,
        )
    if "n_clusters_found" in r1:
        assert r1["n_clusters_found"] == r2["n_clusters_found"]
    if "inertia" in r1:
        assert float(r1["inertia"]) == pytest.approx(float(r2["inertia"]), rel=1e-8, abs=1e-8)
    if "cluster_centers" in r1:
        np.testing.assert_allclose(r1["cluster_centers"], r2["cluster_centers"], rtol=1e-8, atol=1e-8)


@pytest.mark.parametrize("case", [c for c in SMOKE_CASES if c[0] in SOFT_BATCH67], ids=lambda c: c[0])
def test_batch67_layer3_contract_property(router, tmp_path, case):
    """L3：软目标算子在烟测入参下输出契约成立且关键值有限。"""
    op_id, params_builder, inputs_builder, expected_keys, extra_asserts = case
    params = params_builder(tmp_path)
    # 训练类避免落盘干扰
    if "mode" in params and params.get("mode") == "train":
        params = {**params, "save_model": "true"}
    inputs = inputs_builder(tmp_path)
    result = router.execute(op_id, params, inputs)
    assert isinstance(result, dict)
    for key in expected_keys:
        # save_model=false 时部分实现返回空 model_id；此处强制落盘以保证契约
        assert key in result, f"{op_id} missing {key}"
    extra_asserts(result)
    if "score" in result:
        assert np.isfinite(float(result["score"]))
    if "scores" in result and isinstance(result["scores"], dict):
        assert all(np.isfinite(float(v)) for v in result["scores"].values())
    elif "scores" in result and not isinstance(result["scores"], (str, dict)):
        arr = np.asarray(result["scores"], dtype=float)
        assert np.all(np.isfinite(arr))
    if "forecast" in result:
        assert np.all(np.isfinite(np.asarray(result["forecast"], dtype=float)))


@pytest.mark.parametrize(
    "case",
    [c for c in SMOKE_CASES if c[0] in SOFT_BATCH67 and c[0] not in MODEL_ROUNDTRIP_OPS],
    ids=lambda c: c[0],
)
def test_batch67_layer4_deterministic_replay(router, tmp_path, case):
    """L4：无模型软目标算子确定性重放。"""
    op_id, params_builder, inputs_builder, _keys, _extra = case
    params = params_builder(tmp_path)
    inputs = inputs_builder(tmp_path)
    r1 = router.execute(op_id, params, inputs)
    r2 = router.execute(op_id, params, inputs)
    _assert_replay_equal(op_id, r1, r2)
# @AI_GENERATED: end
