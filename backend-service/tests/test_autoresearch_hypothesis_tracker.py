from services.autoresearch_hypothesis_tracker import AutoResearchHypothesisTracker


def test_verify_hypothesis_increase_threshold():
    tracker = AutoResearchHypothesisTracker()
    result = tracker.verify(
        {"evaluation": {"mape_improvement": 0.03}},
        {
            "hypothesis": "increase improvement",
            "expected_outcome": {
                "metric": "mape_improvement",
                "direction": "increase",
                "threshold": 0.02,
            },
        },
    )

    assert result["verified"] is True
    assert result["actual_improvement"] == 0.03


def test_update_state_records_disproved_hypothesis_with_patch_fingerprint():
    tracker = AutoResearchHypothesisTracker()
    state = {
        "last_applied_proposal": {
            "structure_patch": {
                "node_switches": [
                    {"functionId": "holiday_features", "enabled": True},
                ],
            },
            "node_param_patches": [
                {"functionId": "create_lag_features", "param_patch": {"lags": [1, 7]}},
            ],
            "global_config_patch": {"ensemble_mode": "all_adaptive"},
        }
    }
    verification = {
        "hypothesis": "calendar helps",
        "verified": False,
        "actual_improvement": -0.01,
    }

    tracker.update_state(state, 3, verification, now="2026-05-21T12:04:00")

    assert state["insights"]["total_hypotheses_tested"] == 1
    assert state["insights"]["hypotheses_disproved"] == 1
    assert state["disproved_hypotheses"][0]["patch_fingerprint"] == (
        "sw:holiday_features=True|np:create_lag_features:['lags']|gc:['ensemble_mode']"
    )


def test_update_chain_and_consecutive_type_count():
    tracker = AutoResearchHypothesisTracker()
    state = {
        "hypothesis_chain": [
            {"proposal_id": "prop-1", "status": "pending_verification"},
        ],
        "consecutive_type_count": {"parameter": 2, "feature": 0, "model": 0, "data": 0},
    }

    updated = tracker.update_chain(
        state,
        "prop-1",
        5,
        {"verified": True, "hypothesis": "ok"},
    )
    counts = tracker.update_consecutive_type_count(state, "feature")

    assert updated is True
    assert state["hypothesis_chain"][0]["status"] == "verified"
    assert state["hypothesis_chain"][0]["verified_iteration"] == 5
    assert counts == {"parameter": 0, "feature": 1, "model": 0, "data": 0}
