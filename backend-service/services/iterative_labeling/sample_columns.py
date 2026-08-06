# -*- coding: utf-8 -*-
"""
services/iterative_labeling/sample_columns.py — 样本派生列的唯一实现

训练侧（``snapshot_builder``）和预测侧（``inference_sample``）都从这里取
``period_is_*`` 与 ``night_*`` 列的构造逻辑，用「共用同一份代码」从结构上保证
训练/预测特征口径一致——两边各写一份是这条链路上最容易出现静默错的地方。

原先这些函数是 ``snapshot_builder`` 的模块级私有函数，预测侧没有对应实现，
导致逐点标签路径下预测产出的列与训练快照不同构。
"""

# @AI_GENERATED
from __future__ import annotations

import logging
from typing import Dict

import pandas as pd

from services.operator_backends.night_anomaly import compute_night_anomaly_features

logger = logging.getLogger(__name__)

#: 夜间量级坏值阈值 —— 超过即视为脏数据并置 0，避免污染夜间特征。
NIGHT_BAD_VALUE_THRESHOLD = 1e9

#: 采样间隔（秒）。逐点标签链路按 5 分钟采样。
SAMPLING_INTERVAL_SECONDS = 300

#: 样本派生列名，供预测侧校验特征契约是否可满足。
PERIOD_ONE_HOT_COLUMNS = ("period_is_whole", "period_is_daylight", "period_is_night")
NIGHT_FEATURE_COLUMNS = (
    "night_nonzero_current_ratio",
    "night_current_mean",
    "night_current_max",
    "night_over_threshold_duration",
    "night_power_residual_mean",
)


def period_one_hot(period_role: str) -> Dict[str, float]:
    """把 period_role 展开成三个 one-hot 列。"""
    return {
        "period_is_whole": 1.0 if period_role == "whole" else 0.0,
        "period_is_daylight": 1.0 if period_role == "daylight" else 0.0,
        "period_is_night": 1.0 if period_role == "night" else 0.0,
    }


def night_feature_defaults() -> Dict[str, float]:
    """非夜间样本的 night_* 列取值（全 0），保证列集合恒定。"""
    return {
        "night_nonzero_current_ratio": 0.0,
        "night_current_mean": 0.0,
        "night_current_max": 0.0,
        "night_over_threshold_duration": 0.0,
        "night_power_residual_mean": 0.0,
    }


def sanitize_night_values(df: pd.DataFrame) -> pd.DataFrame:
    """拦截夜间量级坏值（|x| > 1e9）并置 0，不改变行数。"""
    out = df.copy()
    for col in ("value", "i_cal"):
        if col not in out.columns:
            continue
        numeric = pd.to_numeric(out[col], errors="coerce")
        bad = numeric.abs() > NIGHT_BAD_VALUE_THRESHOLD
        if bad.any():
            logger.warning("sample_columns: 拦截 %d 行夜间量级坏值列 %s", int(bad.sum()), col)
            numeric = numeric.mask(bad, 0.0)
        out[col] = numeric
    return out


def compute_night_features(sample_rows: pd.DataFrame) -> Dict[str, float]:
    """对夜间样本计算 night_* 特征。"""
    cleaned = sanitize_night_values(sample_rows)
    return compute_night_anomaly_features(
        cleaned,
        current_col="i_cal" if "i_cal" in cleaned.columns else "value",
        power_col="value" if "value" in cleaned.columns else None,
    )


def sample_derived_columns(period_role: str, sample_rows: pd.DataFrame) -> Dict[str, float]:
    """返回一条样本的全部派生列（period one-hot + night_*）。

    Args:
        period_role: 样本时段角色（whole / daylight / night）。
        sample_rows: 该样本覆盖的测量行。
    Returns:
        列名到取值的映射，训练侧与预测侧共用。
    """
    night = (
        compute_night_features(sample_rows)
        if period_role == "night"
        else night_feature_defaults()
    )
    return {**period_one_hot(period_role), **night}
# @AI_GENERATED: end
