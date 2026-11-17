from datetime import datetime
from typing import Any, Dict, List, Optional


class AutoResearchInsightBuilder:
    def build(
        self,
        run_id: str,
        state: Dict[str, Any],
        *,
        scenario_fingerprint: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        iterations = state.get("iterations") or []
        insights = state.get("insights") or {}
        disproved = state.get("disproved_hypotheses") or []
        best = state.get("best_candidate") or {}
        best_eval = (best.get("evaluation") or {}) if isinstance(best, dict) else {}
        fingerprint = scenario_fingerprint or {}
        fingerprint_inputs = {
            "baseline_workflow_id": state.get("baseline_workflow_id"),
            "registry_id": state.get("registry_id"),
            "evaluation_contract": state.get("evaluation_contract") or {},
            "scenario_tags": state.get("scenario_tags") or [],
            "windows": state.get("windows") or [],
        }
        latest_dataset_profile = state.get("dataset_profile") if isinstance(state.get("dataset_profile"), dict) else {}
        train_profile = latest_dataset_profile.get("train_profile") if isinstance(latest_dataset_profile.get("train_profile"), dict) else {}
        profile_quality = train_profile.get("profile_quality") if isinstance(train_profile.get("profile_quality"), dict) else {}

        data_profile = {
            "granularity_minutes": 15 if fingerprint.get("granularity") == "daily" else None,
            "span_days": fingerprint.get("span_days"),
            "weekend_weekday_gap": train_profile.get("weekday_weekend_gap") if train_profile else self._mean_weekend_gap(iterations),
            "outlier_ratio": ((train_profile.get("data_quality") or {}).get("outlier_ratio") if train_profile else fingerprint.get("anomaly_ratio")),
            "profile_quality": profile_quality,
            "periodicity_strength": train_profile.get("periodicity_strength") if train_profile else {},
        }

        success_iters = [
            item for item in iterations
            if isinstance(item, dict) and str(item.get("status")) == "success"
        ]
        completed_iters = [
            item for item in iterations
            if isinstance(item, dict) and str(item.get("status")) in ("success", "failed", "cancelled")
        ]
        failed_iters = [
            item for item in iterations
            if isinstance(item, dict) and str(item.get("status")) in ("failed", "error")
        ]
        cancelled_iters = [
            item for item in iterations
            if isinstance(item, dict) and str(item.get("status")) == "cancelled"
        ]
        improved_iters = []
        for item in success_iters:
            evaluation = item.get("evaluation") or {}
            try:
                if float(evaluation.get("mape_improvement")) > 0:
                    improved_iters.append(item)
            except (TypeError, ValueError):
                pass

        exploration_summary = {
            "phases": self._phases_seen(iterations),
            "hypotheses_tested": int(insights.get("total_hypotheses_tested") or 0),
            "hypotheses_verified": int(insights.get("hypotheses_verified") or 0),
            "hypotheses_disproved": int(insights.get("hypotheses_disproved") or 0),
            "total_iterations": len(iterations),
            "completed_iterations": len(completed_iters),
            "success_iterations": len(success_iters),
            "improved_iterations": len(improved_iters),
            "failed_iterations": len(failed_iters),
            "cancelled_iterations": len(cancelled_iters),
            "success_iterations_legacy_note": "success_iterations counts completed successful executions; use improved_iterations for positive MAPE gains",
        }
        error_diagnostics = [
            {
                "iteration": item.get("iteration"),
                "status": item.get("status"),
                "error": item.get("error"),
                "sampled_layers": item.get("sampled_layers") or [],
            }
            for item in iterations
            if isinstance(item, dict) and str(item.get("status")) not in ("success", "")
        ]

        learned_rules: List[str] = list(insights.get("effective_directions") or [])
        ineffective_attempts: List[str] = [
            f"{item.get('hypothesis', '')}（第{item.get('iteration', '?')}轮，实际={item.get('actual_result', '?')}）"
            for item in disproved
            if isinstance(item, dict) and item.get("hypothesis")
        ]

        best_override = (best.get("override") or {}) if isinstance(best, dict) else {}
        best_global_patch = (best.get("global_config_patch") or {}) if isinstance(best, dict) else {}
        recommended_config: Dict[str, Any] = {}
        for key in ("train_days", "auto_tune_n_trials", "ensemble_mode", "daily_horizon"):
            if key in best_override:
                recommended_config[key] = best_override[key]
        for key in ("ensemble_mode", "backtest_mode"):
            if key in best_global_patch:
                recommended_config[key] = best_global_patch[key]

        return {
            "run_id": run_id,
            "created_at": created_at or datetime.now().isoformat(),
            "baseline_workflow_id": state.get("baseline_workflow_id"),
            "registry_id": state.get("registry_id"),
            "scenario_fingerprint": fingerprint,
            "scenario_fingerprint_inputs": fingerprint_inputs,
            "scenario_condition_hash_fields": list(fingerprint.keys()) if isinstance(fingerprint, dict) else [],
            "total_iterations": len(iterations),
            "best_mape_improvement": best_eval.get("mape_improvement"),
            "best_candidate_config": {
                "override": best_override,
                "global_config_patch": best_global_patch,
            },
            "data_profile": data_profile,
            "exploration_summary": exploration_summary,
            "error_diagnostics": error_diagnostics[-20:],
            "learned_rules": learned_rules,
            "ineffective_attempts": ineffective_attempts,
            "open_questions": [],
            "recommended_starting_config_for_similar": recommended_config,
        }

    def _mean_weekend_gap(self, iterations: List[Dict[str, Any]]) -> Optional[float]:
        gaps: List[float] = []
        for item in iterations:
            if not isinstance(item, dict):
                continue
            error_profile = item.get("error_profile") or {}
            gap = error_profile.get("weekend_vs_weekday_gap")
            if gap is not None:
                try:
                    gaps.append(float(gap))
                except (TypeError, ValueError):
                    pass
        if not gaps:
            return None
        return round(sum(gaps) / len(gaps), 4)

    def _phases_seen(self, iterations: List[Dict[str, Any]]) -> List[str]:
        phases: List[str] = []
        for item in iterations:
            if not isinstance(item, dict):
                continue
            sampled_layers = item.get("sampled_layers") or []
            if "feature" in sampled_layers and "feature_exploration" not in phases:
                phases.append("feature_exploration")
            if "model" in sampled_layers and "model_exploration" not in phases:
                phases.append("model_exploration")
        return phases or ["parameter_exploration"]
