from datetime import datetime
from typing import Any, Dict, List, Optional


class AutoResearchHypothesisTracker:
    def verify(
        self,
        iteration_result: Dict[str, Any],
        last_proposal: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(last_proposal, dict):
            return None
        expected_outcome = last_proposal.get("expected_outcome")
        if not isinstance(expected_outcome, dict):
            return None

        hypothesis = str(last_proposal.get("hypothesis") or "")
        metric = str(expected_outcome.get("metric") or "mape_improvement")
        direction = str(expected_outcome.get("direction") or "increase")
        threshold = expected_outcome.get("threshold")

        evaluation = iteration_result.get("evaluation") or {}
        if metric == "mape_improvement":
            actual_value = evaluation.get("mape_improvement")
        elif metric == "challenger_mape":
            actual_value = evaluation.get("challenger_mape")
        elif metric == "score_advantage":
            actual_value = evaluation.get("score_advantage")
        else:
            actual_value = evaluation.get(metric)

        try:
            actual_float = float(actual_value) if actual_value is not None else None
            threshold_float = float(threshold) if threshold is not None else None
        except (TypeError, ValueError):
            actual_float = None
            threshold_float = None

        verified = False
        if actual_float is not None and threshold_float is not None:
            if direction == "increase":
                verified = actual_float >= threshold_float
            elif direction == "decrease":
                verified = actual_float <= threshold_float
            else:
                verified = abs(actual_float) >= abs(threshold_float)

        actual_str = f"{actual_float:.4f}" if actual_float is not None else "N/A"
        conclusion = (
            f"✓ 成立：{metric}={actual_str}，达到预期阈值 {threshold_float}"
            if verified else
            f"✗ 未成立：{metric}={actual_str}，未达到预期阈值 {threshold_float}"
        )
        return {
            "hypothesis": hypothesis,
            "verified": verified,
            "expected_threshold": threshold_float,
            "actual_improvement": actual_float,
            "conclusion": conclusion,
        }

    def update_state(
        self,
        run_state: Dict[str, Any],
        iteration: int,
        verification: Optional[Dict[str, Any]],
        *,
        now: Optional[str] = None,
    ) -> None:
        if not isinstance(verification, dict):
            return

        if not isinstance(run_state.get("insights"), dict):
            run_state["insights"] = {
                "effective_directions": [],
                "ineffective_directions": [],
                "total_hypotheses_tested": 0,
                "hypotheses_verified": 0,
                "hypotheses_disproved": 0,
            }
        if not isinstance(run_state.get("disproved_hypotheses"), list):
            run_state["disproved_hypotheses"] = []

        insights = run_state["insights"]
        hypothesis = str(verification.get("hypothesis") or "")
        verified = bool(verification.get("verified"))
        actual = verification.get("actual_improvement")
        insights["total_hypotheses_tested"] = int(insights.get("total_hypotheses_tested") or 0) + 1

        if verified:
            insights["hypotheses_verified"] = int(insights.get("hypotheses_verified") or 0) + 1
            improvement_pct = f"{float(actual) * 100:.2f}%" if actual is not None else "?"
            entry = f"{hypothesis}（第{iteration}轮验证，改善{improvement_pct}）"
            effective = insights.get("effective_directions") or []
            effective.append(entry)
            insights["effective_directions"] = effective[-10:]
            return

        insights["hypotheses_disproved"] = int(insights.get("hypotheses_disproved") or 0) + 1
        entry = f"{hypothesis}（第{iteration}轮否证，实际={actual}）"
        ineffective = insights.get("ineffective_directions") or []
        ineffective.append(entry)
        insights["ineffective_directions"] = ineffective[-10:]

        disproved = run_state["disproved_hypotheses"]
        last_proposal = run_state.get("last_applied_proposal") or {}
        disproved.append({
            "hypothesis": hypothesis,
            "iteration": iteration,
            "actual_result": actual,
            "disproved_at": now or datetime.now().isoformat(),
            "patch_fingerprint": self.patch_fingerprint(last_proposal),
        })
        run_state["disproved_hypotheses"] = disproved[-20:]

    def update_chain(
        self,
        run_state: Dict[str, Any],
        proposal_id: str,
        iteration: int,
        verification: Dict[str, Any],
    ) -> bool:
        chain = run_state.get("hypothesis_chain")
        if not isinstance(chain, list):
            return False
        for item in reversed(chain):
            if isinstance(item, dict) and str(item.get("proposal_id") or "") == str(proposal_id or ""):
                item["status"] = "verified" if verification.get("verified") else "disproved"
                item["verified_iteration"] = iteration
                item["verification"] = verification
                return True
        return False

    def update_consecutive_type_count(
        self,
        run_state: Dict[str, Any],
        current_type: str,
    ) -> Dict[str, int]:
        if not isinstance(run_state.get("consecutive_type_count"), dict):
            run_state["consecutive_type_count"] = {"parameter": 0, "feature": 0, "model": 0, "data": 0}
        counts = run_state["consecutive_type_count"]
        current = str(current_type or "parameter")
        for key in list(counts.keys()):
            if key == current:
                counts[key] = int(counts.get(key) or 0) + 1
            else:
                counts[key] = 0
        if current not in counts:
            counts[current] = 1
        run_state["consecutive_type_count"] = counts
        return counts

    def patch_fingerprint(self, proposal: Dict[str, Any]) -> str:
        parts: List[str] = []
        structure_patch = proposal.get("structure_patch") or {}
        switches = structure_patch.get("node_switches") if isinstance(structure_patch, dict) else None
        if isinstance(switches, list):
            for switch in sorted(switches, key=lambda x: str(x.get("functionId", ""))):
                if isinstance(switch, dict):
                    function_id = str(switch.get("functionId") or "")
                    enabled = switch.get("enabled")
                    if function_id:
                        parts.append(f"sw:{function_id}={enabled}")

        node_param_patches = proposal.get("node_param_patches")
        if isinstance(node_param_patches, list):
            for patch in sorted(node_param_patches, key=lambda x: str(x.get("functionId", ""))):
                if isinstance(patch, dict):
                    function_id = str(patch.get("functionId") or "")
                    param_patch = patch.get("param_patch") or {}
                    if function_id and param_patch:
                        parts.append(f"np:{function_id}:{sorted(param_patch.keys())}")

        global_config_patch = proposal.get("global_config_patch")
        if isinstance(global_config_patch, dict) and global_config_patch:
            parts.append(f"gc:{sorted(global_config_patch.keys())}")
        return "|".join(parts) if parts else ""
