"""Causal point alarm state machine — consumes replay point outcomes only (no TSC / grid)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import uuid4

DEFAULT_FAULT_LABELS = frozenset({1, 3, 6, 7, 8, 11, 12})
DEFAULT_NORMAL_LABELS = frozenset({0})


@dataclass
class AlarmPolicy:
    open_consecutive_points: int = 3
    close_consecutive_points: int = 3
    label_switch_consecutive_points: int = 3
    cold_start_alarm_enabled: bool = False
    min_confidence: float = 0.0
    fault_labels: frozenset[int] = DEFAULT_FAULT_LABELS
    normal_labels: frozenset[int] = DEFAULT_NORMAL_LABELS


@dataclass
class EntityAlarmState:
    entity_key: str
    phase: str = "normal"  # normal | suspected_open | active | suspected_close
    active_alarm_id: Optional[str] = None
    active_label: Optional[int] = None
    consecutive_fault: int = 0
    consecutive_normal: int = 0
    consecutive_switch: int = 0
    points_seen: int = 0
    last_point_time: Optional[str] = None
    last_outcome_kind: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AlarmEvent:
    event_id: str
    event_type: str  # alarm_open | alarm_close | alarm_label_switch | alarm_dedupe
    entity_key: str
    point_time: Optional[str]
    label: Optional[int]
    confidence: Optional[float]
    alarm_id: Optional[str]
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_fault_outcome(outcome: dict[str, Any], policy: AlarmPolicy) -> bool:
    if str(outcome.get("kind") or "") != "prediction":
        return False
    label = outcome.get("label")
    if label is None:
        return False
    try:
        label_int = int(label)
    except (TypeError, ValueError):
        return False
    if label_int not in policy.fault_labels:
        return False
    confidence = outcome.get("confidence")
    if confidence is not None and float(confidence) < policy.min_confidence:
        return False
    return True


def _is_normal_outcome(outcome: dict[str, Any], policy: AlarmPolicy) -> bool:
    if str(outcome.get("kind") or "") != "prediction":
        return False
    label = outcome.get("label")
    if label is None:
        return False
    try:
        return int(label) in policy.normal_labels
    except (TypeError, ValueError):
        return False


def apply_point_outcome(
    state: EntityAlarmState,
    outcome: dict[str, Any],
    *,
    policy: AlarmPolicy | None = None,
) -> tuple[EntityAlarmState, list[AlarmEvent]]:
    """Apply one causal point outcome; returns updated state and append-only events."""
    policy = policy or AlarmPolicy()
    events: list[AlarmEvent] = []
    entity_key = str(outcome.get("entity_key") or state.entity_key)
    point_time = outcome.get("point_time")
    if point_time is not None:
        point_time = str(point_time)

    state.entity_key = entity_key
    state.points_seen += 1
    state.last_point_time = point_time
    state.last_outcome_kind = str(outcome.get("kind") or "")

    allow_open = policy.cold_start_alarm_enabled or state.points_seen >= policy.open_consecutive_points

    if _is_fault_outcome(outcome, policy):
        label = int(outcome["label"])
        confidence = outcome.get("confidence")
        state.consecutive_normal = 0

        if state.phase == "active":
            if state.active_label == label:
                events.append(
                    AlarmEvent(
                        event_id=f"alme-{uuid4().hex[:12]}",
                        event_type="alarm_dedupe",
                        entity_key=entity_key,
                        point_time=point_time,
                        label=label,
                        confidence=float(confidence) if confidence is not None else None,
                        alarm_id=state.active_alarm_id,
                        detail={"reason": "same_label_while_active"},
                    )
                )
                state.consecutive_switch = 0
                return state, events

            state.consecutive_switch += 1
            if state.consecutive_switch >= policy.label_switch_consecutive_points:
                events.append(
                    AlarmEvent(
                        event_id=f"alme-{uuid4().hex[:12]}",
                        event_type="alarm_label_switch",
                        entity_key=entity_key,
                        point_time=point_time,
                        label=label,
                        confidence=float(confidence) if confidence is not None else None,
                        alarm_id=state.active_alarm_id,
                        detail={
                            "previous_label": state.active_label,
                            "consecutive_switch": state.consecutive_switch,
                        },
                    )
                )
                state.active_label = label
                state.consecutive_switch = 0
            return state, events

        state.consecutive_fault += 1
        state.phase = "suspected_open"
        if state.consecutive_fault >= policy.open_consecutive_points and allow_open:
            alarm_id = f"alm-{uuid4().hex[:12]}"
            state.active_alarm_id = alarm_id
            state.active_label = label
            state.phase = "active"
            state.consecutive_switch = 0
            events.append(
                AlarmEvent(
                    event_id=f"alme-{uuid4().hex[:12]}",
                    event_type="alarm_open",
                    entity_key=entity_key,
                    point_time=point_time,
                    label=label,
                    confidence=float(confidence) if confidence is not None else None,
                    alarm_id=alarm_id,
                    detail={"consecutive_fault": state.consecutive_fault},
                )
            )
        return state, events

    if _is_normal_outcome(outcome, policy):
        confidence = outcome.get("confidence")
        state.consecutive_fault = 0
        state.consecutive_switch = 0

        if state.phase in {"active", "suspected_close"}:
            state.consecutive_normal += 1
            state.phase = "suspected_close"
            if state.consecutive_normal >= policy.close_consecutive_points:
                events.append(
                    AlarmEvent(
                        event_id=f"alme-{uuid4().hex[:12]}",
                        event_type="alarm_close",
                        entity_key=entity_key,
                        point_time=point_time,
                        label=int(outcome.get("label") or 0),
                        confidence=float(confidence) if confidence is not None else None,
                        alarm_id=state.active_alarm_id,
                        detail={"consecutive_normal": state.consecutive_normal},
                    )
                )
                state.phase = "normal"
                state.active_alarm_id = None
                state.active_label = None
                state.consecutive_normal = 0
            return state, events

        state.phase = "normal"
        state.consecutive_fault = 0
        state.consecutive_normal = 0
        return state, events

    # no_decision or unknown — do not advance open/close counters
    return state, events
