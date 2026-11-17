# -*- coding: utf-8 -*-
"""夜间异常特征族。"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd


def compute_night_anomaly_features(
    night_df: pd.DataFrame,
    current_col: str,
    power_col: Optional[str] = None,
    night_zero_epsilon: float = 0.01,
    night_anomaly_current_threshold: Optional[float] = None,
) -> Dict[str, float]:
    if night_df is None or night_df.empty or current_col not in night_df.columns:
        return {
            "night_nonzero_current_ratio": 0.0,
            "night_current_mean": 0.0,
            "night_current_max": 0.0,
            "night_over_threshold_duration": 0.0,
            "night_power_residual_mean": 0.0,
        }

    current = pd.to_numeric(night_df[current_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    eps = float(night_zero_epsilon)
    threshold = (
        float(night_anomaly_current_threshold)
        if night_anomaly_current_threshold is not None
        else eps
    )
    nonzero = np.abs(current) > eps
    over = np.abs(current) > threshold
    residual = 0.0
    if power_col and power_col in night_df.columns:
        power = pd.to_numeric(night_df[power_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        residual = float(np.mean(np.abs(power))) if len(power) else 0.0

    return {
        "night_nonzero_current_ratio": float(np.mean(nonzero)) if len(current) else 0.0,
        "night_current_mean": float(np.mean(current)) if len(current) else 0.0,
        "night_current_max": float(np.max(np.abs(current))) if len(current) else 0.0,
        "night_over_threshold_duration": float(np.sum(over)),
        "night_power_residual_mean": residual,
    }
