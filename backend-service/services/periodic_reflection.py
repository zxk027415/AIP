from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class ReflectionDecision:
    current_strategy: str
    status: str
    reason: str
    decision: str
    next_focus: Optional[str] = None
    reset_type: Optional[str] = None
    reset_recommendation: Optional[Dict[str, Any]] = None
    meta_warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionResult:
    iteration: int
    improvement_trend: str
    effective_directions: List[str]
    ineffective_directions: List[str]
    exploration_coverage: float
    projected_final_performance: Optional[float]
    gap_to_target: Optional[float]
    estimated_rounds_to_target: Optional[int]
    reflection_decision: ReflectionDecision

    def __post_init__(self):
        if isinstance(self.reflection_decision, dict):
            self.reflection_decision = ReflectionDecision(**self.reflection_decision)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["reflection_decision"] = self.reflection_decision.to_dict()
        return data


class PeriodicReflection:
    def __init__(self, reflection_interval: int = 20, target_mape: Optional[float] = None):
        self.reflection_interval = min(50, max(5, int(reflection_interval or 20)))
        self.target_mape = target_mape

    def should_trigger(self, iteration: int) -> bool:
        return iteration > 0 and iteration % self.reflection_interval == 0

    def reflect(
        self,
        run_state: Dict[str, Any],
        iteration: int,
        target_mape: Optional[float] = None,
    ) -> ReflectionResult:
        history = run_state.get("iterations") or run_state.get("history") or []
        recent = history[-self.reflection_interval :]
        mapes = [self._metric(x) for x in recent if self._metric(x) is not None]
        trend = self._improvement_trend(mapes)
        effective, ineffective = self._directions(recent)
        health = run_state.get("exploration_health") if isinstance(run_state.get("exploration_health"), dict) else {}
        scoreboard = health.get("scoreboard") if isinstance(health.get("scoreboard"), dict) else {}
        if scoreboard:
            effective, ineffective = self._directions_from_scoreboard(scoreboard)
        coverage = self._coverage(run_state, scoreboard)
        novelty_summary = run_state.get("novelty_summary") if isinstance(run_state.get("novelty_summary"), dict) else {}
        evidence_summary = run_state.get("evidence_summary") if isinstance(run_state.get("evidence_summary"), dict) else {}
        target = target_mape if target_mape is not None else self.target_mape
        projected, gap, rounds = self._project(mapes, target)

        decision = self._decision(
            trend,
            coverage,
            projected,
            target,
            rounds,
            effective,
            ineffective,
            evidence_summary=evidence_summary,
            novelty_summary=novelty_summary,
        )
        warning = self._meta_warning(run_state)
        if warning:
            decision.meta_warning = warning

        result = ReflectionResult(
            iteration=iteration,
            improvement_trend=trend,
            effective_directions=effective,
            ineffective_directions=ineffective,
            exploration_coverage=round(coverage, 6),
            projected_final_performance=projected,
            gap_to_target=gap,
            estimated_rounds_to_target=rounds,
            reflection_decision=decision,
        )
        run_state.setdefault("periodic_reflections", []).append(result.to_dict())
        self.apply_decision(run_state, result)
        return result

    def apply_decision(self, run_state: Dict[str, Any], result: ReflectionResult) -> None:
        decision = result.reflection_decision
        if decision.decision == "shift_focus":
            run_state["current_research_focus"] = {
                "focus": decision.next_focus or "focus on effective feature directions",
                "set_by": f"periodic_reflection_iter_{result.iteration}",
                "priority_layers": ["feature"],
                "priority_params": result.effective_directions[:3],
                "avoid_layers": ["training"] if result.ineffective_directions else [],
            }
            active = set(run_state.get("active_layers") or [])
            forced = [x for x in run_state["current_research_focus"]["priority_layers"] if x not in active]
            if forced:
                run_state.setdefault("force_activate", [])
                for layer in forced:
                    if layer not in run_state["force_activate"]:
                        run_state["force_activate"].append(layer)

    def sampling_weight_for_layer(
        self,
        layer: str,
        run_state: Dict[str, Any],
    ) -> float:
        focus = run_state.get("current_research_focus") or {}
        active = set(run_state.get("active_layers") or [])
        if layer not in active:
            return 1.0
        if layer in focus.get("priority_layers", []):
            return 2.0
        if layer in focus.get("avoid_layers", []):
            return 0.5
        return 1.0

    def _metric(self, item: Dict[str, Any]) -> Optional[float]:
        for key in ("mape", "best_mape", "score"):
            if key in item and item[key] is not None:
                try:
                    return float(item[key])
                except Exception:
                    return None
        return None

    def _improvement_trend(self, mapes: List[float]) -> str:
        if len(mapes) < 3:
            return "stagnating"
        x = np.arange(len(mapes), dtype=float)
        slope = float(np.polyfit(x, np.asarray(mapes), 1)[0])
        threshold = max(float(np.mean(mapes)) * 0.002, 0.0005)
        if slope < -threshold:
            return "improving"
        if slope > threshold:
            return "degrading"
        return "stagnating"

    def _directions(self, rows: List[Dict[str, Any]]):
        effective = []
        ineffective = []
        for row in rows:
            direction = row.get("direction") or row.get("param") or row.get("hypothesis")
            if not direction:
                continue
            delta = row.get("delta_mape")
            if delta is None:
                continue
            if float(delta) < 0:
                effective.append(str(direction))
            elif float(delta) >= 0:
                ineffective.append(str(direction))
        return list(dict.fromkeys(effective)), list(dict.fromkeys(ineffective))

    def _directions_from_scoreboard(self, scoreboard: Dict[str, Any]):
        effective = []
        ineffective = []
        for direction, row in (scoreboard or {}).items():
            if not isinstance(row, dict):
                continue
            best = self._safe_float(row.get("best_score_advantage"))
            ineffective_count = int(row.get("ineffective_count") or 0)
            negative_count = int(row.get("negative_score_count") or 0)
            if best is not None and best > 0:
                effective.append(str(direction))
            if ineffective_count > 0 or negative_count > 0 or best is None or best <= 0:
                ineffective.append(str(direction))
        return effective, ineffective

    def _coverage(self, run_state: Dict[str, Any], scoreboard: Dict[str, Any]) -> float:
        if scoreboard:
            directions = [row for row in scoreboard.values() if isinstance(row, dict)]
            if directions:
                covered = sum(1 for row in directions if int(row.get("attempts") or 0) > 0)
                return float(covered / max(len(directions), 1))
        try:
            return float(run_state.get("exploration_coverage", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _project(self, mapes: List[float], target: Optional[float]):
        if not mapes:
            return None, None, None
        projected = round(float(min(mapes)), 6)
        if len(mapes) >= 3:
            x = np.arange(1, len(mapes) + 1, dtype=float)
            y = np.asarray(mapes, dtype=float)
            try:
                coeff = np.polyfit(np.log1p(x), y, 1)
                projected = round(float(coeff[0] * np.log1p(len(mapes) + 50) + coeff[1]), 6)
            except Exception:
                projected = round(float(min(mapes)), 6)
        if target is None:
            return projected, None, None
        gap = round(float(projected - target), 6)
        improvement = max(0.0, float(mapes[0] - mapes[-1])) / max(1, len(mapes) - 1)
        rounds = None if improvement <= 1e-8 else int(np.ceil(max(0.0, mapes[-1] - target) / improvement))
        return projected, gap, rounds

    def _decision(
        self,
        trend: str,
        coverage: float,
        projected: Optional[float],
        target: Optional[float],
        rounds: Optional[int],
        effective: List[str],
        ineffective: List[str],
        evidence_summary: Optional[Dict[str, Any]] = None,
        novelty_summary: Optional[Dict[str, Any]] = None,
    ) -> ReflectionDecision:
        decision = "continue_current"
        next_focus = None
        reset_type = None
        reset = None
        reason = f"trend={trend}, coverage={coverage:.2f}"
        evidence_summary = evidence_summary or {}
        novelty_summary = novelty_summary or {}
        by_strength = evidence_summary.get("by_strength") if isinstance(evidence_summary.get("by_strength"), dict) else {}
        duplicate_count = int(novelty_summary.get("duplicate_count") or 0)
        new_count = int(novelty_summary.get("new_count") or 0)
        if duplicate_count > 0:
            reason += f", duplicate_candidates={duplicate_count}"
        if int(evidence_summary.get("needs_multi_window_confirmation") or 0) > 0:
            reason += f", needs_confirmation={int(evidence_summary.get('needs_multi_window_confirmation') or 0)}"
        if target is not None and projected is not None and projected > target and rounds and rounds > 50:
            decision = "expand_registry" if coverage > 0.8 else "shift_focus"
            reset_type = "expand_registry" if decision == "expand_registry" else None
            next_focus = "shift toward effective feature directions" if decision == "shift_focus" else None
            reset = {"reset_type": reset_type, "rationale": "projected performance remains above target"}
        elif int(evidence_summary.get("needs_multi_window_confirmation") or 0) > 0:
            decision = "shift_focus"
            next_focus = "confirm single-window positives before promoting new candidates"
        elif duplicate_count > 0 and duplicate_count >= new_count:
            decision = "shift_focus"
            next_focus = "prioritize novel candidates over repeated historical configurations"
        elif int(by_strength.get("multi_window_confirmed") or 0) > 0:
            decision = "continue_current"
            next_focus = "exploit multi-window confirmed directions"
        elif trend in ("stagnating", "degrading"):
            decision = "shift_focus" if coverage <= 0.8 else "expand_registry"
            next_focus = "prioritize directions with observed improvement"
            reset_type = "expand_registry" if decision == "expand_registry" else None
        return ReflectionDecision(
            current_strategy="autoresearch iterative search",
            status=trend,
            reason=reason,
            decision=decision,
            next_focus=next_focus,
            reset_type=reset_type,
            reset_recommendation=reset,
        )

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _meta_warning(self, run_state: Dict[str, Any]) -> Optional[str]:
        rows = run_state.get("periodic_reflections", [])[-3:]
        if len(rows) < 3:
            return None
        adopted = [bool(x.get("adopted")) for x in rows]
        if not any(adopted):
            return "连续3次反思建议未被采纳，需要检查反思策略有效性"
        return None
