# @AI_GENERATED
"""
PVDAQ i_cal 消融合同
====================

为 PVDAQ 外部验证提供只在内存中运行的期望电流（i_cal）校准合同。
本模块不写入或覆盖 parquet，所有拟合来源都会返回结构化审计记录。

合同：
- leaky_device_ical：每设备全期 normal 标签日拟合，仅作泄漏上界控制。
- value_only：i_cal 恒为 0，不拟合校准器。
- global_train_devices_only：每折只使用训练设备 normal 日拟合全局校准器。
- history_past_only：每设备只使用最早选定月的无标签历史拟合。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

DAYLIGHT_POA_THRESHOLD = 10.0
MIN_CALIBRATION_POINTS = 50
REGRESSOR_FEATURES = ["poa_irradiance", "module_temp"]

CONTRACT_LEAKY_DEVICE_ICAL = "leaky_device_ical"
CONTRACT_VALUE_ONLY = "value_only"
CONTRACT_GLOBAL_TRAIN_ONLY = "global_train_devices_only"
CONTRACT_HISTORY_PAST_ONLY = "history_past_only"

ALL_CONTRACTS = (
    CONTRACT_LEAKY_DEVICE_ICAL,
    CONTRACT_VALUE_ONLY,
    CONTRACT_GLOBAL_TRAIN_ONLY,
    CONTRACT_HISTORY_PAST_ONLY,
)
STATIC_CONTRACTS = (
    CONTRACT_LEAKY_DEVICE_ICAL,
    CONTRACT_VALUE_ONLY,
    CONTRACT_HISTORY_PAST_ONLY,
)


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{context} 缺少列: {missing}")


def _daylight_feature_mask(frame: pd.DataFrame) -> pd.Series:
    """选择可从部署时特征独立计算 i_cal 的白天点。"""
    _require_columns(
        frame,
        REGRESSOR_FEATURES,
        "i_cal 预测输入",
    )
    return (
        (frame["poa_irradiance"] > DAYLIGHT_POA_THRESHOLD)
        & frame["poa_irradiance"].notna()
        & frame["module_temp"].notna()
    )


def _calibration_fit_mask(frame: pd.DataFrame) -> pd.Series:
    """在预测特征有效的基础上，进一步要求拟合目标 value 有效。"""
    _require_columns(frame, ["value"], "i_cal 校准目标")
    return _daylight_feature_mask(frame) & frame["value"].notna()


def _new_regressor(random_state: int) -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        random_state=random_state,
        n_jobs=-1,
    )


def fit_device_calibrator(
    fit_frame: pd.DataFrame,
    *,
    contract: str,
    system_id: int,
    device_id: str,
    labels_used: bool,
    fit_scope: str,
    random_state: int = 42,
    min_points: int = MIN_CALIBRATION_POINTS,
) -> Tuple[RandomForestRegressor, Dict[str, Any]]:
    """拟合单设备 POA/温度 → 电流回归器，并返回可审计训练来源。"""
    _require_columns(
        fit_frame,
        ["time", "date", "value", "poa_irradiance", "module_temp"],
        f"system {system_id} 单设备校准",
    )
    valid = fit_frame.loc[_calibration_fit_mask(fit_frame)].copy()
    if len(valid) < min_points:
        raise ValueError(
            f"system {system_id} 校准点不足: {len(valid)} < {min_points}; "
            "禁止静默回退为全零 i_cal"
        )

    model = _new_regressor(random_state)
    X_train = valid[REGRESSOR_FEATURES].to_numpy(dtype=float)
    y_train = valid["value"].to_numpy(dtype=float)
    model.fit(X_train, y_train)

    fit_dates = pd.to_datetime(valid["date"])
    audit: Dict[str, Any] = {
        "contract": contract,
        "fold": None,
        "system_id": int(system_id),
        "device_id": str(device_id),
        "fit_scope": fit_scope,
        "fit_device_ids": str(device_id),
        "fit_device_count": 1,
        "fit_row_count": int(len(valid)),
        "fit_day_count": int(fit_dates.dt.date.nunique()),
        "fit_date_min": str(fit_dates.min().date()),
        "fit_date_max": str(fit_dates.max().date()),
        "labels_used": bool(labels_used),
        "test_device_fit_overlap": None,
        "target_scale_mode": "raw_device_current",
        "train_r2": float(model.score(X_train, y_train)),
        "fallback_reason": None,
    }
    return model, audit


def predict_device_calibrator(
    model: RandomForestRegressor,
    frame: pd.DataFrame,
) -> pd.Series:
    """使用单设备校准器预测 i_cal；夜间或特征缺失点保持 0。"""
    prediction = pd.Series(0.0, index=frame.index, dtype=float)
    valid = _daylight_feature_mask(frame)
    if valid.any():
        prediction.loc[valid] = model.predict(
            frame.loc[valid, REGRESSOR_FEATURES].to_numpy(dtype=float)
        )
    return prediction


def build_static_contract_predictions(
    points: pd.DataFrame,
    *,
    contract: str,
    calibration_months: Mapping[int, Tuple[int, int]],
    random_state: int = 42,
    min_points: int = MIN_CALIBRATION_POINTS,
) -> Tuple[pd.Series, List[Dict[str, Any]]]:
    """
    构造不依赖 CV fold 的 i_cal。

    history_past_only 的拟合选择只使用 system_id/year/month，不读取 label；
    label 仅在拟合结束后用于记录校准月污染诊断。
    """
    if contract not in STATIC_CONTRACTS:
        raise ValueError(f"非静态合同不能调用此函数: {contract}")

    prediction = pd.Series(0.0, index=points.index, dtype=float)
    if contract == CONTRACT_VALUE_ONLY:
        return prediction, [
            {
                "contract": contract,
                "fold": None,
                "system_id": None,
                "device_id": None,
                "fit_scope": "no_calibrator",
                "fit_device_ids": "",
                "fit_device_count": 0,
                "fit_row_count": 0,
                "fit_day_count": 0,
                "fit_date_min": None,
                "fit_date_max": None,
                "labels_used": False,
                "test_device_fit_overlap": 0,
                "target_scale_mode": "ical_constant_zero",
                "train_r2": None,
                "fallback_reason": None,
                "prediction_row_count": int(len(points)),
                "negative_prediction_count": 0,
                "calibration_normal_days_diagnostic": 0,
                "calibration_abnormal_days_diagnostic": 0,
            }
        ]

    audits: List[Dict[str, Any]] = []
    for system_id, device_frame in points.groupby("system_id", sort=True):
        system_id = int(system_id)
        device_frame = device_frame.sort_values("time")
        device_id = str(device_frame["device_id"].iloc[0])

        if contract == CONTRACT_LEAKY_DEVICE_ICAL:
            fit_frame = device_frame.loc[device_frame["label"] == "normal"].copy()
            labels_used = True
            fit_scope = "all_six_month_normal_labels_including_evaluation_period"
            calibration_month = None
        else:
            if system_id not in calibration_months:
                raise ValueError(f"system {system_id} 缺少最早校准月")
            cal_year, cal_month = calibration_months[system_id]
            fit_frame = device_frame.loc[
                (device_frame["year"] == cal_year)
                & (device_frame["month"] == cal_month)
            ].copy()
            labels_used = False
            fit_scope = "earliest_selected_month_unlabeled_all_valid_daylight_points"
            calibration_month = f"{cal_year:04d}-{cal_month:02d}"

        model, audit = fit_device_calibrator(
            fit_frame,
            contract=contract,
            system_id=system_id,
            device_id=device_id,
            labels_used=labels_used,
            fit_scope=fit_scope,
            random_state=random_state,
            min_points=min_points,
        )
        device_prediction = predict_device_calibrator(model, device_frame)
        prediction.loc[device_frame.index] = device_prediction

        fit_day_labels = (
            fit_frame[["date", "label"]]
            .drop_duplicates("date")
            .dropna(subset=["label"])
        )
        audit.update(
            {
                "calibration_month": calibration_month,
                "prediction_row_count": int(len(device_frame)),
                "negative_prediction_count": int((device_prediction < 0).sum()),
                "calibration_normal_days_diagnostic": int(
                    (fit_day_labels["label"] == "normal").sum()
                ),
                "calibration_abnormal_days_diagnostic": int(
                    (fit_day_labels["label"] == "abnormal").sum()
                ),
            }
        )
        audits.append(audit)

    if prediction.isna().any():
        raise AssertionError(f"{contract} 产生 NaN i_cal")
    return prediction, audits


def _global_features(frame: pd.DataFrame) -> np.ndarray:
    _require_columns(
        frame,
        ["poa_irradiance", "module_temp", "rated_power_kw"],
        "全局 i_cal 特征",
    )
    rated = frame["rated_power_kw"].to_numpy(dtype=float)
    return np.column_stack(
        [
            frame["poa_irradiance"].to_numpy(dtype=float),
            frame["module_temp"].to_numpy(dtype=float),
            np.log1p(rated),
        ]
    )


def fit_global_calibrator(
    points: pd.DataFrame,
    *,
    train_device_ids: Iterable[str],
    test_device_ids: Iterable[str],
    fold: int,
    random_state: int = 42,
    min_points: int = MIN_CALIBRATION_POINTS,
) -> Tuple[RandomForestRegressor, Dict[str, Any]]:
    """
    每折只用训练设备 normal 日拟合全局 i_cal。

    目标先除以 rated_power_kw，设备按点数倒数等权，测试设备不得进入 fit。
    """
    train_devices = {str(item) for item in train_device_ids}
    test_devices = {str(item) for item in test_device_ids}
    overlap = train_devices & test_devices
    if overlap:
        raise AssertionError(f"fold {fold} train/test 设备重叠: {sorted(overlap)}")

    _require_columns(
        points,
        [
            "time",
            "date",
            "device_id",
            "system_id",
            "label",
            "value",
            "poa_irradiance",
            "module_temp",
            "rated_power_kw",
        ],
        "全局 i_cal 校准输入",
    )
    fit_mask = points["device_id"].isin(train_devices) & (points["label"] == "normal")
    fit_frame = points.loc[fit_mask & _calibration_fit_mask(points)].copy()
    fit_frame = fit_frame.loc[fit_frame["rated_power_kw"] > 0].copy()
    if len(fit_frame) < min_points:
        raise ValueError(
            f"fold {fold} 全局校准点不足: {len(fit_frame)} < {min_points}"
        )

    fit_devices = set(fit_frame["device_id"].astype(str).unique())
    if not fit_devices.issubset(train_devices):
        raise AssertionError(f"fold {fold} 全局 fit 包含非训练设备")
    test_overlap = fit_devices & test_devices
    if test_overlap:
        raise AssertionError(
            f"fold {fold} 全局 fit 泄漏测试设备: {sorted(test_overlap)}"
        )

    X_train = _global_features(fit_frame)
    rated = fit_frame["rated_power_kw"].to_numpy(dtype=float)
    y_train = fit_frame["value"].to_numpy(dtype=float) / rated

    device_counts = fit_frame.groupby("device_id")["device_id"].transform("size")
    sample_weight = 1.0 / device_counts.to_numpy(dtype=float)
    sample_weight *= len(sample_weight) / sample_weight.sum()

    model = _new_regressor(random_state)
    model.fit(X_train, y_train, sample_weight=sample_weight)

    fit_dates = pd.to_datetime(fit_frame["date"])
    audit: Dict[str, Any] = {
        "contract": CONTRACT_GLOBAL_TRAIN_ONLY,
        "fold": int(fold),
        "system_id": None,
        "device_id": None,
        "fit_scope": "train_devices_all_six_month_normal_labels",
        "fit_device_ids": "|".join(sorted(fit_devices)),
        "fit_device_count": int(len(fit_devices)),
        "fit_row_count": int(len(fit_frame)),
        "fit_day_count": int(
            fit_frame[["device_id", "date"]].drop_duplicates().shape[0]
        ),
        "fit_date_min": str(fit_dates.min().date()),
        "fit_date_max": str(fit_dates.max().date()),
        "labels_used": True,
        "test_device_fit_overlap": int(len(test_overlap)),
        "target_scale_mode": "value_divided_by_rated_power_kw",
        "train_r2": float(model.score(X_train, y_train, sample_weight=sample_weight)),
        "fallback_reason": None,
        "calibration_month": None,
        "prediction_row_count": None,
        "negative_prediction_count": None,
        "calibration_normal_days_diagnostic": int(
            fit_frame[["device_id", "date"]].drop_duplicates().shape[0]
        ),
        "calibration_abnormal_days_diagnostic": 0,
    }
    return model, audit


def predict_global_calibrator(
    model: RandomForestRegressor,
    frame: pd.DataFrame,
) -> pd.Series:
    """预测全局 i_cal，并按测试设备 rated_power_kw 恢复电流量级。"""
    prediction = pd.Series(0.0, index=frame.index, dtype=float)
    valid = _daylight_feature_mask(frame) & (frame["rated_power_kw"] > 0)
    if valid.any():
        normalized = model.predict(_global_features(frame.loc[valid]))
        prediction.loc[valid] = (
            normalized * frame.loc[valid, "rated_power_kw"].to_numpy(dtype=float)
        )
    return prediction
# @AI_GENERATED: end
