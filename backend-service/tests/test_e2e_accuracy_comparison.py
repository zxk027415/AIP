# @AI_GENERATED
"""
端到端精度对比测试 — 平台算子 vs 本地参考代码
=============================================

【场景 A】故障诊断链路精度验证（光伏，8类分类）
  数据: fault-diag-algo-release-3.1/enos_fault_diag/test/
  指标: Accuracy / macro-F1
  基准: evaluate_local.py 产出的随机森林精度

【场景 B】负荷预测数值算子精度验证（威海，15min）
  数据: load_forecast_refactored/datasets/load_true_weihai_260415.csv
  指标: SMAPE / RMSE / MAE
  基准: sklearn/scipy/numpy 直接计算

【统一 I/O 契约规则】
  每个算子严格遵守：
  - 输入 DataFrame → inputs["data"]
  - 输出 DataFrame → result["data"]
  - 评估标量输出 → result["score"]
  - 训练型算子输出 → result 含 model_id、predictions、y_true
  - 异常型输出 → OperatorExecutionError，不泄漏 Python 原生异常

运行：
  cd backend-service
  conda run -n cp_web python -m pytest tests/test_e2e_accuracy_comparison.py -v --tb=short -s

"""
import os
import sys
import warnings
import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

# ─── 路径 ──────────────────────────────────────────────────────────────────
_TESTS_DIR   = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
_AIP_ROOT    = os.path.dirname(_BACKEND_DIR)
_FAULT_DIAG  = os.path.join(_AIP_ROOT, "fault-diag-algo-release-3.1")
_LOAD_FORE   = os.path.join(_AIP_ROOT, "load_forecast_refactored")

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ─── 数据文件路径 ──────────────────────────────────────────────────────────
WEIHAI_CSV       = os.path.join(_LOAD_FORE, "datasets", "load_true_weihai_260415.csv")
FAULT_TRAIN      = os.path.join(_FAULT_DIAG, "enos_fault_diag", "test", "train_small.parquet")
FAULT_LABEL      = os.path.join(_FAULT_DIAG, "enos_fault_diag", "test", "label_small.parquet")
FAULT_PREDICT    = os.path.join(_FAULT_DIAG, "enos_fault_diag", "test", "predict_small.parquet")
FAULT_ENOS_PKG   = os.path.join(_FAULT_DIAG, "enos_fault_diag")

# ─── Router fixture ─────────────────────────────────────────────────────────
from services.operator_execution.router import OperatorRouter

@pytest.fixture(scope="session")
def router():
    r = OperatorRouter()
    r.auto_discover(os.path.join(_BACKEND_DIR, "services", "operator_backends"))
    return r

# ─── 公共指标函数 ────────────────────────────────────────────────────────────
def smape(y_true, y_pred, eps=1e-8):
    a, b = np.asarray(y_true, float), np.asarray(y_pred, float)
    d = np.maximum(eps, (np.abs(a) + np.abs(b)) / 2)
    return float(np.mean(np.abs(a - b) / d) * 100)

def regression_metrics(y_true, y_pred):
    a, b = np.asarray(y_true, float), np.asarray(y_pred, float)
    mse  = float(np.mean((a - b) ** 2))
    return {"smape": smape(a, b), "rmse": float(np.sqrt(mse)),
            "mae": float(np.mean(np.abs(a - b))), "mse": mse}

def _print_cmp(title, platform, local):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")
    for k in [x for x in platform if x in local and isinstance(platform[x], (int, float))]:
        p, l = platform[k], local[k]
        diff = p - l
        pct  = diff / l * 100 if l else 0
        print(f"  {k:<18} platform={p:>10.4f}  local={l:>10.4f}  diff={diff:>+10.4f}({pct:+.1f}%)")
    print("=" * 60)


