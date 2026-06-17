from services.autoresearch_self_heal import AutoResearchSelfHeal


def test_self_heal_disables_strict_filters_for_no_test_data():
    state = {"runtime_patch": {"evaluation_contract_patch": {}}}
    candidates = [{"status": "failed", "error": "no test data after mask"}]

    action = AutoResearchSelfHeal().maybe_apply(
        state=state,
        all_candidates=candidates,
        current_iteration=1,
        applied_at="now",
    )

    eval_patch = state["runtime_patch"]["evaluation_contract_patch"]
    assert action["type"] == "no_test_data_recover"
    assert eval_patch["backtest_apply_window_filter"] is False
    assert eval_patch["backtest_mask_target_values"] is False
    assert state["auto_adjust_stats"]["handled_no_test_data"] is True


def test_self_heal_reduces_training_window_for_insufficient_data():
    state = {
        "evaluation_contract": {"train_days": 30, "backtest_train_days": 45},
        "runtime_patch": {"evaluation_contract_patch": {}},
    }
    candidates = [{"status": "failed", "error": "insufficient_train_data"}]

    action = AutoResearchSelfHeal().maybe_apply(
        state=state,
        all_candidates=candidates,
        current_iteration=2,
        applied_at="now",
    )

    eval_patch = state["runtime_patch"]["evaluation_contract_patch"]
    assert action["type"] == "insufficient_train_data_recover"
    assert eval_patch["train_days"] == 23
    assert eval_patch["backtest_train_days"] == 38


def test_self_heal_expands_search_when_recent_successes_plateau():
    state = {
        "runtime_patch": {
            "search_space_patch": {
                "auto_tune_n_trials": [3, 5, 8],
                "train_days": [30, 45],
            }
        }
    }
    candidates = [
        {"status": "success", "evaluation": {"mape_improvement": 0.10}},
        {"status": "success", "evaluation": {"mape_improvement": 0.11}},
        {"status": "success", "evaluation": {"mape_improvement": 0.12}},
    ]

    action = AutoResearchSelfHeal().maybe_apply(
        state=state,
        all_candidates=candidates,
        current_iteration=3,
        applied_at="now",
    )

    search_patch = state["runtime_patch"]["search_space_patch"]
    assert action["type"] == "plateau_expand_search"
    assert search_patch["auto_tune_n_trials"] == [3, 5, 8, 12, 16]
    assert search_patch["train_days"] == [30, 45, 60]
    assert search_patch["backtest_train_days"] == [30, 45, 60]


def test_self_heal_does_not_repeat_same_adjustment():
    state = {
        "auto_adjust_stats": {"handled_no_test_data": True},
        "runtime_patch": {"evaluation_contract_patch": {}},
    }
    candidates = [{"status": "failed", "error": "no test data"}]

    action = AutoResearchSelfHeal().maybe_apply(
        state=state,
        all_candidates=candidates,
        current_iteration=1,
        applied_at="now",
    )

    assert action is None
