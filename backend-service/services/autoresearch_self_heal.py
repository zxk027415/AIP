"""
AutoResearch runtime self-heal rules.

These rules patch only the in-memory runtime_patch of a run. They do not write
back workflow templates.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


class AutoResearchSelfHeal:
    def maybe_apply(
        self,
        *,
        state: Dict[str, Any],
        all_candidates: List[Dict[str, Any]],
        current_iteration: int,
        applied_at: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if current_iteration <= 0:
            return None

        runtime_patch = state.get("runtime_patch") or {
            "search_space_patch": {},
            "evaluation_contract_patch": {},
            "structure_patch": {},
            "global_config_patch": {},
            "node_param_patches": [],
        }
        search_patch = dict(runtime_patch.get("search_space_patch") or {})
        eval_patch = dict(runtime_patch.get("evaluation_contract_patch") or {})
        stats = dict(state.get("auto_adjust_stats") or {})
        action: Dict[str, Any] = {}

        last = all_candidates[-1] if all_candidates else {}
        last_err = str((last or {}).get("error") or "").lower()

        if ("无测试数据" in last_err or "no test data" in last_err) and not bool(stats.get("handled_no_test_data")):
            changed = False
            if eval_patch.get("backtest_apply_window_filter", True) is not False:
                eval_patch["backtest_apply_window_filter"] = False
                changed = True
            if eval_patch.get("backtest_mask_target_values", True) is not False:
                eval_patch["backtest_mask_target_values"] = False
                changed = True
            if changed:
                stats["handled_no_test_data"] = True
                action = {
                    "type": "no_test_data_recover",
                    "message": "检测到无测试数据，已自动关闭窗口过滤与目标掩码",
                }

        if (
            "训练数据不足" in last_err
            or "insufficient_train_data" in last_err
            or "no train data" in last_err
        ) and not bool(stats.get("handled_insufficient_train_data")):
            base_ec = state.get("evaluation_contract") or {}
            td0 = _safe_int(eval_patch.get("train_days", base_ec.get("train_days", 30)), 30)
            btd0 = _safe_int(eval_patch.get("backtest_train_days", base_ec.get("backtest_train_days", td0)), td0)
            td1 = max(14, td0 - 7)
            btd1 = max(14, btd0 - 7)
            if td1 != td0 or btd1 != btd0:
                eval_patch["train_days"] = td1
                eval_patch["backtest_train_days"] = btd1
                stats["handled_insufficient_train_data"] = True
                action = {
                    "type": "insufficient_train_data_recover",
                    "message": f"检测到训练数据不足，已下调 train_days/backtest_train_days 到 {td1}/{btd1}",
                }

        success_rows = [c for c in all_candidates if str(c.get("status") or "") == "success"]
        if not action and len(success_rows) >= 3 and not bool(stats.get("plateau_expanded_once")):
            vals: List[float] = []
            for row in success_rows[-3:]:
                ev = row.get("evaluation") or {}
                try:
                    vals.append(float(ev.get("mape_improvement")))
                except Exception:
                    pass
            if len(vals) == 3 and (max(vals) - min(vals)) <= 0.05:
                trials = search_patch.get("auto_tune_n_trials")
                base_trials = 8
                if isinstance(trials, list) and trials:
                    base_trials = _safe_int(trials[-1], 8)
                expanded_trials = sorted(list(set([3, 5, 8, base_trials, min(16, base_trials + 4), 16])))
                search_patch["auto_tune_n_trials"] = expanded_trials
                train_days = search_patch.get("train_days")
                if not isinstance(train_days, list) or len(train_days) == 0:
                    train_days = [30, 45, 60]
                td_vals: List[int] = []
                for value in train_days:
                    try:
                        td_vals.append(int(value))
                    except Exception:
                        pass
                if td_vals:
                    search_patch["train_days"] = sorted(
                        list(set(td_vals + [max(21, min(td_vals)), max(td_vals), max(td_vals) + 15]))
                    )
                    search_patch["backtest_train_days"] = list(search_patch["train_days"])
                stats["plateau_expanded_once"] = True
                action = {
                    "type": "plateau_expand_search",
                    "message": "连续 3 轮改善进入平台期，已自动扩展搜索空间（n_trials/train_days）",
                }

        if not action:
            return None

        runtime_patch["search_space_patch"] = search_patch
        runtime_patch["evaluation_contract_patch"] = eval_patch
        runtime_patch["structure_patch"] = dict(runtime_patch.get("structure_patch") or {})
        runtime_patch["global_config_patch"] = dict(runtime_patch.get("global_config_patch") or {})
        node_param_patches = runtime_patch.get("node_param_patches")
        runtime_patch["node_param_patches"] = list(node_param_patches) if isinstance(node_param_patches, list) else []
        state["runtime_patch"] = runtime_patch
        state["auto_adjust_stats"] = stats
        action["iteration"] = current_iteration
        action["applied_at"] = applied_at or datetime.now().isoformat()
        state["latest_auto_adjustment"] = action
        return action
