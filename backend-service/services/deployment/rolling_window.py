# @AI_GENERATED
"""Pure strict-Gap-1 history contracts for deployed load-forecast workflows."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

DateLike = Union[date, datetime]


@dataclass(frozen=True)
class TrainingWindow:
    """A Gap-1 training window derived from a business day T."""

    trigger_date: date
    training_start: Optional[date]
    training_end: Optional[date]
    predict_target: date
    window_days: int
    truncated: bool
    included_dates: List[date] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowHistoryRequirement:
    """History requirements inferred from one immutable workflow definition."""

    training_days: int
    feature_warmup_days: int
    points_per_day: int

    @property
    def required_history_days(self) -> int:
        """Number of complete days required before the business day T."""
        return self.training_days + self.feature_warmup_days


@dataclass(frozen=True)
class HistoryReadiness:
    """Whether all pre-T warmup and training days are complete and continuous."""

    trigger_date: date
    warmup_start: date
    training_start: date
    training_end: date
    required_history_days: int
    expected_points_per_day: int
    missing_dates: Tuple[date, ...]
    incomplete_days: Tuple[Tuple[date, int], ...]

    @property
    def ready(self) -> bool:
        return not self.missing_dates and not self.incomplete_days

    def reason(self) -> str:
        """Return a scheduler-safe, non-sensitive explanation for a skipped run."""
        if self.ready:
            return "history_ready"
        parts = [
            "history_not_ready",
            f"required_range={self.warmup_start.isoformat()}~{self.training_end.isoformat()}",
            f"required_days={self.required_history_days}",
            f"expected_points_per_day={self.expected_points_per_day}",
        ]
        if self.missing_dates:
            parts.append(
                "missing_dates=" + ",".join(day.isoformat() for day in self.missing_dates)
            )
        if self.incomplete_days:
            parts.append(
                "incomplete_days="
                + ",".join(f"{day.isoformat()}:{count}" for day, count in self.incomplete_days)
            )
        return " ".join(parts)


def _to_date(value: DateLike) -> date:
    """Normalize a date-like value without allowing a datetime to leak into sets."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(
        "available_data elements must be datetime.date or datetime.datetime; "
        f"received {type(value).__name__}"
    )


def _positive_int(value: Any, default: int) -> int:
    """Read a positive integer from workflow JSON while retaining a safe default."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _numeric_list(value: Any) -> list[float]:
    """Accept JSON lists or JSON-encoded lists used by older workflow exports."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []

    values: list[float] = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if number > 0:
            values.append(number)
    return values


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def derive_workflow_history_requirement(
    workflow: Mapping[str, Any],
    *,
    default_training_days: int = 30,
    default_points_per_day: int = 96,
) -> WorkflowHistoryRequirement:
    """Infer training and feature-lookback needs from a deployed workflow JSON.

    The result is deliberately conservative. It understands the platform's
    time-series feature operators and takes their maximum required lookback;
    unknown nodes never reduce the inferred requirement.
    """
    metadata = workflow.get("metadata") or {}
    global_config = metadata.get("global_config") or workflow.get("global_config") or {}
    training_days = _positive_int(
        global_config.get("backtest_train_days"), default_training_days
    )
    points_per_day = _positive_int(
        global_config.get("backtest_daily_horizon"), default_points_per_day
    )
    max_lookback_points = 0

    for raw_node in workflow.get("nodes") or []:
        config = ((raw_node.get("data") or {}).get("config") or {})
        function_id = config.get("functionId")
        node_points_per_day = _positive_int(
            config.get("horizon_per_day"), points_per_day
        )

        if function_id == "create_lag_features":
            lag_steps = _numeric_list(config.get("lags"))
            lag_days = _numeric_list(config.get("lag_days"))
            max_lookback_points = max(
                max_lookback_points,
                int(max(lag_steps, default=0)),
                math.ceil(max(lag_days, default=0) * node_points_per_day),
            )
        elif function_id == "rolling_statistics":
            window_sizes = _numeric_list(config.get("window_sizes"))
            base_shift = _positive_int(config.get("base_shift"), 0)
            max_lookback_points = max(
                max_lookback_points,
                base_shift + math.ceil(max(window_sizes, default=0)),
            )
        elif function_id == "sliding_window":
            max_lookback_points = max(
                max_lookback_points,
                _positive_int(config.get("window_size"), 0),
            )
        elif function_id == "extract_statistical_features":
            group_shift = _positive_int(config.get("group_shift"), 0)
            max_lookback_points = max(
                max_lookback_points,
                group_shift * node_points_per_day,
            )
        elif function_id == "diff_features":
            diff_periods = _numeric_list(config.get("diff_periods"))
            seasonal_period = _positive_int(config.get("seasonal_period"), 0)
            no_leak_mode = _to_bool(config.get("no_leak_mode"))
            if no_leak_mode:
                no_leak_points = max(
                    1 + math.ceil(max(diff_periods, default=0)),
                    1 + 2 * node_points_per_day,
                )
                max_lookback_points = max(max_lookback_points, no_leak_points)
            else:
                max_lookback_points = max(
                    max_lookback_points,
                    math.ceil(max(max(diff_periods, default=0), seasonal_period)),
                )

    return WorkflowHistoryRequirement(
        training_days=training_days,
        feature_warmup_days=math.ceil(max_lookback_points / points_per_day),
        points_per_day=points_per_day,
    )


