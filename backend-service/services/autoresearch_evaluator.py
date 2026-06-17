from typing import Any, Dict, List, Optional


class AutoResearchEvaluator:
    def evaluate_candidate(
        self,
        compare_state: Dict[str, Any],
        policy: Dict[str, Any],
    ) -> Dict[str, Any]:
        window_results = compare_state.get("window_results") or []
        summary = compare_state.get("summary") or {}
        baseline_mape = self.mean_metric_from_windows(window_results, "baseline", ["avg_mape", "avg_smape"])
        challenger_mape = self.mean_metric_from_windows(window_results, "challenger", ["avg_mape", "avg_smape"])
        challenger_rmse = self.mean_metric_from_windows(window_results, "challenger", ["avg_rmse", "rmse"])
        challenger_bias = self.mean_metric_from_windows(window_results, "challenger", ["avg_bias", "bias", "avg_me", "me"])
        challenger_p95_ape = self.mean_metric_from_windows(window_results, "challenger", ["avg_p95_ape", "p95_ape"])

        training_duration_s: Optional[float] = None
        dur_vals: List[float] = []
        for w in window_results:
            if not isinstance(w, dict):
                continue
            ch = w.get("challenger")
            if not isinstance(ch, dict):
                continue
            d = ch.get("total_duration")
            if d is not None:
                try:
                    dur_vals.append(float(d))
                except (TypeError, ValueError):
                    pass
        if dur_vals:
            training_duration_s = round(sum(dur_vals), 3)

        mape_improvement: Optional[float] = None
        if baseline_mape is not None and challenger_mape is not None:
            mape_improvement = baseline_mape - challenger_mape

        min_mape_improvement = float(policy.get("min_mape_improvement", 0.0))
        max_abs_bias = policy.get("max_abs_bias")
        max_p95_ape = policy.get("max_p95_ape")

        meets_mape = mape_improvement is not None and mape_improvement >= min_mape_improvement
        meets_bias = True
        meets_p95 = True

        if max_abs_bias is not None and challenger_bias is not None:
            meets_bias = abs(challenger_bias) <= float(max_abs_bias)
        if max_p95_ape is not None and challenger_p95_ape is not None:
            meets_p95 = challenger_p95_ape <= float(max_p95_ape)

        meets_constraints = bool(meets_mape and meets_bias and meets_p95)
        adv = summary.get("score_advantage")
        try:
            adv_val = float(adv) if adv is not None else None
        except (TypeError, ValueError):
            adv_val = None

        return {
            "meets_constraints": meets_constraints,
            "baseline_mape": baseline_mape,
            "challenger_mape": challenger_mape,
            "mape_improvement": mape_improvement,
            "challenger_rmse": challenger_rmse,
            "challenger_bias": challenger_bias,
            "challenger_p95_ape": challenger_p95_ape,
            "training_duration_s": training_duration_s,
            "score_advantage": adv_val,
            "policy": {
                "min_mape_improvement": min_mape_improvement,
                "max_abs_bias": max_abs_bias,
                "max_p95_ape": max_p95_ape,
            },
        }

    def rank_key(self, item: Dict[str, Any]) -> tuple:
        eval_info = item.get("evaluation") or {}
        meets = bool(eval_info.get("meets_constraints"))
        mape = eval_info.get("challenger_mape")
        mape_impr = eval_info.get("mape_improvement")
        rmse = eval_info.get("challenger_rmse")
        adv = eval_info.get("score_advantage")
        try:
            mape_val = float(mape) if mape is not None else 1e18
        except (TypeError, ValueError):
            mape_val = 1e18
        try:
            mape_impr_val = float(mape_impr) if mape_impr is not None else 0.0
        except (TypeError, ValueError):
            mape_impr_val = 0.0
        try:
            rmse_val = float(rmse) if rmse is not None else 1e18
        except (TypeError, ValueError):
            rmse_val = 1e18
        try:
            adv_val = float(adv) if adv is not None else -1e18
        except (TypeError, ValueError):
            adv_val = -1e18

        variance_penalty = 0.0
        summary = item.get("summary") or {}
        window_results = summary.get("window_results") or []
        if isinstance(window_results, list) and len(window_results) >= 2:
            scores = []
            for wr in window_results:
                if not isinstance(wr, dict):
                    continue
                cs = wr.get("challenger_score")
                if cs is not None:
                    try:
                        scores.append(float(cs))
                    except (TypeError, ValueError):
                        pass
            if len(scores) >= 2:
                mean_s = sum(scores) / len(scores)
                variance = sum((s - mean_s) ** 2 for s in scores) / len(scores)
                variance_penalty = variance * 0.5

        baseline_mape = eval_info.get("baseline_mape")
        relative_improvement = 0.0
        if baseline_mape is not None and mape_impr_val != 0:
            try:
                bm = float(baseline_mape)
                if bm > 0:
                    relative_improvement = mape_impr_val / bm
            except (TypeError, ValueError):
                pass

        return (0 if meets else 1, mape_val + variance_penalty, rmse_val, -adv_val, -relative_improvement)

    def compute_pareto_frontier(self, candidates: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
        def _get_objectives(c: Dict[str, Any]) -> Optional[tuple]:
            ev = c.get("evaluation") or {}
            mape = ev.get("challenger_mape")
            rmse = ev.get("challenger_rmse")
            if mape is None:
                return None
            try:
                m = float(mape)
                r = float(rmse) if rmse is not None else float("inf")
                d = ev.get("training_duration_s")
                dur = float(d) if d is not None else float("inf")
                return (m, r, dur)
            except (TypeError, ValueError):
                return None

        eligible = [
            c for c in candidates
            if isinstance(c, dict)
            and str(c.get("status")) == "success"
            and bool((c.get("evaluation") or {}).get("meets_constraints"))
            and _get_objectives(c) is not None
        ]

        if not eligible:
            fallback = sorted(
                [c for c in candidates if isinstance(c, dict) and str(c.get("status")) == "success"],
                key=self.rank_key,
            )
            return fallback[:top_k]

        n = len(eligible)
        dominated = [False] * n
        for i in range(n):
            if dominated[i]:
                continue
            obj_i = _get_objectives(eligible[i])
            for j in range(n):
                if i == j or dominated[j]:
                    continue
                obj_j = _get_objectives(eligible[j])
                if all(oi <= oj for oi, oj in zip(obj_i, obj_j)) and any(oi < oj for oi, oj in zip(obj_i, obj_j)):  # type: ignore[arg-type]
                    dominated[j] = True

        frontier = [c for c, d in zip(eligible, dominated) if not d]
        frontier.sort(key=lambda c: float((c.get("evaluation") or {}).get("challenger_mape") or 1e18))
        return frontier[:top_k]

    def mean_metric_from_windows(
        self,
        window_results: List[Dict[str, Any]],
        side: str,
        metric_keys: List[str],
    ) -> Optional[float]:
        vals: List[float] = []
        for item in window_results or []:
            target = item.get(side) if isinstance(item, dict) else None
            avg = (target or {}).get("avg_metrics") if isinstance(target, dict) else None
            if not isinstance(avg, dict):
                continue
            value: Optional[float] = None
            for k in metric_keys:
                raw = avg.get(k)
                if raw is None:
                    continue
                try:
                    value = float(raw)
                    break
                except (TypeError, ValueError):
                    continue
            if value is not None:
                vals.append(value)
        if not vals:
            return None
        return float(sum(vals) / len(vals))

