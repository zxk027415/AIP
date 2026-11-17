from __future__ import annotations

from typing import List

from .models import ErrorCode, err, ok


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def evaluate_accuracy(y_true: List[float], y_pred: List[float]):
    if len(y_true) != len(y_pred) or not y_true:
        return err(ErrorCode.METRIC_ERROR, "y_true and y_pred must be non-empty lists with equal length")
    epsilon = 1e-8
    mape = sum(abs(t - p) / max(abs(t), epsilon) for t, p in zip(y_true, y_pred)) / len(y_true)
    accuracy = clamp((1.0 - mape) * 100.0)
    return ok({"accuracy": round(accuracy, 2), "mape": round(mape, 6)})


def check_degradation(accuracy: float, threshold: float = 90.0) -> bool:
    """精度低于阈值判定为劣化。

    注:温和劣化演示下阈值贴近真实基线(默认 90),
    后续接真实气象影响性分析后再标定。需求层语义阈值为 80。
    """
    return accuracy < threshold

