from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class ExperimentQuality:
    single_variable_control: float
    hypothesis_clarity: float
    expected_outcome_measurable: float
    risk_level: float
    knowledge_gain_estimate: float
    composite_score: float

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


class ExperimentQualityScorer:
    def score(self, experiment: Dict[str, Any]) -> ExperimentQuality:
        patches = experiment.get("patches") or []
        changed = {
            (p.get("target_function_id"), p.get("param_key"))
            for p in patches
            if isinstance(p, dict)
        }
        single = 1.0 if len(changed) <= 1 else max(0.0, 1.0 / len(changed))
        hypothesis = str(experiment.get("hypothesis") or experiment.get("question") or "")
        clarity = 1.0 if len(hypothesis) >= 20 and any(x in hypothesis.lower() for x in ["because", "因为", "验证"]) else 0.5 if hypothesis else 0.0
        expected = experiment.get("expected_outcome")
        measurable = 1.0 if isinstance(expected, dict) and expected.get("metric") else 0.5 if expected else 0.0
        risk = self._risk_score(experiment)
        gain = self._knowledge_gain(experiment)
        composite = self._clamp((single + clarity + measurable + risk + gain) / 5.0)
        return ExperimentQuality(
            single_variable_control=self._clamp(single),
            hypothesis_clarity=self._clamp(clarity),
            expected_outcome_measurable=self._clamp(measurable),
            risk_level=self._clamp(risk),
            knowledge_gain_estimate=self._clamp(gain),
            composite_score=round(composite, 6),
        )

    def rank_experiments(self, experiments: List[Dict[str, Any]], iteration: int = 1) -> List[Dict[str, Any]]:
        rows = []
        late = iteration >= 20
        w_metric = 0.75 if late else 0.2
        w_info = 0.25 if late else 0.8
        for experiment in experiments:
            quality = self.score(experiment)
            expected_gain = float(experiment.get("expected_metric_gain", 0.0) or 0.0)
            metric_score = self._clamp(expected_gain)
            rank_score = quality.knowledge_gain_estimate * w_info + metric_score * w_metric
            item = dict(experiment)
            item["quality"] = quality.to_dict()
            item["rank_score"] = round(rank_score, 6)
            rows.append(item)
        return sorted(rows, key=lambda x: x["rank_score"], reverse=True)

    def _risk_score(self, experiment: Dict[str, Any]) -> float:
        raw = str(experiment.get("risk") or experiment.get("risk_level") or "medium").lower()
        if raw in ("low", "低"):
            return 1.0
        if raw in ("high", "高"):
            return 0.2
        return 0.6

    def _knowledge_gain(self, experiment: Dict[str, Any]) -> float:
        if experiment.get("novel_param"):
            return 1.0
        if experiment.get("recurring_question"):
            return 0.7
        if experiment.get("hypothesis"):
            return 0.5
        return 0.2

    def _clamp(self, value: float) -> float:
        return round(max(0.0, min(1.0, float(value))), 6)


@dataclass
class InformationGainResult:
    param_key: str
    info_gain: float
    exhausted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InformationGainPruner:
    def __init__(self):
        self.space_contraction_log: List[Dict[str, Any]] = []

    def compute_info_gain(self, experiments: List[Dict[str, Any]]) -> Dict[str, float]:
        buckets: Dict[str, List[float]] = {}
        for row in experiments or []:
            param = row.get("param_key") or row.get("target_param")
            if not param:
                continue
            before = row.get("baseline_mape")
            after = row.get("mape")
            if before is None or after is None:
                continue
            gain = max(0.0, float(before) - float(after)) / max(abs(float(before)), 1e-8)
            buckets.setdefault(str(param), []).append(gain)
        return {k: round(float(np.mean(v)), 6) for k, v in buckets.items()}

    def prune(self, gain_history: Dict[str, List[float]]) -> Dict[str, InformationGainResult]:
        out: Dict[str, InformationGainResult] = {}
        for param, values in (gain_history or {}).items():
            recent = list(values)[-3:]
            gain = float(recent[-1]) if recent else 0.0
            exhausted = len(recent) >= 3 and all(float(x) < 0.01 for x in recent)
            out[param] = InformationGainResult(param, round(gain, 6), exhausted)
            if exhausted:
                self.space_contraction_log.append({"param_key": param, "reason": "low_info_gain_3_rounds"})
        return out


@dataclass
class ProactivePrediction:
    predicted_marginal_gain: float
    rounds_to_diminishing_returns: Optional[int]
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProactivePredictor:
    def predict(self, mape_history: List[float]) -> ProactivePrediction:
        values = [float(x) for x in (mape_history or [])]
        if len(values) < 2:
            return ProactivePrediction(0.0, None, None)
        gains = [max(0.0, values[i - 1] - values[i]) / max(values[i - 1], 1e-8) for i in range(1, len(values))]
        marginal = round(float(gains[-1]) * 100.0, 6)
        suggestion = None
        if len(gains) >= 3 and all(g * 100.0 < 0.05 for g in gains[-3:]):
            suggestion = "suggest_early_convergence"
        elif len(values) >= 2:
            slope = values[-2] - values[-1]
            if slope / max(values[-2], 1e-8) * 100.0 > 0.1:
                suggestion = "suggest_extension"

        rounds = None
        if gains[-1] > 0:
            rounds = int(np.ceil(gains[-1] / 0.0005))
        return ProactivePrediction(marginal, rounds, suggestion)


class ParameterInteractionGraph:
    def validate_combination(self, combination: Dict[str, Any]) -> Dict[str, Any]:
        train_days = combination.get("train_days") or combination.get("backtest_train_days")
        lags = combination.get("lags") or combination.get("create_lag_features.lags") or []
        if isinstance(lags, (int, float)):
            lags = [lags]
        if train_days is not None and lags:
            max_lag = max(float(x) for x in lags)
            if max_lag > float(train_days) * 96:
                return {"valid": False, "reason": "lags exceed train_days * 96"}
        window_sizes = combination.get("window_sizes") or combination.get("rolling_statistics.window_sizes") or []
        if isinstance(window_sizes, (int, float)):
            window_sizes = [window_sizes]
        if train_days is not None and window_sizes:
            if max(float(x) for x in window_sizes) > float(train_days) * 96:
                return {"valid": False, "reason": "window_sizes exceed train_days * 96"}
        return {"valid": True, "reason": None}

    def filter_valid_combinations(self, combinations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [c for c in combinations if self.validate_combination(c)["valid"]]


@dataclass
class CausalAttribution:
    effective_config: Dict[str, Any]
    enabling_conditions: Dict[str, Any]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CausalInferenceModule:
    def infer(self, experiment: Dict[str, Any]) -> CausalAttribution:
        baseline = float(experiment.get("baseline_mape", 0.0) or 0.0)
        current = float(experiment.get("mape", baseline) or baseline)
        improvement = max(0.0, baseline - current) / max(abs(baseline), 1e-8)
        single_variable = len(experiment.get("patches") or []) <= 1
        confidence = min(1.0, improvement * (1.0 if single_variable else 0.5) * 10.0)
        return CausalAttribution(
            effective_config=experiment.get("config") or {},
            enabling_conditions=experiment.get("condition") or {},
            confidence=round(confidence, 6),
        )

    def update_knowledge_layer(self, knowledge_layer: Any, claim: Any, experiment: Dict[str, Any]):
        attribution = self.infer(experiment)
        run_id = str(experiment.get("run_id") or "unknown")
        return knowledge_layer.update_evidence(claim, run_id, supports=attribution.confidence >= 0.3)
