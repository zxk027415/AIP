from services.autoresearch_insight_builder import AutoResearchInsightBuilder


def test_insight_builder_summarizes_run_state():
    builder = AutoResearchInsightBuilder()
    state = {
        "baseline_workflow_id": "wf-base",
        "registry_id": "reg-1",
        "iterations": [
            {
                "iteration": 1,
                "status": "success",
                "sampled_layers": ["feature"],
                "evaluation": {"mape_improvement": 0.1},
                "error_profile": {"weekend_vs_weekday_gap": 0.2},
            },
            {
                "iteration": 2,
                "status": "failed",
                "error": "boom",
                "sampled_layers": ["model"],
            },
        ],
        "insights": {
            "total_hypotheses_tested": 2,
            "hypotheses_verified": 1,
            "hypotheses_disproved": 1,
            "effective_directions": ["feature works"],
        },
        "disproved_hypotheses": [
            {"hypothesis": "bad idea", "iteration": 2, "actual_result": -0.1},
        ],
        "best_candidate": {
            "evaluation": {"mape_improvement": 0.1},
            "override": {"train_days": 30},
            "global_config_patch": {"ensemble_mode": "all_adaptive"},
        },
    }

    insight = builder.build(
        "ares-1",
        state,
        scenario_fingerprint={"granularity": "daily", "span_days": 30, "anomaly_ratio": 0.05},
        created_at="2026-05-21T12:05:00",
    )

    assert insight["run_id"] == "ares-1"
    assert insight["baseline_workflow_id"] == "wf-base"
    assert insight["data_profile"]["granularity_minutes"] == 15
    assert insight["data_profile"]["weekend_weekday_gap"] == 0.2
    assert insight["exploration_summary"]["success_iterations"] == 1
    assert insight["exploration_summary"]["improved_iterations"] == 1
    assert insight["error_diagnostics"][0]["error"] == "boom"
    assert insight["learned_rules"] == ["feature works"]
    assert insight["recommended_starting_config_for_similar"]["train_days"] == 30
