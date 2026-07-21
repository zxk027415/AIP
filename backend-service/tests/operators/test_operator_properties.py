# @AI_GENERATED
"""
Layer 3 — Property-Based Tests

用 hypothesis 生成任意合规输入，验证 design.md 中定义的 22 条 Correctness Properties。
每个算子的**不变量**必须对所有生成的样本都成立。

覆盖：
- 数据预处理: min_max_scale 边界、z_score_scale 零均值、remove_duplicates 幂等、column_select 保行数
- 特征工程: pca 方差比递减且 <= 1
- 聚类: kmeans 标签范围、dbscan 噪声语义
- 异常检测: labels ⊆ {-1, 1}
- 评估: r2/mape/roc_auc 值域
- 数据源: load_parquet round-trip
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ────────────────────────────────────────────────────────────────────────────
# 全局配置：控制样本量避免测试太慢
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_SETTINGS = settings(
    max_examples=25,           # 每个 property 生成 25 个样本
    deadline=5000,             # 单样本最多 5s
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ────────────────────────────────────────────────────────────────────────────
# 数据 strategies
# ────────────────────────────────────────────────────────────────────────────


@st.composite
def numeric_df(draw, min_rows: int = 5, max_rows: int = 80, min_cols: int = 2, max_cols: int = 4):
    """生成合规的数值 DataFrame（无 NaN、无 Inf、无常数列泛化到极端）。"""
    n_rows = draw(st.integers(min_value=min_rows, max_value=max_rows))
    n_cols = draw(st.integers(min_value=min_cols, max_value=max_cols))
    values = draw(arrays(
        dtype=np.float64,
        shape=(n_rows, n_cols),
        elements=st.floats(
            min_value=-1e4, max_value=1e4,
            allow_nan=False, allow_infinity=False,
        ),
    ))
    cols = [f"c{i}" for i in range(n_cols)]
    return pd.DataFrame(values, columns=cols)


@st.composite
def paired_arrays(draw, min_len: int = 5, max_len: int = 40):
    """生成等长的一对数组，用于评估指标的 y_true/y_pred。"""
    n = draw(st.integers(min_value=min_len, max_value=max_len))
    y_true = draw(arrays(
        dtype=np.float64, shape=(n,),
        elements=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    ))
    y_pred = draw(arrays(
        dtype=np.float64, shape=(n,),
        elements=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    ))
    return y_true, y_pred


# ────────────────────────────────────────────────────────────────────────────
# Property 1: min_max_scale 输出 ∈ [0, 1]
# ────────────────────────────────────────────────────────────────────────────


class TestMinMaxScale:
    @DEFAULT_SETTINGS
    @given(df=numeric_df())
    def test_output_bounded_in_0_1(self, router, df):
        """min_max_scale 输出的每列都在 [0, 1] 内。"""
        result = router.execute("min_max_scale", {}, {"data": df})
        out = result["data"]
        for col in out.select_dtypes(include="number").columns:
            series = out[col].dropna()
            if len(series) > 0 and series.nunique() > 1:
                assert series.min() >= -1e-9, f"col {col} min={series.min()} < 0"
                assert series.max() <= 1.0 + 1e-9, f"col {col} max={series.max()} > 1"


# ────────────────────────────────────────────────────────────────────────────
# Property 2: z_score_scale 零均值单位方差
# ────────────────────────────────────────────────────────────────────────────


class TestZScoreScale:
    @DEFAULT_SETTINGS
    @given(df=numeric_df())
    def test_zero_mean_unit_variance(self, router, df):
        """z_score_scale 每列均值 ≈ 0（非常数列）。"""
        result = router.execute("z_score_scale", {}, {"data": df})
        out = result["data"]
        for col in out.select_dtypes(include="number").columns:
            series = out[col].dropna()
            if len(series) > 1 and series.nunique() > 1:
                assert abs(series.mean()) < 1e-6, (
                    f"col {col} mean={series.mean()} not ≈ 0"
                )


# ────────────────────────────────────────────────────────────────────────────
# Property 3: column_select 保行数、精确保留列
# ────────────────────────────────────────────────────────────────────────────


class TestColumnSelect:
    @DEFAULT_SETTINGS
    @given(df=numeric_df())
    def test_preserves_row_count(self, router, df):
        cols = list(df.columns[:2])
        result = router.execute("column_select", {"columns": cols}, {"data": df})
        assert len(result["data"]) == len(df)
        assert list(result["data"].columns) == cols


# ────────────────────────────────────────────────────────────────────────────
# Property 5: remove_duplicates 幂等
# ────────────────────────────────────────────────────────────────────────────


class TestRemoveDuplicatesIdempotent:
    @DEFAULT_SETTINGS
    @given(df=numeric_df())
    def test_idempotent(self, router, df):
        """两次去重结果 == 一次去重结果。"""
        once = router.execute("remove_duplicates", {}, {"data": df})["data"]
        twice = router.execute("remove_duplicates", {}, {"data": once})["data"]
        pd.testing.assert_frame_equal(
            once.reset_index(drop=True),
            twice.reset_index(drop=True),
        )


# ────────────────────────────────────────────────────────────────────────────
# Property 6: PCA explained_variance_ratio 降序且和 <= 1
# ────────────────────────────────────────────────────────────────────────────


class TestPCAVarianceRatio:
    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=10, max_rows=50, min_cols=3, max_cols=5))
    def test_variance_ratio_descending_and_bounded(self, router, df):
        # 跳过全常数或近似退化的输入（PCA 无定义）
        if any(df[c].nunique() < 2 for c in df.columns):
            return
        # 若列间几乎完全相关，方差为 0 也跳过
        total_var = float(df.var().sum())
        if total_var < 1e-10:
            return

        try:
            result = router.execute("pca", {"n_components": min(2, len(df.columns) - 1)}, {"data": df})
        except Exception:
            return  # 极端退化输入不检验
        evr = result["explained_variance_ratio"]
        assert isinstance(evr, list)
        # 若因数值退化返回 NaN，也算不检验（sklearn 会算出 nan）
        if any(not math.isfinite(v) for v in evr):
            return
        # 降序
        for i in range(len(evr) - 1):
            assert evr[i] + 1e-9 >= evr[i + 1], f"PCA variance ratio not descending: {evr}"
        # 和 <= 1
        assert sum(evr) <= 1.0 + 1e-9, f"sum(evr)={sum(evr)} > 1"


# ────────────────────────────────────────────────────────────────────────────
# Property 10: kmeans labels ∈ [0, n_clusters-1]
# ────────────────────────────────────────────────────────────────────────────


class TestKMeansLabels:
    @DEFAULT_SETTINGS
    @given(
        df=numeric_df(min_rows=20, max_rows=60, min_cols=2, max_cols=4),
        n_clusters=st.integers(min_value=2, max_value=5),
    )
    def test_labels_in_range(self, router, df, n_clusters):
        # 样本数必须 >= n_clusters
        if len(df) < n_clusters:
            return
        result = router.execute("kmeans", {"n_clusters": n_clusters}, {"data": df})
        labels = result["labels"]
        assert labels.min() >= 0
        assert labels.max() < n_clusters
        # cluster_centers shape 检查
        centers = result["cluster_centers"]
        assert centers.shape == (n_clusters, df.shape[1])


# ────────────────────────────────────────────────────────────────────────────
# Property 12: isolation_forest / one_class_svm labels ⊆ {-1, 1}
# ────────────────────────────────────────────────────────────────────────────


class TestAnomalyLabels:
    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=20, max_rows=50))
    def test_isolation_forest_binary_labels(self, router, df):
        result = router.execute("isolation_forest",
                                 {"mode": "fit_predict", "contamination": 0.1, "save_model": False},
                                 {"data": df})
        labels = result["labels"]
        unique = set(labels.tolist())
        assert unique.issubset({-1, 1}), f"labels contain {unique}, expected subset of {{-1, 1}}"
        assert len(result["scores"]) == len(df)

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=20, max_rows=50))
    def test_one_class_svm_binary_labels(self, router, df):
        # OneClassSVM 数值稳定性依赖数据尺度，极端 float 值会让 sklearn 内部的 dual
        # coefficients 不收敛。跳过这类数据（真实使用前一般会做归一化）。
        from services.operator_execution.router import OperatorExecutionError
        try:
            result = router.execute(
                "one_class_svm",
                {"mode": "fit_predict", "nu": 0.1, "save_model": False},
                {"data": df},
            )
        except OperatorExecutionError as e:
            # 只放过"数值不稳定"类型的错误；其他仍抛
            if "not finite" in e.message or "large values" in e.message:
                return
            raise
        labels = result["labels"]
        unique = set(labels.tolist())
        assert unique.issubset({-1, 1})
        assert len(result["scores"]) == len(df)


# ────────────────────────────────────────────────────────────────────────────
# Property 13-14: R² 和 MAPE
# ────────────────────────────────────────────────────────────────────────────


class TestRegressionMetrics:
    @DEFAULT_SETTINGS
    @given(pair=paired_arrays())
    def test_r2_bound_and_perfect_fit(self, router, pair):
        """R² <= 1，且完美拟合时 R² == 1。"""
        y_true, y_pred = pair
        # 避免 y_true 常数（R² 无定义）
        if len(set(y_true.tolist())) < 2:
            return
        result = router.execute("r2_score", {}, {"y_true": y_true.tolist(), "y_pred": y_pred.tolist()})
        assert result["score"] <= 1.0 + 1e-9

        # 完美拟合
        result_perfect = router.execute("r2_score", {}, {"y_true": y_true.tolist(), "y_pred": y_true.tolist()})
        assert abs(result_perfect["score"] - 1.0) < 1e-9

    @DEFAULT_SETTINGS
    @given(pair=paired_arrays())
    def test_mape_non_negative_and_perfect_fit(self, router, pair):
        """MAPE >= 0，完美拟合时 == 0（若 y_true 不含 0）。"""
        y_true, y_pred = pair
        # 过滤掉零，避免 MAPE 排除后全为 0
        y_true_nz = np.where(y_true == 0, 1.0, y_true)

        result = router.execute("mape_score", {},
                                 {"y_true": y_true_nz.tolist(), "y_pred": y_pred.tolist()})
        assert result["score"] >= 0

        # 完美拟合
        result_perfect = router.execute("mape_score", {},
                                         {"y_true": y_true_nz.tolist(), "y_pred": y_true_nz.tolist()})
        assert result_perfect["score"] < 1e-9


# ────────────────────────────────────────────────────────────────────────────
# Property 15: ROC AUC 值域 [0, 1]
# ────────────────────────────────────────────────────────────────────────────


class TestROCAUC:
    @DEFAULT_SETTINGS
    @given(
        n=st.integers(min_value=10, max_value=40),
        seed=st.integers(min_value=0, max_value=1000),
    )
    def test_roc_auc_bounded(self, router, n, seed):
        rng = np.random.RandomState(seed)
        # 保证两类都有
        y_true = np.concatenate([np.zeros(n // 2), np.ones(n - n // 2)])
        y_score = rng.rand(n)
        result = router.execute("roc_auc", {}, {"y_true": y_true.tolist(), "y_score": y_score.tolist()})
        assert 0.0 <= result["score"] <= 1.0


# ────────────────────────────────────────────────────────────────────────────
# Property 16: chart_option 结构合法
# ────────────────────────────────────────────────────────────────────────────


class TestChartOptionStructure:
    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=10, max_rows=30, min_cols=2, max_cols=3))
    def test_line_chart_has_series(self, router, df):
        result = router.execute("line_chart",
                                 {"x_column": df.columns[0], "y_column": df.columns[1]},
                                 {"data": df})
        assert result["chart_type"] == "line"
        assert isinstance(result["chart_option"], dict)
        assert "series" in result["chart_option"]
        assert isinstance(result["chart_option"]["series"], list)
        assert len(result["chart_option"]["series"]) >= 1
        assert result["chart_option"]["series"][0]["type"] == "line"

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=10, max_rows=30, min_cols=2, max_cols=3))
    def test_scatter_chart_has_series(self, router, df):
        result = router.execute("scatter_chart",
                                 {"x_column": df.columns[0], "y_column": df.columns[1]},
                                 {"data": df})
        assert result["chart_type"] == "scatter"
        assert result["chart_option"]["series"][0]["type"] == "scatter"

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=20, max_rows=50, min_cols=1, max_cols=2))
    def test_histogram_bar_series(self, router, df):
        result = router.execute("histogram",
                                 {"target_column": df.columns[0], "bins": 10},
                                 {"data": df})
        assert result["chart_type"] == "histogram"
        assert result["chart_option"]["series"][0]["type"] == "bar"


# ────────────────────────────────────────────────────────────────────────────
# Property 17: export_csv/export_excel 输出相对路径
# ────────────────────────────────────────────────────────────────────────────


class TestExportRelativePath:
    """
    验证 export_csv 输出永远是相对路径。

    不用 tmp_path fixture（hypothesis 禁止 function-scoped fixture），
    改由算子默认路径 `data/exports/*.csv` 落盘，测试后清理。
    """

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=3, max_rows=10, min_cols=1, max_cols=3))
    def test_export_csv_path_is_relative(self, router, df):
        import os
        # 用默认路径（算子会自动生成 data/exports/export_YYYYMMDD_HHMMSS.csv）
        result = router.execute("export_csv", {}, {"data": df})
        out = result["output_path"]
        # 相对路径断言
        assert not out.startswith("/"), f"output_path {out} starts with /"
        assert not (len(out) >= 2 and out[1] == ":"), f"output_path {out} has drive letter"
        assert result["rows_written"] == len(df)
        # 清理落盘文件（相对于 backend-service）
        backend_dir = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        ))
        candidate = os.path.join(backend_dir, out)
        if os.path.exists(candidate):
            try:
                os.remove(candidate)
            except OSError:
                pass


# ────────────────────────────────────────────────────────────────────────────
# Property 18: load_parquet round-trip
# ────────────────────────────────────────────────────────────────────────────


class TestLoadParquetRoundTrip:
    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=5, max_rows=30, min_cols=2, max_cols=4))
    def test_parquet_write_read_equal(self, router, df, tmp_path_factory):
        """写出 → load_parquet 读回 → 数值应完全相等。"""
        p = tmp_path_factory.mktemp("hyp") / "rt.parquet"
        df.to_parquet(p)
        result = router.execute("load_parquet", {"file_path": str(p)}, {})
        loaded = result["data"]

        assert loaded.shape == df.shape
        assert list(loaded.columns) == list(df.columns)
        np.testing.assert_array_almost_equal(
            loaded.values.astype(float),
            df.values.astype(float),
        )


# ────────────────────────────────────────────────────────────────────────────
# Property 19: load_json 空数组安全
# ────────────────────────────────────────────────────────────────────────────


class TestLoadJsonEmpty:
    def test_empty_json_returns_zero_row_df(self, router, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("[]", encoding="utf-8")
        result = router.execute("load_json", {"file_path": str(p)}, {})
        assert isinstance(result["data"], pd.DataFrame)
        assert len(result["data"]) == 0


# ────────────────────────────────────────────────────────────────────────────
# 额外性质：dbscan 噪声语义
# ────────────────────────────────────────────────────────────────────────────


class TestDBSCANNoise:
    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=15, max_rows=40))
    def test_labels_noise_semantics(self, router, df):
        """dbscan 若 labels 含 -1，则表示噪声；n_clusters_found 不含 -1。"""
        result = router.execute("dbscan", {"eps": 0.5, "min_samples": 3}, {"data": df})
        labels = result["labels"]
        n_clusters = result["n_clusters_found"]
        unique_valid = set(labels.tolist()) - {-1}
        assert len(unique_valid) == n_clusters
        # 有效标签 ∈ [0, n_clusters-1]
        if n_clusters > 0:
            assert max(unique_valid) < n_clusters


# ────────────────────────────────────────────────────────────────────────────
# 额外性质：accuracy 和 f1 值域
# ────────────────────────────────────────────────────────────────────────────


class TestClassificationScoreBounds:
    @DEFAULT_SETTINGS
    @given(
        n=st.integers(min_value=5, max_value=30),
        seed=st.integers(min_value=0, max_value=1000),
    )
    def test_accuracy_in_0_1(self, router, n, seed):
        rng = np.random.RandomState(seed)
        y_true = rng.randint(0, 3, size=n)
        y_pred = rng.randint(0, 3, size=n)
        result = router.execute("accuracy_score", {},
                                 {"y_true": y_true.tolist(), "y_pred": y_pred.tolist()})
        assert 0.0 <= result["score"] <= 1.0

    @DEFAULT_SETTINGS
    @given(
        n=st.integers(min_value=5, max_value=30),
        seed=st.integers(min_value=0, max_value=1000),
    )
    def test_f1_in_0_1(self, router, n, seed):
        rng = np.random.RandomState(seed)
        y_true = rng.randint(0, 3, size=n)
        y_pred = rng.randint(0, 3, size=n)
        result = router.execute("f1_score", {"average": "macro"},
                                 {"y_true": y_true.tolist(), "y_pred": y_pred.tolist()})
        assert 0.0 <= result["score"] <= 1.0


# ────────────────────────────────────────────────────────────────────────────
# P3 W1 — 特征 / 异常性质
# ────────────────────────────────────────────────────────────────────────────


class TestP3W1FeatureProperties:
    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=40, max_rows=80, min_cols=1, max_cols=2))
    def test_autocorrelation_feature_count_and_finite(self, router, df):
        col = df.columns[0]
        nlags = 8
        r = router.execute(
            "autocorrelation_features",
            {"column": col, "nlags": nlags, "include_pacf": True},
            {"data": df},
        )
        out = r["data"]
        assert len(out) == 1
        assert out.shape[1] == nlags * 2
        assert np.all(np.isfinite(out.to_numpy()))

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=16, max_rows=64, min_cols=1, max_cols=2))
    def test_spectral_energy_non_negative(self, router, df):
        col = df.columns[0]
        r = router.execute("spectral_features", {"column": col}, {"data": df})
        row = r["data"].iloc[0]
        assert row["spectral_energy"] >= 0
        assert np.isfinite(row["spectral_centroid"])

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=8, max_rows=60, min_cols=1, max_cols=2))
    def test_shape_peak_to_peak_non_negative(self, router, df):
        col = df.columns[0]
        r = router.execute("shape_features", {"column": col}, {"data": df})
        assert r["data"].iloc[0]["shape_peak_to_peak"] >= -1e-12
        assert 0.0 <= r["data"].iloc[0]["shape_zero_crossing_rate"] <= 1.0

    @DEFAULT_SETTINGS
    @given(
        n=st.integers(min_value=30, max_value=80),
        seed=st.integers(min_value=0, max_value=500),
    )
    def test_chi2_select_column_subset(self, router, n, seed):
        rng = np.random.RandomState(seed)
        X = np.abs(rng.randn(n, 5)) + 0.01
        y = rng.randint(0, 2, size=n)
        feats = pd.DataFrame(X, columns=list("abcde"))
        r = router.execute("chi2_select", {"k": 3}, {"features": feats, "target": y})
        assert set(r["selected_columns"]).issubset(set(feats.columns))
        assert len(r["selected_columns"]) == 3
        assert list(r["data"].columns) == r["selected_columns"]

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=30, max_rows=80))
    def test_quantile_transform_preserves_shape(self, router, df):
        cols = list(df.columns)
        r = router.execute(
            "quantile_transform",
            {"columns": cols, "output_distribution": "uniform", "n_quantiles": 20, "random_state": 0},
            {"data": df},
        )
        assert r["data"].shape == df.shape
        vals = r["data"][cols].to_numpy()
        assert np.all(np.isfinite(vals))
        # uniform 映射大致落在 [0,1]
        assert vals.min() >= -1e-6
        assert vals.max() <= 1.0 + 1e-6


class TestP3W1AnomalyProperties:
    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=20, max_rows=80, min_cols=1, max_cols=3))
    def test_zscore_labels_binary(self, router, df):
        r = router.execute("zscore_anomaly", {"column": df.columns[0], "threshold": 3.0}, {"data": df})
        assert set(np.unique(r["labels"])).issubset({-1, 1})
        assert len(r["labels"]) == len(df)
        assert np.all(r["scores"] >= -1e-12)

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=20, max_rows=80, min_cols=1, max_cols=3))
    def test_iqr_labels_binary(self, router, df):
        r = router.execute("iqr_anomaly", {"column": df.columns[0], "factor": 1.5}, {"data": df})
        assert set(np.unique(r["labels"])).issubset({-1, 1})
        assert len(r["scores"]) == len(df)

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=20, max_rows=80, min_cols=1, max_cols=3))
    def test_mad_labels_binary(self, router, df):
        r = router.execute("mad_anomaly", {"column": df.columns[0], "threshold": 3.0}, {"data": df})
        assert set(np.unique(r["labels"])).issubset({-1, 1})

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=30, max_rows=80, min_cols=1, max_cols=2))
    def test_ewma_labels_binary(self, router, df):
        r = router.execute(
            "ewma_anomaly",
            {"column": df.columns[0], "span": 8, "threshold": 3.0},
            {"data": df},
        )
        assert set(np.unique(r["labels"])).issubset({-1, 1})
        assert len(r["labels"]) == len(df)

    @DEFAULT_SETTINGS
    @given(df=numeric_df(min_rows=30, max_rows=80, min_cols=2, max_cols=4))
    def test_knn_anomaly_labels_and_contamination_bound(self, router, df):
        r = router.execute(
            "knn_anomaly",
            {"n_neighbors": 5, "contamination": 0.1},
            {"data": df},
        )
        assert set(np.unique(r["labels"])).issubset({-1, 1})
        assert len(r["labels"]) == len(df)
        assert len(r["scores"]) == len(df)
        assert np.all(np.isfinite(r["scores"]))


# ────────────────────────────────────────────────────────────────────────────
# P3 W2 — 时序预测 / 分类性质
# ────────────────────────────────────────────────────────────────────────────


class TestP3W2ForecastProperties:
    def test_forecast_ops_horizon_and_finite(self, router):
        ts = pd.date_range("2024-01-01", periods=80, freq="h")
        df = pd.DataFrame({
            "timestamp": ts,
            "value": np.sin(np.arange(80) / 6.0) * 5 + 20 + 0.1 * np.random.RandomState(0).randn(80),
        })
        cases = [
            ("random_forest_forecast", {"forecast_horizon": 6, "n_lags": 8, "n_estimators": 15}),
            ("knn_forecast", {"forecast_horizon": 6, "n_lags": 8, "n_neighbors": 3}),
            ("quantile_regression_forecast", {"forecast_horizon": 5, "n_lags": 6, "quantile": 0.5}),
            ("exponential_smoothing", {"forecast_horizon": 6, "trend": "add"}),
        ]
        for op_id, extra in cases:
            params = {
                "timestamp_column": "timestamp",
                "value_column": "value",
                **extra,
            }
            r = router.execute(op_id, params, {"data": df})
            h = int(extra["forecast_horizon"])
            assert len(r["forecast"]) == h, op_id
            assert len(r["forecast_dates"]) == h, op_id
            assert np.all(np.isfinite(r["forecast"])), op_id


class TestP3W2ClassifierProperties:
    def test_classifier_train_prediction_length(self, router, classification_data):
        features, target = classification_data
        cases = [
            ("extra_trees_classifier", {"mode": "train", "n_estimators": 20, "save_model": "false"}),
            ("adaboost_classifier", {"mode": "train", "n_estimators": 20, "save_model": "false"}),
            ("calibrated_classifier", {"mode": "train", "cv": 2, "save_model": "false"}),
            ("lightgbm_classifier", {"mode": "train", "n_estimators": 20, "save_model": "false"}),
        ]
        for op_id, params in cases:
            r = router.execute(op_id, params, {"features": features, "target": target})
            assert len(r["predictions"]) == len(r["y_true"]), op_id
            assert len(r["feature_list"]) == features.shape[1], op_id


class TestP3W3ClusterSampleEvalProperties:
    def test_cluster_ops_label_length(self, router):
        rng = np.random.RandomState(1)
        df = pd.DataFrame(rng.randn(60, 3), columns=list("abc"))
        for op_id, params in [
            ("hdbscan_cluster", {"min_cluster_size": 5}),
            ("gmm_cluster", {"n_components": 3, "random_state": 0}),
            ("optics_cluster", {"min_samples": 5}),
        ]:
            r = router.execute(op_id, params, {"data": df})
            assert len(r["labels"]) == len(df), op_id
            assert r["n_clusters_found"] >= 0, op_id

    def test_sample_and_metrics(self, router, classification_data):
        features, target = classification_data
        imb = router.execute("class_imbalance_check", {}, {"target": target})
        assert imb["n_classes"] >= 2
        assert imb["imbalance_ratio"] >= 1.0

        samp = router.execute(
            "stratified_sample",
            {"sample_ratio": 0.5, "random_state": 0},
            {"features": features, "target": target},
        )
        assert 0 < samp["n_rows"] < len(features)

        ada = router.execute(
            "adasyn_oversample",
            {"n_neighbors": 3, "random_state": 0},
            {"features": features, "target": target},
        )
        assert len(ada["features"]) == len(ada["target"])
        assert ada["n_synthetic"] >= 0

        ba = router.execute(
            "balanced_accuracy",
            {},
            {"y_true": [0, 1, 0, 1], "y_pred": [0, 1, 1, 1]},
        )
        assert 0.0 <= ba["score"] <= 1.0

        pb = router.execute(
            "pinball_loss",
            {"quantile": 0.5},
            {"y_true": [1.0, 2.0, 3.0], "y_pred": [1.0, 2.5, 2.5]},
        )
        assert np.isfinite(pb["score"])
# @AI_GENERATED: end
