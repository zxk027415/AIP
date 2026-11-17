import ast
from pathlib import Path

from services.autoresearch_batch_selector import AutoResearchBatchSelector
from api.workflows_enhanced import (
    _build_autoresearch_batch_group_record,
    _force_override_diff_from_contract,
    _sample_override_from_search_space_patch,
)


def test_batch_best_selects_successful_non_main_group():
    rows = [
        {
            "group_idx": 0,
            "comparison_id": "cmp-main",
            "override": {"train_days": 30},
            "state": {"status": "failed", "error": "group0 failed"},
        },
        {
            "group_idx": 1,
            "comparison_id": "cmp-b",
            "override": {"train_days": 45},
            "state": {"status": "success", "summary": {"score_advantage": 0.12}},
        },
        {
            "group_idx": 2,
            "comparison_id": "cmp-c",
            "override": {"train_days": 60},
            "state": {"status": "success", "summary": {"score_advantage": 0.08}},
        },
    ]

    best = AutoResearchBatchSelector().select_best_successful(rows)

    assert best is rows[1]
    assert rows[0]["state"]["status"] == "failed"


def test_batch_best_returns_none_when_all_groups_failed():
    rows = [
        {"group_idx": 0, "state": {"status": "failed"}},
        {"group_idx": 1, "state": {"status": "error"}},
    ]

    assert AutoResearchBatchSelector().select_best_successful(rows) is None


def test_batch_best_ignores_success_without_comparable_windows():
    rows = [
        {
            "group_idx": 0,
            "state": {
                "status": "success",
                "summary": {"score_advantage": 9.9, "windows_comparable": 0},
            },
        },
        {
            "group_idx": 1,
            "state": {
                "status": "success",
                "summary": {"score_advantage": 0.2, "windows_comparable": 1},
            },
        },
    ]

    assert AutoResearchBatchSelector().select_best_successful(rows) is rows[1]


def test_batch_group_record_builds_applied_patch_fingerprint():
    record = _build_autoresearch_batch_group_record(
        iteration=1,
        group_idx=0,
        comparison_id="cmp-main",
        override={"train_days": 45},
        compare_state={
            "status": "success",
            "summary": {
                "score_advantage": 0.12,
                "baseline_mape": 4.8,
                "challenger_mape": 4.2,
            },
            "total_duration": 3.5,
        },
        policy={},
        group_spec={
            "candidate_source": "candidate_planner",
            "selected_layer": "training",
            "target_direction": "parameter",
            "structure_patch": {"enabled_node_ids": ["xgb"]},
            "global_config_patch": {"sliding_window.step": 1},
            "node_param_patches": [{"node_id": "xgb", "params": {"max_depth": 5}}],
        },
        is_best=True,
        is_primary=True,
        runtime_patch_snapshot={},
        effective_search_space={},
        effective_evaluation_contract={},
    )

    assert record["status"] == "success"
    assert record["candidate_source"] == "candidate_planner"
    assert record["applied_patch_fingerprint"]


def test_batch_group_record_marks_no_comparable_success_as_failed():
    record = _build_autoresearch_batch_group_record(
        iteration=1,
        group_idx=1,
        comparison_id="cmp-feature",
        override={"train_days": 30},
        compare_state={
            "status": "success",
            "summary": {"windows_comparable": 0, "failure_reason": "no_comparable_windows"},
        },
        policy={},
        group_spec={"target_direction": "feature", "selected_layer": "feature"},
        is_best=False,
        is_primary=False,
        runtime_patch_snapshot={},
        effective_search_space={},
        effective_evaluation_contract={},
    )

    assert record["status"] == "failed"
    assert record["failure_reason"] == "no_comparable_windows"


def test_search_space_patch_arrays_become_scalar_override():
    override = _sample_override_from_search_space_patch(
        {"train_days": [16, 30, 44], "backtest_train_days": [16, 30, 44], "feature_recipe_id": ["r1"]},
        iteration=2,
        seed=1,
    )

    assert isinstance(override["train_days"], int)
    assert "backtest_train_days" not in override
    assert "feature_recipe_id" not in override


def test_force_override_treats_added_key_as_difference():
    override = _force_override_diff_from_contract(
        override={"ensemble_mode": "all_adaptive"},
        search_space={"train_days": [30, 60, 90]},
        contract={"train_days": 30},
        iteration=1,
        seed=1,
    )

    assert override == {"ensemble_mode": "all_adaptive"}


def test_workflows_enhanced_has_no_duplicate_module_functions():
    source_path = Path(__file__).resolve().parents[1] / "api" / "workflows_enhanced.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    seen = {}
    duplicates = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in seen:
                duplicates.append((node.name, seen[node.name], node.lineno))
            else:
                seen[node.name] = node.lineno

    assert duplicates == []
