# @AI_GENERATED
"""
Skill 执行脚本: collect 阶段
从数据源拉取数据 → 基线预测 → 故障注入 → 劣化预测 → 候选策略实跑评估
产出: artifacts/rca_input.json

用法（从 operation_skill/ 根目录运行）:
  conda run -n cp_web python scripts/run_collect.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保 skill 根目录在 path 中
_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.core.event_log import OperationEventLog
from scripts.core.metrics import evaluate_accuracy
from scripts.core.run_workspace import create_run_dir, get_active_run_info
from scripts.core.real_data import (
    DEFAULT_ASSET, DEFAULT_REGION,
    inject_fault_a,
    load_real_dataset,
    run_prediction_gap_strategy,
    generate_gap_strategies,
)
from typing import Any, Dict

DEGRADE_THRESHOLD = 90.0
RECOVERY_TARGET = 85.0
LOOP_ID = "loop_gap_fault_a_v1"
FAULT_DESC = "D-1(昨天)整天数据丢失"


def _unwrap(result: Dict[str, Any]) -> Any:
    if result["status"] != "ok":
        raise RuntimeError(result["error"])
    return result["data"]


def _metric(pred: Dict[str, Any]) -> Dict[str, Any]:
    m = _unwrap(evaluate_accuracy(pred["y_true"], pred["y_pred"]))
    return {
        "accuracy": m["accuracy"], "mape": m["mape"],
        "algorithm_version": pred["algorithm_version"],
        "prediction_id": pred["prediction_id"],
    }


def phase_collect(target_day: str | None = None) -> Dict[str, Any]:
    run_dir = create_run_dir(_SKILL_ROOT)
    event_log_path = run_dir / "operation_event_log.json"
    rca_input_path = run_dir / "rca_input.json"
    state_path = run_dir / "_loop_state.json"

    print(f"  运行目录: {run_dir}")
    print()

    log = OperationEventLog(event_log_path, LOOP_ID)

    # 1) 基线
    print("=" * 70)
    print("【步骤1】从数据源拉取真实数据")
    print("=" * 70)
    baseline_ds = _unwrap(load_real_dataset(region=DEFAULT_REGION, asset=DEFAULT_ASSET, target_day=target_day))
    print(f"  资产: {DEFAULT_REGION} / {DEFAULT_ASSET}")
    print(f"  预测目标日(D+1): {baseline_ds['meta']['target_day']}")
    print()

    print("=" * 70)
    print("【步骤2】基线预测(真·gap一天, lag→D-1)")
    print("=" * 70)
    baseline_pred = _unwrap(run_prediction_gap_strategy(baseline_ds, "baseline_gap1", "load_xgb_v1"))
    baseline_metric = _metric(baseline_pred)
    group_importance = baseline_pred.get("group_importance", {})
    print(f"  ★ 基线精度: {baseline_metric['accuracy']}%")
    print()

    log.append_event("monitor", "baseline", {
        **baseline_metric, "asset": DEFAULT_ASSET, "region": DEFAULT_REGION,
        "group_importance": group_importance,
        "mode": 1, "baseline_scenario": "baseline_gap1",
        "message": "真·gap一天基线预测稳定。",
    })

    # 2) 注入故障A
    print("=" * 70)
    print(f"【步骤3】注入故障: {FAULT_DESC}")
    print("=" * 70)
    degraded_ds = _unwrap(inject_fault_a(baseline_ds))
    meta_d = degraded_ds["meta"]
    print(f"  缺失区间: {meta_d['missing_start']} ~ {meta_d['missing_end']}")
    print()

    # 3) 劣化预测
    print("=" * 70)
    print("【步骤4】劣化预测")
    print("=" * 70)
    degraded_pred = _unwrap(run_prediction_gap_strategy(degraded_ds, "degraded_a", "load_xgb_v1_degraded"))
    degraded_metric = _metric(degraded_pred)
    drop = baseline_metric["accuracy"] - degraded_metric["accuracy"]
    print(f"  ★ 劣化精度: {degraded_metric['accuracy']}% (跌幅: {drop:.2f}pp)")
    print()

    log.append_event("monitor", "degradation", {
        **degraded_metric,
        "event_id": "evt_gap_fault_a_001",
        "threshold": DEGRADE_THRESHOLD,
        "baseline_accuracy": baseline_metric["accuracy"],
        "degraded_accuracy": degraded_metric["accuracy"],
        "message": meta_d["missing_description"],
    })

    # 4) 证据
    evidence = {
        "fault_type": "A",
        "missing_start": meta_d["missing_start"],
        "missing_end": meta_d["missing_end"],
        "missing_description": meta_d["missing_description"],
        "accuracy_drop": round(drop, 2),
        "baseline_accuracy": baseline_metric["accuracy"],
        "degraded_accuracy": degraded_metric["accuracy"],
        "group_importance_baseline": group_importance,
        "checked_items": ["原始负荷完整性", "缺失时间范围", "级联特征影响", "气象数据正常"],
    }

    # 5) 候选策略实跑评估
    print("=" * 70)
    print("【步骤5】候选策略实跑评估")
    print("=" * 70)

    def _evaluate(strategy_id: str) -> float:
        print(f"  评估中: {strategy_id} ...", end="", flush=True)
        pred = _unwrap(run_prediction_gap_strategy(degraded_ds, strategy_id, "load_xgb_eval"))
        acc = _metric(pred)["accuracy"]
        print(f" -> {acc}%")
        return acc

    strategies = _unwrap(generate_gap_strategies("A", evaluator=_evaluate))
    print()

    # 写 RCA 输入
    rca_input = {
        "loop_id": LOOP_ID,
        "asset": DEFAULT_ASSET,
        "fault_type": "A",
        "baseline_accuracy": baseline_metric["accuracy"],
        "degraded_accuracy": degraded_metric["accuracy"],
        "recovery_target": RECOVERY_TARGET,
        "evidence": evidence,
        "candidate_strategies": strategies,
        "instructions_for_kiro": (
            "请基于 evidence 做根因推理(故障A: D-1整天丢失),并结合 candidate_strategies 的实测精度选择最终恢复策略;"
            "将结论写入同目录 rca_decision.json。"
        ),
        "decision_schema": {
            "rca": {"analyzer": "kiro_llm", "root_cause": "str", "confidence": "0..1",
                    "reasoning": "str", "supporting_evidence": ["str"], "undetermined": "bool"},
            "strategy": {"selected_strategy_id": "str", "decision_reasoning": "str"},
        },
    }
    rca_input_path.write_text(json.dumps(rca_input, ensure_ascii=False, indent=2), encoding="utf-8")

    ds_meta = baseline_ds.get("meta", {})
    meta_d = degraded_ds.get("meta", {})

    # 状态
    state = {
        "run_dir": str(run_dir),
        "baseline_metric": baseline_metric,
        "degraded_metric": degraded_metric,
        "group_importance": group_importance,
        "evidence": evidence,
        "candidate_strategies": strategies,
        "degraded_dataset": degraded_ds,
        "baseline_pred": {
            "y_true": baseline_pred["y_true"],
            "y_pred": baseline_pred["y_pred"],
        },
        "degraded_pred": {
            "y_true": degraded_pred["y_true"],
            "y_pred": degraded_pred["y_pred"],
        },
        "dataset_meta": {
            "target_day": ds_meta.get("target_day"),
            "d_minus_1": meta_d.get("missing_start", "")[:10],
            "gap_day": meta_d.get("missing_end", "")[:10],
        },
        "events_written_in_collect": len(log.events),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    run_info = get_active_run_info(_SKILL_ROOT)

    print("=" * 70)
    print("【Collect 完成】")
    result = {
        "phase": "collect",
        "run_dir": str(run_dir),
        "baseline_accuracy": baseline_metric["accuracy"],
        "degraded_accuracy": degraded_metric["accuracy"],
        "candidate_evaluations": {s["strategy_id"]: s["expected_accuracy"] for s in strategies},
        "rca_input_path": str(rca_input_path),
        "rca_decision_path": str(run_dir / "rca_decision.json"),
        "report_file": run_info.get("report_file"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 70)
    print(f"\n→ 下一步: Agent 读取 {rca_input_path} 进行推理，写入 {run_dir / 'rca_decision.json'}")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="collect 阶段：基线→故障注入→劣化→候选策略实跑评估")
    parser.add_argument(
        "--target-day", default="2026-05-24",
        help="事故日(D+1, 预测目标日)，如 2026-05-24。缺失日为其 D-1(05-22)。默认 2026-05-24。",
    )
    args = parser.parse_args()
    phase_collect(target_day=args.target_day)
# @AI_GENERATED: end
