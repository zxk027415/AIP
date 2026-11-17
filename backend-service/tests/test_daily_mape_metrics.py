# @AI_GENERATED
"""日 MAPE / 滚动 median MAPE 单元测试。"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from services.precision_ops.daily_mape import (
    build_daily_series_from_predictions,
    merge_daily_series,
    rolling_mape_from_daily_series,
)


def _row(pred, actual, ts, cycle_id="c1"):
    return SimpleNamespace(
        predicted_value=pred,
        actual_value=actual,
        forecast_timestamp=ts,
        prediction_cycle_id=cycle_id,
    )


def test_daily_mape_single_cycle():
    rows = [
        _row(100.0, 100.0, datetime(2025, 10, 10, 0, 0)),
        _row(110.0, 100.0, datetime(2025, 10, 10, 0, 15)),
    ]
    series = build_daily_series_from_predictions(rows)
    assert len(series) == 1
    assert series[0]["business_day"] == "2025-10-10"
    assert series[0]["daily_mape"] == 5.0  # mean(0, 10)


def test_rolling_mape_is_median_of_daily_not_pooled():
    series = [
        {"business_day": "2025-10-06", "daily_mape": 1.0},
        {"business_day": "2025-10-07", "daily_mape": 2.0},
        {"business_day": "2025-10-08", "daily_mape": 3.0},
        {"business_day": "2025-10-09", "daily_mape": 100.0},  # outlier day
    ]
    med = rolling_mape_from_daily_series(series, window_days=7, method="median")
    assert med == 2.5


def test_merge_daily_series_keeps_recent_days():
    existing = [
        {"business_day": f"2025-10-{d:02d}", "prediction_cycle_id": f"a{d}", "daily_mape": 9.0}
        for d in range(1, 10)
    ]
    fresh = [{"business_day": "2025-10-10", "prediction_cycle_id": "b", "daily_mape": 1.0}]
    merged = merge_daily_series(existing, fresh, keep_days=7)
    days = sorted(x["business_day"] for x in merged)
    assert "2025-10-01" not in days
    assert days[-1] == "2025-10-10"
    assert len(days) == 7
# @AI_GENERATED: end
