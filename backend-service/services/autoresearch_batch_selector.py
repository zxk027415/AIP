from typing import Any, Dict, List, Optional


class AutoResearchBatchSelector:
    def select_best_successful(self, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        successful: List[Dict[str, Any]] = []
        for row in rows:
            state = row.get("state") if isinstance(row, dict) else None
            if not isinstance(state, dict):
                continue
            if str(state.get("status") or "") != "success":
                continue
            summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
            if "windows_comparable" in summary and int(summary.get("windows_comparable") or 0) <= 0:
                continue
            successful.append(row)
        if not successful:
            return None

        def _score(row: Dict[str, Any]) -> float:
            state = row.get("state") if isinstance(row.get("state"), dict) else {}
            summary = state.get("summary") if isinstance(state, dict) else {}
            try:
                return float((summary or {}).get("score_advantage"))
            except (TypeError, ValueError):
                return -1e18

        return max(successful, key=lambda row: (_score(row), -int(row.get("group_idx") or 0)))
