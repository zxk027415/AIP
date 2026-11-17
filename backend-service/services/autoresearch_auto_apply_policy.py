"""
AutoResearch GLM proposal auto-apply policy helpers.

The service keeps proposal bookkeeping and risk decisions out of the main
workflow loop. It is intentionally pure except for mutating the provided run
state dict where history needs to be recorded.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional


class AutoResearchAutoApplyPolicy:
    _RISK_RANK = {"low": 0, "medium": 1, "high": 2}

    def risk_rank(self, level: str) -> int:
        return self._RISK_RANK.get(str(level or "low").lower(), 0)

    def risk_allowed(self, risk: str, risk_max: str) -> bool:
        return self.risk_rank(risk) <= self.risk_rank(risk_max)

    def proposal_validation(self, proposal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        p = proposal if isinstance(proposal, dict) else {}
        validation = p.get("validation") or {}
        errors = validation.get("errors")
        return {
            "valid": bool(validation.get("valid")),
            "risk": str(p.get("risk_level") or "low").lower(),
            "errors": errors if isinstance(errors, list) else [],
        }

    def skip_reason(
        self,
        recommended_id: str,
        auto_apply: bool,
        valid: bool,
        risk_ok: bool,
    ) -> Optional[str]:
        if not recommended_id:
            return "no_recommended_proposal"
        if not auto_apply:
            return "auto_apply_disabled"
        if not valid:
            return "validator_failed"
        if not risk_ok:
            return "risk_exceeds_threshold"
        return None

    def proposal_text_fields(self, proposal: Optional[Dict[str, Any]]) -> Dict[str, str]:
        p = proposal if isinstance(proposal, dict) else {}
        rationale = ""
        notes = p.get("notes")
        if isinstance(notes, list) and notes:
            rationale = str(notes[0])
        return {
            "hypothesis": str(p.get("hypothesis") or ""),
            "observation": str(p.get("observation") or ""),
            "rationale": rationale,
        }

    def build_latest_auto_proposal(
        self,
        *,
        auto_pack: Dict[str, Any],
        recommended_id: str,
        proposal: Optional[Dict[str, Any]],
        auto_apply: bool,
        risk_max: str,
        duration_s: float,
        generated_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        validation = self.proposal_validation(proposal)
        risk_ok = self.risk_allowed(validation["risk"], risk_max)
        text = self.proposal_text_fields(proposal)
        return {
            "generated_at": generated_at or datetime.now().isoformat(),
            "generated_count": auto_pack.get("generated_count"),
            "recommended_proposal_id": recommended_id or None,
            "recommended_valid": validation["valid"] if recommended_id else None,
            "recommended_risk": validation["risk"] if recommended_id else None,
            "auto_apply_risk_level_max": risk_max,
            "skip_apply_reason": self.skip_reason(
                recommended_id,
                auto_apply,
                validation["valid"],
                risk_ok,
            ),
            "validation_errors": validation["errors"],
            "glm_input_debug": auto_pack.get("glm_input_debug") or {},
            "glm_meta": auto_pack.get("glm_meta") or {},
            "duration_s": duration_s,
            "hypothesis": text["hypothesis"],
            "observation": text["observation"],
            "rationale": text["rationale"],
        }

    def append_history(
        self,
        state: Dict[str, Any],
        *,
        iteration: int,
        latest: Dict[str, Any],
        called_at: Optional[str] = None,
        max_items: int = 30,
    ) -> Dict[str, Any]:
        if not isinstance(state.get("glm_call_history"), list):
            state["glm_call_history"] = []
        row = {
            "iteration": iteration,
            "called_at": called_at or datetime.now().isoformat(),
            "duration_s": latest.get("duration_s"),
            "generated_count": latest.get("generated_count"),
            "recommended_id": latest.get("recommended_proposal_id"),
            "recommended_valid": latest.get("recommended_valid"),
            "recommended_risk": latest.get("recommended_risk"),
            "auto_apply_risk_level_max": latest.get("auto_apply_risk_level_max"),
            "skip_apply_reason": latest.get("skip_apply_reason"),
            "validation_errors": latest.get("validation_errors") or [],
            "glm_input_debug": latest.get("glm_input_debug") or {},
            "hypothesis": latest.get("hypothesis") or "",
            "observation": latest.get("observation") or "",
            "rationale": latest.get("rationale") or "",
            "glm_meta": latest.get("glm_meta") or {},
            "applied": False,
        }
        state["glm_call_history"].append(row)
        state["glm_call_history"] = state["glm_call_history"][-max_items:]
        return row

    def evaluate_application(
        self,
        *,
        recommended_id: str,
        proposal: Optional[Dict[str, Any]],
        auto_apply: bool,
        risk_max: str,
    ) -> Dict[str, Any]:
        validation = self.proposal_validation(proposal)
        risk_ok = self.risk_allowed(validation["risk"], risk_max)
        return {
            "recommended_id": recommended_id,
            "valid": validation["valid"],
            "risk": validation["risk"],
            "risk_ok": risk_ok,
            "can_apply": bool(recommended_id and auto_apply and validation["valid"] and risk_ok),
            "skip_apply_reason": self.skip_reason(
                recommended_id,
                auto_apply,
                validation["valid"],
                risk_ok,
            ),
            "validation_errors": validation["errors"],
        }

    def mark_latest_applied(self, state: Dict[str, Any]) -> None:
        history = state.get("glm_call_history")
        if isinstance(history, list) and history:
            history[-1]["applied"] = True
            history[-1]["skip_apply_reason"] = None
        latest_auto = state.get("latest_auto_proposal")
        if isinstance(latest_auto, dict):
            latest_auto["skip_apply_reason"] = None
        state["_consecutive_proposal_skips"] = 0

    def record_blocked_application(
        self,
        state: Dict[str, Any],
        *,
        risk_max: str,
        escalation_threshold: int = 3,
    ) -> Dict[str, Any]:
        skip_count = int(state.get("_consecutive_proposal_skips") or 0) + 1
        state["_consecutive_proposal_skips"] = skip_count
        next_risk_max = risk_max
        escalated = False
        if skip_count >= escalation_threshold and risk_max == "low":
            next_risk_max = "medium"
            escalated = True
            state["_auto_escalated_risk_max"] = True
        return {
            "skip_count": skip_count,
            "risk_max": next_risk_max,
            "escalated": escalated,
        }

    def enrich_history(
        self,
        history: Any,
        *,
        proposals: Dict[str, Dict[str, Any]],
        risk_max: str,
        auto_apply: bool,
    ) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for raw in history or []:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            recommended_id = str(row.get("recommended_id") or "")
            proposal = proposals.get(recommended_id) if recommended_id else None
            if isinstance(proposal, dict):
                validation = self.proposal_validation(proposal)
                risk_ok = self.risk_allowed(validation["risk"], risk_max)
                row.setdefault("recommended_valid", validation["valid"])
                row.setdefault("recommended_risk", validation["risk"])
                row.setdefault("auto_apply_risk_level_max", risk_max)
                row.setdefault("validation_errors", validation["errors"])
                if not bool(row.get("applied")) and not row.get("skip_apply_reason"):
                    row["skip_apply_reason"] = self.skip_reason(
                        recommended_id,
                        auto_apply,
                        validation["valid"],
                        risk_ok,
                    )
            elif recommended_id and "auto_apply_risk_level_max" not in row:
                row["auto_apply_risk_level_max"] = risk_max
            elif not recommended_id and not row.get("skip_apply_reason"):
                row["skip_apply_reason"] = "no_recommended_proposal"
            enriched.append(row)
        return enriched