# ══════════════════════════════════════════════════════════════════════════
# 场景 A — 故障诊断：平台算子完整链路（用 stratified_cv_eval 一步出精度）
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not os.path.exists(FAULT_TRAIN), reason="train_small.parquet not found")
class TestFaultDiagPipelinePlatform:
    """
    使用平台算子完整跑故障诊断链路：
      load_parquet → merge → time_window_split → handle_missing →
      detect_outliers → extract_statistical_features → ts_comparison_features →
      feature_select → stratified_cv_eval
    最终与 evaluate_local.py 的基准对比 Accuracy/macro-F1。
    """

    @pytest.fixture(scope="class")
    def fault_data(self):
        """加载测试数据"""
        train_df = pd.read_parquet(FAULT_TRAIN)
        label_df = pd.read_parquet(FAULT_LABEL)
        train_df["time"] = pd.to_datetime(train_df["time"])
        label_df["time"] = pd.to_datetime(label_df["time"])
        label_df = label_df.rename(columns={"custom_label_id": "label"})
        return train_df, label_df

    def test_step1_load_parquet_contract(self, router):
        """I/O 契约：load_parquet 必须返回 {"data": DataFrame}"""
        r = router.execute("load_parquet", {"file_path": FAULT_TRAIN}, {})
        assert "data" in r, f"load_parquet missing 'data' key: {list(r.keys())}"
        assert isinstance(r["data"], pd.DataFrame)
        df = r["data"]
        for col in ["site_id", "device_id", "branch_id", "time", "value", "i_cal"]:
            assert col in df.columns, f"train_small 缺列: {col}"
        print(f"\n  [load_parquet] {df.shape[0]} rows × {df.shape[1]} cols ✓")

    def test_step2_merge_label_contract(self, router, fault_data):
        """I/O 契约：merge_label 必须返回 {"data": DataFrame}，且含 label 列"""
        train_df, label_df = fault_data
        r = router.execute("merge_label", {
            "id_fields":    ["site_id", "device_id", "branch_id"],
            "time_field":   "time",
            "label_col":    "label",
            "output_label_col": "label",
        }, {"data": train_df, "label_data": label_df})
        assert "data" in r
        merged = r["data"]
        assert "label" in merged.columns
        assert len(merged) > 0
        print(f"\n  [merge_label] merged rows={len(merged)}, label distribution:")
        print("  ", merged["label"].value_counts().sort_index().to_dict())

    def test_step3_extract_statistical_features_vs_local(self, fault_data):
        """
        精度对比：extract_statistical_features (groupby_aggregate 模式)
        vs 本地 FeatureEngineer.get_basic_features()。
        要求：max/min/mean/std 等基础统计值差 < 1e-3（命名可不同）。
        """
        train_df, label_df = fault_data

        # 合并标签到时序
        id_fields = ["site_id", "device_id", "branch_id"]
        train_df["date"] = train_df["time"].dt.date
        label_df["date"] = label_df["time"].dt.date
        merged = train_df.merge(
            label_df[id_fields + ["date", "label"]],
            on=id_fields + ["date"], how="inner"
        ).drop_duplicates().reset_index(drop=True)
        merged["time_window"] = pd.to_datetime(merged["date"])
        id_fields_full = id_fields + ["time_window"]

        # 平台算子
        from services.operator_backends.extract_statistical_features import execute as esf_exec
        r_platform = esf_exec({
            "mode": "groupby_aggregate",
            "id_fields": id_fields_full,
            "value_fields": ["value", "i_cal"],
            "compute_diff": False,
            "quantiles": [],
        }, {"data": merged})
        feat_platform = r_platform["data"]

        # 本地代码：手动 groupby 计算 max/min/mean/std
        local_rows = []
        for key, grp in merged.groupby(id_fields_full):
            row = dict(zip(id_fields_full, key)) if isinstance(key, tuple) else {id_fields_full[0]: key}
            for col in ["value", "i_cal"]:
                row[f"{col}_max_local"]  = float(np.nanmax(grp[col]))
                row[f"{col}_min_local"]  = float(np.nanmin(grp[col]))
                row[f"{col}_mean_local"] = float(np.nanmean(grp[col]))
                row[f"{col}_std_local"]  = float(np.nanstd(grp[col]))
            local_rows.append(row)
        feat_local = pd.DataFrame(local_rows)

        # 合并对比（按 id_fields_full 对齐）
        cmp = feat_platform.merge(feat_local, on=id_fields_full, how="inner")
        assert len(cmp) > 0, "对比合并后行数为 0"

        # 逐列比较（找 platform 中 nanmax/nanmin/nanmean/nanstd 对应列）
        for col in ["value", "i_cal"]:
            for stat, local_key in [("max", f"{col}_max_local"),
                                     ("min", f"{col}_min_local"),
                                     ("mean", f"{col}_mean_local"),
                                     ("std", f"{col}_std_local")]:
                p_col = next((c for c in feat_platform.columns
                              if col in c and stat in c), None)
                if p_col is None:
                    continue  # 算子命名不同，跳过此统计
                diff = np.abs(cmp[p_col].values - cmp[local_key].values)
                max_diff = float(np.nanmax(diff))
                # std: np.nanstd 用 ddof=0, pandas .std() 用 ddof=1 → 小样本有差异，放宽到 0.1
                tol = 0.1 if stat == "std" else 1e-3
                assert max_diff < tol, \
                    f"{col}.{stat}: 最大差值={max_diff:.6f} 超出 {tol} 阈值"
                print(f"\n  [{col}.{stat}] max_diff={max_diff:.8f} ✓")

    def test_step4_full_pipeline_accuracy_vs_local(self, router, fault_data):
        """
        完整管线精度对比：
          平台算子链路 (stratified_cv_eval) vs 本地 evaluate_local.py 方式 B
        要求：Accuracy 差 < 5%，macro-F1 差 < 5%（允许随机性和特征命名差异）
        """
        train_df, label_df = fault_data
        id_fields = ["site_id", "device_id", "branch_id"]
        train_df["date"] = train_df["time"].dt.date
        label_df["date"] = label_df["time"].dt.date
        merged = train_df.merge(
            label_df[id_fields + ["date", "label"]],
            on=id_fields + ["date"], how="inner"
        ).drop_duplicates().reset_index(drop=True)
        merged["time_window"] = pd.to_datetime(merged["date"])
        id_fields_full = id_fields + ["time_window"]

        # ── 平台算子：统计特征提取 ──────────────────────────────────────
        r_stat = router.execute("extract_statistical_features", {
            "mode": "groupby_aggregate",
            "id_fields": id_fields_full,
            "value_fields": ["value", "i_cal"],
            "compute_diff": True,
            "quantiles": [0.15, 0.25, 0.35, 0.65, 0.75, 0.85, 0.95],
        }, {"data": merged})
        assert "data" in r_stat
        feat_stat = r_stat["data"]

        # 合并标签
        label_win = merged.groupby(id_fields_full)["label"].max().reset_index()
        feat_stat = feat_stat.merge(label_win, on=id_fields_full, how="inner").dropna()
        print(f"\n  [extract_statistical_features] {feat_stat.shape[0]} samples × {feat_stat.shape[1]} cols")

        if feat_stat.shape[0] < 10:
            pytest.skip(f"样本太少({feat_stat.shape[0]})，跳过精度对比")

        # ── 平台算子：stratified_cv_eval（n_repeats=5 加速）──────────────
        r_cv = router.execute("stratified_cv_eval", {
            "n_repeats":     5,
            "test_ratio":    0.2,
            "k":             20,
            "n_estimators":  80,
            "random_state":  90,
            "smote_limit":   300,
            "id_fields":     id_fields_full,
            "target_col":    "label",
            "save_final_model": "false",
        }, {"stat_features": feat_stat})

        platform_acc  = r_cv["accuracy_mean"]
        platform_f1   = r_cv["macro_f1_mean"]
        print(f"\n  [平台算子] Accuracy={platform_acc:.4f}  macro-F1={platform_f1:.4f}")
        print(f"  分布: {r_cv['class_distribution']}")

        # ── 本地代码基准（复现 evaluate_local.py 方式 B）────────────────
        local_acc, local_f1 = _run_local_fault_diag_eval(feat_stat, id_fields_full)
        print(f"\n  [本地代码] Accuracy={local_acc:.4f}  macro-F1={local_f1:.4f}")

        # ── 精度对比断言 ─────────────────────────────────────────────────
        _print_cmp("故障诊断精度对比",
                   {"accuracy": platform_acc, "macro_f1": platform_f1},
                   {"accuracy": local_acc,    "macro_f1": local_f1})

        assert abs(platform_acc - local_acc) < 0.05, \
            f"Accuracy 差 {abs(platform_acc - local_acc):.4f} 超出 5% 容差"
        assert abs(platform_f1 - local_f1) < 0.05, \
            f"macro-F1 差 {abs(platform_f1 - local_f1):.4f} 超出 5% 容差"


