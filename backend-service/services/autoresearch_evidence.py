import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


EVIDENCE_STRENGTHS = {
    "single_window_positive",
    "single_window_negative",
    "multi_window_confirmed",
    "multi_window_rejected",
    "insufficient_evidence",
}


@dataclass
class ExperimentEvidence:
    run_id: str
    iteration: int
    group_idx: Optional[int]
    target_direction: str
    target_layer: str
    patch_fingerprint: str
    changed_variables: List[str] = field(default_factory=list)
    windows_total: int = 0
    windows_success: int = 0
    baseline_metric: Optional[float] = None
    challenger_metric: Optional[float] = None
    mape_improvement: Optional[float] = None
    status: str = "unknown"
    evidence_strength: str = "insufficient_evidence"
    needs_multi_window_confirmation: bool = False
    failure_reason: Optional[str] = None
    candidate_source: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutoResearchEvidenceBuilder:
    def build_many_for_groups(self, *, run_id: str, groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.build_for_group(run_id=run_id, group=group).to_dict() for group in groups or [] if isinstance(group, dict)]

    def build_for_candidate(
        self,
        *,
        run_id: str,
        candidate: Dict[str, Any],
        comparison_state: Optional[Dict[str, Any]] = None,
    ) -> ExperimentEvidence:
        comparison_state = comparison_state or {}
        evaluation = candidate.get("evaluation") if isinstance(candidate.get("evaluation"), dict) else {}
        summary = candidate.get("summary") if isinstance(candidate.get("summary"), dict) else {}
        window_results = self._window_results(comparison_state, summary)
        windows_total, windows_success = self._window_counts(window_results, comparison_state)
        mape_improvement = self._float_or_none(evaluation.get("mape_improvement"))
        status = str(candidate.get("status") or comparison_state.get("status") or "unknown").lower()
        return ExperimentEvidence(
            run_id=str(run_id),
            iteration=int(candidate.get("iteration") or candidate.get("iteration_no") or 0),
            group_idx=None,
            target_direction=str(candidate.get("target_direction") or self._direction_from_candidate(candidate)),
            target_layer=str(candidate.get("target_layer") or self._layer_from_candidate(candidate)),
            patch_fingerprint=str(candidate.get("applied_patch_fingerprint") or self.patch_fingerprint(candidate)),
            changed_variables=self.changed_variables(candidate),
            windows_total=windows_total,
            windows_success=windows_success,
            baseline_metric=self._float_or_none(evaluation.get("baseline_mape") or summary.get("baseline_mape")),
            challenger_metric=self._float_or_none(evaluation.get("challenger_mape") or summary.get("challenger_mape")),
            mape_improvement=mape_improvement,
            status=status,
            evidence_strength=self.evidence_strength(
                status=status,
                mape_improvement=mape_improvement,
                windows_total=windows_total,
                windows_success=windows_success,
            ),
            needs_multi_window_confirmation=self.needs_confirmation(
                status=status,
                mape_improvement=mape_improvement,
                windows_total=windows_total,
                windows_success=windows_success,
            ),
            failure_reason=str(candidate.get("error") or comparison_state.get("error") or "") or None,
            candidate_source=str(candidate.get("candidate_source") or "") or None,
        )

    def build_for_group(self, *, run_id: str, group: Dict[str, Any]) -> ExperimentEvidence:
        status = str(group.get("status") or "unknown").lower()
        summary = group.get("summary") if isinstance(group.get("summary"), dict) else {}
        windows_total = self._safe_int(
            group.get("windows_total")
            or group.get("windows_used")
            or summary.get("windows_total")
            or summary.get("windows_comparable")
            or 0
        )
        windows_success = self._safe_int(
            group.get("windows_done")
            or summary.get("windows_challenger_better")
            or summary.get("windows_comparable")
            or 0
        )
        mape_improvement = self._float_or_none(group.get("mape_improvement"))
        failure_reason = self._failure_reason(group, status)
        return ExperimentEvidence(
            run_id=str(run_id),
            iteration=int(group.get("iteration") or group.get("iteration_no") or 0),
            group_idx=self._int_or_none(group.get("group_idx")),
            target_direction=str(group.get("target_direction") or self._direction_from_candidate(group)),
            target_layer=str(group.get("target_layer") or group.get("selected_layer") or self._layer_from_candidate(group)),
            patch_fingerprint=str(group.get("applied_patch_fingerprint") or self.patch_fingerprint(group)),
            changed_variables=self.changed_variables(group),
            windows_total=windows_total,
            windows_success=windows_success,
            baseline_metric=self._float_or_none(group.get("baseline_mape")),
            challenger_metric=self._float_or_none(group.get("challenger_mape")),
            mape_improvement=mape_improvement,
            status=status,
            evidence_strength=self.evidence_strength(
                status=status,
                mape_improvement=mape_improvement,
                windows_total=windows_total,
                windows_success=windows_success,
            ),
            needs_multi_window_confirmation=self.needs_confirmation(
                status=status,
                mape_improvement=mape_improvement,
                windows_total=windows_total,
                windows_success=windows_success,
            ),
            failure_reason=failure_reason,
            candidate_source=str(group.get("candidate_source") or "") or None,
        )

    def evidence_strength(
        self,
        *,
        status: str,
        mape_improvement: Optional[float],
        windows_total: int,
        windows_success: int,
    ) -> str:
        if str(status).lower() != "success" or mape_improvement is None or windows_success <= 0:
            return "insufficient_evidence"
        positive = float(mape_improvement) > 0
        multi = int(windows_total or windows_success or 0) >= 2 and int(windows_success or 0) >= 2
        if positive and multi:
            return "multi_window_confirmed"
        if positive:
            return "single_window_positive"
        if multi:
            return "multi_window_rejected"
        return "single_window_negative"

    def needs_confirmation(
        self,
        *,
        status: str,
        mape_improvement: Optional[float],
        windows_total: int,
        windows_success: int,
    ) -> bool:
        return (
            str(status).lower() == "success"
            and mape_improvement is not None
            and float(mape_improvement) > 0
            and int(windows_total or windows_success or 0) <= 1
        )

    def changed_variables(self, payload: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        override = payload.get("override") if isinstance(payload.get("override"), dict) else {}
        out.extend(str(k) for k in override.keys())
        global_patch = payload.get("global_config_patch") if isinstance(payload.get("global_config_patch"), dict) else {}
        out.extend(str(k) for k in global_patch.keys())
        for patch in payload.get("node_param_patches") or []:
            if not isinstance(patch, dict):
                continue
            function_id = str(patch.get("functionId") or patch.get("function_id") or patch.get("node_id") or "node")
            param_patch = patch.get("param_patch") if isinstance(patch.get("param_patch"), dict) else {}
            out.extend(f"{function_id}.{k}" for k in param_patch.keys())
        structure_patch = payload.get("structure_patch") if isinstance(payload.get("structure_patch"), dict) else {}
        if structure_patch:
            out.append("structure_patch")
        return sorted(dict.fromkeys(x for x in out if x))

    def patch_fingerprint(self, payload: Dict[str, Any]) -> str:
        relevant = {
            "override": payload.get("override") or {},
            "structure_patch": payload.get("structure_patch") or {},
            "global_config_patch": payload.get("global_config_patch") or {},
            "node_param_patches": payload.get("node_param_patches") or [],
        }
        raw = json.dumps(relevant, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def summarize(self, evidences: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        direction_counts: Dict[str, int] = {}
        needs_confirmation = 0
        for item in evidences or []:
            if not isinstance(item, dict):
                continue
            strength = str(item.get("evidence_strength") or "insufficient_evidence")
            counts[strength] = counts.get(strength, 0) + 1
            direction = str(item.get("target_direction") or "unknown")
            direction_counts[direction] = direction_counts.get(direction, 0) + 1
            if bool(item.get("needs_multi_window_confirmation")):
                needs_confirmation += 1
        return {
            "total": len([x for x in evidences or [] if isinstance(x, dict)]),
            "by_strength": counts,
            "by_direction": direction_counts,
            "needs_multi_window_confirmation": needs_confirmation,
        }

    def _window_results(self, comparison_state: Dict[str, Any], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = comparison_state.get("window_results")
        if isinstance(rows, list):
            return rows
        rows = summary.get("window_results")
        return rows if isinstance(rows, list) else []

    def _window_counts(self, window_results: List[Dict[str, Any]], comparison_state: Dict[str, Any]) -> tuple[int, int]:
        if window_results:
            total = len(window_results)
            success = 0
            for row in window_results:
                if not isinstance(row, dict):
                    continue
                if str(row.get("status") or "success").lower() not in {"failed", "error", "cancelled"}:
                    success += 1
            return total, success
        summary = comparison_state.get("summary") if isinstance(comparison_state.get("summary"), dict) else {}
        total = int(summary.get("total_windows") or comparison_state.get("total_windows") or 0)
        return total, int(summary.get("success_windows") or total or 0)

    def _direction_from_candidate(self, payload: Dict[str, Any]) -> str:
        raw = str(payload.get("hypothesis_type") or payload.get("selected_layer") or "").lower()
        if raw in {"feature", "model", "data", "risk", "parameter"}:
            return raw
        if raw == "training":
            return "parameter"
        if payload.get("structure_patch"):
            return "feature"
        return "parameter"

    def _layer_from_candidate(self, payload: Dict[str, Any]) -> str:
        raw = str(payload.get("selected_layer") or payload.get("hypothesis_type") or "").lower()
        if raw in {"training", "feature", "model", "data"}:
            return raw
        if raw == "parameter":
            return "training"
        return "feature" if payload.get("structure_patch") else "training"

    def _float_or_none(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int_or_none(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _failure_reason(self, payload: Dict[str, Any], status: str) -> Optional[str]:
        explicit = payload.get("failure_reason") or payload.get("error") or payload.get("error_message")
        if explicit:
            return str(explicit)
        normalized = str(status or "").lower()
        if normalized in {"cancelled", "canceled"}:
            return "cancelled"
        if normalized in {"timeout", "timed_out"}:
            return "timeout"
        if normalized in {"failed", "error"}:
            return "failed_without_error_detail"
        return None


def build_evidence_contract_summary(evidences: List[Dict[str, Any]]) -> Dict[str, Any]:
    return AutoResearchEvidenceBuilder().summarize(evidences)
