# @AI_GENERATED
"""experiment_patch 归一化 + 应用到工作流 dict 的单元测试。"""
from __future__ import annotations

from services.deployment.experiment_patch import (
    apply_experiment_patch_to_workflow_dict,
    experiment_patch_fingerprint,
    normalize_experiment_patch,
)


def test_normalize_from_candidate_aliases():
    raw = {
        "challenger_override": {"train_days": 90, "ensemble_mode": "all_adaptive"},
        "effective_parameter_patch": {"backtest_bo_n_iter": 24},
        "effective_structure_patch": {
            "node_switches": [{"node_id": "n1", "enabled": False, "functionId": "lag_features"}]
        },
        "node_param_patches": [
            {"node_id": "n2", "functionId": "xgboost_forecast", "param_patch": {"n_estimators": 400}}
        ],
    }
    patch = normalize_experiment_patch(raw)
    assert patch["challenger_override"]["train_days"] == 90
    assert patch["effective_parameter_patch"]["backtest_bo_n_iter"] == 24
    assert patch["effective_structure_patch"]["node_switches"][0]["enabled"] is False
    assert patch["node_param_patches"][0]["param_patch"]["n_estimators"] == 400
    assert experiment_patch_fingerprint(patch) != "nopatch"


def test_apply_structure_switch_and_global_config_fallback():
    wf = {
        "id": "wf-test",
        "name": "t",
        "nodes": [
            {
                "id": "n1",
                "data": {"config": {"functionId": "lag_features", "enabled": True}},
            },
            {
                "id": "n2",
                "data": {"config": {"functionId": "xgboost_forecast", "n_estimators": 120}},
            },
        ],
        "edges": [],
        "metadata": {"global_config": {"backtest_train_days": 30}},
    }
    patch = {
        "challenger_override": {"train_days": 90},
        "effective_parameter_patch": {},
        "effective_structure_patch": {
            "node_switches": [{"node_id": "n1", "enabled": False, "functionId": "lag_features"}]
        },
        "node_param_patches": [
            {"node_id": "n2", "param_patch": {"n_estimators": 400}}
        ],
    }
    out = apply_experiment_patch_to_workflow_dict(wf, patch)
    # 结构开关：若 AR 白名单 apply 失败则走 dict 回退，也应关掉 n1
    n1 = next(n for n in out["nodes"] if n["id"] == "n1")
    assert n1["data"]["config"]["enabled"] is False
    # train_days → backtest_train_days
    gc = (out.get("metadata") or {}).get("global_config") or {}
    assert int(gc.get("backtest_train_days") or 0) == 90
# @AI_GENERATED: end
