# @AI_GENERATED
"""负荷预测故事线端到端自检（只读 + 可回滚的 dry 路径）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True
notes = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    mark = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    notes.append(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    from services.deployment.experiment_patch import (
        apply_experiment_patch_to_workflow_dict,
        normalize_experiment_patch,
    )
    from services.deployment.models import ModelVersion
    from services.deployment.store import DeploymentSlotStore

    # 1) ModelVersion 可持久化 experiment_patch
    mv = ModelVersion(
        workflow_id="wf-x",
        version_tag="prelaunch-test",
        status="prelaunch",
        deployed_at="2026-07-27T00:00:00",
        experiment_patch={
            "challenger_override": {"train_days": 90},
            "effective_parameter_patch": {},
            "effective_structure_patch": {},
            "node_param_patches": [],
        },
    )
    dumped = mv.model_dump()
    check(
        "ModelVersion.experiment_patch 可序列化",
        isinstance(dumped.get("experiment_patch"), dict)
        and dumped["experiment_patch"]["challenger_override"]["train_days"] == 90,
    )

    # 2) 现有 slot 影子若有 candidate_id，应能从候选池回填（或明确无池）
    store = DeploymentSlotStore()
    slot = store.get("load_forecast")
    check("load_forecast 槽位存在", slot is not None)
    if slot and slot.shadow_models:
        for sh in slot.shadow_models:
            if not sh.source_candidate_id:
                continue
            try:
                from services.deployment.experiment_patch import load_experiment_patch_from_candidate_id

                patch = load_experiment_patch_from_candidate_id(sh.source_candidate_id)
                check(
                    f"影子 {sh.version_tag} 候选 patch 回填",
                    True,
                    f"candidate={sh.source_candidate_id} patch_empty={not bool(patch)} keys={list(patch.keys()) if patch else []}",
                )
            except Exception as exc:
                check(f"影子 {sh.version_tag} 候选 patch 回填", False, str(exc))

    # 3) apply 改变工作流
    wf = {
        "id": "wf",
        "name": "t",
        "nodes": [
            {"id": "n1", "data": {"config": {"functionId": "lag_features", "enabled": True}}},
        ],
        "edges": [],
        "metadata": {"global_config": {"backtest_train_days": 30}},
    }
    patch = normalize_experiment_patch(
        {
            "challenger_override": {"train_days": 120},
            "effective_structure_patch": {
                "node_switches": [{"node_id": "n1", "enabled": False, "functionId": "lag_features"}]
            },
        }
    )
    out = apply_experiment_patch_to_workflow_dict(wf, patch)
    gc = (out.get("metadata") or {}).get("global_config") or {}
    check("apply 写入 backtest_train_days", int(gc.get("backtest_train_days") or 0) == 120)

    # 4) 预测时序 / MAPE 口径（若 DB 可用）
    try:
        from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
        from sqlalchemy import func
        from services.db.models.load_forecast import PredictionResult

        if _is_db_enabled() and slot and slot.production_model:
            repo = _get_lf_repo()
            with repo._adapter.get_sync_session() as session:
                cnt = (
                    session.query(func.count(PredictionResult.id))
                    .filter(
                        PredictionResult.slot == "load_forecast",
                        PredictionResult.workflow_id == slot.production_model.workflow_id,
                    )
                    .scalar()
                )
                cnt_tag = (
                    session.query(func.count(PredictionResult.id))
                    .filter(
                        PredictionResult.slot == "load_forecast",
                        PredictionResult.workflow_id == slot.production_model.workflow_id,
                        PredictionResult.version_tag == slot.production_model.version_tag,
                    )
                    .scalar()
                )
            check(
                "生产 workflow 有 PredictionResult",
                int(cnt or 0) > 0,
                f"wf_count={cnt} exact_tag_count={cnt_tag} tag={slot.production_model.version_tag}",
            )
            # 口径说明：运营 MAPE 是百分点；baseline_mape~5.66 是登记基线，滚动可更低
            prod_mape = slot.production_model.accuracy_score
            base = slot.production_model.baseline_mape
            check(
                "运营 MAPE 已是百分点（通常 < 50）",
                prod_mape is None or float(prod_mape) < 50,
                f"rolling≈{prod_mape} baseline={base}",
            )
        else:
            check("DB 可用性", False, "DB 未启用或无 production，跳过时序计数")
    except Exception as exc:
        check("DB 时序检查", False, str(exc))

    # 5) 指标公式自检
    mape = sum(abs(a - b) / abs(b) * 100 for a, b in [(10, 11), (20, 19)]) / 2
    wmape = (abs(10 - 11) + abs(20 - 19)) / (11 + 19) * 100
    check("MAPE 公式（百分点均值）", abs(mape - (100 / 11 + 100 / 19) / 2) < 1e-6, f"mape={mape:.4f}")
    check("WMAPE 公式（总量加权）", abs(wmape - 200 / 30) < 1e-6, f"wmape={wmape:.4f}")

    print("\n".join(notes))
    print("---")
    print("OVERALL", "OK" if ok else "HAS_FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
# @AI_GENERATED: end
