import math

import pytest

from api import workflows_enhanced as wf


def test_canonical_json_key_normalizes_nan_values():
    left = wf._canonical_json_key({"x": float("nan"), "y": [1, math.inf]})
    right = wf._canonical_json_key({"y": [1, None], "x": None})

    assert left == right


@pytest.mark.asyncio
async def test_feature_recipe_intent_validates_and_applies_to_runtime_patch():
    recipe_id = "features_trim_calendar_v1"
    run_id = "test-run-feature-recipe"
    proposal_id = "test-prop-feature-recipe"

    translated = wf._translate_intent_to_patches(
        {"action": "add_feature_recipe", "recipe_id": recipe_id},
        "workflow-load-forecast-backtest-v2",
    )
    proposal = {
        "proposal_id": proposal_id,
        "run_id": run_id,
        "status": "pending_review",
        "search_space_patch": translated.get("search_space_patch") or {},
        "evaluation_contract_patch": {},
        "structure_patch": translated.get("structure_patch") or {},
        "global_config_patch": {},
        "node_param_patches": [],
        "feature_recipe_id": translated.get("feature_recipe_id"),
        "risk_level": "low",
    }

    validation = wf._validate_proposal_patch(
        proposal,
        baseline_workflow_id="workflow-load-forecast-backtest-v2",
    )
    assert validation["valid"] is True
    assert proposal["search_space_patch"]["feature_recipe_id"] == [recipe_id]
    assert len(proposal["structure_patch"]["node_switches"]) > 0

    wf._auto_research_store[run_id] = {
        "run_id": run_id,
        "baseline_workflow_id": "workflow-load-forecast-backtest-v2",
        "current_iteration": 1,
        "runtime_patch": {
            "search_space_patch": {},
            "evaluation_contract_patch": {},
            "structure_patch": {},
            "global_config_patch": {},
            "node_param_patches": [],
        },
    }
    wf._auto_research_proposals_store[proposal_id] = proposal
    try:
        result = await wf.apply_auto_research_proposal(proposal_id, {})
        runtime_patch = result["runtime_patch"]
        assert runtime_patch["feature_recipe_id"] == recipe_id
        assert runtime_patch["search_space_patch"]["feature_recipe_id"] == [recipe_id]
        assert len(runtime_patch["structure_patch"]["node_switches"]) > 0
    finally:
        wf._auto_research_store.pop(run_id, None)
        wf._auto_research_proposals_store.pop(proposal_id, None)


def test_experiment_quality_participates_in_proposal_score():
    base = {
        "validation": {"valid": True},
        "risk_level": "low",
        "search_space_patch": {"train_days": [30]},
        "evaluation_contract_patch": {},
        "structure_patch": {},
        "global_config_patch": {},
        "node_param_patches": [],
        "hypothesis": "因为训练窗口可能影响泛化，验证 train_days 是否改善 MAPE",
        "expected_outcome": {"metric": "mape_improvement", "threshold": 0.01},
        "llm_used": True,
    }
    high = dict(base)
    high["experiment_quality"] = {
        "composite_score": 0.9,
        "single_variable_control": 1.0,
    }
    low = dict(base)
    low["experiment_quality"] = {
        "composite_score": 0.2,
        "single_variable_control": 0.25,
    }

    assert wf._score_proposal_candidate(high) > wf._score_proposal_candidate(low)


def test_window_actuals_build_train_profile_and_pattern_mismatch():
    window_results = [
        {
            "challenger": {
                "daily_results": [
                    {
                        "date": "2026-04-04",
                        "status": "success",
                        "y_true": [200.0] * 96,
                        "y_pred": [210.0] * 96,
                    },
                    {
                        "date": "2026-04-05",
                        "status": "success",
                        "y_true": [200.0] * 96,
                        "y_pred": [210.0] * 96,
                    },
                    {
                        "date": "2026-04-06",
                        "status": "success",
                        "y_true": [100.0] * 96,
                        "y_pred": [120.0] * 96,
                    },
                ]
            }
        }
    ]

    train_profile = wf._build_train_profile_from_windows(window_results, train_fit_mape=5.0)
    test_profile = wf._build_test_profiles_from_windows(window_results)[-1]

    from services.dataset_profiler import DatasetProfiler

    diagnosis = DatasetProfiler().compute_tri_dataset_diagnosis(
        train_profile,
        validation_profile=None,
        test_profile=test_profile,
    )

    assert train_profile.dominant_pattern == "weekend_dominant"
    assert test_profile.day_type == "weekday"
    assert diagnosis.pattern_consistency["status"] == "pattern_mismatch"
