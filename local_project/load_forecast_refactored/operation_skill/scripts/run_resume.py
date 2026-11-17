# @AI_GENERATED
"""
Skill 执行脚本: resume 阶段
读取 rca_decision.json → 校验 → 执行恢复策略 → 验证 → 对比 → CoE → 完成闭环

前置条件:
  1. 已完成 collect 阶段
  2. Agent 已写入 artifacts/rca_decision.json

用法（从 operation_skill/ 根目录运行）:
  conda run -n cp_web python scripts/run_resume.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd

# 确保 skill 根目录在 path 中
_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.core.event_log import OperationEventLog
from scripts.core.metrics import evaluate_accuracy
from scripts.core.comparison import build_comparison
from scripts.core.real_data import (
    _GAP_STRATEGY_META,
    run_prediction_gap_strategy,
    select_gap_strategy,
    execute_gap_strategy,
    compute_real_timeline,
)
from scripts.core.models import OperationEvent
from scripts.core.html_report import build_chart_curves, write_html_report
from scripts.core.run_workspace import finalize_loop_result, get_active_run_dir, get_active_run_info

RECOVERY_TARGET = 85.0
RCA_CONFIDENCE_THRESHOLD = 0.6
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


def _fallback_rca(evidence: Dict[str, Any]) -> Dict[str, Any]:
    drop = evidence.get("accuracy_drop", 0.0)
    if drop > 1.0:
        confidence = round(max(0.6, min(0.95, 0.6 + min(drop, 30) * 0.011)), 2)
        root_cause = f"D-1 整天负荷数据丢失,gap一天基线的 lag_1d(→D-1) 全 NaN,精度下降 {drop:.2f}pp"
        return {
            "analyzer": "fallback_rule",
            "root_cause": root_cause,
            "confidence": confidence,
            "supporting_evidence": [
                f"故障类型: {evidence.get('missing_description', 'A')}",
                f"精度下降: {drop:.2f}pp",
                "级联影响: lag/rolling 部分 NaN",
            ],
            "checked_items": ["原始负荷完整性", "缺失时间范围", "级联特征影响"],
            "undetermined": False,
        }
    return {
        "analyzer": "fallback_rule", "root_cause": "根因未确定", "confidence": 0.0,
        "supporting_evidence": [], "checked_items": [], "undetermined": True,
    }


def _coe_builder(selected: Dict[str, Any], recovered_metric: Dict[str, Any],
                 baseline_metric: Dict[str, Any]) -> Dict[str, Any]:
    residual = round(baseline_metric["accuracy"] - recovered_metric["accuracy"], 2)
    return {
        "advice_id": "coe_gap_fault_a_001",
        "summary": f"{FAULT_DESC},Agent 通过「{selected['name']}」恢复至 {recovered_metric['accuracy']}%{'(超越基线)' if residual < 0 else f'(距基线差 {residual}pp)'}。",
        "rationale": "原始负荷丢失级联影响 lag/rolling。恢复策略的选择取决于故障发生在哪天、丢了多少、预测值质量如何。",
        "risks": "预测值回填引入代理误差;多 gap 丢失近期信息。需根据实测精度决策。",
        "prevention": "建立负荷采集多通道冗余;设置入库超时告警;预置 gap 降级预案。",
    }


def phase_resume() -> Dict[str, Any]:
    run_dir = get_active_run_dir(_SKILL_ROOT)
    run_info = get_active_run_info(_SKILL_ROOT)
    event_log_path = run_dir / "operation_event_log.json"
    rca_decision_path = run_dir / "rca_decision.json"
    state_path = run_dir / "_loop_state.json"

    if not state_path.exists():
        raise FileNotFoundError(f"缺少 {state_path},请先运行 run_collect.py")
    state = json.loads(state_path.read_text(encoding="utf-8"))

    baseline_metric = state["baseline_metric"]
    degraded_metric = state["degraded_metric"]
    evidence = state["evidence"]
    candidates = state["candidate_strategies"]
    degraded_ds = state["degraded_dataset"]
    candidate_ids = [s["strategy_id"] for s in candidates]

    log = OperationEventLog(event_log_path, LOOP_ID)
    prefix_count = int(state.get("events_written_in_collect", 0))
    if event_log_path.exists():
        data = json.loads(event_log_path.read_text(encoding="utf-8"))
        all_events = []
        for e in data.get("events", []):
            all_events.append(OperationEvent(loop_id=e["loop_id"], stage=e["stage"],
                                             type=e["type"], payload=e["payload"], ts=e["ts"]))
        log.events = all_events[:prefix_count]
        log.write_json()

    # 决策来源
    decision = None
    degrade_reason = None
    if rca_decision_path.exists():
        decision = json.loads(rca_decision_path.read_text(encoding="utf-8"))
        rca = decision.get("rca") or {}
        if rca.get("analyzer") != "kiro_llm":
            degrade_reason = "analyzer 非 kiro_llm"
        elif rca.get("undetermined"):
            degrade_reason = "根因未确定"
        elif float(rca.get("confidence", 0.0)) < RCA_CONFIDENCE_THRESHOLD:
            degrade_reason = "置信度不足"
        else:
            strat = decision.get("strategy") or {}
            if strat.get("selected_strategy_id") not in candidate_ids:
                degrade_reason = "策略 id 不在候选集"
    else:
        degrade_reason = "未找到 rca_decision.json"

    if decision is not None and degrade_reason is None:
        rca_payload = dict(decision["rca"])
        rca_payload["analyzer"] = "kiro_llm"
        selected_id = decision["strategy"]["selected_strategy_id"]
        strategy_reasoning = decision["strategy"].get("decision_reasoning", "")
        rca_source = "kiro_llm"
        print(f"  ✓ 使用 Agent 决策: {selected_id}")
    else:
        rca_payload = _fallback_rca(evidence)
        sel = _unwrap(select_gap_strategy([dict(s) for s in candidates]))
        selected_id = sel["selected_strategy"]["strategy_id"]
        strategy_reasoning = f"(规则兜底)实测最高精度择优;降级原因:{degrade_reason}"
        rca_source = "fallback_rule"
        print(f"  ⚠ 降级到规则兜底: {degrade_reason}")

    rca_payload["evidence"] = evidence
    log.append_event("rca", "rca", rca_payload)

    # 策略
    evals = [dict(s) for s in candidates]
    for s in evals:
        s["selected"] = s["strategy_id"] == selected_id
    selected_strategy = next(s for s in evals if s["strategy_id"] == selected_id)
    log.append_event("strategy", "strategy", {
        "evaluations": evals, "selected_strategy": selected_strategy,
        "decision_reasoning": strategy_reasoning,
    })

    # 执行
    exec_payload = _unwrap(execute_gap_strategy(selected_id, degraded_ds))
    execution = exec_payload["execution"]
    log.append_event("execute", "execution", execution)

    # 验证
    recovered_pred = _unwrap(run_prediction_gap_strategy(
        degraded_ds, selected_id, execution["new_algorithm_version"]
    ))
    recovered_metric = _metric(recovered_pred)
    recovered = recovered_metric["accuracy"] >= RECOVERY_TARGET
    log.append_event("verify", "verification", {
        **recovered_metric, "recovered": recovered, "recovery_target": RECOVERY_TARGET,
    })

    # 对比 + CoE
    comparison = _unwrap(build_comparison(baseline_metric, degraded_metric, recovered_metric, selected_id))
    log.append_event("compare", "comparison", comparison)
    advice = _coe_builder(selected_strategy, recovered_metric, baseline_metric)
    log.append_event("coe", "coe_advice", advice)

    # 逐日真实计算 7 天精度轨迹（全部 XGB 实跑，无插值）
    ds_meta = state.get("dataset_meta", {})
    incident_day = ds_meta.get("target_day", "")
    missing_day = ds_meta.get("d_minus_1", "")
    real_timeline = None
    if incident_day and missing_day:
        # 窗口：事故日前 3 天 ~ 事故日后 3 天（共 7 天，事故日居中，展示 05-21~05-27）
        inc_ts = pd.Timestamp(incident_day)
        window_start = (inc_ts - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
        window_end = (inc_ts + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
        print("  逐日真实计算 7 天精度轨迹中（XGB 实跑，无插值）...")
        rt = compute_real_timeline(
            incident_day=incident_day,
            missing_day=missing_day,
            selected_strategy=selected_id,
            window_start=window_start,
            window_end=window_end,
        )
        if rt["status"] == "ok":
            real_timeline = rt["data"]
            (run_dir / "real_timeline.json").write_text(
                json.dumps(real_timeline, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"  ✓ 真实时间线已计算: {len(real_timeline['days'])} 天")
        else:
            print(f"  ⚠ 真实时间线计算失败，回退插值: {rt['error']}")

    chart_curves = build_chart_curves(
        meta=state.get("dataset_meta", {}),
        baseline_pred=state.get("baseline_pred", {}),
        degraded_pred=state.get("degraded_pred", {}),
        recovered_pred={
            "y_true": recovered_pred["y_true"],
            "y_pred": recovered_pred["y_pred"],
        },
        baseline_acc=baseline_metric["accuracy"],
        degraded_acc=degraded_metric["accuracy"],
        recovered_acc=recovered_metric["accuracy"],
        real_timeline=real_timeline,
        selected_label=_GAP_STRATEGY_META.get(selected_id, {}).get("name", selected_id),
    )
    (run_dir / "chart_curves.json").write_text(
        json.dumps(chart_curves, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    html_path = write_html_report(run_dir)

    result = {
        "phase": "resume",
        "run_dir": str(run_dir),
        "rca_source": rca_source,
        "selected_strategy": selected_id,
        "baseline_accuracy": baseline_metric["accuracy"],
        "degraded_accuracy": degraded_metric["accuracy"],
        "recovered_accuracy": recovered_metric["accuracy"],
        "delta_recovery": comparison["delta_recovery"],
        "html_report_path": str(html_path),
        "report_file": run_info.get("report_file"),
    }
    finalize_loop_result(run_dir, result)

    print("\n" + "=" * 70)
    print("【Resume 完成 — 闭环结束】")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 70)
    print(f"\n📄 HTML 报告: {html_path}")
    if recovered:
        print(f"\n✅ 恢复成功! 精度 {recovered_metric['accuracy']}% ≥ {RECOVERY_TARGET}% 目标")
    else:
        print(f"\n⚠️ 恢复未达标: {recovered_metric['accuracy']}% < {RECOVERY_TARGET}% 目标")
    return result


if __name__ == "__main__":
    phase_resume()
# @AI_GENERATED: end
