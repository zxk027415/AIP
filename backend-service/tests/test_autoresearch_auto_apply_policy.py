from services.autoresearch_auto_apply_policy import AutoResearchAutoApplyPolicy


def test_build_latest_auto_proposal_sets_skip_reason_for_risk_threshold():
    policy = AutoResearchAutoApplyPolicy()
    proposal = {
        "validation": {"valid": True, "errors": []},
        "risk_level": "medium",
        "hypothesis": "try wider search",
        "observation": "plateau",
        "notes": ["medium-risk structural change"],
    }

    latest = policy.build_latest_auto_proposal(
        auto_pack={"generated_count": 2, "glm_input_debug": {"k": 1}},
        recommended_id="p1",
        proposal=proposal,
        auto_apply=True,
        risk_max="low",
        duration_s=1.2,
        generated_at="2026-05-21T00:00:00",
    )

    assert latest["recommended_valid"] is True
    assert latest["recommended_risk"] == "medium"
    assert latest["skip_apply_reason"] == "risk_exceeds_threshold"
    assert latest["hypothesis"] == "try wider search"
    assert latest["rationale"] == "medium-risk structural change"


def test_append_history_caps_recent_items_and_mark_applied_resets_skips():
    policy = AutoResearchAutoApplyPolicy()
    state = {"_consecutive_proposal_skips": 2}
    latest = {
        "duration_s": 0.1,
        "generated_count": 1,
        "recommended_proposal_id": "p1",
        "recommended_valid": True,
        "recommended_risk": "low",
        "auto_apply_risk_level_max": "low",
        "skip_apply_reason": None,
    }

    for i in range(35):
        policy.append_history(state, iteration=i, latest=latest, called_at=f"t{i}")
    policy.mark_latest_applied(state)

    assert len(state["glm_call_history"]) == 30
    assert state["glm_call_history"][0]["iteration"] == 5
    assert state["glm_call_history"][-1]["applied"] is True
    assert state["_consecutive_proposal_skips"] == 0


def test_record_blocked_application_escalates_after_three_low_risk_blocks():
    policy = AutoResearchAutoApplyPolicy()
    state = {"_consecutive_proposal_skips": 2}

    result = policy.record_blocked_application(state, risk_max="low")

    assert result == {"skip_count": 3, "risk_max": "medium", "escalated": True}
    assert state["_auto_escalated_risk_max"] is True


def test_enrich_history_infers_missing_validation_fields():
    policy = AutoResearchAutoApplyPolicy()
    history = [{"recommended_id": "p1", "applied": False}]
    proposals = {
        "p1": {
            "validation": {"valid": False, "errors": ["bad patch"]},
            "risk_level": "low",
        }
    }

    enriched = policy.enrich_history(
        history,
        proposals=proposals,
        risk_max="low",
        auto_apply=True,
    )

    assert enriched == [{
        "recommended_id": "p1",
        "applied": False,
        "recommended_valid": False,
        "recommended_risk": "low",
        "auto_apply_risk_level_max": "low",
        "validation_errors": ["bad patch"],
        "skip_apply_reason": "validator_failed",
    }]