def assess_history_readiness(
    trigger_date: DateLike,
    requirement: WorkflowHistoryRequirement,
    timestamps: Iterable[datetime],
) -> HistoryReadiness:
    """Require all warmup and training days before T to be continuous and complete.

    A complete day has exactly the configured 15-minute slots. The business day
    itself is intentionally excluded: strict Gap 1 must never use T-day truth.
    """
    trigger_d = _to_date(trigger_date)
    training_end = trigger_d - timedelta(days=1)
    training_start = trigger_d - timedelta(days=requirement.training_days)
    warmup_start = training_start - timedelta(days=requirement.feature_warmup_days)
    expected_minutes = {
        slot * (24 * 60 // requirement.points_per_day)
        for slot in range(requirement.points_per_day)
    }
    observed_slots: dict[date, set[int]] = {}

    for timestamp in timestamps:
        if not isinstance(timestamp, datetime):
            continue
        current_date = timestamp.date()
        if current_date < warmup_start or current_date > training_end:
            continue
        minute_of_day = timestamp.hour * 60 + timestamp.minute
        if timestamp.second == 0 and timestamp.microsecond == 0:
            observed_slots.setdefault(current_date, set()).add(minute_of_day)
        else:
            observed_slots.setdefault(current_date, set())

    missing_dates: list[date] = []
    incomplete_days: list[tuple[date, int]] = []
    current_date = warmup_start
    while current_date <= training_end:
        slots = observed_slots.get(current_date)
        if not slots:
            missing_dates.append(current_date)
        elif slots != expected_minutes:
            incomplete_days.append((current_date, len(slots)))
        current_date += timedelta(days=1)

    return HistoryReadiness(
        trigger_date=trigger_d,
        warmup_start=warmup_start,
        training_start=training_start,
        training_end=training_end,
        required_history_days=requirement.required_history_days,
        expected_points_per_day=requirement.points_per_day,
        missing_dates=tuple(missing_dates),
        incomplete_days=tuple(incomplete_days),
    )


def compute_training_window(
    trigger_date: DateLike,
    max_window_days: Optional[int],
    available_data: Iterable[DateLike],
) -> TrainingWindow:
    """Build a Gap-1 window; readiness is checked separately from truncation."""
    trigger_d = _to_date(trigger_date)
    predict_target = trigger_d + timedelta(days=1)

    if max_window_days is not None:
        if not isinstance(max_window_days, int) or isinstance(max_window_days, bool):
            raise TypeError(
                "max_window_days must be an int or None; "
                f"received {type(max_window_days).__name__}"
            )
        if max_window_days <= 0:
            raise ValueError(f"max_window_days must be positive; received {max_window_days}")

    gap_cutoff = trigger_d - timedelta(days=1)
    filtered = {_to_date(raw) for raw in available_data if _to_date(raw) <= gap_cutoff}
    if not filtered:
        return TrainingWindow(
            trigger_date=trigger_d,
            training_start=None,
            training_end=None,
            predict_target=predict_target,
            window_days=0,
            truncated=False,
            included_dates=[],
        )

    sorted_dates: List[date] = sorted(filtered)
    truncated = False
    if max_window_days is not None:
        window_floor = gap_cutoff - timedelta(days=max_window_days - 1)
        if sorted_dates[0] < window_floor:
            truncated = True
            sorted_dates = [value for value in sorted_dates if value >= window_floor]

    if not sorted_dates:
        return TrainingWindow(
            trigger_date=trigger_d,
            training_start=None,
            training_end=None,
            predict_target=predict_target,
            window_days=0,
            truncated=truncated,
            included_dates=[],
        )

    return TrainingWindow(
        trigger_date=trigger_d,
        training_start=sorted_dates[0],
        training_end=sorted_dates[-1],
        predict_target=predict_target,
        window_days=(sorted_dates[-1] - sorted_dates[0]).days + 1,
        truncated=truncated,
        included_dates=sorted_dates,
    )
# @AI_GENERATED: end
