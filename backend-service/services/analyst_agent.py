from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .dataset_profiler_models import CrossWindowPattern, TestProfile, TrainProfile, TriDatasetDiagnosis


@dataclass
class ErrorAttribution:
    primary_cause: str
    contributing_factors: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalystOutput:
    error_attribution: ErrorAttribution
    pattern_report: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_attribution": self.error_attribution.to_dict(),
            "pattern_report": self.pattern_report,
        }


class AnalystAgent:
    PRIORITY = (
        "pattern_mismatch",
        "confirmed_overfit",
        "drift_signal",
        "peak_valley_concentration",
        "period_specific_error",
        "model_divergence",
        "parameter_saturation",
    )

    def analyze(
        self,
        train_profile: TrainProfile,
        test_profile: TestProfile,
        tri_dataset_diagnosis: TriDatasetDiagnosis,
        cross_window_pattern: Optional[CrossWindowPattern] = None,
        model_report: Optional[Dict[str, Any]] = None,
    ) -> AnalystOutput:
        candidates: Dict[str, List[str]] = {}

        if tri_dataset_diagnosis.pattern_consistency.get("status") == "pattern_mismatch":
            candidates["pattern_mismatch"] = ["train/test dominant pattern mismatch"]
        if tri_dataset_diagnosis.overfit_detection == "confirmed_overfit":
            candidates["confirmed_overfit"] = ["test error exceeds validation/train baseline"]
        if cross_window_pattern and float(cross_window_pattern.drift_signal or 0.0) > 0:
            candidates["drift_signal"] = [f"drift_signal={cross_window_pattern.drift_signal}"]
        if test_profile.high_error_at_extremes:
            candidates["peak_valley_concentration"] = [
                f"peak_ratio={test_profile.peak_error_ratio}",
                f"valley_ratio={test_profile.valley_error_ratio}",
            ]
        worst = test_profile.period_error_breakdown.get("worst_period")
        if worst:
            period_value = test_profile.period_error_breakdown.get(worst)
            if period_value is not None and float(period_value) > float(test_profile.overall_mape) * 1.5:
                candidates["period_specific_error"] = [f"{worst} mape={period_value}"]
        if model_report and model_report.get("model_divergence"):
            candidates["model_divergence"] = ["model predictions diverge"]

        primary = "parameter_saturation"
        for cause in self.PRIORITY:
            if cause in candidates:
                primary = cause
                break

        contributing = [cause for cause in self.PRIORITY if cause in candidates and cause != primary]
        evidence = candidates.get(primary, ["no stronger attribution rule matched"])
        return AnalystOutput(
            error_attribution=ErrorAttribution(
                primary_cause=primary,
                contributing_factors=contributing,
                evidence=evidence,
            ),
            pattern_report={
                "train_pattern": train_profile.dominant_pattern,
                "worst_period": worst,
                "diagnosis": tri_dataset_diagnosis.to_dict(),
                "cross_window_pattern": cross_window_pattern.to_dict() if cross_window_pattern else None,
            },
        )