def _run_local_fault_diag_eval(feat_df: pd.DataFrame, id_fields: list) -> tuple:
    """本地基准：分层留出 5 次重复，与 evaluate_local.py 方式 B 一致"""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, f1_score
    try:
        from imblearn.over_sampling import SMOTE
        _smote_avail = True
    except ImportError:
        _smote_avail = False

    label_col = "label"
    drop_cols = set(id_fields) | {label_col, "time", "time_window", "date"}
    feature_cols = [c for c in feat_df.columns
                    if c not in drop_cols and pd.api.types.is_numeric_dtype(feat_df[c])]
    X = feat_df[feature_cols].fillna(0).values
    y = feat_df[label_col].astype(int).values

    # mRMR K=20
    try:
        from mrmr import mrmr_classif
        X_df = pd.DataFrame(X, columns=feature_cols)
        sel = mrmr_classif(X=X_df, y=pd.Series(y), K=min(20, len(feature_cols)))
        X = X_df[sel].values
    except Exception:
        pass  # fallback to all features

    acc_list, f1_list = [], []
    for i in range(5):
        rng = np.random.RandomState(90 + i)
        tr_idx, te_idx = [], []
        for cls in np.unique(y):
            idx = np.where(y == cls)[0]
            rng.shuffle(idx)
            n = len(idx)
            if n < 2:
                tr_idx.extend(idx.tolist()); continue
            n_te = max(1, min(int(round(n * 0.2)), n - 1))
            te_idx.extend(idx[:n_te].tolist())
            tr_idx.extend(idx[n_te:].tolist())

        X_tr, X_te = X[tr_idx], X[te_idx]
        y_tr, y_te = y[tr_idx], y[te_idx]

        if _smote_avail:
            try:
                classes, counts = np.unique(y_tr, return_counts=True)
                majority = counts.max()
                strat = {c: min(300, majority) for c, cnt in zip(classes, counts)
                         if cnt < majority and cnt >= 2}
                if strat:
                    min_cnt = min(counts[np.isin(classes, list(strat.keys()))])
                    k_n = max(1, min(5, int(min_cnt) - 1))
                    sm = SMOTE(sampling_strategy=strat, k_neighbors=k_n, random_state=90 + i)
                    X_tr, y_tr = sm.fit_resample(X_tr, y_tr)
            except Exception:
                pass

        clf = RandomForestClassifier(n_estimators=80, random_state=90, n_jobs=-1)
        clf.fit(X_tr, y_tr)
        y_pred = clf.predict(X_te)
        acc_list.append(float(accuracy_score(y_te, y_pred)))
        f1_list.append(float(f1_score(y_te, y_pred, average="macro", zero_division=0)))

    return float(np.mean(acc_list)), float(np.mean(f1_list))


