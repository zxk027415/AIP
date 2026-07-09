from __future__ import annotations

from typing import Dict

from .models import ComparisonResult, ok


def build_comparison(baseline: Dict, degraded: Dict, recovered: Dict, selected_strategy: str):
    result = ComparisonResult(
        baseline_accuracy=baseline["accuracy"],
        degraded_accuracy=degraded["accuracy"],
        recovered_accuracy=recovered["accuracy"],
        delta_recovery=round(recovered["accuracy"] - degraded["accuracy"], 2),
        selected_strategy=selected_strategy,
        baseline_version=baseline["algorithm_version"],
        degraded_version=degraded["algorithm_version"],
        recovered_version=recovered["algorithm_version"],
    )
    return ok(result)

