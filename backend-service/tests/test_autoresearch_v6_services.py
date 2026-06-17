import json
from pathlib import Path

from services.autoresearch_research_action import ProfileSignal, ResearchAction
from services.autoresearch_v6_services import PatchCompiler, ResearchActionPlanner


def _workflow():
    function_ids = [
        "auto_tune_xgboost",
        "create_lag_features",
        "rolling_statistics",
        "sliding_window",
        "ensemble_forecast",
        "load_csv",
        "holiday_features",
        "workday_features",
        "diff_features",
        "extract_statistical_features",
    ]
    return {
        "nodes": [
            {
                "id": f"node-{function_id}",
                "data": {"config": {"functionId": function_id}},
            }
            for function_id in function_ids
        ]
    }


def _v3_actions():
    root = Path(__file__).resolve().parents[1]
    path = root / "data" / "autoresearch_search_registries" / "load_forecast_v3.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ResearchAction.from_dict(item) for item in data["actions"]]


def _action(action_id):
    return next(action for action in _v3_actions() if action.action_id == action_id)


def test_v3_actions_compile_to_unique_variants():
    compiler = PatchCompiler()

    for action in _v3_actions():
        variants = compiler.expand_variants(action)
        fingerprints = [
            compiler.variant_fingerprint(action, item["variant_index"])
            for item in variants
        ]

        assert len(fingerprints) == len(set(fingerprints)), action.action_id
        assert all(fingerprints), action.action_id


def test_compile_runtime_patch_matches_main_loop_contract_for_node_and_switch():
    compiler = PatchCompiler()

    node_action = _action("ensemble_weight_strategy")
    node_patch = compiler.compile_runtime_patch(
        node_action,
        variant_index=0,
        workflow=_workflow(),
    )

    assert node_patch["node_param_patches"] == [
        {
            "node_id": "node-ensemble_forecast",
            "functionId": "ensemble_forecast",
            "param_patch": {"weight_mode": "upstream_oof_rmse"},
        }
    ]
    assert node_patch["structure_patch"] == {}

    switch_action = _action("calendar_feature_ablation")
    switch_patch = compiler.compile_runtime_patch(
        switch_action,
        variant_index=0,
        workflow=_workflow(),
    )

    assert switch_patch["node_param_patches"] == []
    assert switch_patch["structure_patch"]["node_switches"] == [
        {"node_id": "node-holiday_features", "functionId": "holiday_features", "enabled": True},
        {"node_id": "node-workday_features", "functionId": "workday_features", "enabled": True},
    ]


def test_compile_runtime_patch_keeps_model_focus_out_of_global_config():
    compiler = PatchCompiler()

    patch = compiler.compile_runtime_patch(
        _action("model_subset_focus"),
        variant_index=0,
        workflow=_workflow(),
    )

    assert patch["global_config_patch"] == {"ensemble_mode": "subset_adaptive"}
    assert patch["model_focus"] == ["xgboost_forecast", "lightgbm_forecast"]


def test_planner_does_not_commit_until_called():
    planner = ResearchActionPlanner()
    state = {}

    selected = planner.plan(
        questions=[{"target_direction": "model", "target_layer": "model", "priority": 1.0}],
        available_actions=_v3_actions(),
        profile_signal=ProfileSignal(noise_level="medium", data_length_days=90),
        evidence_records=[],
        candidate_pool=[],
        run_iterations=[],
        run_state=state,
        max_actions=3,
    )

    assert selected
    assert state == {}

    planner.commit_plan_result(state, selected[:1])

    assert list(state["action_tested_fingerprints"]) == [selected[0]["action_id"]]
    assert state["action_variant_cursor"][selected[0]["action_id"]] == selected[0]["variant_index"] + 1


def test_planner_uses_fallback_when_action_exhausted():
    planner = ResearchActionPlanner()
    compiler = PatchCompiler()
    actions = _v3_actions()
    short_window = _action("short_window_probe")
    tested = [
        compiler.variant_fingerprint(short_window, item["variant_index"])
        for item in compiler.expand_variants(short_window)
    ]
    state = {"action_tested_fingerprints": {"short_window_probe": tested}}

    selected = planner.plan(
        questions=[{"target_direction": "parameter", "target_layer": "training", "priority": 2.0}],
        available_actions=[short_window, _action("long_window_probe")],
        profile_signal=ProfileSignal(drift_strength=0.4, data_length_days=90),
        evidence_records=[],
        candidate_pool=[],
        run_iterations=[],
        run_state=state,
        max_actions=1,
    )

    assert len(selected) == 1
    assert selected[0]["action_id"] == "long_window_probe"
    assert "fallback from exhausted short_window_probe" in selected[0]["reason"]
