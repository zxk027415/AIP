from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class ErrorCode(str, Enum):
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    METRIC_ERROR = "METRIC_ERROR"
    RCA_UNDETERMINED = "RCA_UNDETERMINED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    REPORT_FAILED = "REPORT_FAILED"


def to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain(item) for key, item in value.items()}
    return value


def ok(data: Any) -> Dict[str, Any]:
    return {"status": "ok", "data": to_plain(data), "error": None}


def err(code: ErrorCode, message: str) -> Dict[str, Any]:
    return {"status": "error", "data": None, "error": {"code": code.value, "message": message}}


@dataclass
class OperationEvent:
    loop_id: str
    stage: str
    type: str
    payload: Dict[str, Any]
    ts: str = field(default_factory=now_iso)


@dataclass
class DatasetStatus:
    dataset_id: str
    time_range: List[str]
    feature_status: Dict[str, str]
    records: List[Dict[str, Any]]


@dataclass
class PredictionResult:
    prediction_id: str
    algorithm_version: str
    scenario: str
    y_true: List[float]
    y_pred: List[float]


@dataclass
class DegradationEvent:
    event_id: str
    algorithm_id: str
    accuracy: float
    threshold: float
    missing_features: List[str]
    baseline_accuracy: float
    degraded_accuracy: float
    timestamp: str = field(default_factory=now_iso)


@dataclass
class RCAResult:
    root_cause: str
    confidence: float
    supporting_evidence: List[str]
    checked_items: List[str]
    undetermined: bool = False


@dataclass
class StrategyEvaluation:
    strategy_id: str
    name: str
    expected_accuracy: float
    cost: str
    risk: str
    rationale: str
    selected: bool = False


@dataclass
class ExecutionResult:
    execution_id: str
    selected_strategy: str
    recovered_dataset_id: str
    new_algorithm_version: str
    steps: List[str]
    status: str


@dataclass
class ComparisonResult:
    baseline_accuracy: float
    degraded_accuracy: float
    recovered_accuracy: float
    delta_recovery: float
    selected_strategy: str
    baseline_version: str
    degraded_version: str
    recovered_version: str


@dataclass
class CoEAdvice:
    advice_id: str
    summary: str
    rationale: str
    risks: str
    prevention: str

