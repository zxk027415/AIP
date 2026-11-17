from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional


def _from_dict(cls, data: Dict[str, Any]):
    return cls(**(data or {}))


def to_json_dict(obj: Any) -> Dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    return dict(obj or {})


@dataclass
class CVFoldMetric:
    fold_id: int
    train_loss: float
    val_loss: float
    val_mape: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CVFoldMetric":
        return _from_dict(cls, data)


@dataclass
class TrainProfile:
    load_curve_stats: Dict[str, Optional[float]]
    peak_valley_distribution: Dict[str, Optional[float]]
    data_quality: Dict[str, Optional[float]]
    periodicity_strength: Dict[str, Optional[float]]
    period_distribution: Dict[str, Dict[str, Optional[float]]]
    dominant_pattern: str
    weekday_weekend_gap: Optional[float]
    train_fit_mape: Optional[float] = None
    profile_quality: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainProfile":
        return _from_dict(cls, data)


@dataclass
class ValidationProfile:
    cv_fold_losses: List[Dict[str, float]]
    cv_val_mape: Optional[float]
    overfit_indicator: str
    cv_loss_trend: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationProfile":
        return _from_dict(cls, data)


@dataclass
class TestProfile:
    actual_vs_predicted: List[Dict[str, Any]]
    overall_mape: float
    overall_rmse: float
    max_single_point_error: Dict[str, Any]
    period_error_breakdown: Dict[str, Any]
    peak_error_ratio: float
    valley_error_ratio: float
    high_error_at_extremes: bool
    day_type: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestProfile":
        return _from_dict(cls, data)


@dataclass
class TriDatasetDiagnosis:
    pattern_consistency: Dict[str, Any]
    overfit_detection: str
    generalization_assessment: str
    diagnosis_conclusion: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TriDatasetDiagnosis":
        return _from_dict(cls, data)


@dataclass
class CrossWindowPattern:
    error_trend: str
    periodic_error_pattern: Dict[str, Any]
    drift_signal: float
    consistently_bad_periods: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossWindowPattern":
        return _from_dict(cls, data)