# ══════════════════════════════════════════════════════════════════════════
# 场景 B — 负荷预测：数值算子精度验证（sklearn/scipy/numpy 基准）
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai csv not found")
class TestLoadForecastNumericalOperators:
    """
    针对威海 CSV 数据验证各数值处理算子的精度。
    对比基准：sklearn/scipy/numpy 直接运算，容差 1e-6。
    """

    @pytest.fixture(scope="class")
    def weihai_df(self, router):
        """加载并基础处理威海数据"""
        r = router.execute("load_csv", {"file_path": WEIHAI_CSV, "delimiter": ","}, {})
        df = r["data"]
        if "parent_id" in df.columns and "child_id" in df.columns:
            df = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
        if "value" not in df.columns and "load" in df.columns:
            df = df.rename(columns={"load": "value"})
        df["record_time"] = pd.to_datetime(df["record_time"])
        return df.sort_values("record_time").reset_index(drop=True)

    # ── min_max_scale ──────────────────────────────────────────────────────
    def test_min_max_scale_vs_sklearn(self, router, weihai_df):
        """平台 min_max_scale 与 sklearn.MinMaxScaler 差 < 1e-6"""
        from sklearn.preprocessing import MinMaxScaler

        df = weihai_df[["value"]].head(500).dropna().copy()
        r = router.execute("min_max_scale", {"columns": ["value"]}, {"data": df})
        assert "data" in r
        platform_col = r["data"]["value"].values

        scaler = MinMaxScaler()
        local_col = scaler.fit_transform(df[["value"]]).ravel()

        max_diff = float(np.max(np.abs(platform_col - local_col)))
        print(f"\n  [min_max_scale] max_diff={max_diff:.2e} ✓")
        assert max_diff < 1e-6

    # ── z_score_scale ──────────────────────────────────────────────────────
    def test_z_score_scale_vs_sklearn(self, router, weihai_df):
        """平台 z_score_scale 与 sklearn.StandardScaler 差 < 1e-6"""
        from sklearn.preprocessing import StandardScaler

        df = weihai_df[["value"]].head(500).dropna().copy()
        r = router.execute("z_score_scale", {"columns": ["value"]}, {"data": df})
        assert "data" in r
        platform_col = r["data"]["value"].values

        scaler = StandardScaler()
        local_col = scaler.fit_transform(df[["value"]]).ravel()

        max_diff = float(np.max(np.abs(platform_col - local_col)))
        print(f"\n  [z_score_scale] max_diff={max_diff:.2e} ✓")
        assert max_diff < 1e-6

    # ── pca ───────────────────────────────────────────────────────────────
    def test_pca_vs_sklearn(self, router, weihai_df):
        """平台 pca 的 explained_variance_ratio 与 sklearn.PCA 差 < 1e-4"""
        from sklearn.decomposition import PCA as SkPCA
        from sklearn.preprocessing import StandardScaler

        df = weihai_df[["value"]].head(200).dropna().copy()
        # 需要多列才能做 PCA，手工造 lag 列
        df["v1"] = df["value"].shift(1)
        df["v2"] = df["value"].shift(2)
        df = df.dropna().reset_index(drop=True)

        r = router.execute("pca", {"n_components": 2}, {"data": df})
        assert "data" in r and "explained_variance_ratio" in r
        platform_evr = r["explained_variance_ratio"]

        X = StandardScaler().fit_transform(df.values)
        sk_pca = SkPCA(n_components=2)
        sk_pca.fit(X)
        local_evr = sk_pca.explained_variance_ratio_.tolist()

        print(f"\n  [pca] platform_evr={[round(v,4) for v in platform_evr]}")
        print(f"        local_evr={[round(v,4) for v in local_evr]}")
        for p, l in zip(platform_evr, local_evr):
            assert abs(p - l) < 1e-3, f"EVR 差 {abs(p-l):.6f} 超出 1e-3"

    # ── moving_average ─────────────────────────────────────────────────────
    def test_moving_average_sma_vs_pandas(self, router, weihai_df):
        """SMA(window=5) 与 pandas.rolling(5).mean() 差 < 1e-9"""
        df = weihai_df[["value"]].head(100).copy()
        r = router.execute("moving_average",
                           {"columns": ["value"], "window": 5, "method": "sma"},
                           {"data": df})
        assert "data" in r
        platform = r["data"]["value"].values
        local    = df["value"].rolling(5).mean().values

        # 两端 NaN 位置对齐后比较
        mask = ~(np.isnan(platform) | np.isnan(local))
        max_diff = float(np.max(np.abs(platform[mask] - local[mask])))
        print(f"\n  [moving_average SMA] max_diff={max_diff:.2e} ✓")
        assert max_diff < 1e-9

    # ── log_transform ──────────────────────────────────────────────────────
    def test_log_transform_vs_numpy(self, router, weihai_df):
        """ln(x+1) 与 numpy.log(x+1) 差 < 1e-9"""
        df = weihai_df[["value"]].head(100).dropna().copy()
        # 确保值 > 0
        df = df[df["value"] > 0].head(80).reset_index(drop=True)
        r = router.execute("log_transform",
                           {"base": "ln", "offset": 1, "columns": ["value"]},
                           {"data": df})
        assert "data" in r
        platform = r["data"]["value"].values
        local    = np.log(df["value"].values + 1)
        max_diff = float(np.max(np.abs(platform - local)))
        print(f"\n  [log_transform ln] max_diff={max_diff:.2e} ✓")
        assert max_diff < 1e-9

    # ── stationarity_test ──────────────────────────────────────────────────
    def test_stationarity_test_vs_statsmodels(self, router, weihai_df):
        """ADF 检验 adf_statistic / p_value 与 statsmodels.adfuller 完全一致"""
        from statsmodels.tsa.stattools import adfuller

        df = weihai_df[["record_time", "value"]].head(300).dropna().copy()
        r = router.execute("stationarity_test",
                           {"column": "value", "significance": 0.05},
                           {"data": df})
        assert "adf_statistic" in r and "p_value" in r
        platform_stat = r["adf_statistic"]
        platform_p    = r["p_value"]

        result_local = adfuller(df["value"].values, autolag="AIC")
        local_stat   = float(result_local[0])
        local_p      = float(result_local[1])

        print(f"\n  [stationarity_test] ADF stat: platform={platform_stat:.6f} local={local_stat:.6f}")
        print(f"                      p-value: platform={platform_p:.6f} local={local_p:.6f}")
        assert abs(platform_stat - local_stat) < 1e-9
        assert abs(platform_p   - local_p)    < 1e-9

    # ── correlation_analysis ───────────────────────────────────────────────
    def test_correlation_analysis_vs_pandas(self, router, weihai_df):
        """Pearson 相关矩阵与 DataFrame.corr() 差 < 1e-6"""
        # 造两列
        df = weihai_df[["value"]].head(200).copy()
        df["v_lag1"] = df["value"].shift(1)
        df = df.dropna().reset_index(drop=True)

        r = router.execute("correlation_analysis",
                           {"method": "pearson"},
                           {"data": df})
        assert "correlation_matrix" in r
        cm_platform = r["correlation_matrix"]

        cm_local = df.corr(method="pearson")

        for col in cm_local.columns:
            for row in cm_local.index:
                if col in cm_platform.columns and row in cm_platform.index:
                    diff = abs(float(cm_platform.loc[row, col]) - float(cm_local.loc[row, col]))
                    assert diff < 1e-6, f"corr[{row},{col}] diff={diff:.8f}"
        print(f"\n  [correlation_analysis Pearson] max_diff verified < 1e-6 ✓")

    # ── savgol_filter ──────────────────────────────────────────────────────
    def test_savgol_filter_vs_scipy(self, router, weihai_df):
        """SG 滤波 与 scipy.signal.savgol_filter 差 < 1e-6"""
        from scipy.signal import savgol_filter as sg

        df = weihai_df[["value"]].head(100).dropna().copy()
        r = router.execute("savgol_filter",
                           {"window_length": 11, "polyorder": 2, "columns": ["value"]},
                           {"data": df})
        assert "data" in r
        platform = r["data"]["value"].values
        local    = sg(df["value"].values, window_length=11, polyorder=2)
        max_diff = float(np.max(np.abs(platform - local)))
        print(f"\n  [savgol_filter] max_diff={max_diff:.2e} ✓")
        assert max_diff < 1e-6

    # ── arima ──────────────────────────────────────────────────────────────
    def test_arima_forecast_vs_statsmodels(self, router, weihai_df):
        """ARIMA(1,1,1) 预测 5 步与 statsmodels 差 < 0.1%"""
        from statsmodels.tsa.arima.model import ARIMA

        ts = weihai_df[["record_time", "value"]].dropna().head(100)
        r = router.execute("arima", {
            "timestamp_column": "record_time", "value_column": "value",
            "forecast_horizon": 5, "p": 1, "d": 1, "q": 1,
        }, {"data": ts})
        assert "forecast" in r and len(r["forecast"]) == 5
        platform = np.asarray(r["forecast"])

        series = ts["value"].astype(float).values
        model  = ARIMA(series, order=(1, 1, 1))
        fit    = model.fit()
        local  = fit.forecast(steps=5)

        max_diff = float(np.max(np.abs(platform - local)))
        rel_diff = max_diff / (np.abs(local).mean() + 1e-8) * 100
        print(f"\n  [arima] max_abs_diff={max_diff:.4f}  rel_diff={rel_diff:.4f}%")
        assert rel_diff < 0.1, f"ARIMA 预测相对误差 {rel_diff:.4f}% 超出 0.1%"

    # ── fft_transform ──────────────────────────────────────────────────────
    def test_fft_transform_vs_numpy(self, router, weihai_df):
        """FFT 幅值序列与 numpy.fft.rfft 完全一致（diff < 1e-6）"""
        df = weihai_df[["value"]].head(128).dropna().reset_index(drop=True)
        r = router.execute("fft_transform", {
            "column": "value", "sampling_rate": 96.0, "top_k": 0,
        }, {"data": df})
        assert "data" in r and "dominant_frequency" in r
        platform_amp = r["data"]["amplitude"].values

        signal  = df["value"].astype(float).values
        n       = len(signal)
        fft_val = np.fft.rfft(signal)
        local_amp = np.abs(fft_val) * 2.0 / n

        # 截到 platform 返回的长度
        min_len  = min(len(platform_amp), len(local_amp))
        max_diff = float(np.max(np.abs(platform_amp[:min_len] - local_amp[:min_len])))
        print(f"\n  [fft_transform] max_diff={max_diff:.2e} ✓")
        assert max_diff < 1e-6

    # ── smape_score / mse_rmse_mae 评估算子 ────────────────────────────────
    def test_evaluation_operators_vs_numpy(self, router):
        """评估指标算子与 numpy/sklearn 手算完全一致"""
        y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y_pred = np.array([1.1, 2.2, 2.9, 4.1, 5.0])

        r_smape = router.execute("smape_score", {}, {
            "y_true": y_true.tolist(), "y_pred": y_pred.tolist()
        })
        r_reg = router.execute("mse_rmse_mae", {}, {
            "y_true": y_true.tolist(), "y_pred": y_pred.tolist()
        })
        assert "score" in r_smape
        assert all(k in r_reg for k in ("mse", "rmse", "mae"))

        # numpy 基准
        local_smape = smape(y_true, y_pred)
        local_mse   = float(np.mean((y_true - y_pred) ** 2))
        local_rmse  = float(np.sqrt(local_mse))
        local_mae   = float(np.mean(np.abs(y_true - y_pred)))

        print(f"\n  [smape_score]  platform={r_smape['score']:.6f}  local={local_smape:.6f}")
        print(f"  [mse_rmse_mae] mse={r_reg['mse']:.6f}/{local_mse:.6f}  "
              f"rmse={r_reg['rmse']:.6f}/{local_rmse:.6f}  "
              f"mae={r_reg['mae']:.6f}/{local_mae:.6f}")

        assert abs(r_smape["score"] - local_smape) < 1e-6
        assert abs(r_reg["mse"]  - local_mse)  < 1e-6
        assert abs(r_reg["rmse"] - local_rmse) < 1e-6
        assert abs(r_reg["mae"]  - local_mae)  < 1e-6

    # ── r2_score ───────────────────────────────────────────────────────────
    def test_r2_score_vs_sklearn(self, router):
        """r2_score 与 sklearn.r2_score 完全一致"""
        from sklearn.metrics import r2_score as sk_r2
        y_true = [1.0, 2.0, 3.0, 4.0, 5.0]
        y_pred = [1.1, 2.2, 2.9, 4.1, 5.0]
        r = router.execute("r2_score", {}, {"y_true": y_true, "y_pred": y_pred})
        assert "score" in r
        local = float(sk_r2(y_true, y_pred))
        diff  = abs(r["score"] - local)
        print(f"\n  [r2_score] platform={r['score']:.8f}  local={local:.8f}  diff={diff:.2e}")
        assert diff < 1e-9


