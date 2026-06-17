from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set


class AutoResearchProposalManager:
    def risk_rank(self, risk_level: str) -> int:
        value = str(risk_level or "low").lower()
        if value == "high":
            return 2
        if value == "medium":
            return 1
        return 0

    def score_candidate(self, candidate: Dict[str, Any]) -> float:
        validation = candidate.get("validation") or {}
        if not bool(validation.get("valid")):
            return -1e9

        risk = self.risk_rank(str(candidate.get("risk_level") or "low"))
        search_patch = candidate.get("search_space_patch") or {}
        eval_patch = candidate.get("evaluation_contract_patch") or {}
        structure_patch = candidate.get("structure_patch") or {}
        global_patch = candidate.get("global_config_patch") or {}
        node_param_patches = candidate.get("node_param_patches") if isinstance(candidate.get("node_param_patches"), list) else []
        switches = structure_patch.get("node_switches") if isinstance(structure_patch, dict) else None
        patch_size = (
            len(search_patch.keys())
            + len(eval_patch.keys())
            + (len(switches) if isinstance(switches, list) else 0)
            + len(global_patch.keys())
            + len(node_param_patches)
        )

        score = 100.0
        score -= risk * 10.0
        score -= patch_size * 1.0
        score += float(len(global_patch.keys())) * 2.5
        score += float(len(node_param_patches)) * 3.0
        if "auto_tune_n_trials" in search_patch:
            score += 1.5
        if "train_days" in search_patch or "backtest_train_days" in search_patch:
            score += 1.0
        if isinstance(switches, list) and len(switches) > 0:
            score -= 5.0
        if isinstance(search_patch, dict) and isinstance(search_patch.get("feature_recipe_id"), list) and len(search_patch.get("feature_recipe_id")) > 0:
            score -= 3.0

        hypothesis = str(candidate.get("hypothesis") or "")
        expected_outcome = candidate.get("expected_outcome") or {}
        hypothesis_type = str(candidate.get("hypothesis_type") or "")
        if hypothesis:
            score += 5.0
            if hypothesis_type in ("feature", "model") and (
                (isinstance(switches, list) and len(switches) > 0) or len(node_param_patches) > 0
            ):
                score += 3.0
            if isinstance(expected_outcome, dict) and expected_outcome.get("threshold"):
                try:
                    if float(expected_outcome["threshold"]) > 0:
                        score += 2.0
                except (TypeError, ValueError):
                    pass

        llm_used = bool(candidate.get("llm_used"))
        has_any_real_patch = (
            len(global_patch.keys()) > 0
            or (isinstance(node_param_patches, list) and len(node_param_patches) > 0)
            or (isinstance(switches, list) and len(switches) > 0)
            or len(search_patch.keys()) > 0
            or len(eval_patch.keys()) > 0
        )
        if llm_used and has_any_real_patch:
            score += 15.0
        elif llm_used and not has_any_real_patch:
            score -= 20.0
        if isinstance(node_param_patches, list) and len(node_param_patches) > 0:
            score += 8.0
        if isinstance(switches, list) and len(switches) > 0:
            score += 6.0
        if candidate.get("primary_variable"):
            score += 5.0

        threshold = expected_outcome.get("threshold") if isinstance(expected_outcome, dict) else None
        confidence = str(candidate.get("_diagnosis_confidence") or "medium").lower()
        confidence_weight = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(confidence, 0.7)
        if threshold is not None:
            try:
                priority = float(threshold) * confidence_weight
                score += priority * (10.0 if llm_used else 3.0)
            except (TypeError, ValueError):
                pass

        consecutive_counts = candidate.get("_consecutive_type_count") or {}
        if isinstance(consecutive_counts, dict):
            htype = str(candidate.get("hypothesis_type") or "parameter")
            try:
                if int(consecutive_counts.get(htype) or 0) >= 3:
                    score -= 30.0
            except (TypeError, ValueError):
                pass

        quality = candidate.get("experiment_quality")
        if isinstance(quality, dict):
            try:
                score += (float(quality.get("composite_score")) - 0.5) * 20.0
            except (TypeError, ValueError):
                pass
            try:
                if float(quality.get("single_variable_control")) < 0.5:
                    score -= 6.0
            except (TypeError, ValueError):
                pass

        return score

    def score_experiment_quality(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        from services.experiment_quality import ExperimentQualityScorer

        patches: List[Dict[str, Any]] = []
        for key in (proposal.get("search_space_patch") or {}).keys():
            patches.append({"target_function_id": "search_space", "param_key": str(key)})
        for key in (proposal.get("evaluation_contract_patch") or {}).keys():
            patches.append({"target_function_id": "evaluation_contract", "param_key": str(key)})
        for key in (proposal.get("global_config_patch") or {}).keys():
            patches.append({"target_function_id": "global_config", "param_key": str(key)})
        for item in proposal.get("node_param_patches") if isinstance(proposal.get("node_param_patches"), list) else []:
            if isinstance(item, dict):
                for key in (item.get("param_patch") or {}).keys():
                    patches.append({
                        "target_function_id": str(item.get("functionId") or item.get("node_id") or "node"),
                        "param_key": str(key),
                    })
        for item in ((proposal.get("structure_patch") or {}).get("node_switches") or []):
            if isinstance(item, dict):
                patches.append({
                    "target_function_id": str(item.get("functionId") or item.get("node_id") or "structure"),
                    "param_key": "enabled",
                })

        return ExperimentQualityScorer().score({
            "patches": patches,
            "hypothesis": proposal.get("hypothesis") or "",
            "expected_outcome": proposal.get("expected_outcome") or {},
            "risk_level": proposal.get("risk_level") or "medium",
            "novel_param": bool(proposal.get("_source") == "glm"),
        }).to_dict()

    def rank_proposals(self, proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        glm_valid = [
            p for p in proposals
            if p.get("_source") == "glm" and bool((p.get("validation") or {}).get("valid"))
        ]
        glm_invalid = [
            p for p in proposals
            if p.get("_source") == "glm" and not bool((p.get("validation") or {}).get("valid"))
        ]
        rule_proposals = [p for p in proposals if p.get("_source") != "glm"]
        rule_sorted = sorted(rule_proposals, key=lambda x: float(x.get("score") or -1e9), reverse=True)
        return glm_valid + rule_sorted + glm_invalid

    def build_proposal(
        self,
        generated: Dict[str, Any],
        *,
        proposal_id: str,
        run_id: str,
        candidate_index: int,
        memory_references: Optional[List[Dict[str, Any]]] = None,
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "proposal_id": proposal_id,
            "run_id": run_id,
            "status": "pending_review",
            "created_at": created_at or datetime.now().isoformat(),
            "candidate_index": candidate_index,
            "_source": generated.get("_source") or "rule",
            "search_space_patch": generated.get("search_space_patch") or {},
            "evaluation_contract_patch": generated.get("evaluation_contract_patch") or {},
            "structure_patch": generated.get("structure_patch") or {},
            "global_config_patch": generated.get("global_config_patch") or {},
            "node_param_patches": generated.get("node_param_patches") if isinstance(generated.get("node_param_patches"), list) else [],
            "feature_recipe_id": generated.get("feature_recipe_id"),
            "notes": generated.get("notes") or [],
            "risk_level": generated.get("risk_level") or "low",
            "base_search_space": generated.get("base_search_space") or {},
            "base_evaluation_contract": generated.get("base_evaluation_contract") or {},
            "memory_references": generated.get("memory_references") or memory_references or [],
            "llm_used": bool(generated.get("llm_used")) if isinstance(generated, dict) else False,
            "llm_model": generated.get("llm_model") if isinstance(generated, dict) else None,
            "llm_error": generated.get("llm_error") if isinstance(generated, dict) else None,
            "hypothesis": generated.get("hypothesis") if isinstance(generated, dict) else None,
            "hypothesis_type": generated.get("hypothesis_type") if isinstance(generated, dict) else None,
            "expected_outcome": generated.get("expected_outcome") if isinstance(generated, dict) else None,
            "fallback_if_failed": generated.get("fallback_if_failed") if isinstance(generated, dict) else None,
            "observation": generated.get("observation") if isinstance(generated, dict) else None,
            "primary_variable": generated.get("primary_variable") if isinstance(generated, dict) else None,
        }

    def apply_to_state(
        self,
        state: Dict[str, Any],
        proposal: Dict[str, Any],
        *,
        proposal_id: str,
        allowed_global_config_keys: Optional[Iterable[str]] = None,
        now: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = now or datetime.now().isoformat()
        runtime_patch = self.merge_runtime_patch(
            state.get("runtime_patch"),
            proposal,
            allowed_global_config_keys=allowed_global_config_keys,
        )
        state["runtime_patch"] = runtime_patch
        state["latest_applied_proposal_id"] = proposal_id
        state["last_applied_proposal_id"] = proposal_id

        current_iteration = state.get("current_iteration")
        try:
            effective_from_iteration = int(current_iteration or 0) + 1
        except (TypeError, ValueError):
            effective_from_iteration = None

        state["last_applied_proposal"] = deepcopy(proposal)
        history = state.get("runtime_patch_history")
        if not isinstance(history, list):
            history = []
        history.append({
            "proposal_id": proposal_id,
            "applied_at": timestamp,
            "applied_iteration": current_iteration,
            "effective_from_iteration": effective_from_iteration,
            "hypothesis": proposal.get("hypothesis"),
            "risk_level": proposal.get("risk_level"),
            "runtime_patch": deepcopy(runtime_patch),
            "proposal_patch": self.extract_patch(proposal),
        })
        state["runtime_patch_history"] = history[-100:]

        chain = state.get("hypothesis_chain")
        if not isinstance(chain, list):
            chain = []
        chain.append({
            "proposal_id": proposal_id,
            "applied_iteration": current_iteration,
            "hypothesis": proposal.get("hypothesis"),
            "hypothesis_type": proposal.get("hypothesis_type"),
            "expected_outcome": proposal.get("expected_outcome"),
            "status": "pending_verification",
            "applied_at": timestamp,
        })
        state["hypothesis_chain"] = chain[-30:]

        return {
            "runtime_patch": runtime_patch,
            "effective_from_iteration": effective_from_iteration,
            "applied_at": timestamp,
        }

    def merge_runtime_patch(
        self,
        current_patch: Any,
        proposal: Dict[str, Any],
        *,
        allowed_global_config_keys: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        runtime_patch = dict(current_patch) if isinstance(current_patch, dict) else {}
        runtime_patch.setdefault("search_space_patch", {})
        runtime_patch.setdefault("evaluation_contract_patch", {})
        runtime_patch.setdefault("structure_patch", {})
        runtime_patch.setdefault("global_config_patch", {})
        runtime_patch.setdefault("node_param_patches", [])

        runtime_patch["search_space_patch"] = dict(runtime_patch.get("search_space_patch") or {})
        runtime_patch["search_space_patch"].update(dict(proposal.get("search_space_patch") or {}))

        runtime_patch["evaluation_contract_patch"] = dict(runtime_patch.get("evaluation_contract_patch") or {})
        runtime_patch["evaluation_contract_patch"].update(dict(proposal.get("evaluation_contract_patch") or {}))

        runtime_patch["structure_patch"] = self.merge_structure_patch_bundle(
            dict(runtime_patch.get("structure_patch") or {}),
            dict(proposal.get("structure_patch") or {}),
        )
        runtime_patch["global_config_patch"] = self.merge_global_config_patch_bundle(
            dict(runtime_patch.get("global_config_patch") or {}),
            dict(proposal.get("global_config_patch") or {}),
            allowed_keys=set(str(x) for x in allowed_global_config_keys or []),
        )
        runtime_patch["node_param_patches"] = self.merge_node_param_patches_bundle(
            runtime_patch.get("node_param_patches"),
            proposal.get("node_param_patches"),
        )

        feature_recipe_id = proposal.get("feature_recipe_id")
        if isinstance(feature_recipe_id, str) and feature_recipe_id.strip():
            runtime_patch["feature_recipe_id"] = feature_recipe_id.strip()
        return runtime_patch

    def extract_patch(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "search_space_patch": proposal.get("search_space_patch") or {},
            "evaluation_contract_patch": proposal.get("evaluation_contract_patch") or {},
            "structure_patch": proposal.get("structure_patch") or {},
            "global_config_patch": proposal.get("global_config_patch") or {},
            "node_param_patches": proposal.get("node_param_patches") if isinstance(proposal.get("node_param_patches"), list) else [],
            "feature_recipe_id": proposal.get("feature_recipe_id"),
        }

    def mark_applied(
        self,
        proposal: Dict[str, Any],
        *,
        reviewer: Any,
        validation: Dict[str, Any],
        now: Optional[str] = None,
    ) -> Dict[str, Any]:
        proposal["status"] = "applied"
        proposal["review_action"] = "apply"
        proposal["reviewed_at"] = now or datetime.now().isoformat()
        proposal["reviewer"] = reviewer
        proposal["validation"] = validation
        return proposal

    def mark_rejected(
        self,
        proposal: Dict[str, Any],
        *,
        reviewer: Any,
        reason: Any,
        now: Optional[str] = None,
    ) -> Dict[str, Any]:
        proposal["status"] = "rejected"
        proposal["review_action"] = "reject"
        proposal["reviewed_at"] = now or datetime.now().isoformat()
        proposal["reviewer"] = reviewer
        proposal["reject_reason"] = reason
        return proposal

    def merge_structure_patch_bundle(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        base = dict(base or {})
        overlay = dict(overlay or {})
        out: Dict[str, Any] = {
            "node_switches": self.merge_node_switches(
                base.get("node_switches") if isinstance(base.get("node_switches"), list) else [],
                overlay.get("node_switches") if isinstance(overlay.get("node_switches"), list) else [],
            )
        }
        out["node_config_patches"] = self.merge_node_config_patches_bundle(
            base.get("node_config_patches"),
            overlay.get("node_config_patches"),
        )
        return out

    def merge_node_switches(self, base: Any, overlay: Any) -> List[Dict[str, Any]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        for item in base if isinstance(base, list) else []:
            if isinstance(item, dict) and item.get("node_id"):
                node_id = str(item["node_id"]).strip()
                if node_id:
                    by_id[node_id] = dict(item)
        for item in overlay if isinstance(overlay, list) else []:
            if isinstance(item, dict) and item.get("node_id"):
                node_id = str(item["node_id"]).strip()
                if node_id:
                    by_id[node_id] = {**by_id.get(node_id, {}), **item}
        return list(by_id.values())

    def merge_node_config_patches_bundle(self, base: Any, overlay: Any) -> List[Dict[str, Any]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        for item in base if isinstance(base, list) else []:
            self._merge_node_patch_row(by_id, item, patch_key="config_patch")
        for item in overlay if isinstance(overlay, list) else []:
            self._merge_node_patch_row(by_id, item, patch_key="config_patch")
        return list(by_id.values())

    def merge_node_param_patches_bundle(self, base: Any, overlay: Any) -> List[Dict[str, Any]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        for item in base if isinstance(base, list) else []:
            self._merge_node_patch_row(by_id, item, patch_key="param_patch")
        for item in overlay if isinstance(overlay, list) else []:
            self._merge_node_patch_row(by_id, item, patch_key="param_patch")
        return list(by_id.values())

    def merge_global_config_patch_bundle(
        self,
        base: Dict[str, Any],
        overlay: Dict[str, Any],
        *,
        allowed_keys: Set[str],
    ) -> Dict[str, Any]:
        out = dict(base or {})
        for key, value in dict(overlay or {}).items():
            skey = str(key).strip()
            if skey in allowed_keys:
                out[skey] = value
        return out

    def _merge_node_patch_row(self, by_id: Dict[str, Dict[str, Any]], item: Any, *, patch_key: str) -> None:
        if not isinstance(item, dict):
            return
        node_id = str(item.get("node_id") or "").strip()
        if not node_id:
            return
        prev = by_id.get(node_id, {})
        prev_patch = prev.get(patch_key) if isinstance(prev.get(patch_key), dict) else {}
        item_patch = item.get(patch_key) if isinstance(item.get(patch_key), dict) else {}
        by_id[node_id] = {**prev, **item, "node_id": node_id, patch_key: {**prev_patch, **item_patch}}
