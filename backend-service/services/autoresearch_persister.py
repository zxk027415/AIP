from datetime import datetime
from typing import Any, Dict, List, Optional

from .autoresearch_run_store import AutoResearchRunStore
from .autoresearch_trial_ledger import AutoResearchTrialLedger


class AutoResearchPersister:
    def __init__(
        self,
        root_dir: Optional[str] = None,
        run_store: Optional[AutoResearchRunStore] = None,
        trial_ledger: Optional[AutoResearchTrialLedger] = None,
    ):
        self.run_store = run_store or AutoResearchRunStore(root_dir=root_dir)
        self.trial_ledger = trial_ledger or AutoResearchTrialLedger(root_dir=root_dir)

    def save_snapshot(self, run_id: str, state: Dict[str, Any]) -> str:
        return self.run_store.save(run_id, state)

    def load_snapshot(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self.run_store.load(run_id)

    def load_for_status(self, run_id: str, active_in_memory: bool = False) -> Optional[Dict[str, Any]]:
        return self.run_store.load_for_status(run_id, active_in_memory=active_in_memory)

    def list_runs(
        self,
        limit: int = 50,
        memory_store: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        rows = self.run_store.list(limit=limit)
        memory_store = memory_store or {}
        memory_ids = set(memory_store.keys())
        for row in rows:
            run_id = str(row.get("run_id") or "")
            row["snapshot_source"] = "memory+disk" if run_id in memory_ids else "disk"
            if run_id in memory_ids:
                mem_state = memory_store.get(run_id) or {}
                row["status"] = mem_state.get("status", row.get("status"))
                row["progress"] = mem_state.get("progress", row.get("progress"))
        disk_ids = {str(row.get("run_id")) for row in rows}
        for run_id, state in memory_store.items():
            if run_id in disk_ids:
                continue
            rows.append({
                "run_id": run_id,
                "status": state.get("status"),
                "progress": state.get("progress"),
                "baseline_workflow_id": state.get("baseline_workflow_id"),
                "created_at": state.get("created_at"),
                "updated_at": state.get("updated_at"),
                "snapshot_source": "memory",
            })
        return rows[: max(1, int(limit or 50))]

    def record_trial_from_candidate(self, run_id: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
        evaluation = candidate.get("evaluation") if isinstance(candidate.get("evaluation"), dict) else {}
        summary = candidate.get("summary") if isinstance(candidate.get("summary"), dict) else {}
        row = {
            "iteration_no": candidate.get("iteration"),
            "comparison_id": candidate.get("comparison_id"),
            "status": candidate.get("status"),
            "sampled_layers": candidate.get("sampled_layers") or [],
            "override": candidate.get("override") or {},
            "search_space_patch": candidate.get("search_space_patch") or {},
            "structure_patch": candidate.get("structure_patch") or {},
            "global_config_patch": candidate.get("global_config_patch") or {},
            "node_param_patches": candidate.get("node_param_patches") or [],
            "runtime_patch_snapshot": candidate.get("runtime_patch") or candidate.get("runtime_patch_snapshot") or {},
            "effective_search_space": candidate.get("effective_search_space") or {},
            "effective_evaluation_contract": candidate.get("effective_evaluation_contract") or {},
            "hypothesis_type": candidate.get("hypothesis_type"),
            "primary_variable": candidate.get("primary_variable"),
            "batch_groups": candidate.get("batch_groups") or [],
            "evidence": candidate.get("evidence") or {},
            "evidence_summary": candidate.get("evidence_summary") or {},
            "exploration_health": candidate.get("exploration_health") or {},
            "hypothesis_verification": candidate.get("hypothesis_verification"),
            "baseline_metrics": evaluation.get("baseline_metrics") or summary.get("baseline_metrics"),
            "challenger_metrics": evaluation.get("challenger_metrics") or summary.get("challenger_metrics"),
            "mape_improvement": evaluation.get("mape_improvement"),
            "score_advantage": evaluation.get("score_advantage") or summary.get("score_advantage"),
            "challenger_mape": evaluation.get("challenger_mape"),
            "baseline_mape": evaluation.get("baseline_mape"),
            "error_message": candidate.get("error"),
            "is_control_round": bool(candidate.get("is_control_round")),
        }
        if row["override"] or row["structure_patch"] or row["global_config_patch"] or row["node_param_patches"]:
            row["applied_patch_fingerprint"] = str(candidate.get("applied_patch_fingerprint") or "")
        return self.trial_ledger.append_trial(run_id, row)

    def record_decision(
        self,
        run_id: str,
        decision_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        row = dict(payload or {})
        row["decision_type"] = decision_type
        row.setdefault("created_at", datetime.now().isoformat())
        return self.trial_ledger.append_decision(run_id, row)

    def list_trials(self, run_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        return self.trial_ledger.list_trials(run_id, limit=limit)

    def list_decisions(self, run_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        return self.trial_ledger.list_decisions(run_id, limit=limit)

    def stats(self) -> Dict[str, Any]:
        return self.trial_ledger.stats()
