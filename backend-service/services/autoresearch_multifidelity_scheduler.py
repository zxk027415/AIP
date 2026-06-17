from math import ceil
from typing import Any, Dict, List


class AutoResearchMultiFidelityScheduler:
    def enabled(self, compare_config: Dict[str, Any], batch_size: int, windows: List[dict]) -> bool:
        if batch_size <= 1 or len(windows or []) <= 1:
            return False
        return bool(compare_config.get("multi_fidelity_enabled") or compare_config.get("asha_enabled"))

    def initial_windows(
        self,
        windows: List[dict],
        *,
        min_windows: int = 1,
        fraction: float = 0.5,
    ) -> List[dict]:
        if not windows:
            return []
        try:
            frac = float(fraction)
        except (TypeError, ValueError):
            frac = 0.5
        frac = min(1.0, max(0.1, frac))
        try:
            minimum = int(min_windows)
        except (TypeError, ValueError):
            minimum = 1
        count = max(1, minimum, int(ceil(len(windows) * frac)))
        count = min(len(windows), count)
        return list(windows[:count])

    def select_promotions(
        self,
        rows: List[Dict[str, Any]],
        *,
        reduction_factor: int = 2,
        min_promotions: int = 1,
    ) -> List[int]:
        successful = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            state = row.get("state") if isinstance(row.get("state"), dict) else {}
            if str(state.get("status") or "") != "success":
                continue
            summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
            try:
                score = float(summary.get("score_advantage"))
            except (TypeError, ValueError):
                score = -1e18
            successful.append((score, -int(row.get("group_idx") or 0), int(row.get("group_idx") or 0)))
        if not successful:
            return []
        successful.sort(reverse=True)
        try:
            rf = max(2, int(reduction_factor))
        except (TypeError, ValueError):
            rf = 2
        try:
            min_keep = max(1, int(min_promotions))
        except (TypeError, ValueError):
            min_keep = 1
        keep = max(min_keep, int(ceil(len(successful) / rf)))
        keep = min(len(successful), keep)
        return [group_idx for _, __, group_idx in successful[:keep]]

    def mark_pruned_groups(
        self,
        rows: List[Dict[str, Any]],
        promoted_group_indices: List[int],
    ) -> List[Dict[str, Any]]:
        promoted = set(int(x) for x in promoted_group_indices)
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            group_idx = int(item.get("group_idx") or 0)
            state = dict(item.get("state") or {})
            if group_idx not in promoted and str(state.get("status") or "") == "success":
                state["status"] = "pruned"
                state["pruned_by"] = "asha"
            item["state"] = state
            out.append(item)
        return out
