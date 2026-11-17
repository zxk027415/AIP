# @AI_GENERATED
"""
PVDAQ Q1 方法重拟合（Path b）
==============================
在 PVDAQ 转换后数据 + PR 物理金标上，分别训练 RF 和 TSC 二分类模型，
使用 device-isolated GroupShuffleSplit CV 评估检测能力。

**RF 路线**：25 维 value_* 日统计特征 → RandomForestClassifier
**TSC 路线**：单通道 dc_current（即 value 列）288 点日波形 → MultiRocketClassifier

**标签**：0 = normal，1 = abnormal（来自 PR 物理金标）

**CV 策略**：按 device_id 分组隔离，测试集设备不出现在训练集中，
防止同设备时序模式泄漏。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import kurtosis as scipy_kurtosis, skew as scipy_skew
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    auc,
)
from sklearn.model_selection import GroupShuffleSplit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

LABEL_MAP = {"normal": 0, "abnormal": 1}

RF_FEATURE_SUFFIXES = [
    "max", "min", "mean", "median", "std",
    "kurtosis", "skew", "max_min",
    "above_mean_ratio", "variation_coef",
    "quantile_25", "quantile_75",
    "autocorr_lag1", "autocorr_lag2", "autocorr_lag3",
    "flat_rate", "flat_max", "flat_count", "max_drop",
    "diff_max", "diff_min", "diff_mean", "diff_median", "diff_std",
    "diff_kurtosis",
]
"""RF 特征后缀列表（25 维，与平台 _extract_rfc_features 对齐）"""

RF_FEATURE_NAMES = [f"value_{s}" for s in RF_FEATURE_SUFFIXES]

ALL_CHANNELS = ["value", "dc_power", "ac_power", "poa_irradiance", "module_temp"]
"""转换后 parquet 中的五核心数值通道"""


def rf_feature_names_for_channels(channels: List[str]) -> List[str]:
    """根据通道列表生成对应的 RF 特征列名列表。"""
    return [f"{ch}_{s}" for ch in channels for s in RF_FEATURE_SUFFIXES]


# ---------------------------------------------------------------------------
# RF 特征提取（支持多通道）
# ---------------------------------------------------------------------------

def extract_rf_day_features(
    day_values: np.ndarray,
    col_name: str = "value",
) -> Dict[str, float]:
    """
    从单日单通道时序提取 25 维统计特征。

    Parameters
    ----------
    day_values : ndarray
        单日某通道的值数组
    col_name : str
        通道名，用于特征命名前缀（如 "value"、"ac_power"）

    Returns
    -------
    dict
        {feature_name: float}
    """
    vals = day_values[~np.isnan(day_values)].astype(float)
    if len(vals) == 0:
        vals = np.array([0.0])
    diff = np.diff(vals) if len(vals) > 1 else np.array([0.0])

    mean_val = float(np.nanmean(vals))
    row: Dict[str, float] = {}

    # basic stats
    row[f"{col_name}_max"] = float(np.nanmax(vals))
    row[f"{col_name}_min"] = float(np.nanmin(vals))
    row[f"{col_name}_mean"] = mean_val
    row[f"{col_name}_median"] = float(np.nanmedian(vals))
    row[f"{col_name}_std"] = float(np.nanstd(vals))
    row[f"{col_name}_kurtosis"] = (
        float(scipy_kurtosis(vals, fisher=True, bias=False)) if len(vals) > 1 else 0.0
    )
    row[f"{col_name}_skew"] = (
        float(scipy_skew(vals, bias=False)) if len(vals) > 1 else 0.0
    )
    row[f"{col_name}_max_min"] = float(np.nanmax(vals) - np.nanmin(vals))
    row[f"{col_name}_above_mean_ratio"] = (
        float(np.sum(vals > mean_val) / len(vals)) if len(vals) > 0 else 0.0
    )
    row[f"{col_name}_variation_coef"] = (
        float(np.nanstd(vals) / abs(mean_val)) if abs(mean_val) > 1e-9 else 0.0
    )

    # quantiles
    row[f"{col_name}_quantile_25"] = float(np.nanquantile(vals, 0.25))
    row[f"{col_name}_quantile_75"] = float(np.nanquantile(vals, 0.75))

    # autocorrelation lag 1-3
    for lag in (1, 2, 3):
        if len(vals) > lag:
            c0 = np.var(vals)
            if c0 > 1e-12:
                cl = np.mean((vals[lag:] - mean_val) * (vals[:-lag] - mean_val))
                row[f"{col_name}_autocorr_lag{lag}"] = float(cl / c0)
            else:
                row[f"{col_name}_autocorr_lag{lag}"] = 0.0
        else:
            row[f"{col_name}_autocorr_lag{lag}"] = 0.0

    # flat features
    if len(vals) > 1:
        is_flat = np.abs(np.diff(vals)) < 1e-6
        flat_runs: List[int] = []
        run_len = 0
        for v in is_flat:
            if v:
                run_len += 1
            else:
                if run_len > 0:
                    flat_runs.append(run_len)
                run_len = 0
        if run_len > 0:
            flat_runs.append(run_len)
        row[f"{col_name}_flat_rate"] = float(np.sum(is_flat) / len(is_flat))
        row[f"{col_name}_flat_max"] = float(max(flat_runs)) if flat_runs else 0.0
        row[f"{col_name}_flat_count"] = float(len(flat_runs))
        row[f"{col_name}_max_drop"] = float(np.min(np.diff(vals)))
    else:
        row[f"{col_name}_flat_rate"] = 0.0
        row[f"{col_name}_flat_max"] = 0.0
        row[f"{col_name}_flat_count"] = 0.0
        row[f"{col_name}_max_drop"] = 0.0

    # diff stats
    row[f"{col_name}_diff_max"] = float(np.nanmax(diff)) if len(diff) > 0 else 0.0
    row[f"{col_name}_diff_min"] = float(np.nanmin(diff)) if len(diff) > 0 else 0.0
    row[f"{col_name}_diff_mean"] = float(np.nanmean(diff)) if len(diff) > 0 else 0.0
    row[f"{col_name}_diff_median"] = float(np.nanmedian(diff)) if len(diff) > 0 else 0.0
    row[f"{col_name}_diff_std"] = float(np.nanstd(diff)) if len(diff) > 0 else 0.0
    row[f"{col_name}_diff_kurtosis"] = (
        float(scipy_kurtosis(diff, fisher=True, bias=False)) if len(diff) > 2 else 0.0
    )

    return row


# ---------------------------------------------------------------------------
# 数据准备
# ---------------------------------------------------------------------------

def prepare_rf_dataset(
    converted_dir: Path,
    truth_csv: Path,
    channels: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """
    准备 RF 训练数据集：从转换后 parquet 提取日统计特征，对齐金标。

    Parameters
    ----------
    channels : list[str] | None
        要提取特征的通道列表。None 默认 ["value"]（Q1 向后兼容）

    Returns
    -------
    (features_df, X, y, groups)
        features_df: 含 system_id/date/device_id 和 N×25 维特征的 DataFrame
        X: [n_days, N*25] 特征矩阵
        y: [n_days] 标签（0/1）
        groups: [n_days] 设备分组 ID（用于 GroupShuffleSplit）
    """
    if channels is None:
        channels = ["value"]
    feature_cols = rf_feature_names_for_channels(channels)

    truth = pd.read_csv(truth_csv)
    truth = truth[truth["label"].notna()].copy()
    truth["date"] = pd.to_datetime(truth["date"]).dt.date
    truth["y"] = truth["label"].map(LABEL_MAP).astype(int)

    all_rows: List[Dict] = []

    for _, trow in truth.iterrows():
        sid = int(trow["system_id"])
        date_val = trow["date"]

        year = date_val.year
        month = date_val.month
        pq_path = converted_dir / str(sid) / f"{year}-{month:02d}.parquet"
        if not pq_path.exists():
            continue

        df = pd.read_parquet(pq_path)
        df["date"] = df["time"].dt.date
        day_df = df[df["date"] == date_val]
        if day_df.empty:
            continue

        # 提取每个通道的 25 维特征
        feats: Dict[str, Any] = {}
        for ch in channels:
            if ch in day_df.columns:
                ch_feats = extract_rf_day_features(day_df[ch].values, col_name=ch)
            else:
                ch_feats = {f"{ch}_{s}": 0.0 for s in RF_FEATURE_SUFFIXES}
            feats.update(ch_feats)

        feats["system_id"] = sid
        feats["date"] = str(date_val)
        feats["device_id"] = day_df["device_id"].iloc[0]
        feats["y"] = trow["y"]
        all_rows.append(feats)

    features_df = pd.DataFrame(all_rows)
    X = features_df[feature_cols].fillna(0).values
    y = features_df["y"].values
    groups = features_df["device_id"].values

    return features_df, X, y, groups


def prepare_tsc_dataset(
    converted_dir: Path,
    truth_csv: Path,
    window_length: int = 288,
    channels: Optional[List[str]] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """
    准备 TSC 训练数据集：从转换后 parquet 提取多通道日波形，对齐金标。

    Parameters
    ----------
    channels : list[str] | None
        通道列表。None 默认 ["value"]（Q1 向后兼容）

    Returns
    -------
    (X, y, groups, meta)
        X: [n_days, window_length, n_channels] 波形
        y: [n_days] 标签（0/1）
        groups: [n_days] 设备分组 ID
        meta: DataFrame 含 system_id/date/device_id
    """
    if channels is None:
        channels = ["value"]
    n_ch = len(channels)
    truth = pd.read_csv(truth_csv)
    truth = truth[truth["label"].notna()].copy()
    truth["date"] = pd.to_datetime(truth["date"]).dt.date
    truth["y"] = truth["label"].map(LABEL_MAP).astype(int)

    all_X: List[np.ndarray] = []
    all_y: List[int] = []
    all_groups: List[str] = []
    all_meta: List[Dict] = []

    for _, trow in truth.iterrows():
        sid = int(trow["system_id"])
        date_val = trow["date"]
        interval_min = float(trow.get("interval_minutes", 5.0))
        expected_len = int(24 * 60 / interval_min)  # 288 for 5min, 96 for 15min

        year = date_val.year
        month = date_val.month
        pq_path = converted_dir / str(sid) / f"{year}-{month:02d}.parquet"
        if not pq_path.exists():
            continue

        df = pd.read_parquet(pq_path)
        df["date"] = df["time"].dt.date
        day_df = df[df["date"] == date_val].sort_values("time")

        if len(day_df) != expected_len:
            # 不完整天：跳过
            continue

        # 提取多通道波形
        waveform_channels = []
        for ch in channels:
            if ch in day_df.columns:
                ch_vals = day_df[ch].values.astype(np.float32)
            else:
                ch_vals = np.zeros(expected_len, dtype=np.float32)
            ch_vals = np.nan_to_num(ch_vals, nan=0.0)
            waveform_channels.append(ch_vals)

        # shape: [expected_len, n_channels]
        waveform = np.column_stack(waveform_channels)

        all_X.append(waveform)
        all_y.append(int(trow["y"]))
        all_groups.append(day_df["device_id"].iloc[0])
        all_meta.append({
            "system_id": sid,
            "date": str(date_val),
            "device_id": day_df["device_id"].iloc[0],
            "window_length": expected_len,
        })

    if not all_X:
        return np.empty((0, window_length, n_ch)), np.array([]), np.array([]), pd.DataFrame()

    # 分离不同 window_length 的样本（288 vs 96）
    # 主模型只用 288 点的样本
    meta_df = pd.DataFrame(all_meta)
    mask_main = meta_df["window_length"] == window_length
    X = np.array([all_X[i] for i in range(len(all_X)) if mask_main.iloc[i]])
    y = np.array([all_y[i] for i in range(len(all_y)) if mask_main.iloc[i]])
    groups = np.array([all_groups[i] for i in range(len(all_groups)) if mask_main.iloc[i]])
    meta_out = meta_df[mask_main].reset_index(drop=True)

    n_excluded = (~mask_main).sum()
    if n_excluded > 0:
        logger.info("TSC: 排除 %d 个非 %d 点样本（如 15min 系统）", n_excluded, window_length)

    return X, y, groups, meta_out


# ---------------------------------------------------------------------------
# Device-isolated CV
# ---------------------------------------------------------------------------

def run_device_isolated_cv(
    model_name: str,
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    n_splits: int = 5,
    test_size: float = 0.3,
    random_state: int = 42,
    model_factory=None,
) -> Dict[str, Any]:
    """
    Device-isolated GroupShuffleSplit CV。

    Parameters
    ----------
    model_name : str
        "rf" 或 "tsc"
    X : ndarray
        特征矩阵（RF: [n, 25]，TSC: [n, 288, 1]）
    y : ndarray
        标签 [n]
    groups : ndarray
        设备分组 [n]
    n_splits : int
        CV 折数
    test_size : float
        测试集设备比例
    random_state : int
        随机种子
    model_factory : callable | None
        创建模型的工厂函数。None 则根据 model_name 自动选择。

    Returns
    -------
    dict
        包含各折指标、汇总指标、混淆矩阵、PR-AUC 等
    """
    if model_factory is None:
        if model_name == "rf":
            model_factory = lambda: RandomForestClassifier(
                n_estimators=200,
                max_depth=None,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1,
            )
        elif model_name == "tsc":
            model_factory = lambda: _create_multirocket()
        else:
            raise ValueError(f"未知 model_name: {model_name}")

    gss = GroupShuffleSplit(
        n_splits=n_splits,
        test_size=test_size,
        random_state=random_state,
    )

    fold_results: List[Dict] = []
    all_y_true: List[int] = []
    all_y_pred: List[int] = []
    all_y_proba: List[float] = []

    unique_devices = np.unique(groups)
    logger.info(
        "%s CV: %d 样本, %d 设备, %d 折, test_size=%.1f%%",
        model_name.upper(), len(y), len(unique_devices), n_splits, test_size * 100,
    )

    for fold_i, (train_idx, test_idx) in enumerate(gss.split(X, y, groups)):
        t0 = time.time()
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        groups_train = groups[train_idx]
        groups_test = groups[test_idx]

        # 验证设备隔离
        train_devices = set(groups_train)
        test_devices = set(groups_test)
        leak = train_devices & test_devices
        if leak:
            logger.warning("fold %d: 设备泄漏 %s", fold_i, leak)

        model = model_factory()

        if model_name == "tsc":
            # TSC: _prepare_input 由 wrapper 处理，这里直接用 aeon API
            X_train_aeon = np.ascontiguousarray(X_train.transpose(0, 2, 1))
            X_test_aeon = np.ascontiguousarray(X_test.transpose(0, 2, 1))
            model.fit(X_train_aeon, y_train)
            y_pred = model.predict(X_test_aeon)
            y_proba = None
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X_test_aeon)
                y_proba = proba[:, 1] if proba.shape[1] == 2 else None
        else:
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            y_proba = None
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X_test)
                y_proba = proba[:, 1] if proba.shape[1] == 2 else None

        elapsed = time.time() - t0
        bal_acc = balanced_accuracy_score(y_test, y_pred)
        cm = confusion_matrix(y_test, y_pred, labels=[0, 1])

        fold_result = {
            "fold": fold_i,
            "n_train": len(y_train),
            "n_test": len(y_test),
            "train_devices": len(train_devices),
            "test_devices": len(test_devices),
            "device_leak": len(leak),
            "balanced_accuracy": bal_acc,
            "confusion_matrix": cm.tolist(),
            "elapsed_sec": round(elapsed, 2),
        }

        # 计算 PR-AUC（仅当有 proba 时）
        if y_proba is not None and len(np.unique(y_test)) == 2:
            precision, recall, _ = precision_recall_curve(y_test, y_proba, pos_label=1)
            pr_auc = auc(recall, precision)
            fold_result["pr_auc"] = pr_auc
        else:
            fold_result["pr_auc"] = None

        fold_results.append(fold_result)
        all_y_true.extend(y_test.tolist())
        all_y_pred.extend(y_pred.tolist())
        if y_proba is not None:
            all_y_proba.extend(y_proba.tolist())

        logger.info(
            "  fold %d: bal_acc=%.3f, PR-AUC=%s, train=%d(%dd), test=%d(%dd), %.1fs",
            fold_i, bal_acc,
            "%.3f" % fold_result["pr_auc"] if fold_result["pr_auc"] is not None else "N/A",
            len(y_train), len(train_devices),
            len(y_test), len(test_devices),
            elapsed,
        )

    # 汇总
    all_y_true = np.array(all_y_true)
    all_y_pred = np.array(all_y_pred)
    overall_bal_acc = balanced_accuracy_score(all_y_true, all_y_pred)
    overall_cm = confusion_matrix(all_y_true, all_y_pred, labels=[0, 1])
    report = classification_report(
        all_y_true, all_y_pred,
        target_names=["normal", "abnormal"],
        output_dict=True,
        zero_division=0,
    )

    overall_pr_auc = None
    if all_y_proba and len(np.unique(all_y_true)) == 2:
        precision, recall, _ = precision_recall_curve(
            all_y_true, np.array(all_y_proba), pos_label=1,
        )
        overall_pr_auc = auc(recall, precision)

    return {
        "model_name": model_name,
        "n_samples": len(y),
        "n_devices": len(np.unique(groups)),
        "n_splits": n_splits,
        "test_size": test_size,
        "fold_results": fold_results,
        "overall_balanced_accuracy": overall_bal_acc,
        "overall_confusion_matrix": overall_cm.tolist(),
        "overall_classification_report": report,
        "overall_pr_auc": overall_pr_auc,
        "mean_balanced_accuracy": np.mean([f["balanced_accuracy"] for f in fold_results]),
        "std_balanced_accuracy": np.std([f["balanced_accuracy"] for f in fold_results]),
        "mean_pr_auc": (
            np.mean([f["pr_auc"] for f in fold_results if f["pr_auc"] is not None])
            if any(f["pr_auc"] is not None for f in fold_results) else None
        ),
    }


def _create_multirocket():
    """创建 MultiRocketClassifier 实例。"""
    from aeon.classification.convolution_based import MultiRocketClassifier
    return MultiRocketClassifier(random_state=42)


# ---------------------------------------------------------------------------
# 批量运行入口
# ---------------------------------------------------------------------------

def run_q1_refit(
    converted_dir: str | Path,
    truth_csv: str | Path,
    output_dir: str | Path,
    n_splits: int = 5,
    test_size: float = 0.3,
    random_state: int = 42,
    skip_tsc: bool = False,
    rf_channels: Optional[List[str]] = None,
    tsc_channels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    运行 Q1 Path(b) 方法重拟合：RF + TSC device-isolated CV。

    Parameters
    ----------
    rf_channels : list[str] | None
        RF 特征提取通道。None 默认 ["value"]
    tsc_channels : list[str] | None
        TSC 波形通道。None 默认 ["value"]
    """
    converted_dir = Path(converted_dir)
    truth_csv = Path(truth_csv)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Any] = {}

    # --- RF ---
    logger.info("=" * 60)
    logger.info("RF 二分类重拟合")
    logger.info("=" * 60)

    t0 = time.time()
    features_df, X_rf, y_rf, groups_rf = prepare_rf_dataset(converted_dir, truth_csv, channels=rf_channels)
    rf_ch_names = rf_channels or ["value"]
    logger.info("RF 数据准备: %d 样本, %d 特征 (%d 通道), %.1fs",
                len(y_rf), X_rf.shape[1], len(rf_ch_names), time.time() - t0)
    logger.info("  标签分布: normal=%d, abnormal=%d", (y_rf == 0).sum(), (y_rf == 1).sum())

    rf_result = run_device_isolated_cv(
        "rf", X_rf, y_rf, groups_rf,
        n_splits=n_splits, test_size=test_size, random_state=random_state,
    )
    results["rf"] = rf_result

    # 保存 RF 特征和逐折结果
    features_df.to_csv(output_dir / "q1_rf_features.csv", index=False)
    _save_results(rf_result, output_dir, "rf")

    # --- TSC ---
    if not skip_tsc:
        logger.info("=" * 60)
        logger.info("TSC MultiRocket 二分类重拟合")
        logger.info("=" * 60)

        t0 = time.time()
        X_tsc, y_tsc, groups_tsc, meta_tsc = prepare_tsc_dataset(
            converted_dir, truth_csv, window_length=288, channels=tsc_channels,
        )
        logger.info(
            "TSC 数据准备: %d 样本, shape=%s, %.1fs",
            len(y_tsc), X_tsc.shape, time.time() - t0,
        )
        logger.info("  标签分布: normal=%d, abnormal=%d", (y_tsc == 0).sum(), (y_tsc == 1).sum())

        if len(y_tsc) > 0:
            tsc_result = run_device_isolated_cv(
                "tsc", X_tsc, y_tsc, groups_tsc,
                n_splits=n_splits, test_size=test_size, random_state=random_state,
            )
            results["tsc"] = tsc_result
            meta_tsc.to_csv(output_dir / "q1_tsc_meta.csv", index=False)
            _save_results(tsc_result, output_dir, "tsc")
        else:
            logger.warning("TSC: 无有效 288 点样本")
            results["tsc"] = {"status": "no_valid_samples"}

    # 汇总打印
    print("\n" + "=" * 70)
    print("Q1 Path(b) 方法重拟合结果")
    print("=" * 70)
    for name in ["rf", "tsc"]:
        r = results.get(name)
        if not r or r.get("status") == "no_valid_samples":
            print(f"\n{name.upper()}: 无有效结果")
            continue
        print(f"\n--- {name.upper()} ---")
        print(f"  样本数: {r['n_samples']}, 设备数: {r['n_devices']}")
        print(f"  Balanced Accuracy: {r['mean_balanced_accuracy']:.3f} ± {r['std_balanced_accuracy']:.3f}")
        if r.get("mean_pr_auc") is not None:
            print(f"  PR-AUC: {r['mean_pr_auc']:.3f}")
        print(f"  Overall confusion matrix (pooled):")
        cm = r["overall_confusion_matrix"]
        print(f"    TN={cm[0][0]}, FP={cm[0][1]}")
        print(f"    FN={cm[1][0]}, TP={cm[1][1]}")
        rpt = r["overall_classification_report"]
        print(f"  Abnormal precision={rpt['abnormal']['precision']:.3f}, recall={rpt['abnormal']['recall']:.3f}, f1={rpt['abnormal']['f1-score']:.3f}")

    return results


