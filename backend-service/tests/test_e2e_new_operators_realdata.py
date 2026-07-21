# @AI_GENERATED
"""
新填充算子 — 真实业务数据端到端测试
====================================

场景 A  光伏故障诊断（train_small + label_small）
  load/merge → extract_statistical_features → 特征选择 → 分类器 → 评估指标

场景 B  威海负荷（load_true_weihai_260415.csv）
  滤波算子 vs scipy；prophet 预测长度契约

场景 C  光伏功率 demo（pv_power_data.csv）
  多特征回归器 train holdout → mape_score / r2_score

运行：
  cd backend-service
  conda run -n cp_web python -m pytest tests/test_e2e_new_operators_realdata.py -v --tb=short -s
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
_AIP_ROOT = os.path.dirname(_BACKEND_DIR)
_FAULT_DIAG = os.path.join(_AIP_ROOT, "fault-diag-algo-release-3.1")
_LOAD_FORE = os.path.join(_AIP_ROOT, "load_forecast_refactored")

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

WEIHAI_CSV = os.path.join(_LOAD_FORE, "datasets", "load_true_weihai_260415.csv")
FAULT_TRAIN = os.path.join(_FAULT_DIAG, "enos_fault_diag", "test", "train_small.parquet")
FAULT_LABEL = os.path.join(_FAULT_DIAG, "enos_fault_diag", "test", "label_small.parquet")
PV_POWER_CSV = os.path.join(_BACKEND_DIR, "data", "demo", "pv_power_data.csv")

from services.operator_execution.router import OperatorRouter


@pytest.fixture(scope="session")
def router():
    r = OperatorRouter()
    r.auto_discover(os.path.join(_BACKEND_DIR, "services", "operator_backends"))
    return r


def _assert_train_keys(result: dict, op_id: str):
    for key in ("predictions", "y_true"):
        assert key in result, f"{op_id} train 缺少 '{key}': {list(result.keys())}"
    assert len(result["predictions"]) == len(result["y_true"])
    assert len(result["predictions"]) > 0


# ══════════════════════════════════════════════════════════════════════════
# 场景 A — 光伏故障：真实窗口特征上的新分类器
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not os.path.exists(FAULT_TRAIN), reason="train_small.parquet not found")
class TestPvFaultNewClassifiers:
    """
    真实链路：
      train_small + label_small
      → 按日窗口聚合统计特征
      → variance_threshold / mutual_info_select
      → 新填充分类器 train
      → accuracy_score / f1_score / classification_report
    """

    @pytest.fixture(scope="class")
    def pv_xy(self, router):
        train_df = pd.read_parquet(FAULT_TRAIN)
        label_df = pd.read_parquet(FAULT_LABEL)
        train_df["time"] = pd.to_datetime(train_df["time"])
        label_df["time"] = pd.to_datetime(label_df["time"])
        label_df = label_df.rename(columns={"custom_label_id": "label"})

        id_fields = ["site_id", "device_id", "branch_id"]
        train_df["date"] = train_df["time"].dt.date
        label_df["date"] = label_df["time"].dt.date
        merged = train_df.merge(
            label_df[id_fields + ["date", "label"]],
            on=id_fields + ["date"],
            how="inner",
        ).drop_duplicates().reset_index(drop=True)
        merged["time_window"] = pd.to_datetime(merged["date"])
        id_fields_full = id_fields + ["time_window"]

        r_stat = router.execute(
            "extract_statistical_features",
            {
                "mode": "groupby_aggregate",
                "id_fields": id_fields_full,
                "value_fields": ["value", "i_cal"],
                "compute_diff": True,
                "quantiles": [0.25, 0.5, 0.75],
            },
            {"data": merged},
        )
        feat = r_stat["data"]
        label_win = merged.groupby(id_fields_full)["label"].max().reset_index()
        feat = feat.merge(label_win, on=id_fields_full, how="inner").dropna()

        # 稀有类（<5）去掉，避免 80/20 随机切分时某侧缺类导致不稳定
        vc = feat["label"].value_counts()
        keep = vc[vc >= 5].index
        feat = feat[feat["label"].isin(keep)].reset_index(drop=True)

        drop_cols = set(id_fields_full) | {"label", "time", "date"}
        feature_cols = [
            c for c in feat.columns
            if c not in drop_cols and pd.api.types.is_numeric_dtype(feat[c])
        ]
        X = feat[feature_cols].fillna(0)
        y = feat["label"].astype(int).values
        assert len(X) >= 20, f"可用窗口样本过少: {len(X)}"
        print(f"\n  [pv_xy] samples={len(X)} features={X.shape[1]} classes={sorted(np.unique(y))}")
        return X, y

    def test_variance_threshold_on_pv_features(self, router, pv_xy):
        X, _ = pv_xy
        r = router.execute("variance_threshold", {"threshold": 0.0}, {"data": X})
        assert "data" in r
        assert isinstance(r["data"], pd.DataFrame)
        assert r["data"].shape[0] == X.shape[0]
        assert r["data"].shape[1] <= X.shape[1]
        print(f"\n  [variance_threshold] {X.shape[1]} → {r['data'].shape[1]} cols ✓")

    def test_mutual_info_select_on_pv_features(self, router, pv_xy):
        X, y = pv_xy
        r = router.execute(
            "mutual_info_select",
            {"task": "classification", "top_k": 15},
            {"features": X, "target": y},
        )
        assert "data" in r and "selected_columns" in r and "scores" in r
        assert len(r["selected_columns"]) == r["data"].shape[1]
        assert 1 <= len(r["selected_columns"]) <= 15
        print(f"\n  [mutual_info_select] top={r['selected_columns'][:5]} ... ✓")

    @pytest.mark.parametrize(
        "op_id,params",
        [
            ("logistic_regression", {"mode": "train", "max_iter": 400, "save_model": "false"}),
            ("svm_classifier", {"mode": "train", "C": 1.0, "save_model": "false"}),
            ("decision_tree_classifier", {"mode": "train", "max_depth": 8, "save_model": "false"}),
            ("knn_classifier", {"mode": "train", "n_neighbors": 5, "save_model": "false"}),
            ("gradient_boosting_classifier", {
                "mode": "train", "n_estimators": 40, "max_depth": 3, "save_model": "false",
            }),
            ("naive_bayes_classifier", {"mode": "train", "save_model": "false"}),
            ("xgboost_classifier", {
                "mode": "train", "n_estimators": 40, "max_depth": 3, "learning_rate": 0.1,
            }),
        ],
    )
    def test_classifier_train_on_pv_features(self, router, pv_xy, op_id, params):
        X, y = pv_xy
        # 先做互信息降维，加速 SVM / GB，并贴近真实管线
        r_sel = router.execute(
            "mutual_info_select",
            {"task": "classification", "top_k": 20},
            {"features": X, "target": y},
        )
        X_sel = r_sel["data"]

        r = router.execute(op_id, params, {"features": X_sel, "target": y})
        _assert_train_keys(r, op_id)

        from sklearn.metrics import accuracy_score, f1_score

        acc = float(accuracy_score(r["y_true"], r["predictions"]))
        f1 = float(f1_score(r["y_true"], r["predictions"], average="macro", zero_division=0))
        majority = float(np.max(np.bincount(y.astype(int))) / len(y))

        # 真实小样本：至少明显好于纯随机（1/n_classes），且不全崩到 0
        n_classes = len(np.unique(y))
        floor = max(1.0 / n_classes + 0.05, 0.20)
        assert acc >= floor, f"{op_id} holdout acc={acc:.3f} < floor={floor:.3f} (majority={majority:.3f})"
        assert f1 >= 0.05, f"{op_id} macro-F1={f1:.3f} 过低"

        # 评估算子契约：与 sklearn 对齐
        r_acc = router.execute("accuracy_score", {}, {"y_true": r["y_true"], "y_pred": r["predictions"]})
        r_f1 = router.execute(
            "f1_score", {"average": "macro"},
            {"y_true": r["y_true"], "y_pred": r["predictions"]},
        )
        assert abs(r_acc["score"] - acc) < 1e-9
        assert abs(r_f1["score"] - f1) < 1e-6

        r_rep = router.execute(
            "classification_report", {},
            {"y_true": r["y_true"], "y_pred": r["predictions"]},
        )
        for key in ("accuracy", "macro_f1", "report_text", "report_dict"):
            assert key in r_rep, f"classification_report 缺少 '{key}'"
        assert abs(r_rep["accuracy"] - acc) < 1e-9
        print(f"\n  [{op_id}] holdout acc={acc:.3f} macro-F1={f1:.3f} ✓")


# ══════════════════════════════════════════════════════════════════════════
# 场景 B — 威海负荷：滤波精度 + Prophet
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai csv not found")
class TestLoadForecastFiltersAndProphet:

    @pytest.fixture(scope="class")
    def weihai_series(self, router):
        r = router.execute("load_csv", {"file_path": WEIHAI_CSV, "delimiter": ","}, {})
        df = r["data"]
        # 单设备连续序列，避免多设备交错破坏滤波语义
        sub = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
        sub = sub.sort_values("record_time").reset_index(drop=True)
        # 截一段够滤波 / Prophet，控制耗时
        sub = sub.head(1500)
        assert len(sub) >= 200
        return sub

    def test_median_filter_vs_scipy(self, router, weihai_series):
        from scipy.ndimage import median_filter as sp_median

        df = weihai_series[["record_time", "value"]].copy()
        r = router.execute("median_filter", {"columns": ["value"], "size": 5}, {"data": df})
        expected = sp_median(df["value"].astype(float).values, size=5)
        np.testing.assert_allclose(r["data"]["value"].values, expected, rtol=0, atol=1e-9)
        print("\n  [median_filter] matches scipy ✓")

    def test_gaussian_filter_vs_scipy(self, router, weihai_series):
        from scipy.ndimage import gaussian_filter1d

        df = weihai_series[["record_time", "value"]].copy()
        r = router.execute("gaussian_filter", {"columns": ["value"], "sigma": 2.0}, {"data": df})
        expected = gaussian_filter1d(df["value"].astype(float).values, sigma=2.0)
        np.testing.assert_allclose(r["data"]["value"].values, expected, rtol=0, atol=1e-9)
        print("\n  [gaussian_filter] matches scipy ✓")

    def test_lowpass_filter_vs_scipy(self, router, weihai_series):
        from scipy.signal import butter, filtfilt

        df = weihai_series[["record_time", "value"]].copy()
        cutoff, fs, order = 0.1, 1.0, 4
        r = router.execute(
            "lowpass_filter",
            {"columns": ["value"], "cutoff": cutoff, "sampling_rate": fs, "order": order},
            {"data": df},
        )
        b, a = butter(order, cutoff / (fs / 2.0), btype="low")
        expected = filtfilt(b, a, df["value"].astype(float).values)
        np.testing.assert_allclose(r["data"]["value"].values, expected, rtol=1e-6, atol=1e-6)
        print("\n  [lowpass_filter] matches scipy ✓")

    def test_bandpass_filter_vs_scipy(self, router, weihai_series):
        from scipy.signal import butter, filtfilt

        df = weihai_series[["record_time", "value"]].copy()
        low, high, fs, order = 0.05, 0.2, 1.0, 4
        r = router.execute(
            "bandpass_filter",
            {
                "columns": ["value"],
                "low_cutoff": low,
                "high_cutoff": high,
                "sampling_rate": fs,
                "order": order,
            },
            {"data": df},
        )
        b, a = butter(order, [low / (fs / 2.0), high / (fs / 2.0)], btype="band")
        expected = filtfilt(b, a, df["value"].astype(float).values)
        np.testing.assert_allclose(r["data"]["value"].values, expected, rtol=1e-6, atol=1e-6)
        print("\n  [bandpass_filter] matches scipy ✓")

    def test_prophet_forecast_contract(self, router, weihai_series):
        df = weihai_series[["record_time", "value"]].copy()
        # Prophet 对长序列较慢：只取最近 400 点
        df = df.tail(400).reset_index(drop=True)
        horizon = 16
        try:
            r = router.execute(
                "prophet",
                {
                    "timestamp_column": "record_time",
                    "value_column": "value",
                    "forecast_horizon": horizon,
                    "freq": "15min",
                },
                {"data": df},
            )
        except Exception as e:
            if "DependencyError" in type(e).__name__ or "prophet" in str(e).lower():
                pytest.skip(f"prophet unavailable: {e}")
            raise

        for key in ("forecast", "forecast_dates", "forecast_lower", "forecast_upper"):
            assert key in r, f"prophet 缺少 '{key}'"
            assert len(r[key]) == horizon
        assert all(np.isfinite(r["forecast"]))
        print(f"\n  [prophet] horizon={horizon} forecast[0]={r['forecast'][0]:.2f} ✓")


# ══════════════════════════════════════════════════════════════════════════
# 场景 C — 光伏功率：多特征回归真实数据
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not os.path.exists(PV_POWER_CSV), reason="pv_power_data.csv not found")
class TestPvPowerNewRegressors:

    @pytest.fixture(scope="class")
    def power_xy(self):
        df = pd.read_csv(PV_POWER_CSV)
        # 白天样本更有回归意义（辐照/功率不为 0）
        day = df[df["irradiance"] > 50].copy()
        if len(day) < 500:
            day = df.copy()
        day = day.sample(n=min(3000, len(day)), random_state=42)
        feature_cols = ["irradiance", "temperature", "humidity", "wind_speed", "cloud_cover"]
        X = day[feature_cols].astype(float)
        y = day["power_actual"].astype(float).values
        return X, y

    @pytest.mark.parametrize(
        "op_id,params",
        [
            ("linear_regression", {"mode": "train"}),
            ("lasso_regression", {"mode": "train", "alpha": 0.1}),
            ("elastic_net", {"mode": "train", "alpha": 0.1, "l1_ratio": 0.5}),
            ("ridge_regression", {"mode": "train", "alpha": 1.0}),
            ("svr_regression", {"mode": "train", "C": 1.0}),
            ("xgboost_regression", {"mode": "train", "n_estimators": 40, "max_depth": 4}),
        ],
    )
    def test_regressor_train_on_pv_power(self, router, power_xy, op_id, params):
        X, y = power_xy
        try:
            r = router.execute(op_id, params, {"features": X, "target": y})
        except Exception as e:
            if "DependencyError" in type(e).__name__ or "not installed" in str(e).lower():
                pytest.skip(f"{op_id} dependency missing: {e}")
            raise

        _assert_train_keys(r, op_id)
        y_true = np.asarray(r["y_true"], dtype=float)
        y_pred = np.asarray(r["predictions"], dtype=float)

        r_mape = router.execute("mape_score", {}, {"y_true": y_true, "y_pred": y_pred})
        r_r2 = router.execute("r2_score", {}, {"y_true": y_true, "y_pred": y_pred})
        assert "score" in r_mape and "score" in r_r2

        # 功率与辐照强相关：线性族应明显优于预测均值（R2 > 0.3）
        # SVR 在未标准化时可能偏弱，放宽到 R2 > 0
        floor = 0.0 if op_id == "svr_regression" else 0.3
        assert r_r2["score"] > floor, f"{op_id} R2={r_r2['score']:.3f} <= {floor}"
        assert np.isfinite(r_mape["score"])
        print(f"\n  [{op_id}] holdout R2={r_r2['score']:.3f} MAPE={r_mape['score']:.2f}% ✓")
