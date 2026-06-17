from services.agent_orchestrator import AgentOrchestrator, DesignerAgent, HypothesisDeduplicator, PatchFingerprint
from services.dataset_profiler_models import CrossWindowPattern, TestProfile, TrainProfile, TriDatasetDiagnosis


def test_patch_fingerprint_rejects_disproved_patch():
    patch = {"target_function_id": "feature", "param_key": "lags", "direction": "increase"}
    fp = PatchFingerprint.from_patch(patch).to_key()
    dedup = HypothesisDeduplicator([fp])

    assert dedup.is_disproved(patch) is True
    assert dedup.filter_patches([patch]) == []
    assert dedup.filter_patches([{"target_function_id": "feature", "param_key": "window", "direction": "increase"}])


def test_designer_agent_translates_structured_intent_and_falls_back_empty():
    designer = DesignerAgent()

    assert designer.translate({"target_function_id": "feature", "param_key": "lags", "value": [96]}) == [
        {"target_function_id": "feature", "param_key": "lags", "direction": "set", "value": [96]}
    ]
    assert designer.translate({"param_key": "lags"}) == []


def test_designer_agent_translates_proposal_like_candidate():
    designer = DesignerAgent()

    patches = designer.translate(
        {
            "global_config_patch": {"ensemble_mode": "all_adaptive"},
            "node_param_patches": [
                {
                    "node_id": "n1",
                    "functionId": "rolling_statistics",
                    "param_patch": {"window_sizes": [4, 8, 24]},
                }
            ],
        }
    )

    assert {"target_function_id": "global_config_patch", "param_key": "ensemble_mode", "direction": "set", "value": "all_adaptive"} in patches
    assert {
        "target_function_id": "rolling_statistics",
        "param_key": "window_sizes",
        "direction": "set",
        "value": [4, 8, 24],
    } in patches


def test_orchestrator_multi_agent_records_traces():
    train = TrainProfile({}, {}, {}, {}, {}, "weekday_dominant", 0.2, 4.0)
    test = TestProfile(
        [],
        10.0,
        1.0,
        {},
        {"morning_peak": 20.0, "midday": 1.0, "evening_peak": 1.0, "night": 1.0, "worst_period": "morning_peak"},
        0.0,
        0.0,
        False,
        "weekday",
    )
    diagnosis = TriDatasetDiagnosis({"status": "consistent"}, "confirmed_overfit", "poor", "x")
    cross = CrossWindowPattern("increasing", {"worst_periods": ["morning_peak"] * 3}, 1.0)

    orchestrator = AgentOrchestrator(
        "multi_agent",
        glm_generate=lambda _: [{"target_function_id": "feature", "param_key": "lags", "direction": "increase"}],
    )
    run_state = {}
    result = orchestrator.run_pipeline(
        {
            "train_profile": train,
            "test_profile": test,
            "tri_dataset_diagnosis": diagnosis,
            "cross_window_pattern": cross,
        },
        run_state,
    )

    assert result["mode"] == "multi_agent"
    assert result["patches"]
    assert run_state["agent_traces"]


def test_orchestrator_falls_back_to_single_agent_on_error():
    orchestrator = AgentOrchestrator(
        "multi_agent",
        glm_generate=lambda _: [{"target_function_id": "feature", "param_key": "lags"}],
    )
    run_state = {}

    result = orchestrator.run_pipeline({}, run_state)

    assert result["mode"] == "single_agent"
    assert any(x["message_type"] == "fallback" for x in run_state["agent_traces"])
