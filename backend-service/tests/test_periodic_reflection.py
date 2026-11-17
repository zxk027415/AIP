from services.periodic_reflection import PeriodicReflection


def test_reflection_trigger_interval_clamped_and_decision_shape():
    reflection = PeriodicReflection(reflection_interval=3)

    assert reflection.reflection_interval == 5
    assert reflection.should_trigger(5) is True
    assert reflection.should_trigger(4) is False

    run_state = {
        "iterations": [{"mape": 10.0}, {"mape": 10.0}, {"mape": 10.0}, {"mape": 10.0}, {"mape": 10.0}],
        "exploration_coverage": 0.4,
        "active_layers": ["feature"],
    }
    result = reflection.reflect(run_state, 5, target_mape=5.0)

    decision = result.reflection_decision.to_dict()
    assert result.improvement_trend == "stagnating"
    assert {"current_strategy", "status", "reason", "decision", "next_focus", "reset_type"} <= set(decision)
    assert decision["decision"] in {"continue_current", "shift_focus", "expand_registry", "early_stop"}


def test_shift_focus_writes_run_state_and_sampling_bias():
    reflection = PeriodicReflection(reflection_interval=5)
    run_state = {
        "iterations": [
            {"mape": 10.0, "direction": "feature.lag", "delta_mape": -0.1},
            {"mape": 10.0, "direction": "training.depth", "delta_mape": 0.1},
            {"mape": 10.0},
            {"mape": 10.0},
            {"mape": 10.0},
        ],
        "exploration_coverage": 0.2,
        "active_layers": ["feature", "training"],
    }

    result = reflection.reflect(run_state, 5)

    assert result.reflection_decision.decision == "shift_focus"
    assert "current_research_focus" in run_state
    assert reflection.sampling_weight_for_layer("feature", run_state) == 2.0
    assert reflection.sampling_weight_for_layer("training", run_state) == 0.5


def test_force_activate_for_inactive_priority_layer():
    reflection = PeriodicReflection(reflection_interval=5)
    run_state = {
        "iterations": [{"mape": 10.0} for _ in range(5)],
        "exploration_coverage": 0.2,
        "active_layers": [],
    }

    reflection.reflect(run_state, 5)

    assert "feature" in run_state["force_activate"]


def test_meta_warning_after_three_unadopted_reflections():
    reflection = PeriodicReflection(reflection_interval=5)
    run_state = {
        "iterations": [{"mape": 10.0} for _ in range(5)],
        "exploration_coverage": 0.2,
        "periodic_reflections": [{"adopted": False}, {"adopted": False}, {"adopted": False}],
    }

    result = reflection.reflect(run_state, 5)

    assert result.reflection_decision.meta_warning is not None
