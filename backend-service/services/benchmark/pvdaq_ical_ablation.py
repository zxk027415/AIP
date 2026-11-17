# @AI_GENERATED
"""
PVDAQ leakage-safe i_cal 消融运行器
===================================

在固定设备日、固定设备 split 和固定模型形状下比较四个 i_cal 合同：

1. leaky_device_ical：全期 normal 标签拟合，仅作泄漏上界控制。
2. value_only：i_cal 恒为 0，作为无校准基线。
3. global_train_devices_only：每折只用训练设备 normal 日拟合。
4. history_past_only：每设备只用最早选定月的无标签历史拟合。

本模块只读取转换后的 benchmark parquet，不修改生产工作流或输入数据。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    auc,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
)
from sklearn.model_selection import GroupShuffleSplit

from services.benchmark.pvdaq_ical_contracts import (
    ALL_CONTRACTS,
    CONTRACT_GLOBAL_TRAIN_ONLY,
    STATIC_CONTRACTS,
    build_static_contract_predictions,
    fit_global_calibrator,
    predict_global_calibrator,
)
from services.benchmark.pvdaq_q1_refit import (
    RF_FEATURE_SUFFIXES,
    extract_rf_day_features,
    rf_feature_names_for_channels,
)

logger = logging.getLogger(__name__)

LABEL_MAP = {"normal": 0, "abnormal": 1}
MODEL_RF = "rf"
MODEL_TSC = "tsc"
ALL_MODELS = (MODEL_RF, MODEL_TSC)
COMMON_WINDOW_LENGTH = 288
RF_CHANNELS = ("value", "i_cal")
TSC_CHANNELS = ("value", "i_cal", "is_measured")


def _require_relative_path(value: str, field_name: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"{field_name} 必须是相对路径: {value}")
    return path


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"不能 JSON 序列化: {type(value)!r}")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=_json_default)


def _load_corpus(
    converted_dir: Path,
    truth_csv: Path,
    cohort_csv: Path,
    scope_csv: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[int, Tuple[int, int]], Dict[str, Any]]:
    """加载 72 个正式 system-month，并建立共同设备日纳入/排除索引。"""
    scope = pd.read_csv(scope_csv)
    required_scope = {"system_id", "year", "month"}
    if not required_scope.issubset(scope.columns):
        raise ValueError(f"scope 缺少列: {sorted(required_scope - set(scope.columns))}")
    scope = scope[["system_id", "year", "month"]].copy()
    scope[["system_id", "year", "month"]] = scope[
        ["system_id", "year", "month"]
    ].astype(int)
    if len(scope) != 72 or not scope.groupby("system_id").size().eq(6).all():
        raise ValueError("消融要求 12 个系统各 6 个正式月份，共 72 system-month")

    cohort = pd.read_csv(cohort_csv)
    rated_power = cohort.set_index("system_id")["rated_power_kw"].astype(float).to_dict()
    target_interval = (
        cohort.set_index("system_id")["target_analysis_interval"].astype(str).to_dict()
    )

    calibration_months: Dict[int, Tuple[int, int]] = {}
    for system_id, group in scope.sort_values(["year", "month"]).groupby("system_id"):
        first = group.iloc[0]
        calibration_months[int(system_id)] = (int(first["year"]), int(first["month"]))

    frames: List[pd.DataFrame] = []
    for row in scope.sort_values(["system_id", "year", "month"]).itertuples(index=False):
        system_id = int(row.system_id)
        year = int(row.year)
        month = int(row.month)
        source = converted_dir / str(system_id) / f"{year}-{month:02d}.parquet"
        if not source.exists():
            raise FileNotFoundError(source)
        frame = pd.read_parquet(source)
        if "i_cal" in frame.columns or "is_measured" in frame.columns:
            raise ValueError(
                f"输入必须是未注入 i_cal 的 converted_base，发现预构造列: {source}"
            )
        required = {
            "time",
            "device_id",
            "value",
            "poa_irradiance",
            "module_temp",
        }
        if not required.issubset(frame.columns):
            raise ValueError(f"{source} 缺少列: {sorted(required - set(frame.columns))}")
        frame = frame.copy()
        frame["time"] = pd.to_datetime(frame["time"])
        frame["date"] = frame["time"].dt.normalize()
        frame["system_id"] = system_id
        frame["year"] = year
        frame["month"] = month
        frame["rated_power_kw"] = float(rated_power[system_id])
        frame["target_analysis_interval"] = target_interval[system_id]
        frames.append(frame)

    points = pd.concat(frames, ignore_index=True)
    duplicate_points = points.duplicated(["system_id", "time"]).sum()
    if duplicate_points:
        raise ValueError(f"转换数据存在 {duplicate_points} 个重复 system/time 点")

    truth = pd.read_csv(truth_csv)
    truth["date"] = pd.to_datetime(truth["date"]).dt.normalize()
    truth["system_id"] = truth["system_id"].astype(int)
    truth["y"] = truth["label"].map(LABEL_MAP)
    truth_fields = truth[
        ["system_id", "date", "label", "y", "interval_minutes", "relative_pr"]
    ].copy()
    if truth_fields.duplicated(["system_id", "date"]).any():
        raise ValueError("truth 存在重复 system/date")

    points = points.merge(
        truth_fields[["system_id", "date", "label", "y"]],
        on=["system_id", "date"],
        how="left",
        validate="many_to_one",
    )
    points["sample_id"] = (
        points["device_id"].astype(str)
        + "|"
        + points["date"].dt.strftime("%Y-%m-%d")
    )

    daily = (
        points.groupby(["system_id", "date", "sample_id"], as_index=False)
        .agg(
            device_id=("device_id", "first"),
            points_count=("time", "size"),
            year=("year", "first"),
            month=("month", "first"),
            target_analysis_interval=("target_analysis_interval", "first"),
            rated_power_kw=("rated_power_kw", "first"),
        )
    )
    sample_index = truth_fields.merge(
        daily,
        on=["system_id", "date"],
        how="left",
        validate="one_to_one",
    )
    sample_index["sample_id"] = sample_index["sample_id"].fillna(
        sample_index["system_id"].map(lambda sid: f"pvdaq-system-{int(sid)}")
        + "|"
        + sample_index["date"].dt.strftime("%Y-%m-%d")
    )

    calibration_values = sample_index["system_id"].map(calibration_months)
    sample_index["calibration_year"] = calibration_values.map(
        lambda item: int(item[0])
    )
    sample_index["calibration_month"] = calibration_values.map(
        lambda item: int(item[1])
    )
    sample_index["is_calibration_month"] = (
        (sample_index["year"] == sample_index["calibration_year"])
        & (sample_index["month"] == sample_index["calibration_month"])
    )

    def exclusion_reasons(row: pd.Series) -> str:
        reasons: List[str] = []
        if pd.isna(row["label"]):
            reasons.append("missing_pr_label")
        if row["target_analysis_interval"] != "5min_from_1min":
            reasons.append("non_5min_system")
        points_count = row["points_count"]
        if pd.isna(points_count) or int(points_count) != COMMON_WINDOW_LENGTH:
            reasons.append("not_exactly_288_points")
        if bool(row["is_calibration_month"]):
            reasons.append("earliest_month_reserved_for_calibration")
        return "|".join(reasons)

    sample_index["exclusion_reason"] = sample_index.apply(exclusion_reasons, axis=1)
    sample_index["included"] = sample_index["exclusion_reason"] == ""
    sample_index.sort_values(["device_id", "date"], inplace=True)
    sample_index.reset_index(drop=True, inplace=True)

    included = sample_index.loc[sample_index["included"]].copy()
    if included["device_id"].nunique() != 11:
        raise ValueError(
            f"共同 universe 预期 11 台 5min 设备，实际 {included['device_id'].nunique()}"
        )
    if not included["points_count"].eq(COMMON_WINDOW_LENGTH).all():
        raise AssertionError("共同样本中存在非 288 点日")
    if included["label"].isna().any():
        raise AssertionError("共同样本中存在空标签")
    if included["is_calibration_month"].any():
        raise AssertionError("最早校准月泄漏进共同分类样本")

    included_ids = set(included["sample_id"])
    common_points = points.loc[points["sample_id"].isin(included_ids)]
    if len(common_points) != len(included) * COMMON_WINDOW_LENGTH:
        raise AssertionError("共同点数与设备日 × 288 不一致")

    sample_payload = "\n".join(
        f"{row.sample_id}|{int(row.y)}"
        for row in included.itertuples(index=False)
    )
    corpus_meta = {
        "scope_months": int(len(scope)),
        "scope_systems": int(scope["system_id"].nunique()),
        "point_rows": int(len(points)),
        "sample_rows_total": int(len(sample_index)),
        "sample_rows_included": int(len(included)),
        "sample_devices_included": int(included["device_id"].nunique()),
        "normal_samples": int((included["label"] == "normal").sum()),
        "abnormal_samples": int((included["label"] == "abnormal").sum()),
        "sample_index_sha256": _sha256_text(sample_payload),
        "label_sha256": _sha256_text(
            "\n".join(str(int(value)) for value in included["y"])
        ),
    }
    return points, sample_index, calibration_months, corpus_meta


def _build_device_splits(
    included: pd.DataFrame,
    *,
    n_splits: int,
    test_size: float,
    random_state: int,
    sample_index_sha256: str,
    label_sha256: str,
) -> List[Dict[str, Any]]:
    groups = included["device_id"].astype(str).to_numpy()
    y = included["y"].astype(int).to_numpy()
    splitter = GroupShuffleSplit(
        n_splits=n_splits,
        test_size=test_size,
        random_state=random_state,
    )
    splits: List[Dict[str, Any]] = []
    seen_signatures: Dict[str, int] = {}
    for fold, (train_idx, test_idx) in enumerate(
        splitter.split(np.zeros(len(included)), y, groups)
    ):
        train_devices = sorted(set(groups[train_idx]))
        test_devices = sorted(set(groups[test_idx]))
        overlap = set(train_devices) & set(test_devices)
        if overlap:
            raise AssertionError(f"fold {fold} 设备泄漏: {sorted(overlap)}")
        if len(np.unique(y[test_idx])) != 2:
            raise ValueError(f"fold {fold} 测试集不是二分类")
        signature = _sha256_text(
            "train=" + "|".join(train_devices) + ";test=" + "|".join(test_devices)
        )
        duplicate_of = seen_signatures.get(signature)
        if duplicate_of is None:
            seen_signatures[signature] = fold
        splits.append(
            {
                "fold": int(fold),
                "train_device_ids": train_devices,
                "test_device_ids": test_devices,
                "train_device_count": int(len(train_devices)),
                "test_device_count": int(len(test_devices)),
                "train_sample_count": int(len(train_idx)),
                "test_sample_count": int(len(test_idx)),
                "split_signature": signature,
                "duplicate_of_fold": duplicate_of,
                "sample_index_sha256": sample_index_sha256,
                "label_sha256": label_sha256,
            }
        )
    return splits


def _build_sample_point_index(
    points: pd.DataFrame,
    included: pd.DataFrame,
) -> Dict[str, np.ndarray]:
    included_ids = set(included["sample_id"])
    common = points.loc[points["sample_id"].isin(included_ids)].sort_values(
        ["sample_id", "time"]
    )
    groups: Dict[str, np.ndarray] = {}
    for sample_id, group in common.groupby("sample_id", sort=False):
        indices = group.index.to_numpy()
        if len(indices) != COMMON_WINDOW_LENGTH:
            raise AssertionError(f"{sample_id} 不是 {COMMON_WINDOW_LENGTH} 点")
        groups[str(sample_id)] = indices
    if set(groups) != included_ids:
        raise AssertionError("sample point index 与共同样本 ID 不一致")
    return groups


def _build_model_matrix(
    model_name: str,
    points: pd.DataFrame,
    included: pd.DataFrame,
    sample_point_index: Mapping[str, np.ndarray],
    ical_prediction: pd.Series,
) -> Tuple[np.ndarray, pd.DataFrame]:
    """按固定 sample 顺序构造 RF 50 维或 TSC 288×3 输入。"""
    if not points.index.equals(ical_prediction.index):
        raise AssertionError("i_cal prediction index 与 point index 不一致")

    matrices: List[np.ndarray] = []
    summaries: List[Dict[str, Any]] = []
    rf_feature_names = rf_feature_names_for_channels(list(RF_CHANNELS))

    for row in included.itertuples(index=False):
        indices = sample_point_index[str(row.sample_id)]
        day = points.loc[indices].sort_values("time")
        value = day["value"].to_numpy(dtype=float)
        i_cal = ical_prediction.loc[day.index].to_numpy(dtype=float)

        if model_name == MODEL_RF:
            features: Dict[str, float] = {}
            features.update(extract_rf_day_features(value, col_name="value"))
            features.update(extract_rf_day_features(i_cal, col_name="i_cal"))
            feature_vector = np.asarray(
                [features[name] for name in rf_feature_names], dtype=float
            )
            matrices.append(
                np.nan_to_num(
                    feature_vector,
                    nan=0.0,
                    posinf=0.0,
                    neginf=0.0,
                )
            )
        elif model_name == MODEL_TSC:
            waveform = np.column_stack(
                [
                    np.nan_to_num(value, nan=0.0),
                    np.nan_to_num(i_cal, nan=0.0),
                    np.ones(COMMON_WINDOW_LENGTH, dtype=float),
                ]
            ).astype(np.float32)
            matrices.append(waveform)
        else:
            raise ValueError(f"未知 model_name: {model_name}")

        summaries.append(
            {
                "sample_id": str(row.sample_id),
                "ical_mean": float(np.nanmean(i_cal)),
                "ical_max": float(np.nanmax(i_cal)),
                "ical_nonzero_points": int(np.count_nonzero(i_cal)),
                "ical_negative_points": int((i_cal < 0).sum()),
            }
        )

    X = np.stack(matrices)
    if np.isnan(X).any() or np.isinf(X).any():
        raise ValueError(f"{model_name} 输入存在 NaN/Inf")
    expected_shape = (
        (len(included), len(RF_CHANNELS) * len(RF_FEATURE_SUFFIXES))
        if model_name == MODEL_RF
        else (len(included), COMMON_WINDOW_LENGTH, len(TSC_CHANNELS))
    )
    if X.shape != expected_shape:
        raise AssertionError(f"{model_name} shape={X.shape}, expected={expected_shape}")
    return X, pd.DataFrame(summaries)


def _new_classifier(model_name: str, random_state: int) -> Any:
    if model_name == MODEL_RF:
        return RandomForestClassifier(
            n_estimators=200,
            max_depth=None,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        )
    if model_name == MODEL_TSC:
        from aeon.classification.convolution_based import MultiRocketClassifier

        return MultiRocketClassifier(random_state=random_state)
    raise ValueError(f"未知 model_name: {model_name}")


def _fit_predict_classifier(
    model_name: str,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    *,
    random_state: int,
) -> Tuple[np.ndarray, np.ndarray]:
    model = _new_classifier(model_name, random_state)
    if model_name == MODEL_TSC:
        X_train = np.ascontiguousarray(X_train.transpose(0, 2, 1))
        X_test = np.ascontiguousarray(X_test.transpose(0, 2, 1))
    model.fit(X_train, y_train)
    y_pred = np.asarray(model.predict(X_test), dtype=int)
    if not hasattr(model, "predict_proba"):
        raise ValueError(f"{model_name} 不支持 predict_proba，无法计算 PR-AUC")
    probabilities = np.asarray(model.predict_proba(X_test), dtype=float)
    classes = list(np.asarray(model.classes_, dtype=int))
    if 1 not in classes:
        raise ValueError(f"{model_name} classes_ 不含 abnormal=1: {classes}")
    y_score = probabilities[:, classes.index(1)]
    return y_pred, y_score


def _fold_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
) -> Dict[str, Any]:
    precision, recall, _ = precision_recall_curve(y_true, y_score, pos_label=1)
    return {
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "pr_auc": float(auc(recall, precision)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }


def _summarize_results(
    contract: str,
    model_name: str,
    included: pd.DataFrame,
    fold_rows: List[Dict[str, Any]],
    predictions: pd.DataFrame,
    corpus_meta: Mapping[str, Any],
    n_splits: int,
    test_size: float,
    random_state: int,
) -> Dict[str, Any]:
    y_true = predictions["y_true"].to_numpy(dtype=int)
    y_pred = predictions["y_pred"].to_numpy(dtype=int)
    y_score = predictions["y_score"].to_numpy(dtype=float)
    precision, recall, _ = precision_recall_curve(y_true, y_score, pos_label=1)
    fold_ba = [float(row["balanced_accuracy"]) for row in fold_rows]
    fold_pr = [float(row["pr_auc"]) for row in fold_rows]
    input_shape = (
        [len(included), len(RF_CHANNELS) * len(RF_FEATURE_SUFFIXES)]
        if model_name == MODEL_RF
        else [len(included), COMMON_WINDOW_LENGTH, len(TSC_CHANNELS)]
    )
    return {
        "_comment": "@AI_GENERATED",
        "contract": contract,
        "model_name": model_name,
        "n_samples": int(len(included)),
        "n_devices": int(included["device_id"].nunique()),
        "n_splits": int(n_splits),
        "test_size": float(test_size),
        "random_state": int(random_state),
        "input_shape": input_shape,
        "sample_index_sha256": corpus_meta["sample_index_sha256"],
        "label_sha256": corpus_meta["label_sha256"],
        "mean_balanced_accuracy": float(np.mean(fold_ba)),
        "std_balanced_accuracy": float(np.std(fold_ba)),
        "mean_pr_auc": float(np.mean(fold_pr)),
        "overall_balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "overall_pr_auc": float(auc(recall, precision)),
        "overall_confusion_matrix": confusion_matrix(
            y_true, y_pred, labels=[0, 1]
        ).tolist(),
        "overall_classification_report": classification_report(
            y_true,
            y_pred,
            target_names=["normal", "abnormal"],
            output_dict=True,
            zero_division=0,
        ),
        "fold_results": fold_rows,
        "_comment_end": "@AI_GENERATED: end",
    }


def _run_contract_model(
    *,
    contract: str,
    model_name: str,
    points: pd.DataFrame,
    included: pd.DataFrame,
    sample_point_index: Mapping[str, np.ndarray],
    calibration_months: Mapping[int, Tuple[int, int]],
    splits: Sequence[Mapping[str, Any]],
    corpus_meta: Mapping[str, Any],
    output_dir: Path,
    n_splits: int,
    test_size: float,
    random_state: int,
) -> None:
    target = output_dir / contract / model_name
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"拒绝覆盖已有结果目录: {target}")
    target.mkdir(parents=True, exist_ok=True)

    y = included["y"].astype(int).to_numpy()
    groups = included["device_id"].astype(str).to_numpy()
    sample_ids = included["sample_id"].astype(str).to_numpy()

    static_prediction: pd.Series | None = None
    static_matrix: np.ndarray | None = None
    static_summaries: pd.DataFrame | None = None
    calibration_audits: List[Dict[str, Any]] = []

    if contract in STATIC_CONTRACTS:
        static_prediction, calibration_audits = build_static_contract_predictions(
            points,
            contract=contract,
            calibration_months=calibration_months,
            random_state=random_state,
        )
        static_matrix, static_summaries = _build_model_matrix(
            model_name,
            points,
            included,
            sample_point_index,
            static_prediction,
        )

    fold_rows: List[Dict[str, Any]] = []
    prediction_rows: List[Dict[str, Any]] = []

    for split in splits:
        fold = int(split["fold"])
        train_devices = set(split["train_device_ids"])
        test_devices = set(split["test_device_ids"])
        train_mask = np.asarray([device in train_devices for device in groups])
        test_mask = np.asarray([device in test_devices for device in groups])
        if np.any(train_mask & test_mask):
            raise AssertionError(f"fold {fold} sample 设备泄漏")
        if int(train_mask.sum()) != int(split["train_sample_count"]):
            raise AssertionError(f"fold {fold} train 样本数与 split manifest 不一致")
        if int(test_mask.sum()) != int(split["test_sample_count"]):
            raise AssertionError(f"fold {fold} test 样本数与 split manifest 不一致")

        if contract == CONTRACT_GLOBAL_TRAIN_ONLY:
            calibrator, audit = fit_global_calibrator(
                points,
                train_device_ids=train_devices,
                test_device_ids=test_devices,
                fold=fold,
                random_state=random_state,
            )
            fold_prediction = pd.Series(0.0, index=points.index, dtype=float)
            common_indices = np.concatenate(list(sample_point_index.values()))
            common_frame = points.loc[common_indices]
            common_prediction = predict_global_calibrator(calibrator, common_frame)
            fold_prediction.loc[common_prediction.index] = common_prediction
            audit["prediction_row_count"] = int(len(common_prediction))
            audit["negative_prediction_count"] = int((common_prediction < 0).sum())
            calibration_audits.append(audit)
            X, daily_summaries = _build_model_matrix(
                model_name,
                points,
                included,
                sample_point_index,
                fold_prediction,
            )
        else:
            if static_matrix is None or static_summaries is None:
                raise AssertionError(f"{contract} 静态矩阵未构造")
            X = static_matrix
            daily_summaries = static_summaries

        t0 = time.time()
        y_pred, y_score = _fit_predict_classifier(
            model_name,
            X[train_mask],
            y[train_mask],
            X[test_mask],
            random_state=random_state,
        )
        elapsed = time.time() - t0
        metrics = _fold_metrics(y[test_mask], y_pred, y_score)
        fold_row: Dict[str, Any] = {
            "fold": fold,
            "contract": contract,
            "model_name": model_name,
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
            "train_devices": int(len(train_devices)),
            "test_devices": int(len(test_devices)),
            "train_device_ids": "|".join(sorted(train_devices)),
            "test_device_ids": "|".join(sorted(test_devices)),
            "device_leak": 0,
            "split_signature": split["split_signature"],
            "duplicate_of_fold": split["duplicate_of_fold"],
            "sample_index_sha256": corpus_meta["sample_index_sha256"],
            "label_sha256": corpus_meta["label_sha256"],
            "balanced_accuracy": metrics["balanced_accuracy"],
            "pr_auc": metrics["pr_auc"],
            "confusion_matrix": json.dumps(metrics["confusion_matrix"]),
            "elapsed_sec": round(elapsed, 3),
        }
        fold_rows.append(fold_row)

        test_positions = np.flatnonzero(test_mask)
        summary_by_id = daily_summaries.set_index("sample_id")
        for position, prediction, score in zip(test_positions, y_pred, y_score):
            sample_id = sample_ids[position]
            meta = included.iloc[position]
            i_cal_summary = summary_by_id.loc[sample_id]
            prediction_rows.append(
                {
                    "contract": contract,
                    "model_name": model_name,
                    "fold": fold,
                    "sample_id": sample_id,
                    "system_id": int(meta["system_id"]),
                    "device_id": str(meta["device_id"]),
                    "date": str(pd.Timestamp(meta["date"]).date()),
                    "y_true": int(y[position]),
                    "y_pred": int(prediction),
                    "y_score": float(score),
                    "ical_source": contract,
                    "ical_mean": float(i_cal_summary["ical_mean"]),
                    "ical_max": float(i_cal_summary["ical_max"]),
                    "ical_nonzero_points": int(
                        i_cal_summary["ical_nonzero_points"]
                    ),
                    "ical_negative_points": int(
                        i_cal_summary["ical_negative_points"]
                    ),
                    "split_signature": split["split_signature"],
                    "sample_index_sha256": corpus_meta["sample_index_sha256"],
                }
            )

        logger.info(
            "%s/%s fold=%d BA=%.3f PR-AUC=%.3f train=%d test=%d elapsed=%.1fs",
            contract,
            model_name,
            fold,
            metrics["balanced_accuracy"],
            metrics["pr_auc"],
            train_mask.sum(),
            test_mask.sum(),
            elapsed,
        )

    fold_frame = pd.DataFrame(fold_rows)
    prediction_frame = pd.DataFrame(prediction_rows)
    summary = _summarize_results(
        contract,
        model_name,
        included,
        fold_rows,
        prediction_frame,
        corpus_meta,
        n_splits,
        test_size,
        random_state,
    )

    fold_frame.to_csv(target / "fold_metrics.csv", index=False)
    prediction_frame.to_parquet(target / "predictions.parquet", index=False)
    pd.DataFrame(calibration_audits).to_csv(
        target / "calibration_audit.csv", index=False
    )
    _write_json(target / "summary.json", summary)

    logger.info(
        "%s/%s 完成: BA=%.3f±%.3f PR-AUC=%.3f abnormal_F1=%.3f",
        contract,
        model_name,
        summary["mean_balanced_accuracy"],
        summary["std_balanced_accuracy"],
        summary["mean_pr_auc"],
        summary["overall_classification_report"]["abnormal"]["f1-score"],
    )


def _write_base_artifacts(
    *,
    output_dir: Path,
    sample_index: pd.DataFrame,
    calibration_months: Mapping[int, Tuple[int, int]],
    splits: Sequence[Mapping[str, Any]],
    corpus_meta: Mapping[str, Any],
    converted_dir: Path,
    truth_csv: Path,
    cohort_csv: Path,
    scope_csv: Path,
    n_splits: int,
    test_size: float,
    random_state: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    serializable_index = sample_index.copy()
    serializable_index["date"] = pd.to_datetime(serializable_index["date"]).dt.strftime(
        "%Y-%m-%d"
    )
    serializable_index.to_csv(output_dir / "sample_index.csv", index=False)
    serializable_index.loc[~serializable_index["included"]].to_csv(
        output_dir / "excluded_samples.csv", index=False
    )

    split_payload = {
        "_comment": "@AI_GENERATED",
        "_field_notes": {
            "fold": "折号",
            "train_device_ids": "训练设备 ID 列表",
            "test_device_ids": "测试设备 ID 列表",
            "split_signature": "设备分区签名",
            "duplicate_of_fold": "若设备组合重复，指向首次出现的折号",
            "sample_index_sha256": "共同设备日及标签顺序哈希",
        },
        "splits": list(splits),
        "_comment_end": "@AI_GENERATED: end",
    }
    _write_json(output_dir / "device_splits.json", split_payload)

    source_files = {
        "services/benchmark/pvdaq_ical_ablation.py": Path(__file__),
        "services/benchmark/pvdaq_ical_contracts.py": Path(__file__).with_name(
            "pvdaq_ical_contracts.py"
        ),
    }
    manifest = {
        "_comment": "@AI_GENERATED",
        "_field_notes": {
            "sample_index_sha256": "共同样本索引哈希",
            "label_sha256": "共同标签顺序哈希",
            "calibration_months": "各系统仅供 history 合同拟合的最早选定月",
            "relative_inputs": "全部相对于 backend-service 的输入路径",
        },
        "goal": "在完全相同的后校准设备日和设备 split 上审计 i_cal 泄漏影响",
        "contracts": {
            "leaky_device_ical": "测试设备全期 normal 标签参与拟合，仅作上界控制",
            "value_only": "i_cal 恒为 0；保持 RF 50 维和 TSC 288x3 形状",
            "global_train_devices_only": "每折只用训练设备 normal 日拟合；测试设备零参与",
            "history_past_only": "每设备只用最早选定月无标签拟合；该月不参与分类",
        },
        "common_universe": {
            **dict(corpus_meta),
            "window_length": COMMON_WINDOW_LENGTH,
            "rf_channels": list(RF_CHANNELS),
            "tsc_channels": list(TSC_CHANNELS),
            "is_measured_semantics": "PVDAQ 对齐控制，恒为 1，不代表本轮验证了缺失掩码价值",
        },
        "evaluation_contract": {
            "splitter": "GroupShuffleSplit",
            "n_splits": int(n_splits),
            "test_size": float(test_size),
            "random_state": int(random_state),
            "group_key": "device_id",
        },
        "calibration_months": {
            str(system_id): f"{year:04d}-{month:02d}"
            for system_id, (year, month) in calibration_months.items()
        },
        "relative_inputs": {
            "converted_dir": converted_dir.as_posix(),
            "truth_csv": truth_csv.as_posix(),
            "cohort_csv": cohort_csv.as_posix(),
            "scope_csv": scope_csv.as_posix(),
        },
        "source_sha256": {
            relative_path: _sha256_file(source_path)
            for relative_path, source_path in source_files.items()
        },
        "limitations": [
            "PR 标签仍由六个月全期中位数构造，不是完全在线因果真值。",
            "global i_cal 用 rated_power_kw 近似电流缩放，缺少电压和串并联元数据。",
            "history 最早月包含未知比例异常且月份不连续，按部署现实保留污染。",
            "10 次随机设备划分可能出现重复设备组合，device_splits.json 显式审计。",
        ],
        "_comment_end": "@AI_GENERATED: end",
    }
    _write_json(output_dir / "run_manifest.json", manifest)


def run_ablation(
    *,
    converted_dir: Path,
    truth_csv: Path,
    cohort_csv: Path,
    scope_csv: Path,
    output_dir: Path,
    contracts: Sequence[str],
    models: Sequence[str],
    n_splits: int,
    test_size: float,
    random_state: int,
) -> None:
    points, sample_index, calibration_months, corpus_meta = _load_corpus(
        converted_dir,
        truth_csv,
        cohort_csv,
        scope_csv,
    )
    included = sample_index.loc[sample_index["included"]].copy().reset_index(drop=True)
    splits = _build_device_splits(
        included,
        n_splits=n_splits,
        test_size=test_size,
        random_state=random_state,
        sample_index_sha256=str(corpus_meta["sample_index_sha256"]),
        label_sha256=str(corpus_meta["label_sha256"]),
    )
    _write_base_artifacts(
        output_dir=output_dir,
        sample_index=sample_index,
        calibration_months=calibration_months,
        splits=splits,
        corpus_meta=corpus_meta,
        converted_dir=converted_dir,
        truth_csv=truth_csv,
        cohort_csv=cohort_csv,
        scope_csv=scope_csv,
        n_splits=n_splits,
        test_size=test_size,
        random_state=random_state,
    )
    sample_point_index = _build_sample_point_index(points, included)

    logger.info(
        "共同样本: %d 日, %d 设备, normal=%d, abnormal=%d",
        len(included),
        included["device_id"].nunique(),
        (included["label"] == "normal").sum(),
        (included["label"] == "abnormal").sum(),
    )
    for contract in contracts:
        if contract not in ALL_CONTRACTS:
            raise ValueError(f"未知 contract: {contract}")
        for model_name in models:
            if model_name not in ALL_MODELS:
                raise ValueError(f"未知 model: {model_name}")
            _run_contract_model(
                contract=contract,
                model_name=model_name,
                points=points,
                included=included,
                sample_point_index=sample_point_index,
                calibration_months=calibration_months,
                splits=splits,
                corpus_meta=corpus_meta,
                output_dir=output_dir,
                n_splits=n_splits,
                test_size=test_size,
                random_state=random_state,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PVDAQ leakage-safe i_cal 固定样本/固定设备 split 消融",
    )
    parser.add_argument(
        "--converted-dir",
        default=(
            "data/benchmark_raw/pvdaq/reruns/expansion_6months_20260907/"
            "converted_base"
        ),
    )
    parser.add_argument(
        "--truth-csv",
        default=(
            "data/benchmark_raw/pvdaq/reruns/expansion_6months_20260907/"
            "analysis/q1_daily_truth.csv"
        ),
    )
    parser.add_argument(
        "--cohort-csv",
        default="data/benchmark_raw/pvdaq/analysis/q1_cohort_selected.csv",
    )
    parser.add_argument(
        "--scope-csv",
        default=(
            "data/benchmark_raw/pvdaq/reruns/expansion_6months_20260907/"
            "analysis/combined_6month_scope.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=(
            "data/benchmark_raw/pvdaq/reruns/expansion_6months_20260907/"
            "analysis/ical_leakage_ablation"
        ),
    )
    parser.add_argument("--contracts", nargs="+", default=list(ALL_CONTRACTS))
    parser.add_argument("--models", nargs="+", default=list(ALL_MODELS))
    parser.add_argument("--n-splits", type=int, default=10)
    parser.add_argument("--test-size", type=float, default=0.3)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    paths = {
        "converted_dir": _require_relative_path(args.converted_dir, "converted_dir"),
        "truth_csv": _require_relative_path(args.truth_csv, "truth_csv"),
        "cohort_csv": _require_relative_path(args.cohort_csv, "cohort_csv"),
        "scope_csv": _require_relative_path(args.scope_csv, "scope_csv"),
        "output_dir": _require_relative_path(args.output_dir, "output_dir"),
    }
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_ablation(
        converted_dir=paths["converted_dir"],
        truth_csv=paths["truth_csv"],
        cohort_csv=paths["cohort_csv"],
        scope_csv=paths["scope_csv"],
        output_dir=paths["output_dir"],
        contracts=list(args.contracts),
        models=list(args.models),
        n_splits=int(args.n_splits),
        test_size=float(args.test_size),
        random_state=int(args.random_state),
    )


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
