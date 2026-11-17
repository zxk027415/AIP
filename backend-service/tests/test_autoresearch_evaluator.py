from services.autoresearch_evaluator import AutoResearchEvaluator


def test_evaluator_computes_candidate_metrics_and_constraints():
    evaluator = AutoResearchEvaluator()
    compare_state = {
        "summary": {"score_advantage": 0.2},
        "window_results": [
            {
                "baseline": {"avg_metrics": {"avg_mape": 0.10}},
                "challenger": {
                    "avg_metrics": {"avg_mape": 0.08, "avg_rmse": 2.0, "avg_bias": 0.01, "avg_p95_ape": 0.12},
                    "total_duration": 1.5,
                },
            },
            {
                "baseline": {"avg_metrics": {"avg_mape": 0.12}},
                "challenger": {
                    "avg_metrics": {"avg_mape": 0.09, "avg_rmse": 3.0, "avg_bias": -0.01, "avg_p95_ape": 0.10},
                    "total_duration": 2.0,
                },
            },
        ],
    }

    result = evaluator.evaluate_candidate(compare_state, {"min_mape_improvement": 0.01, "max_abs_bias": 0.05})

    assert round(result["baseline_mape"], 6) == 0.11
    assert round(result["challenger_mape"], 6) == 0.085
    assert round(result["mape_improvement"], 6) == 0.025
    assert result["training_duration_s"] == 3.5
    assert result["meets_constraints"] is True


def test_evaluator_rank_key_prefers_meeting_constraints_and_lower_mape():
    evaluator = AutoResearchEvaluator()
    good = {"evaluation": {"meets_constraints": True, "challenger_mape": 0.08, "challenger_rmse": 2.0}}
    bad = {"evaluation": {"meets_constraints": False, "challenger_mape": 0.07, "challenger_rmse": 1.0}}

    assert evaluator.rank_key(good) < evaluator.rank_key(bad)


def test_evaluator_pareto_frontier_filters_dominated_candidates():
    evaluator = AutoResearchEvaluator()
    candidates = [
        {
            "status": "success",
            "evaluation": {
                "meets_constraints": True,
                "challenger_mape": 0.10,
                "challenger_rmse": 3.0,
                "training_duration_s": 5.0,
            },
        },
        {
            "status": "success",
            "evaluation": {
                "meets_constraints": True,
                "challenger_mape": 0.08,
                "challenger_rmse": 2.0,
                "training_duration_s": 4.0,
            },
        },
    ]

    frontier = evaluator.compute_pareto_frontier(candidates)

    assert len(frontier) == 1
    assert frontier[0]["evaluation"]["challenger_mape"] == 0.08

