"""Shared contracts for real-point pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WindowResult:
    status: str  # ready | not_ready
    reason: Optional[str] = None
    window_tensor: Optional[Any] = None
    entity_key: Optional[tuple] = None
    point_time: Optional[str] = None
    context_length: int = 0


@dataclass
class PointOutcome:
    kind: str  # prediction | no_decision
    label: Optional[int] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    evidence: dict[str, Any] = field(default_factory=dict)
