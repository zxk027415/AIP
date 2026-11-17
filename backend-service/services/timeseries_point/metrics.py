"""Point-level metrics from committed outcomes."""

from __future__ import annotations

from typing import Any


def compute_point_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(outcomes)
    predictions = [o for o in outcomes if o.get("kind") == "prediction"]
    no_decisions = [o for o in outcomes if o.get("kind") == "no_decision"]
    labeled = [o for o in predictions if o.get("true_label") is not None]

    correct = sum(1 for o in labeled if o.get("label") == o.get("true_label"))
    coverage = len(predictions) / total if total else 0.0
    accuracy = correct / len(labeled) if labeled else None

    return {
        "point_count": total,
        "prediction_count": len(predictions),
        "no_decision_count": len(no_decisions),
        "coverage": round(coverage, 4),
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "no_decision_reasons": _count_reasons(no_decisions),
    }


def _count_reasons(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        reason = str(item.get("reason") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return counts
