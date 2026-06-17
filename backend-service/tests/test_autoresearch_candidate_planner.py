from services.autoresearch_candidate_planner import AutoResearchCandidatePlanner


def test_candidate_planner_batch_three_roles_and_rotating_directions():
    planner = AutoResearchCandidatePlanner()

    slots = planner.build_slots(batch_size=3, iteration=1, run_state={}, active_layers=["training", "feature", "model", "data"])

    assert [slot["exploration_role"] for slot in slots] == ["exploit", "diversify", "explore_risk"]
    assert slots[0]["target_direction"] == "parameter"
    assert slots[1]["target_direction"] in {"feature", "model"}
    assert slots[2]["target_direction"] in {"data", "risk"}
    assert all(slot["planner_reason"] for slot in slots)


def test_candidate_planner_batch_five_covers_all_directions():
    slots = AutoResearchCandidatePlanner().build_slots(batch_size=5, iteration=3, run_state={})

    assert [slot["target_direction"] for slot in slots] == ["parameter", "feature", "model", "data", "risk"]


def test_candidate_planner_prefers_coverage_gap_for_second_slot():
    run_state = {
        "latest_batch_groups": [
            {"target_direction": "feature", "status": "success", "score_advantage": 0.1},
            {"target_direction": "model", "status": "success", "score_advantage": 0.2},
            {"target_direction": "data", "status": "success", "score_advantage": 0.3},
            {"target_direction": "feature", "status": "success", "score_advantage": 0.4},
        ]
    }

    slots = AutoResearchCandidatePlanner().build_slots(batch_size=2, iteration=2, run_state=run_state)

    assert slots[1]["target_direction"] == "risk"


def test_candidate_planner_timeout_penalizes_but_does_not_disable_direction():
    run_state = {
        "latest_batch_groups": [
            {"target_direction": "risk", "status": "failed", "error": "batch_eval_timeout"},
            {"target_direction": "feature", "status": "success", "score_advantage": 0.1},
        ]
    }

    planner = AutoResearchCandidatePlanner()
    scoreboard = planner.build_scoreboard(run_state)
    slots = planner.build_slots(batch_size=5, iteration=5, run_state=run_state)

    assert scoreboard["risk"]["timeout_count"] == 1
    assert "risk" in [slot["target_direction"] for slot in slots]


def test_candidate_planner_avoids_timed_out_directions_when_alternatives_exist():
    run_state = {
        "latest_batch_groups": [
            {"target_direction": "model", "status": "failed", "error": "batch_eval_timeout"},
            {"target_direction": "risk", "status": "failed", "error": "batch_eval_timeout"},
        ]
    }

    slots = AutoResearchCandidatePlanner().build_slots(batch_size=3, iteration=2, run_state=run_state)

    assert [slot["target_direction"] for slot in slots] == ["parameter", "feature", "data"]


def test_exploration_health_exposes_p07_control_fields():
    run_state = {
        "latest_auto_proposal": {"glm_meta": {"candidates_count": 0, "memory_hit_count": 1}},
        "iterations": [
            {"iteration": 1, "batch_groups": [{"group_idx": 0, "target_direction": "parameter", "status": "success", "mape_improvement": -0.1}]},
            {"iteration": 2, "batch_groups": [{"group_idx": 0, "target_direction": "parameter", "status": "success", "mape_improvement": -0.2}]},
            {"iteration": 3, "batch_groups": [{"group_idx": 0, "target_direction": "parameter", "status": "success", "mape_improvement": -0.3}]},
            {"iteration": 4, "batch_groups": [{"group_idx": 0, "target_direction": "parameter", "status": "success", "mape_improvement": -0.4}]},
        ],
    }

    health = AutoResearchCandidatePlanner().exploration_health(run_state, active_layers=["training", "feature", "model"])

    assert health["parameter_overdominance"] is True
    assert health["recommended_primary_direction"] in {"feature", "model", "data", "risk"}
    assert health["direction_coverage"]["parameter"] == 1.0
    assert health["ineffective_count"] >= 4
    assert health["llm_used"] is False
    assert health["proposal_source"] == "memory"
