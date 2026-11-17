# @AI_GENERATED: strict Gap-1 load-forecast history contract tests
from datetime import date, datetime, time, timedelta

import pandas as pd

from services.deployment.rolling_window import (
    WorkflowHistoryRequirement,
    assess_history_readiness,
    derive_workflow_history_requirement,
)
from services.scheduler.tasks.load_forecast_tasks import _append_causal_forecast_rows


def _quarter_hour_timestamps(start: date, days: int) -> list[datetime]:
    return [
        datetime.combine(start + timedelta(days=day_offset), time.min)
        + timedelta(minutes=15 * slot)
        for day_offset in range(days)
        for slot in range(96)
    ]


def test_production_workflow_contract_derives_28_day_warmup_and_30_day_training():
    workflow = {
        "metadata": {
            "global_config": {
                "backtest_train_days": 30,
                "backtest_daily_horizon": 96,
                "backtest_gap_days": 1,
            }
        },
        "nodes": [
            {
                "data": {
                    "config": {
                        "functionId": "create_lag_features",
                        "lag_days": [1, 7, 14, 21, 28],
                        "horizon_per_day": 96,
                    }
                }
            },
            {
                "data": {
                    "config": {
                        "functionId": "rolling_statistics",
                        "base_shift": 96,
                        "window_sizes": [4, 96],
                    }
                }
            },
            {
                "data": {
                    "config": {
                        "functionId": "diff_features",
                        "no_leak_mode": True,
                        "horizon_per_day": 96,
                        "diff_periods": [1],
                    }
                }
            },
        ],
    }

    requirement = derive_workflow_history_requirement(workflow)

    assert requirement.training_days == 30
    assert requirement.points_per_day == 96
    assert requirement.feature_warmup_days == 28
    assert requirement.required_history_days == 58


def test_history_readiness_requires_all_58_pre_t_days_to_be_complete():
    requirement = WorkflowHistoryRequirement(
        training_days=30,
        feature_warmup_days=28,
        points_per_day=96,
    )
    business_date = date(2025, 8, 29)
    timestamps = _quarter_hour_timestamps(date(2025, 7, 2), 58)

    readiness = assess_history_readiness(business_date, requirement, timestamps)

    assert readiness.ready is True
    assert readiness.warmup_start == date(2025, 7, 2)
    assert readiness.training_start == date(2025, 7, 30)
    assert readiness.training_end == date(2025, 8, 28)
    assert readiness.missing_dates == ()
    assert readiness.incomplete_days == ()


def test_history_readiness_rejects_one_missing_quarter_hour_point():
    requirement = WorkflowHistoryRequirement(
        training_days=30,
        feature_warmup_days=28,
        points_per_day=96,
    )
    missing_point = datetime(2025, 7, 16, 12, 0)
    timestamps = [
        timestamp
        for timestamp in _quarter_hour_timestamps(date(2025, 7, 2), 58)
        if timestamp != missing_point
    ]

    readiness = assess_history_readiness(date(2025, 8, 29), requirement, timestamps)

    assert readiness.ready is False
    assert readiness.missing_dates == ()
    assert readiness.incomplete_days == ((date(2025, 7, 16), 95),)
    assert "history_not_ready" in readiness.reason()
    assert "2025-07-16:95" in readiness.reason()


def test_future_forecast_rows_are_marked_without_creating_future_truth():
    historical = pd.DataFrame(
        {
            "record_time": pd.to_datetime(["2025-07-30 23:30", "2025-07-30 23:45"]),
            "value": [100.0, 101.0],
        }
    )

    output = _append_causal_forecast_rows(
        historical,
        forecast_start=datetime(2025, 8, 1, 0, 0),
        interval=timedelta(minutes=15),
        steps=2,
    )

    assert output["__aip_online_forecast_row"].tolist() == [False, False, True, True]
    assert output["record_time"].iloc[-2:].tolist() == [
        pd.Timestamp("2025-08-01 00:00:00"),
        pd.Timestamp("2025-08-01 00:15:00"),
    ]
    assert output["value"].iloc[-2:].tolist() == [101.0, 101.0]
# @AI_GENERATED: end
