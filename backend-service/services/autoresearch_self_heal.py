"""
AutoResearch runtime self-heal rules.

These rules patch only the in-memory runtime_patch of a run. They do not write
back workflow templates.

设计约定（Strategy C：训练窗口天数走"手动运营决策"）：
  - `train_days` 属于**结构参数**（改动语义大、影响 baseline 缓存、跨 run 可比性），
    不自动进入 search_space，即便 plateau 也不自动扩展。
  - 若 plateau 检测触发，只在 `state["latest_suggestions"]` 里追加一条
    「建议尝试探索 train_days」的建议，供前端展示，用户可决定是否手动
    在 AutoResearch 启动 UI 上勾选「探索训练窗口天数」重新开始 run。
  - 相关字段：`slot.training_window_days`（部署侧）由人工在算法部署页面调，
    Promote 不自动改。
"""
# @AI_GENERATED
from datetime import datetime
from typing import Any, Dict, List, Optional


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _append_suggestion(state: Dict[str, Any], suggestion: Dict[str, Any]) -> None:
    """
    向 state["latest_suggestions"] 追加一条建议记录（去重 by suggestion["key"]）。

    建议记录仅供前端展示，绝不影响 runtime_patch / search_space。
    调用方保证 suggestion 含 `key`、`type`、`message` 字段。
    """
    suggestions = state.get("latest_suggestions")
    if not isinstance(suggestions, list):
        suggestions = []
    key = suggestion.get("key")
    if key is not None:
        # 已存在同 key 的建议 → 更新时间戳，不重复追加
        for existing in suggestions:
            if isinstance(existing, dict) and existing.get("key") == key:
                existing.update(suggestion)
                state["latest_suggestions"] = suggestions
                return
    suggestions.append(suggestion)
    state["latest_suggestions"] = suggestions
# @AI_GENERATED: end


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

        # @AI_GENERATED: Strategy C — plateau 时只扩展 n_trials（模型层参数），
        # 不再自动扩展 train_days（结构参数，走手动运营决策）；仅追加一条建议。
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
                # 只扩展 n_trials（属于调参深度，模型层，可自动）
                trials = search_patch.get("auto_tune_n_trials")
                base_trials = 8
                if isinstance(trials, list) and trials:
                    base_trials = _safe_int(trials[-1], 8)
                expanded_trials = sorted(list(set([3, 5, 8, base_trials, min(16, base_trials + 4), 16])))
                search_patch["auto_tune_n_trials"] = expanded_trials

                # train_days 不再自动扩展 —— 追加建议给前端展示
                _append_suggestion(state, {
                    "key": "plateau_consider_train_days",
                    "type": "explore_train_days",
                    "iteration": current_iteration,
                    "message": (
                        "连续 3 轮改善进入平台期。当前不自动探索训练窗口天数（train_days）。"
                        "如需探索，请人工在启动新 AutoResearch run 时勾选「探索训练窗口天数」，"
                        "或到算法部署页面手动调整 slot 的 training_window_days。"
                    ),
                    "current_train_days": (
                        (state.get("evaluation_contract") or {}).get("train_days")
                    ),
                    "suggested_at": applied_at or datetime.now().isoformat(),
                })

                stats["plateau_expanded_once"] = True
                action = {
                    "type": "plateau_expand_search",
                    "message": (
                        "连续 3 轮改善进入平台期，已自动扩展 n_trials；"
                        "train_days 属于结构参数不自动改，见 latest_suggestions"
                    ),
                }
        # @AI_GENERATED: end

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
