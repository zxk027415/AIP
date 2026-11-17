# @AI_GENERATED
"""
Layer 4 扩展 — 无状态算子确定性重放（Deterministic Replay）

对非 train/predict 算子：同一 params/inputs 连续执行两次，关键输出必须一致。
这是六重测试中 L4 对「无模型算子」的等价要求。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _assert_df_equal(a: pd.DataFrame, b: pd.DataFrame, op_id: str):
    pd.testing.assert_frame_equal(
        a.reset_index(drop=True),
        b.reset_index(drop=True),
        check_dtype=False,
        rtol=1e-9,
        atol=1e-9,
    )


def _assert_anomaly_equal(r1: dict, r2: dict, op_id: str):
    np.testing.assert_array_equal(r1["labels"], r2["labels"], err_msg=f"{op_id} labels mismatch")
    np.testing.assert_allclose(r1["scores"], r2["scores"], rtol=1e-9, atol=1e-9)


P3_W1_STATELESS_CASES = [
    (
        "autocorrelation_features",
        {"column": "value", "nlags": 6, "include_pacf": True},
        lambda: {"data": pd.DataFrame({"value": np.sin(np.linspace(0, 8, 64))})},
        "data",
    ),
    (
        "spectral_features",
        {"column": "value", "sampling_rate": 1.0},
        lambda: {"data": pd.DataFrame({"value": np.sin(np.linspace(0, 6, 48))})},
        "data",
    ),
    (
        "shape_features",
        {"column": "value"},
        lambda: {"data": pd.DataFrame({"value": np.linspace(-2, 3, 40) ** 2})},
        "data",
    ),
    (
        "quantile_transform",
        {"columns": ["a", "b"], "output_distribution": "uniform", "n_quantiles": 20, "random_state": 7},
        lambda: {"data": pd.DataFrame(np.random.RandomState(0).randn(50, 2), columns=list("ab"))},
        "data",
    ),
    (
        "zscore_anomaly",
        {"column": "a", "threshold": 2.5},
        lambda: {"data": pd.DataFrame({"a": np.random.RandomState(1).randn(60)})},
        "anomaly",
    ),
    (
        "iqr_anomaly",
        {"column": "a", "factor": 1.5},
        lambda: {"data": pd.DataFrame({"a": np.random.RandomState(2).randn(60)})},
        "anomaly",
    ),
    (
        "mad_anomaly",
        {"column": "a", "threshold": 3.0},
        lambda: {"data": pd.DataFrame({"a": np.random.RandomState(3).randn(60)})},
        "anomaly",
    ),
    (
        "ewma_anomaly",
        {"column": "a", "span": 10, "threshold": 3.0},
        lambda: {"data": pd.DataFrame({"a": np.cumsum(np.random.RandomState(4).randn(80))})},
        "anomaly",
    ),
    (
        "knn_anomaly",
        {"n_neighbors": 5, "contamination": 0.1},
        lambda: {"data": pd.DataFrame(np.random.RandomState(5).randn(70, 3), columns=list("abc"))},
        "anomaly",
    ),
]


@pytest.mark.parametrize(
    "op_id,params,inputs_builder,kind",
    P3_W1_STATELESS_CASES,
    ids=[c[0] for c in P3_W1_STATELESS_CASES],
)
def test_p3_w1_stateless_deterministic_replay(router, op_id, params, inputs_builder, kind):
    inputs = inputs_builder()
    r1 = router.execute(op_id, params, inputs)
    r2 = router.execute(op_id, params, inputs)
    if kind == "data":
        _assert_df_equal(r1["data"], r2["data"], op_id)
    else:
        _assert_anomaly_equal(r1, r2, op_id)


def test_chi2_select_deterministic_replay(router):
    rng = np.random.RandomState(11)
    feats = pd.DataFrame(np.abs(rng.randn(60, 4)) + 0.1, columns=list("abcd"))
    y = rng.randint(0, 2, size=60)
    params = {"k": 2}
    inputs = {"features": feats, "target": y}
    r1 = router.execute("chi2_select", params, inputs)
    r2 = router.execute("chi2_select", params, inputs)
    assert r1["selected_columns"] == r2["selected_columns"]
    _assert_df_equal(r1["data"], r2["data"], "chi2_select")


def test_prophet_layer3_and_layer4_when_available(router):
    """prophet 不在 SMOKE_CASES：单独补 L3/L4。"""
    try:
        import prophet  # noqa: F401
    except ImportError:
        pytest.skip("prophet not installed")
    ts = pd.date_range("2024-01-01", periods=48, freq="h")
    df = pd.DataFrame({"ds": ts, "y": np.sin(np.arange(48) / 6.0) * 5 + 10})
    params = {"timestamp_column": "ds", "value_column": "y", "forecast_horizon": 6, "freq": "h"}
    r1 = router.execute("prophet", params, {"data": df})
    assert len(r1["forecast"]) == 6
    assert np.all(np.isfinite(r1["forecast"]))
    r2 = router.execute("prophet", params, {"data": df})
    # Prophet 区间带随机性；均值预测应接近
    np.testing.assert_allclose(r1["forecast"], r2["forecast"], rtol=0.05, atol=0.5)


P3_W2_FORECAST_REPLAY = [
    (
        "random_forest_forecast",
        {
            "timestamp_column": "timestamp", "value_column": "value",
            "forecast_horizon": 4, "n_lags": 8, "n_estimators": 20, "random_state": 7,
        },
    ),
    (
        "knn_forecast",
        {
            "timestamp_column": "timestamp", "value_column": "value",
            "forecast_horizon": 4, "n_lags": 8, "n_neighbors": 3,
        },
    ),
    (
        "quantile_regression_forecast",
        {
            "timestamp_column": "timestamp", "value_column": "value",
            "forecast_horizon": 4, "n_lags": 6, "quantile": 0.5, "alpha": 0.0,
        },
    ),
    (
        "exponential_smoothing",
        {
            "timestamp_column": "timestamp", "value_column": "value",
            "forecast_horizon": 4, "trend": "add",
        },
    ),
]


@pytest.mark.parametrize("op_id,params", P3_W2_FORECAST_REPLAY, ids=[c[0] for c in P3_W2_FORECAST_REPLAY])
def test_p3_w2_forecast_deterministic_replay(router, op_id, params):
    ts = pd.date_range("2024-01-01", periods=72, freq="h")
    df = pd.DataFrame({
        "timestamp": ts,
        "value": np.sin(np.arange(72) / 5.0) * 4 + 15,
    })
    r1 = router.execute(op_id, params, {"data": df})
    r2 = router.execute(op_id, params, {"data": df})
    np.testing.assert_allclose(r1["forecast"], r2["forecast"], rtol=1e-8, atol=1e-8)
    assert r1["forecast_dates"] == r2["forecast_dates"]


def test_p3_w3_stateless_deterministic_replay(router, classification_data):
    rng = np.random.RandomState(2)
    df = pd.DataFrame(rng.randn(70, 3), columns=list("abc"))
    for op_id, params in [
        ("hdbscan_cluster", {"min_cluster_size": 5}),
        ("gmm_cluster", {"n_components": 3, "random_state": 0}),
        ("optics_cluster", {"min_samples": 5}),
    ]:
        r1 = router.execute(op_id, params, {"data": df})
        r2 = router.execute(op_id, params, {"data": df})
        np.testing.assert_array_equal(r1["labels"], r2["labels"])
        assert r1["n_clusters_found"] == r2["n_clusters_found"]

    features, target = classification_data
    for op_id, params in [
        ("adasyn_oversample", {"n_neighbors": 3, "random_state": 0}),
        ("stratified_sample", {"sample_ratio": 0.5, "random_state": 0}),
    ]:
        r1 = router.execute(op_id, params, {"features": features, "target": target})
        r2 = router.execute(op_id, params, {"features": features, "target": target})
        if "features" in r1:
            pd.testing.assert_frame_equal(r1["features"], r2["features"], check_dtype=False)
        np.testing.assert_array_equal(r1["target"], r2["target"])

    imb1 = router.execute("class_imbalance_check", {}, {"target": target})
    imb2 = router.execute("class_imbalance_check", {}, {"target": target})
    assert imb1 == imb2

    ba1 = router.execute("balanced_accuracy", {}, {"y_true": [0, 1, 0, 1], "y_pred": [0, 1, 1, 0]})
    ba2 = router.execute("balanced_accuracy", {}, {"y_true": [0, 1, 0, 1], "y_pred": [0, 1, 1, 0]})
    assert ba1["score"] == ba2["score"]

    pb1 = router.execute("pinball_loss", {"quantile": 0.9}, {"y_true": [1, 2, 3], "y_pred": [1.1, 1.8, 3.2]})
    pb2 = router.execute("pinball_loss", {"quantile": 0.9}, {"y_true": [1, 2, 3], "y_pred": [1.1, 1.8, 3.2]})
    assert pb1["score"] == pytest.approx(pb2["score"])
# @AI_GENERATED: end
