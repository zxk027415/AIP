# @AI_GENERATED
"""
Layer 4 — 模型往返测试（Round-trip Tests）

针对所有 train/predict 双模式算子：
1. train → 返回 model + model_id
2. 用 model_id 从磁盘加载 → predict
3. 用内存中的 model 对象 → predict
4. 断言两种 predict 路径的输出**逐元素相等**

覆盖：
- 分类器（6 个）：logistic_regression, svm_classifier, decision_tree_classifier,
                   random_forest_classifier, knn_classifier, gradient_boosting_classifier
- 回归器（5 个）：linear_regression, lasso_regression, ridge_regression,
                   elastic_net, svr_regression
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest


# ────────────────────────────────────────────────────────────────────────────
# 参数化用例：所有 train/predict 双模式算子
# ────────────────────────────────────────────────────────────────────────────

CLASSIFIER_CASES = [
    ("logistic_regression", {"mode": "train", "C": 1.0, "max_iter": 500}),
    ("svm_classifier", {"mode": "train", "kernel": "rbf", "C": 1.0}),
    ("decision_tree_classifier", {"mode": "train", "max_depth": 5}),
    ("random_forest_classifier", {"mode": "train", "n_estimators": 20}),
    ("knn_classifier", {"mode": "train", "n_neighbors": 3}),
    ("gradient_boosting_classifier", {"mode": "train", "n_estimators": 20, "learning_rate": 0.1}),
    # @AI_GENERATED — P2 batch additions
    ("naive_bayes_classifier", {"mode": "train"}),
    ("xgboost_classifier", {"mode": "train", "n_estimators": 20, "max_depth": 3, "learning_rate": 0.1}),
    # @AI_GENERATED: end
]

REGRESSOR_CASES = [
    ("linear_regression", {"mode": "train"}),
    ("lasso_regression", {"mode": "train", "alpha": 0.1}),
    ("ridge_regression", {"mode": "train", "alpha": 1.0}),
    ("elastic_net", {"mode": "train", "alpha": 0.1, "l1_ratio": 0.5}),
    ("svr_regression", {"mode": "train", "kernel": "rbf", "C": 1.0, "epsilon": 0.1}),
    # @AI_GENERATED — P2 batch additions
    ("xgboost_regression", {"mode": "train", "n_estimators": 20, "max_depth": 3, "learning_rate": 0.1}),
    # @AI_GENERATED: end
]


@pytest.mark.parametrize("op_id,train_params", CLASSIFIER_CASES, ids=[c[0] for c in CLASSIFIER_CASES])
def test_classifier_train_predict_roundtrip(router, classification_data, op_id, train_params):
    """
    分类器 train/predict 往返一致性。

    Property 8: model_id round-trip — 保存 → 用 model_id 加载 → 预测，
                与 in-memory model 的预测结果**逐元素相等**。
    """
    features, target = classification_data

    # ─── train ────────────────────────────────────────────────────────────
    train_result = router.execute(op_id, train_params, {"features": features, "target": target})

    model_id = train_result["model_id"]
    assert model_id, f"{op_id} did not return a valid model_id"
    memory_model = train_result["model"]

    # ─── predict via model_id (磁盘加载) ─────────────────────────────────
    pred_from_disk = router.execute(
        op_id,
        {"mode": "predict", "model_id": model_id},
        {"predict_features": features},
    )
    assert "predictions" in pred_from_disk
    disk_preds = np.asarray(pred_from_disk["predictions"])

    # ─── predict via in-memory model 对象 ────────────────────────────────
    pred_from_memory = router.execute(
        op_id,
        {"mode": "predict"},
        {"model": memory_model, "predict_features": features},
    )
    memory_preds = np.asarray(pred_from_memory["predictions"])

    # ─── 逐元素相等（Property 8）───────────────────────────────────────
    assert len(disk_preds) == len(memory_preds) == len(features)
    np.testing.assert_array_equal(
        disk_preds, memory_preds,
        err_msg=f"{op_id}: disk-loaded and in-memory model produced different predictions",
    )


@pytest.mark.parametrize("op_id,train_params", REGRESSOR_CASES, ids=[c[0] for c in REGRESSOR_CASES])
def test_regressor_train_predict_roundtrip(router, regression_data, op_id, train_params):
    """回归器 train/predict 往返一致性（允许浮点误差）。"""
    features, target = regression_data

    train_result = router.execute(op_id, train_params, {"features": features, "target": target})
    model_id = train_result["model_id"]
    memory_model = train_result["model"]

    pred_from_disk = router.execute(
        op_id,
        {"mode": "predict", "model_id": model_id},
        {"predict_features": features},
    )
    disk_preds = np.asarray(pred_from_disk["predictions"], dtype=float)

    pred_from_memory = router.execute(
        op_id,
        {"mode": "predict"},
        {"model": memory_model, "predict_features": features},
    )
    memory_preds = np.asarray(pred_from_memory["predictions"], dtype=float)

    assert len(disk_preds) == len(memory_preds) == len(features)
    np.testing.assert_allclose(
        disk_preds, memory_preds, rtol=1e-6, atol=1e-9,
        err_msg=f"{op_id}: disk-loaded vs in-memory prediction mismatch",
    )


# ────────────────────────────────────────────────────────────────────────────
# holdout predictions 长度契约（Property 9）
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("op_id,train_params", CLASSIFIER_CASES + REGRESSOR_CASES,
                          ids=[c[0] for c in CLASSIFIER_CASES + REGRESSOR_CASES])
def test_holdout_predictions_length(router, op_id, train_params):
    """
    Property 9: holdout predictions 长度 = ceil(0.2 * n_total)。

    分类器用 classification_data，回归器用 regression_data。
    统一构造 40 样本输入，holdout 应为 8。
    """
    if "classif" in op_id or "tree" in op_id or "logistic" in op_id or "knn" in op_id or "svm_classi" in op_id or "gradient" in op_id or "forest" in op_id or "bayes" in op_id or "xgboost_class" in op_id:
        from sklearn.datasets import make_classification
        X, y = make_classification(n_samples=40, n_features=5, n_classes=2, random_state=42)
    else:
        from sklearn.datasets import make_regression
        X, y = make_regression(n_samples=40, n_features=3, noise=0.1, random_state=42)

    features = pd.DataFrame(X, columns=[f"f{i}" for i in range(X.shape[1])])

    result = router.execute(op_id, train_params, {"features": features, "target": y})

    predictions = np.asarray(result["predictions"])
    y_true = np.asarray(result["y_true"])

    assert len(predictions) == len(y_true), (
        f"{op_id}: predictions len ({len(predictions)}) != y_true len ({len(y_true)})"
    )
    # 40 * 0.2 = 8; 但 sklearn 的 shuffle split 可能有 ±1 误差
    expected = int(40 * 0.2)
    assert abs(len(predictions) - expected) <= 1, (
        f"{op_id}: holdout size {len(predictions)} not near expected {expected}"
    )


# ────────────────────────────────────────────────────────────────────────────
# Anomaly detector 模型往返（isolation_forest / one_class_svm）
# ────────────────────────────────────────────────────────────────────────────


ANOMALY_CASES = [
    ("isolation_forest", {"mode": "fit_predict", "contamination": 0.1, "n_estimators": 30}),
    ("one_class_svm", {"mode": "fit_predict", "kernel": "rbf", "nu": 0.1}),
]


@pytest.mark.parametrize("op_id,fit_params", ANOMALY_CASES, ids=[c[0] for c in ANOMALY_CASES])
def test_anomaly_detector_roundtrip(router, numeric_df_medium, op_id, fit_params):
    """异常检测算子：fit_predict 保存 → 用 model_id 重新 predict → labels/scores 一致。"""
    # fit_predict + save
    fit_result = router.execute(op_id, fit_params, {"data": numeric_df_medium})
    fit_labels = fit_result["labels"]
    fit_scores = fit_result["scores"]
    model_id = fit_result["model_id"]

    assert model_id, f"{op_id} did not save model in fit_predict mode"

    # predict via model_id
    predict_result = router.execute(
        op_id,
        {"mode": "predict", "model_id": model_id},
        {"data": numeric_df_medium},
    )
    predict_labels = predict_result["labels"]
    predict_scores = predict_result["scores"]

    # fit_predict 和 predict 应输出相同 labels
    np.testing.assert_array_equal(
        fit_labels, predict_labels,
        err_msg=f"{op_id}: fit_predict vs predict-from-disk label mismatch",
    )
    np.testing.assert_allclose(
        fit_scores, predict_scores, rtol=1e-6,
        err_msg=f"{op_id}: fit_predict vs predict-from-disk score mismatch",
    )


# ────────────────────────────────────────────────────────────────────────────
# feature_list 一致性
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("op_id,train_params", CLASSIFIER_CASES + REGRESSOR_CASES,
                          ids=[c[0] for c in CLASSIFIER_CASES + REGRESSOR_CASES])
def test_train_returns_feature_list(router, op_id, train_params):
    """训练模式必须返回 feature_list，且与输入 features 的列名一致。"""
    from sklearn.datasets import make_classification, make_regression
    is_classifier = any(kw in op_id for kw in ("classif", "tree", "logistic", "knn", "svm_classi", "gradient", "forest", "bayes", "xgboost_class"))
    if is_classifier:
        X, y = make_classification(n_samples=40, n_features=5, n_classes=2, random_state=42)
    else:
        X, y = make_regression(n_samples=40, n_features=3, noise=0.1, random_state=42)

    features = pd.DataFrame(X, columns=[f"f{i}" for i in range(X.shape[1])])
    result = router.execute(op_id, train_params, {"features": features, "target": y})

    assert "feature_list" in result, f"{op_id} missing feature_list in train output"
    assert list(result["feature_list"]) == list(features.columns), (
        f"{op_id}: feature_list {result['feature_list']} != input columns {list(features.columns)}"
    )


# ────────────────────────────────────────────────────────────────────────────
# 测试后清理：删除测试落盘的模型文件
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_models(backends_dir):
    """模块结束时清理本次测试新建的 pickle 模型（前缀识别）。"""
    yield
    models_dir = os.path.join(os.path.dirname(os.path.dirname(backends_dir)), "data", "models")
    if not os.path.isdir(models_dir):
        return
    # 只删除最近 5 分钟内创建的，避免误删业务模型
    import time
    cutoff = time.time() - 300
    prefixes = ("logreg_", "svm_", "dtree_", "linreg_", "lasso_", "enet_", "ridge_",
                "knn_", "gbc_", "svr_", "iforest_", "ocsvm_", "pv_fault_rfc_",
                "nb_", "xgbc_", "xgbr_")
    for f in os.listdir(models_dir):
        if not f.endswith((".pkl", ".json")):
            continue
        if not any(f.startswith(p) for p in prefixes):
            continue
        path = os.path.join(models_dir, f)
        try:
            if os.path.getctime(path) < cutoff:
                continue
            os.remove(path)
        except OSError:
            pass
# @AI_GENERATED: end
