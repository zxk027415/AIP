# -*- coding: utf-8 -*-
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error
from typing import Any, Dict


def smape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    finite = np.isfinite(y_true) & np.isfinite(y_pred)
    if not finite.any():
        return 0.0
    y_true, y_pred = y_true[finite], y_pred[finite]
    denominator = np.abs(y_true) + np.abs(y_pred)
    mask = denominator > 1e-8
    if not mask.any():
        return 0.0
    return float(
        np.round(2.0 * np.mean(np.abs(y_pred[mask] - y_true[mask]) / denominator[mask]) * 100, 4)
    )


def evaluate(y_true, y_pred, label: str = "") -> Dict[str, Any]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    finite = np.isfinite(y_true) & np.isfinite(y_pred)
    if not finite.any():
        return {"label": label, "SMAPE": 0.0, "MAE": 0.0, "RMSE": 0.0}
    y_true, y_pred = y_true[finite], y_pred[finite]
    return {
        "label": label,
        "SMAPE": smape(y_true, y_pred),
        "MAE": float(np.round(mean_absolute_error(y_true, y_pred), 4)),
        "RMSE": float(np.round(np.sqrt(mean_squared_error(y_true, y_pred)), 4)),
    }
