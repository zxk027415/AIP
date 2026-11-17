"""Project consecutive fault predictions into candidate intervals."""

from __future__ import annotations

from typing import Any


def build_candidate_intervals(
    outcomes: list[dict[str, Any]],
    *,
    entity_keys: list[str],
    fault_labels: set[int] | None = None,
    min_consecutive: int = 2,
) -> list[dict[str, Any]]:
    fault_labels = fault_labels or {1, 3, 6, 7, 8, 11, 12}
    intervals: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for outcome in sorted(outcomes, key=lambda o: str(o.get("point_time") or "")):
        if outcome.get("kind") != "prediction":
            if current:
                intervals.append(current)
                current = None
            continue
        label = outcome.get("label")
        if label not in fault_labels:
            if current:
                intervals.append(current)
                current = None
            continue
        entity = outcome.get("entity_key") or tuple(outcome.get(k) for k in entity_keys)
        if current and current.get("entity_key") == entity and current.get("label") == label:
            current["end_time"] = outcome.get("point_time")
            current["point_count"] += 1
        else:
            if current:
                intervals.append(current)
            current = {
                "entity_key": entity,
                "label": label,
                "start_time": outcome.get("point_time"),
                "end_time": outcome.get("point_time"),
                "point_count": 1,
                "kind": "annotation_candidate",
            }

    if current:
        intervals.append(current)

    return [i for i in intervals if int(i.get("point_count") or 0) >= min_consecutive]
