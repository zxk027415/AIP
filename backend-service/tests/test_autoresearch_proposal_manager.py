from services.autoresearch_proposal_manager import AutoResearchProposalManager


def test_apply_to_state_merges_runtime_patch_and_records_history():
    manager = AutoResearchProposalManager()
    state = {
        "current_iteration": 4,
        "runtime_patch": {
            "search_space_patch": {"train_days": [30]},
            "evaluation_contract_patch": {"backtest_train_days": 30},
            "structure_patch": {
                "node_switches": [
                    {"node_id": "n1", "functionId": "holiday_features", "enabled": False}
                ],
                "node_config_patches": [
                    {"node_id": "n2", "config_patch": {"lags": [1, 7]}}
                ],
            },
            "global_config_patch": {"ensemble_mode": "single_best"},
            "node_param_patches": [
                {"node_id": "n2", "functionId": "create_lag_features", "param_patch": {"lags": [1, 7]}}
            ],
        },
    }
    proposal = {
        "search_space_patch": {"train_days": [45]},
        "evaluation_contract_patch": {"backtest_train_days": 45},
        "structure_patch": {
            "node_switches": [
                {"node_id": "n1", "functionId": "holiday_features", "enabled": True}
            ],
            "node_config_patches": [
                {"node_id": "n2", "config_patch": {"window_sizes": [24, 48]}}
            ],
        },
        "global_config_patch": {
            "ensemble_mode": "all_adaptive",
            "not_allowed": "drop",
        },
        "node_param_patches": [
            {"node_id": "n2", "functionId": "create_lag_features", "param_patch": {"window_sizes": [24, 48]}}
        ],
        "feature_recipe_id": "features_full_default_v1",
        "hypothesis": "calendar features improve weekend error",
        "hypothesis_type": "feature",
        "risk_level": "low",
        "expected_outcome": {"metric": "mape_improvement", "threshold": 0.01},
    }

    result = manager.apply_to_state(
        state,
        proposal,
        proposal_id="prop-1",
        allowed_global_config_keys={"ensemble_mode"},
        now="2026-05-21T12:00:00",
    )

    patch = result["runtime_patch"]
    assert result["effective_from_iteration"] == 5
    assert patch["search_space_patch"]["train_days"] == [45]
    assert patch["evaluation_contract_patch"]["backtest_train_days"] == 45
    assert patch["structure_patch"]["node_switches"][0]["enabled"] is True
    assert patch["structure_patch"]["node_config_patches"][0]["config_patch"] == {
        "lags": [1, 7],
        "window_sizes": [24, 48],
    }
    assert patch["global_config_patch"] == {"ensemble_mode": "all_adaptive"}
    assert patch["node_param_patches"][0]["param_patch"] == {
        "lags": [1, 7],
        "window_sizes": [24, 48],
    }
    assert patch["feature_recipe_id"] == "features_full_default_v1"
    assert state["last_applied_proposal_id"] == "prop-1"
    assert state["runtime_patch_history"][-1]["proposal_id"] == "prop-1"
    assert state["hypothesis_chain"][-1]["status"] == "pending_verification"


def test_mark_applied_and_rejected_update_review_fields():
    manager = AutoResearchProposalManager()
    proposal = {"status": "pending_review"}

    manager.mark_applied(
        proposal,
        reviewer="system:auto",
        validation={"valid": True},
        now="2026-05-21T12:01:00",
    )

    assert proposal["status"] == "applied"
    assert proposal["review_action"] == "apply"
    assert proposal["reviewer"] == "system:auto"
    assert proposal["validation"] == {"valid": True}

    rejected = {"status": "pending_review"}
    manager.mark_rejected(
        rejected,
        reviewer="user",
        reason="too risky",
        now="2026-05-21T12:02:00",
    )

    assert rejected["status"] == "rejected"
    assert rejected["review_action"] == "reject"
    assert rejected["reviewer"] == "user"
    assert rejected["reject_reason"] == "too risky"


def test_score_candidate_penalizes_invalid_and_rewards_quality():
    manager = AutoResearchProposalManager()
    invalid = {"validation": {"valid": False}}
    low_quality = {
        "validation": {"valid": True},
        "risk_level": "low",
        "search_space_patch": {"train_days": [30]},
        "evaluation_contract_patch": {},
        "structure_patch": {},
        "global_config_patch": {},
        "node_param_patches": [],
        "hypothesis": "train_days may improve MAPE",
        "expected_outcome": {"threshold": 0.01},
        "experiment_quality": {"composite_score": 0.2, "single_variable_control": 0.2},
    }
    high_quality = dict(low_quality)
    high_quality["experiment_quality"] = {"composite_score": 0.9, "single_variable_control": 1.0}

    assert manager.score_candidate(invalid) == -1e9
    assert manager.score_candidate(high_quality) > manager.score_candidate(low_quality)


def test_rank_proposals_keeps_valid_glm_first_and_sorts_rules_by_score():
    manager = AutoResearchProposalManager()
    glm_valid = {"proposal_id": "glm-valid", "_source": "glm", "validation": {"valid": True}, "score": 1}
    glm_invalid = {"proposal_id": "glm-invalid", "_source": "glm", "validation": {"valid": False}, "score": 999}
    rule_low = {"proposal_id": "rule-low", "_source": "rule", "validation": {"valid": True}, "score": 10}
    rule_high = {"proposal_id": "rule-high", "_source": "rule", "validation": {"valid": True}, "score": 20}

    ranked = manager.rank_proposals([rule_low, glm_invalid, rule_high, glm_valid])

    assert [p["proposal_id"] for p in ranked] == [
        "glm-valid",
        "rule-high",
        "rule-low",
        "glm-invalid",
    ]


def test_build_proposal_preserves_candidate_fields_and_memory_fallback():
    manager = AutoResearchProposalManager()
    generated = {
        "_source": "glm",
        "search_space_patch": {"train_days": [30]},
        "evaluation_contract_patch": {"backtest_train_days": 30},
        "structure_patch": {"node_switches": []},
        "global_config_patch": {"ensemble_mode": "all_adaptive"},
        "node_param_patches": [{"node_id": "n1", "param_patch": {"lags": [1, 7]}}],
        "feature_recipe_id": "features_full_default_v1",
        "notes": ["note"],
        "risk_level": "medium",
        "llm_used": True,
        "llm_model": "glm-test",
        "hypothesis": "test hypothesis",
        "hypothesis_type": "parameter",
        "expected_outcome": {"metric": "mape_improvement", "threshold": 0.01},
        "primary_variable": "train_days",
    }

    proposal = manager.build_proposal(
        generated,
        proposal_id="prop-x",
        run_id="ares-x",
        candidate_index=2,
        memory_references=[{"case_id": "mem-1"}],
        created_at="2026-05-21T12:03:00",
    )

    assert proposal["proposal_id"] == "prop-x"
    assert proposal["run_id"] == "ares-x"
    assert proposal["status"] == "pending_review"
    assert proposal["_source"] == "glm"
    assert proposal["candidate_index"] == 2
    assert proposal["memory_references"] == [{"case_id": "mem-1"}]
    assert proposal["node_param_patches"] == [{"node_id": "n1", "param_patch": {"lags": [1, 7]}}]
    assert proposal["llm_used"] is True
    assert proposal["primary_variable"] == "train_days"
