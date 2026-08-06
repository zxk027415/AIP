# @AI_GENERATED
"""
Layer 5 — 端到端 + API 集成测试

- 典型工作流串联：多算子协作跑通
- Backend Status API 层面验证
- 全量算子契约健康巡检

用合成数据（sklearn make_* / numpy.random）而非真实业务数据，
避免依赖负荷预测或光伏项目文件。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest


# ────────────────────────────────────────────────────────────────────────────
# 工作流 1：无监督聚类完整链路
#   load(synthetic) → remove_duplicates → min_max_scale → pca → kmeans → silhouette_score
# ────────────────────────────────────────────────────────────────────────────


class TestEndToEndClusteringPipeline:
    """无监督聚类完整链路。"""

    def test_clustering_pipeline_full(self, router, blob_data):
        features, _ = blob_data  # 80 samples × 2 features, 3 blobs

        # Step 1: remove_duplicates
        step1 = router.execute("remove_duplicates", {}, {"data": features})
        cleaned = step1["data"]
        assert len(cleaned) <= len(features)

        # Step 2: min_max_scale
        step2 = router.execute("min_max_scale", {}, {"data": cleaned})
        scaled = step2["data"]
        assert scaled.shape == cleaned.shape
        # 每列 min>=0 max<=1
        for col in scaled.columns:
            if scaled[col].nunique() > 1:
                assert scaled[col].min() >= -1e-9
                assert scaled[col].max() <= 1 + 1e-9

        # Step 3: kmeans (skip PCA for 2D data — degenerate)
        step3 = router.execute("kmeans", {"n_clusters": 3}, {"data": scaled})
        labels = step3["labels"]
        assert len(labels) == len(scaled)

        # Step 4: silhouette
        step4 = router.execute("silhouette_score", {},
                                {"data": scaled, "labels": labels})
        # 3 个明显的 blob，silhouette 应显著 > 0
        assert step4["score"] > 0.3, f"silhouette {step4['score']} too low for well-separated blobs"


# ────────────────────────────────────────────────────────────────────────────
# 工作流 2：分类完整链路
#   make_classification → column_select → z_score_scale → logistic_regression (train)
#     → predict → accuracy_score / f1_score
# ────────────────────────────────────────────────────────────────────────────


class TestEndToEndClassificationPipeline:
    def test_classification_pipeline_full(self, router, classification_data):
        features, target = classification_data

        # Step 1: column_select（丢一列做特征子集）
        cols = list(features.columns[:4])
        step1 = router.execute("column_select", {"columns": cols}, {"data": features})
        selected = step1["data"]
        assert list(selected.columns) == cols

        # Step 2: z_score_scale
        step2 = router.execute("z_score_scale", {}, {"data": selected})
        scaled = step2["data"]

        # Step 3: logistic_regression train
        step3 = router.execute("logistic_regression",
                                {"mode": "train"},
                                {"features": scaled, "target": target})
        model_id = step3["model_id"]
        holdout_preds = step3["predictions"]
        holdout_y = step3["y_true"]

        # Step 4: 计算 accuracy_score on holdout
        step4 = router.execute("accuracy_score", {},
                                {"y_true": holdout_y.tolist(), "y_pred": holdout_preds.tolist()})
        assert 0.0 <= step4["score"] <= 1.0

        # Step 5: 计算 f1_score
        step5 = router.execute("f1_score", {"average": "macro"},
                                {"y_true": holdout_y.tolist(), "y_pred": holdout_preds.tolist()})
        assert 0.0 <= step5["score"] <= 1.0

        # Step 6: 用 model_id 加载做全集预测
        step6 = router.execute("logistic_regression",
                                {"mode": "predict", "model_id": model_id},
                                {"predict_features": scaled})
        assert len(step6["predictions"]) == len(scaled)


# ────────────────────────────────────────────────────────────────────────────
# 工作流 3：回归完整链路
#   make_regression → min_max_scale → linear_regression (train)
#     → predict → r2_score / mape_score
# ────────────────────────────────────────────────────────────────────────────


class TestEndToEndRegressionPipeline:
    def test_regression_pipeline_full(self, router, regression_data):
        features, target = regression_data

        # Scale
        step1 = router.execute("min_max_scale", {}, {"data": features})
        scaled = step1["data"]

        # Train
        step2 = router.execute("linear_regression",
                                {"mode": "train"},
                                {"features": scaled, "target": target})
        preds = step2["predictions"]
        y_true = step2["y_true"]

        # R²
        step3 = router.execute("r2_score", {},
                                {"y_true": y_true.tolist(), "y_pred": preds.tolist()})
        assert -np.inf < step3["score"] <= 1.0

        # 完美线性场景下 R² 应该显著 > 0
        assert step3["score"] > 0.5, f"R² {step3['score']} too low for linear regression on linear data"


# ────────────────────────────────────────────────────────────────────────────
# 工作流 4：数据源 → 分析 → 可视化 → 导出
# ────────────────────────────────────────────────────────────────────────────


class TestEndToEndDataFlowPipeline:
    def test_parquet_to_analysis_to_chart_to_export(self, router, tmp_path, numeric_df_medium):
        # 造 parquet 文件
        parquet_path = tmp_path / "raw.parquet"
        numeric_df_medium.to_parquet(parquet_path)

        # Step 1: load_parquet
        step1 = router.execute("load_parquet", {"file_path": str(parquet_path)}, {})
        loaded = step1["data"]
        assert len(loaded) == len(numeric_df_medium)

        # Step 2: data_profile
        step2 = router.execute("data_profile", {}, {"data": loaded})
        assert step2["n_rows"] == len(loaded)
        assert step2["n_columns"] == len(loaded.columns)

        # Step 3: correlation_analysis
        step3 = router.execute("correlation_analysis", {"method": "pearson"}, {"data": loaded})
        assert isinstance(step3["correlation_matrix"], pd.DataFrame)

        # Step 4: heatmap_chart 用相关矩阵渲染
        step4 = router.execute("heatmap_chart", {"title": "Correlation"},
                                {"correlation_matrix": step3["correlation_matrix"]})
        assert step4["chart_type"] == "heatmap"

        # Step 5: line_chart
        step5 = router.execute("line_chart",
                                {"x_column": "a", "y_column": ["b", "c"], "title": "Trends"},
                                {"data": loaded})
        assert step5["chart_type"] == "line"
        assert len(step5["chart_option"]["series"]) == 2

        # Step 6: export_csv
        step6 = router.execute("export_csv", {}, {"data": loaded})
        assert not step6["output_path"].startswith("/")
        assert step6["rows_written"] == len(loaded)
        # 清理
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        abs_out = os.path.join(backend_dir, step6["output_path"])
        if os.path.exists(abs_out):
            os.remove(abs_out)


# ────────────────────────────────────────────────────────────────────────────
# 工作流 5：异常检测链路（fit_predict → 反查 model_id）
# ────────────────────────────────────────────────────────────────────────────


class TestEndToEndAnomalyPipeline:
    def test_anomaly_pipeline(self, router, numeric_df_medium):
        # Step 1: fit_predict 训练异常检测器
        step1 = router.execute("isolation_forest",
                                {"mode": "fit_predict", "contamination": 0.1},
                                {"data": numeric_df_medium})
        model_id = step1["model_id"]
        assert model_id

        # Step 2: 用 model_id 对新数据 predict
        # 造点相似分布的新数据
        rng = np.random.RandomState(999)
        new_data = pd.DataFrame(rng.randn(20, 5), columns=list("abcde"))

        step2 = router.execute("isolation_forest",
                                {"mode": "predict", "model_id": model_id},
                                {"data": new_data})
        assert len(step2["labels"]) == 20
        assert set(step2["labels"].tolist()).issubset({-1, 1})


# ────────────────────────────────────────────────────────────────────────────
# 工作流 6：P3 W1 特征 + 规则异常（合成数据）
#   series → shape/spectral/acf → quantile_transform → zscore/iqr/knn
# ────────────────────────────────────────────────────────────────────────────


class TestEndToEndP3W1FeatureAnomalyPipeline:
    def test_p3_w1_feature_and_anomaly_pipeline(self, router):
        rng = np.random.RandomState(42)
        t = np.linspace(0, 12, 120)
        series = pd.DataFrame({
            "value": np.sin(t) + 0.1 * rng.randn(120),
            "i_cal": np.cos(t / 2) + 0.05 * rng.randn(120),
        })

        r_shape = router.execute("shape_features", {"column": "value"}, {"data": series})
        assert len(r_shape["data"]) == 1

        r_spec = router.execute("spectral_features", {"column": "value"}, {"data": series})
        assert "spectral_centroid" in r_spec["data"].columns

        r_acf = router.execute(
            "autocorrelation_features",
            {"column": "value", "nlags": 6, "include_pacf": False},
            {"data": series},
        )
        assert r_acf["data"].shape[1] == 6

        r_qt = router.execute(
            "quantile_transform",
            {"columns": ["value", "i_cal"], "n_quantiles": 30, "random_state": 0},
            {"data": series},
        )
        scaled = r_qt["data"]

        # 用变换后的序列做规则异常 + 近邻异常
        r_z = router.execute("zscore_anomaly", {"column": "value", "threshold": 3.0}, {"data": scaled})
        r_iqr = router.execute("iqr_anomaly", {"column": "value", "factor": 1.5}, {"data": scaled})
        r_mad = router.execute("mad_anomaly", {"column": "value", "threshold": 3.0}, {"data": scaled})
        r_ewma = router.execute(
            "ewma_anomaly", {"column": "value", "span": 12, "threshold": 3.0}, {"data": scaled},
        )
        r_knn = router.execute(
            "knn_anomaly", {"n_neighbors": 5, "contamination": 0.1}, {"data": scaled},
        )
        for name, rr in [
            ("zscore", r_z), ("iqr", r_iqr), ("mad", r_mad), ("ewma", r_ewma), ("knn", r_knn),
        ]:
            assert len(rr["labels"]) == len(scaled), name
            assert set(np.unique(rr["labels"])).issubset({-1, 1}), name

        # chi2：非负特征 + 伪标签
        feats = scaled.abs()
        y = (feats["value"] > feats["value"].median()).astype(int).values
        r_chi = router.execute("chi2_select", {"k": 1}, {"features": feats, "target": y})
        assert len(r_chi["selected_columns"]) == 1


class TestEndToEndP3W2ForecastClassifyPipeline:
    """L5：合成时序预测 + 分类链路。"""

    def test_p3_w2_forecast_and_classify_pipeline(self, router):
        rng = np.random.RandomState(0)
        ts = pd.date_range("2024-01-01", periods=96, freq="h")
        series = pd.DataFrame({
            "timestamp": ts,
            "value": np.sin(np.arange(96) / 8.0) * 10 + 50 + 0.2 * rng.randn(96),
        })
        for op_id, params in [
            ("random_forest_forecast", {"n_estimators": 15, "n_lags": 10, "forecast_horizon": 6}),
            ("knn_forecast", {"n_neighbors": 3, "n_lags": 10, "forecast_horizon": 6}),
            ("quantile_regression_forecast", {"n_lags": 8, "forecast_horizon": 5, "quantile": 0.5}),
            ("exponential_smoothing", {"forecast_horizon": 6, "trend": "add"}),
        ]:
            r = router.execute(
                op_id,
                {"timestamp_column": "timestamp", "value_column": "value", **params},
                {"data": series},
            )
            assert len(r["forecast"]) == params["forecast_horizon"], op_id

        # 分类：合成二分类
        X = pd.DataFrame(rng.randn(80, 4), columns=list("abcd"))
        y = (X["a"] + X["b"] > 0).astype(int).values
        for op_id, params in [
            ("extra_trees_classifier", {"n_estimators": 20, "save_model": "false"}),
            ("adaboost_classifier", {"n_estimators": 20, "save_model": "false"}),
            ("calibrated_classifier", {"cv": 2, "save_model": "false"}),
            ("lightgbm_classifier", {"n_estimators": 20, "save_model": "false"}),
        ]:
            r = router.execute(
                op_id, {"mode": "train", **params}, {"features": X, "target": y},
            )
            assert "predictions" in r and "model_id" in r, op_id
            pred = router.execute(
                op_id,
                {"mode": "predict"},
                {"model": r["model"], "predict_features": X.head(10)},
            )
            assert len(pred["predictions"]) == 10, op_id


class TestEndToEndP3W3ClusterSampleEvalPipeline:
    """L5：聚类 → 不平衡诊断 → 过采样/分层 → 评估。"""

    def test_p3_w3_cluster_sample_eval_pipeline(self, router):
        rng = np.random.RandomState(3)
        # 两团点
        a = rng.randn(40, 2) + np.array([0, 0])
        b = rng.randn(40, 2) + np.array([5, 5])
        df = pd.DataFrame(np.vstack([a, b]), columns=["x", "y"])
        for op_id, params in [
            ("hdbscan_cluster", {"min_cluster_size": 8}),
            ("gmm_cluster", {"n_components": 2, "random_state": 0}),
            ("optics_cluster", {"min_samples": 5}),
        ]:
            r = router.execute(op_id, params, {"data": df})
            assert len(r["labels"]) == len(df), op_id

        # 不平衡标签
        X = pd.DataFrame(rng.randn(100, 3), columns=list("abc"))
        y = np.array([0] * 85 + [1] * 15)
        imb = router.execute("class_imbalance_check", {"imbalance_threshold": 2.0}, {"target": y})
        assert imb["is_imbalanced"] is True

        ada = router.execute(
            "adasyn_oversample", {"n_neighbors": 3, "random_state": 0},
            {"features": X, "target": y},
        )
        assert ada["n_synthetic"] > 0
        samp = router.execute(
            "stratified_sample", {"sample_ratio": 0.4, "random_state": 0},
            {"features": ada["features"], "target": ada["target"]},
        )
        assert samp["n_rows"] > 0

        # 伪预测评估
        y_true = samp["target"]
        y_pred = y_true.copy()
        y_pred[: max(1, len(y_pred) // 10)] = 1 - y_pred[: max(1, len(y_pred) // 10)]
        ba = router.execute("balanced_accuracy", {}, {"y_true": y_true, "y_pred": y_pred})
        assert 0.0 <= ba["score"] <= 1.0

        pb = router.execute(
            "pinball_loss", {"quantile": 0.5},
            {"y_true": rng.randn(20), "y_pred": rng.randn(20)},
        )
        assert np.isfinite(pb["score"])


class TestEndToEndLegacyWaveL1Pipeline:
    """L5：Legacy L1 + ks_test 合成巡检（逐个执行 + 短链路）。"""

    def test_legacy_wave_l1_ops_execute_once(self, router, tmp_path):
        import importlib.util

        legacy_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "legacy_smoke_cases.py",
        )
        spec = importlib.util.spec_from_file_location("legacy_l5", legacy_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        p4_ops = sorted(mod.LEGACY_WAVE_L1 | mod.P4_NEW_OPERATORS)
        by_id = {s[0]: s for s in mod.legacy_wave_l1_smoke_specs()}

        for op_id in p4_ops:
            _op, params_builder, inputs_builder, expected_keys, _kind = by_id[op_id]
            params = params_builder(tmp_path)
            inputs = inputs_builder(tmp_path)
            result = router.execute(op_id, params, inputs)
            for key in expected_keys:
                assert key in result, f"{op_id} missing {key}"

    def test_legacy_load_to_features_short_chain(self, router, tmp_path):
        import importlib.util

        legacy_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "legacy_smoke_cases.py",
        )
        spec = importlib.util.spec_from_file_location("legacy_l5_chain", legacy_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        csv_path = mod._make_tmp_csv(tmp_path)
        df = router.execute(
            "load_csv",
            {"file_path": csv_path, "timestamp_column": "record_time"},
            {},
        )["data"]
        df = router.execute(
            "handle_missing",
            {"time_field": "record_time", "target_column": "value", "method": "linear"},
            {"data": df},
        )["data"]
        df = router.execute(
            "create_lag_features",
            {"target_column": "value", "lags": [1]},
            {"data": df},
        )["data"]
        assert "value_lag_1" in df.columns

        seg_a = df["value"].iloc[:10].tolist()
        seg_b = df["value"].iloc[10:20].tolist()
        ks = router.execute("ks_test", {"alpha": 0.05}, {"sample_a": seg_a, "sample_b": seg_b})
        assert "pvalue" in ks


class TestEndToEndFeatureBetaPipeline:
    """L5：P4-β 特征工程合成巡检 + 短链路。"""

    def test_feature_beta_ops_execute_once(self, router, tmp_path):
        import importlib.util

        feat_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "feature_smoke_cases.py",
        )
        spec = importlib.util.spec_from_file_location("feat_l5", feat_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        for op_id in sorted(mod.P4_BETA_FE):
            by_id = {s[0]: s for s in mod.feature_beta_smoke_specs()}
            _op, params_builder, inputs_builder, expected_keys, _kind = by_id[op_id]
            result = router.execute(op_id, params_builder(tmp_path), inputs_builder(tmp_path))
            for key in expected_keys:
                assert key in result, f"{op_id} missing {key}"

    def test_feature_time_calendar_chain(self, router):
        ts = pd.date_range("2024-01-01", periods=72, freq="h")
        df = pd.DataFrame({"record_time": ts, "value": np.linspace(1, 2, 72)})
        df = router.execute("extract_time_features", {
            "timestamp_column": "record_time", "features": ["hour"],
        }, {"data": df})["data"]
        df = router.execute("workday_features", {"time_field": "record_time"}, {"data": df})["data"]
        df = router.execute("shift_features", {"time_field": "record_time"}, {"data": df})["data"]
        df = router.execute("pct_change_features", {"target_column": "value"}, {"data": df})["data"]
        assert "is_workday" in df.columns and "value_pct_change_1" in df.columns


class TestEndToEndEvalBetaPipeline:
    """L5：P4-β 评估/采样合成巡检 + 短链路。"""

    def test_eval_beta_ops_execute_once(self, router, tmp_path):
        import importlib.util

        eval_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "eval_smoke_cases.py",
        )
        spec = importlib.util.spec_from_file_location("eval_l5", eval_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        by_id = {s[0]: s for s in mod.eval_beta_smoke_specs()}
        for op_id in sorted(mod.P4_BETA_EVAL):
            _op, params_builder, inputs_builder, expected_keys, _kind = by_id[op_id]
            result = router.execute(op_id, params_builder(tmp_path), inputs_builder(tmp_path))
            for key in expected_keys:
                assert key in result, f"{op_id} missing {key}"

    def test_smote_rfc_eval_short_chain(self, router):
        from sklearn.datasets import make_classification

        x, y = make_classification(
            n_samples=80, n_features=5, n_informative=3, n_classes=2, random_state=1,
        )
        feat = pd.DataFrame(x, columns=[f"f{i}" for i in range(5)])
        sm = router.execute("smote_oversample", {"limit": 45}, {"features": feat, "target": y})
        rfc = router.execute(
            "random_forest_classifier",
            {"mode": "train", "n_estimators": 20, "save_model": "false"},
            {"features": sm["features"], "target": sm["target"]},
        )
        pr = router.execute(
            "precision_recall_f1", {},
            {"y_true": rfc["y_true"], "y_pred": rfc["predictions"]},
        )
        assert "f1" in pr


class TestEndToEndP4GammaPipeline:
    """L5：P4-γ 预测栈 + 模型 IO 合成巡检。"""

    def test_gamma_ops_execute_once(self, router, tmp_path):
        import importlib.util

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "p4_gamma_smoke_cases.py")
        spec = importlib.util.spec_from_file_location("gamma_l5", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        by_id = {s[0]: s for s in mod.gamma_smoke_specs()}
        skip = {"load_api", "lightgbm_forecast", "catboost_forecast", "auto_tune_lightgbm", "auto_tune_catboost"}
        for op_id in sorted(mod.P4_GAMMA - skip):
            if op_id in {"lightgbm_forecast", "catboost_forecast", "auto_tune_lightgbm", "auto_tune_catboost"}:
                continue
            _op, pb, ib, keys, _k = by_id[op_id]
            result = router.execute(op_id, pb(tmp_path), ib(tmp_path))
            for key in keys:
                assert key in result, f"{op_id} missing {key}"

    def test_forecast_artifact_short_chain(self, router, tmp_path):
        import importlib.util

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "p4_gamma_smoke_cases.py")
        spec = importlib.util.spec_from_file_location("gamma_chain", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        fmx = mod._forecast_matrix_inputs()
        ridge = router.execute("ridge_forecast", {"mode": "train", "alpha": 1.0}, fmx)
        saved = router.execute(
            "save_model_artifact",
            {"model_ref": "gamma-l5-ridge"},
            {"model": ridge["model"], "feature_list": list(fmx["train_features"].columns)},
        )
        loaded = router.execute("load_model_artifact", {"model_ref": saved["model_ref"]}, {})
        assert loaded["model"] is not None


class TestEndToEndBatch67SoftCoverage:
    """
    L5：对上一批已有 L2+L6 的软目标算子做合成链路巡检（逐个执行一次）。
    覆盖登记见 services.operator_test_coverage.LAYER5_SYNTHETIC_E2E。
    """

    SOFT_OPS = [
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
        "roc_auc", "silhouette_score",
    ]

    def test_batch67_soft_ops_execute_once(self, router, tmp_path):
        import importlib.util

        smoke_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "test_operators_smoke.py",
        )
        spec = importlib.util.spec_from_file_location("op_smoke_l5", smoke_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        by_id = {c[0]: c for c in mod.SMOKE_CASES}

        missing = [op for op in self.SOFT_OPS if op not in by_id]
        assert not missing, f"SMOKE 缺少: {missing}"

        for op_id in self.SOFT_OPS:
            _op, params_builder, inputs_builder, expected_keys, _extra = by_id[op_id]
            params = params_builder(tmp_path)
            if params.get("mode") == "train":
                params = {**params, "save_model": "false"}
            inputs = inputs_builder(tmp_path)
            result = router.execute(op_id, params, inputs)
            assert isinstance(result, dict), op_id
            for key in expected_keys:
                assert key in result, f"{op_id} missing {key}"

        # prophet：独立烟测入参（不在 SMOKE_CASES）
        try:
            import prophet  # noqa: F401
            ts = pd.date_range("2024-01-01", periods=40, freq="h")
            pdf = pd.DataFrame({"ds": ts, "y": np.sin(np.arange(40) / 5.0) * 10})
            pr = router.execute(
                "prophet",
                {"timestamp_column": "ds", "value_column": "y", "forecast_horizon": 4, "freq": "h"},
                {"data": pdf},
            )
            assert len(pr["forecast"]) == 4
        except ImportError:
            pass


# ────────────────────────────────────────────────────────────────────────────
# API 层测试：Backend Status API
# ────────────────────────────────────────────────────────────────────────────


class TestBackendStatusAPI:
    """通过 FastAPI TestClient 验证 /api/functions/backend-status 接口。"""

    @pytest.fixture(scope="class")
    def api_client(self):
        """启动 FastAPI 应用做集成测试。"""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")

        # 独立小 app 避免拉起整个 main.py（依赖过多）
        from fastapi import FastAPI
        from api.functions import router as functions_router

        app = FastAPI()
        app.include_router(functions_router)
        return TestClient(app)

    def test_backend_status_endpoint_returns_200(self, api_client):
        response = api_client.get("/api/functions/backend-status")
        assert response.status_code == 200

    def test_backend_status_response_shape(self, api_client):
        response = api_client.get("/api/functions/backend-status")
        body = response.json()
        assert "total_registered" in body
        assert "registered_operators" in body
        assert isinstance(body["total_registered"], int)
        assert isinstance(body["registered_operators"], list)
        assert body["total_registered"] == len(body["registered_operators"])

    def test_backend_status_contains_known_operators(self, api_client):
        response = api_client.get("/api/functions/backend-status")
        body = response.json()
        registered = body["registered_operators"]
        # 抽样几个必存的算子
        for op in ("load_csv", "min_max_scale", "pca", "logistic_regression",
                    "kmeans", "r2_score", "line_chart", "export_csv"):
            assert op in registered, f"expected operator '{op}' missing from API response"

    def test_backend_status_operators_sorted(self, api_client):
        response = api_client.get("/api/functions/backend-status")
        registered = response.json()["registered_operators"]
        assert registered == sorted(registered), "registered_operators not alphabetically sorted"


# ────────────────────────────────────────────────────────────────────────────
# 全量健康巡检：所有已注册算子都能通过 has_operator 查询
# ────────────────────────────────────────────────────────────────────────────


class TestOperatorHealthScan:
    def test_all_listed_operators_are_executable(self, router):
        """router.list_operators 返回的每个 id 都能通过 has_operator 查询到。"""
        for op_id in router.list_operators():
            assert router.has_operator(op_id), f"{op_id} listed but has_operator returns False"

    def test_router_registry_is_immutable_across_calls(self, router):
        """连续调用 list_operators 结果一致（副作用检测）。"""
        first = router.list_operators()
        second = router.list_operators()
        assert first == second
# @AI_GENERATED: end
