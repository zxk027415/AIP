"""Benchmark slot governance helpers (G6 skeleton)."""

from __future__ import annotations

from typing import Any

PRODUCT_EXECUTION_PURPOSES = frozenset({"product_workflow", None, ""})
BENCHMARK_EXECUTION_PURPOSE = "benchmark_reuse"


def is_benchmark_slot(slot: str | None) -> bool:
    return str(slot or "").strip().startswith("benchmark_")


def compute_governance_eligible(*, slot: str | None, execution_purpose: str | None) -> bool:
    """Product governance writes are never eligible for benchmark slots or benchmark_reuse runs."""
    purpose = str(execution_purpose or "product_workflow").strip() or "product_workflow"
    if is_benchmark_slot(slot):
        return False
    if purpose == BENCHMARK_EXECUTION_PURPOSE:
        return False
    return True


def resolve_execution_purpose(
    *,
    slot: str | None,
    execution_purpose: str | None,
) -> dict[str, Any]:
    """
    Enforce slot ↔ execution_purpose invariant:
      benchmark_* slot iff benchmark_reuse purpose.
    """
    purpose = str(execution_purpose or "product_workflow").strip() or "product_workflow"
    slot_key = str(slot or "").strip()

    if is_benchmark_slot(slot_key):
        if purpose != BENCHMARK_EXECUTION_PURPOSE:
            raise ValueError(
                f"benchmark slot {slot_key!r} requires execution_purpose=benchmark_reuse",
            )
    elif purpose == BENCHMARK_EXECUTION_PURPOSE:
        raise ValueError(
            f"execution_purpose=benchmark_reuse is only allowed for benchmark_* slots, got slot={slot_key!r}",
        )

    return {
        "execution_purpose": purpose,
        "governance_eligible": compute_governance_eligible(slot=slot_key, execution_purpose=purpose),
    }
