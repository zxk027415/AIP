from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import OperationEvent, to_plain


REQUIRED_EVENT_TYPES = [
    "baseline",
    "degradation",
    "rca",
    "strategy",
    "execution",
    "verification",
    "comparison",
    "coe_advice",
]


class OperationEventLog:
    def __init__(self, path: str | Path, loop_id: str) -> None:
        self.path = Path(path)
        self.loop_id = loop_id
        self.events: List[OperationEvent] = []

    def append_event(self, stage: str, event_type: str, payload: Dict[str, Any]) -> OperationEvent:
        event = OperationEvent(loop_id=self.loop_id, stage=stage, type=event_type, payload=payload)
        self.events.append(event)
        self.write_json()
        return event

    def read_events(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("events", [])

    def write_json(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"loop_id": self.loop_id, "events": [to_plain(event) for event in self.events]}
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def validate_complete(self) -> List[str]:
        errors: List[str] = []
        event_types = {event.type for event in self.events}
        for required in REQUIRED_EVENT_TYPES:
            if required not in event_types:
                errors.append(f"missing event type: {required}")

        timestamps = [event.ts for event in self.events]
        if timestamps != sorted(timestamps):
            errors.append("event timestamps are not monotonic")
        return errors


def read_event_log(path: str | Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)