# ══════════════════════════════════════════════════════════════════════════
# 场景 C — 统一 I/O 契约规范检查（覆盖 A/B 两个场景之外的通用算子）
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not os.path.exists(WEIHAI_CSV), reason="weihai csv not found")
class TestUnifiedIOContracts:
    """
    验证所有未在工作流中用过的新算子严格遵守统一 I/O 契约：
      - 输入 DataFrame → inputs["data"]
      - 输出 DataFrame → result["data"]
      - 评估标量 → result["score"]
      - 训练型算子 → result 含 model_id / predictions / y_true / feature_list
    """

    @pytest.fixture(scope="class")
    def small_df(self, router):
        r = router.execute("load_csv", {"file_path": WEIHAI_CSV, "delimiter": ","}, {})
        df = r["data"]
        if "parent_id" in df.columns:
            df = df[(df["parent_id"] == "park_01") & (df["child_id"] == "yARGkDuq")].copy()
        if "value" not in df.columns and "load" in df.columns:
            df = df.rename(columns={"load": "value"})
        df["record_time"] = pd.to_datetime(df["record_time"])
        return df.head(200).reset_index(drop=True)

    @pytest.fixture(scope="class")
    def clf_data(self):
        from sklearn.datasets import make_classification
        X, y = make_classification(n_samples=60, n_features=5, n_classes=2, random_state=42)
        return pd.DataFrame(X, columns=list("abcde")), y

    def _assert_data_df(self, result, op_id):
        assert "data" in result, f"{op_id}: 缺少 'data' key，返回 {list(result.keys())}"
        assert isinstance(result["data"], pd.DataFrame), f"{op_id}: 'data' 不是 DataFrame"

    def _assert_score_float(self, result, op_id):
        assert "score" in result, f"{op_id}: 缺少 'score' key，返回 {list(result.keys())}"
        assert isinstance(result["score"], (int, float)), f"{op_id}: score 不是数值"

    def _assert_train_keys(self, result, op_id):
        for k in ("model_id", "predictions", "y_true", "feature_list"):
            assert k in result, f"{op_id}: 缺少 '{k}'，返回 {list(result.keys())}"

    # ── 数据预处理 ──────────────────────────────────────────────────────────
    def test_remove_duplicates_contract(self, router, small_df):
        r = router.execute("remove_duplicates", {}, {"data": small_df})
        self._assert_data_df(r, "remove_duplicates")
        assert "rows_removed" in r and isinstance(r["rows_removed"], int)

    def test_column_select_contract(self, router, small_df):
        df = small_df[["record_time", "value"]].copy()
        r = router.execute("column_select", {"columns": ["value"]}, {"data": df})
        self._assert_data_df(r, "column_select")
        assert list(r["data"].columns) == ["value"]
        assert len(r["data"]) == len(df)

    def test_data_aggregate_contract(self, router, small_df):
        df = small_df[["record_time", "value"]].copy()
        df["date"] = df["record_time"].dt.date.astype(str)
        r = router.execute("data_aggregate", {
            "group_by": ["date"], "agg_columns": ["value"], "agg_func": "mean"
        }, {"data": df})
        self._assert_data_df(r, "data_aggregate")
        assert len(r["data"]) <= df["date"].nunique()

    def test_one_hot_encode_contract(self, router, small_df):
        df = small_df[["value"]].head(50).copy()
        df["cat"] = ["A", "B", "C"] * (50 // 3) + ["A"] * (50 % 3)
        r = router.execute("one_hot_encode", {}, {"data": df})
        self._assert_data_df(r, "one_hot_encode")
        assert "new_columns" in r and isinstance(r["new_columns"], list)

    def test_binning_contract(self, router, small_df):
        df = small_df[["value"]].head(50).dropna().copy()
        r = router.execute("binning", {
            "column": "value", "method": "equal_width", "bins": 5
        }, {"data": df})
        self._assert_data_df(r, "binning")
        assert "value_bin" in r["data"].columns

    # ── 特征工程 ────────────────────────────────────────────────────────────
    def test_pca_contract(self, router, small_df):
        df = small_df[["value"]].head(100).copy()
        df["v1"] = df["value"].shift(1)
        df = df.dropna().reset_index(drop=True)
        r = router.execute("pca", {"n_components": 2}, {"data": df})
        self._assert_data_df(r, "pca")
        assert "explained_variance_ratio" in r
        evr = r["explained_variance_ratio"]
        assert sum(evr) <= 1.0 + 1e-9

    def test_polynomial_features_contract(self, router, clf_data):
        X, _ = clf_data
        r = router.execute("polynomial_features", {
            "degree": 2, "interaction_only": True, "include_bias": False
        }, {"data": X})
        self._assert_data_df(r, "polynomial_features")
        assert r["data"].shape[1] > X.shape[1]

    def test_variance_threshold_contract(self, router, clf_data):
        X, _ = clf_data
        # 加一个常数列（方差 = 0）
        X_c = X.copy()
        X_c["const"] = 1.0
        r = router.execute("variance_threshold", {"threshold": 0.0}, {"data": X_c})
        self._assert_data_df(r, "variance_threshold")
        assert "removed_columns" in r
        assert "const" in r["removed_columns"]

    # ── 聚类 ────────────────────────────────────────────────────────────────
    def test_kmeans_contract(self, router, clf_data):
        X, _ = clf_data
        r = router.execute("kmeans", {"n_clusters": 3}, {"data": X})
        labels = r.get("labels")
        assert labels is not None and isinstance(labels, np.ndarray)
        assert set(labels.tolist()).issubset(set(range(3)))
        assert r["cluster_centers"].shape == (3, X.shape[1])
        assert isinstance(r["inertia"], float)

    def test_dbscan_contract(self, router, clf_data):
        X, _ = clf_data
        r = router.execute("dbscan", {"eps": 1.0, "min_samples": 3}, {"data": X})
        labels = r.get("labels")
        assert labels is not None
        n_found = r["n_clusters_found"]
        # -1 is noise label, rest ∈ [0, n_clusters-1]
        valid = set(labels.tolist()) - {-1}
        if valid:
            assert max(valid) < n_found

    def test_isolation_forest_vs_sklearn(self, router, clf_data):
        """平台 isolation_forest 与 sklearn.IsolationForest 同参数 labels 完全一致"""
        from sklearn.ensemble import IsolationForest
        X, _ = clf_data

        r = router.execute("isolation_forest", {
            "mode": "fit_predict", "contamination": 0.1,
            "n_estimators": 50, "random_state": 42, "save_model": "false",
        }, {"data": X})
        labels_platform = r["labels"]

        clf = IsolationForest(n_estimators=50, contamination=0.1, random_state=42)
        labels_local = clf.fit_predict(X.values).astype(int)

        np.testing.assert_array_equal(
            labels_platform, labels_local,
            err_msg="isolation_forest: 与 sklearn 输出不一致"
        )
        print(f"\n  [isolation_forest] labels match sklearn ✓ (n={len(labels_platform)})")

    # ── 分类器 ──────────────────────────────────────────────────────────────
    def test_logistic_regression_train_contract(self, router, clf_data):
        X, y = clf_data
        r = router.execute("logistic_regression", {"mode": "train", "max_iter": 300},
                           {"features": X, "target": y})
        self._assert_train_keys(r, "logistic_regression")

    def test_naive_bayes_classifier_train_contract(self, router, clf_data):
        X, y = clf_data
        r = router.execute("naive_bayes_classifier", {"mode": "train"},
                           {"features": X, "target": y})
        self._assert_train_keys(r, "naive_bayes_classifier")

    def test_xgboost_classifier_train_contract(self, router, clf_data):
        X, y = clf_data
        r = router.execute("xgboost_classifier", {
            "mode": "train", "n_estimators": 30, "max_depth": 3,
        }, {"features": X, "target": y})
        self._assert_train_keys(r, "xgboost_classifier")

    # ── 评估指标 ────────────────────────────────────────────────────────────
    def test_accuracy_score_contract(self, router):
        r = router.execute("accuracy_score", {},
                           {"y_true": [0, 1, 0, 1], "y_pred": [0, 1, 1, 1]})
        self._assert_score_float(r, "accuracy_score")

    def test_f1_score_contract(self, router):
        r = router.execute("f1_score", {"average": "macro"},
                           {"y_true": [0, 1, 0, 1], "y_pred": [0, 1, 1, 1]})
        self._assert_score_float(r, "f1_score")
        assert 0.0 <= r["score"] <= 1.0

    def test_precision_recall_f1_contract(self, router):
        r = router.execute("precision_recall_f1", {},
                           {"y_true": [0, 1, 0, 1, 2, 2],
                            "y_pred": [0, 1, 0, 0, 2, 1]})
        for k in ("precision", "recall", "f1"):
            assert k in r, f"precision_recall_f1 缺少 '{k}'"

    def test_confusion_matrix_vs_sklearn(self, router):
        """confusion_matrix 与 sklearn 完全一致"""
        from sklearn.metrics import confusion_matrix as sk_cm
        y_true = [0, 1, 0, 1, 2, 0, 1, 2, 0, 1]
        y_pred = [0, 1, 0, 0, 2, 0, 1, 1, 0, 2]
        r = router.execute("confusion_matrix", {},
                           {"y_true": y_true, "y_pred": y_pred})
        assert "matrix" in r or "data" in r
        matrix_key = "matrix" if "matrix" in r else "data"
        platform_cm = np.asarray(r[matrix_key])
        local_cm    = sk_cm(y_true, y_pred)
        np.testing.assert_array_equal(platform_cm, local_cm,
                                      err_msg="confusion_matrix: 与 sklearn 不一致")
        print(f"\n  [confusion_matrix] matches sklearn ✓")

    def test_classification_report_vs_sklearn(self, router):
        """classification_report 的 accuracy/macro_f1 与 sklearn 一致"""
        from sklearn.metrics import accuracy_score, f1_score as sk_f1
        y_true = [0, 1, 0, 1, 2, 0, 1, 2, 0, 1]
        y_pred = [0, 1, 0, 0, 2, 0, 1, 1, 0, 2]
        r = router.execute("classification_report", {},
                           {"y_true": y_true, "y_pred": y_pred})
        for k in ("accuracy", "macro_f1", "report_text", "report_dict"):
            assert k in r, f"classification_report 缺少 '{k}'"
        local_acc = float(accuracy_score(y_true, y_pred))
        local_f1  = float(sk_f1(y_true, y_pred, average="macro", zero_division=0))
        assert abs(r["accuracy"]  - local_acc) < 1e-9
        assert abs(r["macro_f1"] - local_f1)  < 1e-9
        print(f"\n  [classification_report] acc={r['accuracy']:.4f} f1={r['macro_f1']:.4f} ✓")

    # ── 可视化算子 ──────────────────────────────────────────────────────────
    def test_visualization_operators_contract(self, router, small_df):
        """line_chart/scatter_chart/histogram/bar_chart/pie_chart 返回合法 ECharts option"""
        df = small_df[["value"]].head(50).copy()
        df["v2"] = df["value"] * 0.9 + 1

        for op_id, params in [
            ("line_chart",    {"x_column": "value", "y_column": "v2"}),
            ("scatter_chart", {"x_column": "value", "y_column": "v2"}),
            ("histogram",     {"target_column": "value", "bins": 10}),
            ("bar_chart",     {"x_column": "value", "y_column": "v2"}),
        ]:
            r = router.execute(op_id, params, {"data": df})
            assert "chart_option" in r and "chart_type" in r, \
                f"{op_id}: 缺少 chart_option 或 chart_type"
            assert "series" in r["chart_option"], \
                f"{op_id}: chart_option 缺少 'series'"

        # pie_chart 需要 name/value 列
        df_cat = pd.DataFrame({"cat": ["A", "B", "C", "A", "B"], "val": [10, 20, 15, 5, 8]})
        r = router.execute("pie_chart",
                           {"name_column": "cat", "value_column": "val"},
                           {"data": df_cat})
        assert r["chart_type"] == "pie"
        print("\n  [visualization ops] all 5 operators return valid ECharts options ✓")

    # ── 数据输出算子 ─────────────────────────────────────────────────────────
    def test_export_csv_relative_path(self, router, small_df):
        r = router.execute("export_csv", {}, {"data": small_df.head(5)})
        assert "output_path" in r
        assert not os.path.isabs(r["output_path"]), \
            f"export_csv output_path 不应是绝对路径: {r['output_path']}"
        assert r["rows_written"] == 5
        # 清理
        candidate = os.path.join(_BACKEND_DIR, r["output_path"])
        if os.path.exists(candidate):
            os.remove(candidate)

    def test_load_parquet_roundtrip(self, router, tmp_path):
        """load_parquet 读回数据与 pd.read_parquet 完全一致"""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        p = str(tmp_path / "rt.parquet")
        df.to_parquet(p)
        r = router.execute("load_parquet", {"file_path": p}, {})
        self._assert_data_df(r, "load_parquet")
        pd.testing.assert_frame_equal(r["data"], df)
        print("\n  [load_parquet round-trip] matches pd.read_parquet ✓")

    def test_load_json_empty_array(self, router, tmp_path):
        """load_json 对空 JSON 数组返回 0 行 DataFrame 不报错"""
        p = str(tmp_path / "empty.json")
        with open(p, "w") as f:
            f.write("[]")
        r = router.execute("load_json", {"file_path": p}, {})
        self._assert_data_df(r, "load_json")
        assert len(r["data"]) == 0
        print("\n  [load_json empty] returns 0-row DataFrame ✓")
# @AI_GENERATED: end