def _save_results(result: Dict, output_dir: Path, prefix: str):
    """保存 CV 结果到 CSV 和 JSON。"""
    import json

    # 逐折指标
    folds = result.get("fold_results", [])
    if folds:
        fold_df = pd.DataFrame([
            {k: v for k, v in f.items() if k != "confusion_matrix"}
            for f in folds
        ])
        fold_df.to_csv(output_dir / f"q1_{prefix}_fold_results.csv", index=False)

    # 完整结果（JSON，混淆矩阵等）
    json_safe = {
        k: (v if not isinstance(v, np.ndarray) else v.tolist())
        for k, v in result.items()
    }
    with open(output_dir / f"q1_{prefix}_results.json", "w", encoding="utf-8") as f:
        json.dump(json_safe, f, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI 入口：python -m services.benchmark.pvdaq_q1_refit"""
    import argparse

    parser = argparse.ArgumentParser(description="PVDAQ Q1 Path(b) 方法重拟合")
    parser.add_argument("--converted-dir", default="data/benchmark_raw/pvdaq/converted")
    parser.add_argument("--truth-csv", default="data/benchmark_raw/pvdaq/analysis/q1_daily_truth.csv")
    parser.add_argument("--output-dir", default="data/benchmark_raw/pvdaq/analysis/q1_refit")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--test-size", type=float, default=0.3)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--skip-tsc", action="store_true", help="跳过 TSC（调试用）")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_q1_refit(
        converted_dir=args.converted_dir,
        truth_csv=args.truth_csv,
        output_dir=args.output_dir,
        n_splits=args.n_splits,
        test_size=args.test_size,
        random_state=args.random_state,
        skip_tsc=args.skip_tsc,
    )


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
