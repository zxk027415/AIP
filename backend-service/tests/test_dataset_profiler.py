from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from hypothesis import given, strategies as st

from services.dataset_profiler import DatasetProfiler
from services.dataset_profiler_models import TestProfile, TrainProfile, ValidationProfile


def _train_df(days=10, weekday_load=120.0, weekend_load=90.0):
    start = datetime(2026, 4, 1)
    rows = []
    for i in range(days * 96):
        ts = start + timedelta(minutes=15 * i)
        base = weekday_load if ts.weekday() < 5 else weekend_load
        rows.append({"timestamp": ts, "load": base + 10 * np.sin(i / 96 * 2 * np.pi)})
    return pd.DataFrame(rows)


def _test_timestamps():
    start = datetime(2026, 4, 6)
    return [(start + timedelta(minutes=15 * i)).isoformat() for i in range(96)]


def test_train_profile_period_ratios_and_dominant_pattern():
    profiler = DatasetProfiler()

    profile = profiler.compute_train_profile(_train_df(), train_fit_mape=3.0)

    ratios = [v["ratio"] for v in profile.period_distribution.values()]
    assert abs(sum(ratios) - 1.0) < 0.01
    assert set(profile.load_curve_stats) == {"mean", "std", "skew", "kurtosis"}
    assert profile.train_fit_mape == 3.0
    assert profile.weekday_weekend_gap is not None
    assert profile.dominant_pattern == "weekday_dominant"


@given(
    train_loss=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    ratio=st.floats(min_value=-0.1, max_value=1.5, allow_nan=False, allow_infinity=False),
)
def test_validation_profile_overfit_thresholds(train_loss, ratio):
    profiler = DatasetProfiler()
    val_loss = train_loss * (1.0 + ratio)
    folds = [
        {"fold_id": i, "train_loss": train_loss, "val_loss": val_loss, "val_mape": 10.0 + i}
        for i in range(1, 6)
    ]

    profile = profiler.compute_validation_profile(folds)

    if ratio > 0.5:
        assert profile.overfit_indicator == "high"
    elif ratio >= 0.2:
        assert profile.overfit_indicator == "moderate"
    else:
        assert profile.overfit_indicator == "low"
    assert len(profile.cv_fold_losses) == 5
    assert profile.cv_val_mape == 13.0


def test_validation_profile_loss_trend_increasing():
    profiler = DatasetProfiler()
    folds = [
        {"fold_id": i, "train_loss": 10.0, "val_loss": 10.0 + i * 3, "val_mape": 10.0}
        for i in range(1, 6)
    ]

    profile = profiler.compute_validation_profile(folds)

    assert profile.cv_loss_trend == "increasing"


def test_test_profile_error_math_and_worst_period():
    profiler = DatasetProfiler()
    actual = np.full(96, 100.0)
    predicted = np.full(96, 100.0)
    predicted[68:84] = 120.0

    profile = profiler.compute_test_profile(actual, predicted, _test_timestamps())

    assert profile.overall_mape == round(float(np.mean(np.abs((actual - predicted) / actual)) * 100), 6)
    assert profile.period_error_breakdown["worst_period"] == "evening_peak"
    assert profile.max_single_point_error["error_pct"] == 20.0


def test_tri_dataset_diagnosis_rules():
    profiler = DatasetProfiler()
    train = TrainProfile(
        load_curve_stats={},
        peak_valley_distribution={},
        data_quality={},
        periodicity_strength={},
        period_distribution={},
        dominant_pattern="weekend_dominant",
        weekday_weekend_gap=-0.2,
        train_fit_mape=5.0,
    )
    validation = ValidationProfile(
        cv_fold_losses=[],
        cv_val_mape=6.0,
        overfit_indicator="low",
        cv_loss_trend="stable",
    )
    test = TestProfile(
        actual_vs_predicted=[],
        overall_mape=10.0,
        overall_rmse=1.0,
        max_single_point_error={},
        period_error_breakdown={"worst_period": "night"},
        peak_error_ratio=0.0,
        valley_error_ratio=0.0,
        high_error_at_extremes=False,
        day_type="weekday",
    )

    diagnosis = profiler.compute_tri_dataset_diagnosis(train, validation, test)

    assert diagnosis.pattern_consistency["status"] == "pattern_mismatch"
    assert diagnosis.overfit_detection == "confirmed_overfit"
    assert diagnosis.generalization_assessment == "poor"
    assert len(diagnosis.diagnosis_conclusion) <= 200


def test_cross_window_consistently_bad_periods():
    profiler = DatasetProfiler()
    profiles = []
    for i in range(5):
        profiles.append(
            TestProfile(
                actual_vs_predicted=[],
                overall_mape=10.0 + i,
                overall_rmse=1.0,
                max_single_point_error={},
                period_error_breakdown={
                    "morning_peak": 30.0,
                    "midday": 5.0,
                    "evening_peak": 6.0,
                    "night": 7.0,
                    "worst_period": "morning_peak",
                },
                peak_error_ratio=0.0,
                valley_error_ratio=0.0,
                high_error_at_extremes=False,
            )
        )

    pattern = profiler.compute_cross_window_pattern(profiles)

    assert pattern.consistently_bad_periods == ["morning_peak"]
    assert pattern.periodic_error_pattern["dominant_worst_period"] == "morning_peak"
