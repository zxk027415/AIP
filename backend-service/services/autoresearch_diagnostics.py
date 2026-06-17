from typing import Any, Dict, List, Optional


class AutoResearchDiagnostics:
    def compute_iteration_error_profile(self, window_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        mape_values: List[float] = []
        bias_values: List[float] = []
        total_days = 0
        success_days_total = 0
        high_error_count = 0

        for window in (window_results or []):
            if not isinstance(window, dict):
                continue
            challenger = window.get("challenger")
            if not isinstance(challenger, dict):
                continue

            avg_metrics = challenger.get("avg_metrics") or {}
            if isinstance(avg_metrics, dict):
                for key in ("avg_mape", "avg_smape"):
                    value = avg_metrics.get(key)
                    if value is not None:
                        try:
                            mape_values.append(float(value))
                        except (TypeError, ValueError):
                            pass
                        break
                for key in ("avg_bias", "bias", "avg_me", "me"):
                    value = avg_metrics.get(key)
                    if value is not None:
                        try:
                            bias_values.append(float(value))
                        except (TypeError, ValueError):
                            pass
                        break

            for key in ("success_days", "failed_days", "skipped_days"):
                try:
                    total_days += int(challenger.get(key) or 0)
                except (TypeError, ValueError):
                    pass
            try:
                success_days_total += int(challenger.get("success_days") or 0)
            except (TypeError, ValueError):
                pass

            challenger_score = window.get("challenger_score")
            baseline_score = window.get("baseline_score")
            if challenger_score is not None and baseline_score is not None:
                try:
                    if float(challenger_score) < float(baseline_score):
                        high_error_count += 1
                except (TypeError, ValueError):
                    pass

        avg_mape = (sum(mape_values) / len(mape_values)) if mape_values else None
        max_daily_mape = max(mape_values) if mape_values else None
        avg_bias = (sum(bias_values) / len(bias_values)) if bias_values else None
        if avg_bias is None:
            bias_direction = None
        elif avg_bias > 0.01:
            bias_direction = "positive"
        elif avg_bias < -0.01:
            bias_direction = "negative"
        else:
            bias_direction = "neutral"

        return {
            "error_profile": {
                "avg_mape": avg_mape,
                "max_daily_mape": max_daily_mape,
                "bias_direction": bias_direction,
                "high_error_days_count": high_error_count,
                "weekend_vs_weekday_gap": None,
            },
            "data_coverage": {
                "total_days": total_days,
                "success_days": success_days_total,
                "skip_reasons": [],
            },
        }

    def compute_error_diagnosis(
        self,
        report: Dict[str, Any],
        *,
        comparison_store: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        iterations = report.get("iterations") or []
        last_success = None
        for item in reversed(iterations):
            if isinstance(item, dict) and str(item.get("status")) == "success":
                last_success = item
                break

        if last_success is None:
            return {
                "primary_error_source": "parameter_saturation",
                "evidence": {},
                "confidence": "low",
                "data_sufficiency": "insufficient",
            }

        error_profile = last_success.get("error_profile") or {}
        data_coverage = last_success.get("data_coverage") or {}
        avg_mape = error_profile.get("avg_mape")
        max_daily_mape = error_profile.get("max_daily_mape")
        weekend_gap = error_profile.get("weekend_vs_weekday_gap")
        total_days = int(data_coverage.get("total_days") or 0)
        success_days = int(data_coverage.get("success_days") or 0)

        if total_days >= 14 and success_days >= 10:
            data_sufficiency = "sufficient"
            confidence = "high"
        elif total_days >= 7:
            data_sufficiency = "partial"
            confidence = "medium"
        else:
            data_sufficiency = "insufficient"
            confidence = "low"

        evidence: Dict[str, Any] = {
            "avg_mape": avg_mape,
            "max_daily_mape": max_daily_mape,
            "weekend_vs_weekday_gap": weekend_gap,
            "total_days": total_days,
            "success_days": success_days,
        }

        cmp_id = str(last_success.get("comparison_id") or "")
        per_model_smape: Dict[str, float] = {}
        if cmp_id and comparison_store and cmp_id in comparison_store:
            per_model_metrics = (comparison_store.get(cmp_id) or {}).get("per_model_metrics") or {}
            for model_key, metrics in per_model_metrics.items():
                if isinstance(metrics, dict) and metrics.get("avg_smape") is not None:
                    try:
                        per_model_smape[model_key] = float(metrics["avg_smape"])
                    except (TypeError, ValueError):
                        pass
        if len(per_model_smape) >= 2:
            values = list(per_model_smape.values())
            divergence = max(values) - min(values)
            evidence["model_divergence"] = round(divergence, 4)
            evidence["per_model_smape"] = per_model_smape
            if divergence > 3.0:
                return self._diagnosis("model_divergence", evidence, confidence, data_sufficiency)

        if weekend_gap is not None:
            try:
                if float(weekend_gap) > 0.05:
                    return self._diagnosis("weekend_pattern_shift", evidence, confidence, data_sufficiency)
            except (TypeError, ValueError):
                pass

        if total_days > 0 and (success_days / total_days) < 0.7:
            return self._diagnosis("data_coverage_insufficient", evidence, confidence, data_sufficiency)

        if avg_mape is not None and max_daily_mape is not None:
            try:
                if float(avg_mape) > 0 and float(max_daily_mape) > float(avg_mape) * 2:
                    return self._diagnosis("outlier_days", evidence, confidence, data_sufficiency)
            except (TypeError, ValueError):
                pass

        return self._diagnosis("parameter_saturation", evidence, confidence, data_sufficiency)

    def _diagnosis(
        self,
        primary: str,
        evidence: Dict[str, Any],
        confidence: str,
        data_sufficiency: str,
    ) -> Dict[str, Any]:
        return {
            "primary_error_source": primary,
            "evidence": evidence,
            "confidence": confidence,
            "data_sufficiency": data_sufficiency,
        }
