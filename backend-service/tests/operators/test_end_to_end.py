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
