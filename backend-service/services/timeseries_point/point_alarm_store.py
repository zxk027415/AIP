"""Persist per-slot point alarm entity states and append-only events."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from services.timeseries_point.point_alarm_state_machine import (
    AlarmEvent,
    AlarmPolicy,
    EntityAlarmState,
    apply_point_outcome,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALARM_ROOT = _BACKEND_DIR / "data" / "timeseries_point" / "alarms"
_LOCK = threading.Lock()


def _slot_dir(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _ALARM_ROOT / safe


def _states_path(slot: str) -> Path:
    return _slot_dir(slot) / "entity_states.json"


def _events_path(slot: str) -> Path:
    return _slot_dir(slot) / "events.jsonl"


def _policy_path(slot: str) -> Path:
    return _slot_dir(slot) / "policy.json"


def _policy_from_payload(payload: dict[str, Any] | None) -> AlarmPolicy:
    raw = payload if isinstance(payload, dict) else {}
    open_n = int(raw.get("open_consecutive_points") or 3)
    close_n = int(raw.get("close_consecutive_points") or open_n)
    switch_n = int(raw.get("label_switch_consecutive_points") or open_n)
    if open_n < 1 or close_n < 1 or switch_n < 1:
        raise ValueError("consecutive point thresholds must be >= 1")
    if open_n > 48 or close_n > 48 or switch_n > 48:
        raise ValueError("consecutive point thresholds must be <= 48")
    min_conf = float(raw.get("min_confidence") or 0.0)
    return AlarmPolicy(
        open_consecutive_points=open_n,
        close_consecutive_points=close_n,
        label_switch_consecutive_points=switch_n,
        cold_start_alarm_enabled=bool(raw.get("cold_start_alarm_enabled", False)),
        min_confidence=min_conf,
    )


def load_alarm_policy(slot: str) -> AlarmPolicy:
    path = _policy_path(slot)
    if not path.is_file():
        return AlarmPolicy()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _policy_from_payload(payload if isinstance(payload, dict) else {})


def save_alarm_policy(slot: str, payload: dict[str, Any]) -> AlarmPolicy:
    policy = _policy_from_payload(payload)
    directory = _slot_dir(slot)
    directory.mkdir(parents=True, exist_ok=True)
    body = {
        "slot": slot,
        "open_consecutive_points": policy.open_consecutive_points,
        "close_consecutive_points": policy.close_consecutive_points,
        "label_switch_consecutive_points": policy.label_switch_consecutive_points,
        "cold_start_alarm_enabled": policy.cold_start_alarm_enabled,
        "min_confidence": policy.min_confidence,
    }
    tmp = _policy_path(slot).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_policy_path(slot))
    return policy


def alarm_policy_to_dict(slot: str, policy: AlarmPolicy | None = None) -> dict[str, Any]:
    current = policy or load_alarm_policy(slot)
    return {
        "slot": slot,
        "open_consecutive_points": current.open_consecutive_points,
        "close_consecutive_points": current.close_consecutive_points,
        "label_switch_consecutive_points": current.label_switch_consecutive_points,
        "cold_start_alarm_enabled": current.cold_start_alarm_enabled,
        "min_confidence": current.min_confidence,
    }


def load_entity_states(slot: str) -> dict[str, EntityAlarmState]:
    path = _states_path(slot)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    entities = payload.get("entities") if isinstance(payload, dict) else {}
    result: dict[str, EntityAlarmState] = {}
    if isinstance(entities, dict):
        for key, raw in entities.items():
            if isinstance(raw, dict):
                result[str(key)] = EntityAlarmState(**raw)
    return result


def save_entity_states(slot: str, states: dict[str, EntityAlarmState]) -> None:
    directory = _slot_dir(slot)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "slot": slot,
        "entities": {key: state.to_dict() for key, state in states.items()},
    }
    tmp = _states_path(slot).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_states_path(slot))


def append_events(slot: str, events: list[AlarmEvent]) -> None:
    if not events:
        return
    directory = _slot_dir(slot)
    directory.mkdir(parents=True, exist_ok=True)
    path = _events_path(slot)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def list_events(
    slot: str,
    *,
    limit: int = 50,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
) -> list[dict[str, Any]]:
    path = _events_path(slot)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    windowed = bool(str(day_from or "").strip() and str(day_to or "").strip())
    start = str(day_from or "")[:10]
    end = str(day_to or "")[:10]
    scan = lines if windowed else lines[-max(int(limit or 50), 1) :]
    items: list[dict[str, Any]] = []
    for line in reversed(scan):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if windowed:
            day = str(payload.get("point_time") or "")[:10]
            if not day or day < start or day > end:
                continue
        items.append(payload)
        if len(items) >= max(int(limit or 50), 1):
            break
    items.reverse()
    return items


def ingest_point_outcome(
    slot: str,
    outcome: dict[str, Any],
    *,
    policy=None,
) -> dict[str, Any]:
    """Apply one outcome to entity state; persist states + events."""
    outcome = dict(outcome)
    ek = outcome.get("entity_key")
    if isinstance(ek, (list, tuple)):
        outcome["entity_key"] = "|".join(str(part) for part in ek)
    entity_key = str(outcome.get("entity_key") or "__default__")
    effective_policy = policy or load_alarm_policy(slot)
    with _LOCK:
        states = load_entity_states(slot)
        state = states.get(entity_key) or EntityAlarmState(entity_key=entity_key)
        updated, events = apply_point_outcome(state, outcome, policy=effective_policy)
        states[entity_key] = updated
        save_entity_states(slot, states)
        append_events(slot, events)
    return {
        "entity_key": entity_key,
        "phase": updated.phase,
        "active_alarm_id": updated.active_alarm_id,
        "active_label": updated.active_label,
        "events": [event.to_dict() for event in events],
    }


def alarm_summary(
    slot: str,
    *,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    event_limit: int = 50,
) -> dict[str, Any]:
    states = load_entity_states(slot)
    start = str(day_from or "")[:10]
    end = str(day_to or "")[:10]
    windowed = bool(start and end)

    def _in_window(stamp: Any) -> bool:
        if not windowed:
            return True
        day = str(stamp or "")[:10]
        return bool(day) and start <= day <= end

    active = [
        state.to_dict()
        for state in states.values()
        if state.phase == "active" and state.active_alarm_id and _in_window(state.last_point_time)
    ]
    recent = list_events(slot, limit=event_limit, day_from=start or None, day_to=end or None)
    return {
        "slot": slot,
        "entity_count": len(states),
        "active_alarm_count": len(active),
        "active_alarms": active,
        "recent_events": recent,
        "policy": alarm_policy_to_dict(slot),
        "window_from": start or None,
        "window_to": end or None,
    }
