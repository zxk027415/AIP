from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from services.agent_tools import AgentToolExecutor


def _should_trigger_backtest(request: Dict[str, Any], toggle_key: str) -> bool:
    explicit = request.get(toggle_key)
    if isinstance(explicit, bool):
        return explicit
    msg = str(request.get("message") or "").lower()
    hints = ["触发回测", "真正回测", "执行回测", "run backtest", "trigger backtest"]
    return any(h in msg for h in hints)


def _infer_backtest_range(request: Dict[str, Any], preload: Dict[str, Any]) -> Tuple[str, str]:
    start = str(request.get("backtest_start_date") or "").strip()
    end = str(request.get("backtest_end_date") or "").strip()
    if start and end:
        return start, end

    bt = preload.get("latest_backtest") if isinstance(preload.get("latest_backtest"), dict) else {}
    daily = bt.get("daily_results") if isinstance(bt, dict) else []
    dates: List[str] = []
    if isinstance(daily, list):
        for dr in daily:
            if not isinstance(dr, dict):
                continue
            d = str(dr.get("date") or "").strip()[:10]
            if len(d) == 10:
                dates.append(d)
    if dates:
        dates = sorted(set(dates))
        return dates[0], dates[-1]

    today = datetime.now().date()
    return str(today - timedelta(days=7)), str(today - timedelta(days=1))


class DriftSubAgent:
    def __init__(self, executor: AgentToolExecutor) -> None:
        self.executor = executor

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        workflow_id = context.get("preload", {}).get("workflow_id")
        kwargs = {"workflow_id": workflow_id} if workflow_id else {}
        drift = await self.executor.run_drift_detection(**kwargs)
        if not isinstance(drift, dict) or drift.get("error"):
            return drift
        bt = context.get("preload", {}).get("latest_backtest") or {}
        daily = bt.get("daily_results") if isinstance(bt, dict) else []
        worst_days = []
        if isinstance(daily, list):
            scored = []
            for dr in daily:
                if not isinstance(dr, dict):
                    continue
                smape = ((dr.get("metrics") or {}).get("smape"))
                if smape is None:
                    continue
                try:
                    scored.append((float(smape), str(dr.get("date") or "")))
                except Exception:
                    continue
            scored.sort(reverse=True)
            worst_days = [{"date": d, "smape": round(v, 4)} for v, d in scored[:5]]
        drift_summary = (
            f"risk={drift.get('risk_level', 'unknown')}, "
            f"concept={((drift.get('concept_drift') or {}).get('level', 'unknown'))}, "
            f"residual_psi={((drift.get('residual_drift') or {}).get('psi', '-'))}"
        )
        detailed_report = {
            "executive_summary": (
                f"检测到漂移风险等级为 {drift.get('risk_level', 'unknown')}，"
                f"概念漂移等级 {((drift.get('concept_drift') or {}).get('level', 'unknown'))}。"
            ),
            "key_evidence": [
                f"concept_relative_change_pct={((drift.get('concept_drift') or {}).get('relative_change_pct', '-'))}",
                f"residual_psi={((drift.get('residual_drift') or {}).get('psi', '-'))}",
            ],
            "impact_assessment": {
                "risk_level": drift.get("risk_level"),
                "high_risk_days": len(worst_days),
            },
            "action_plan": {
                "immediate": [
                    "确认高风险日期是否有外部事件/节假日扰动",
                    "复核特征输入稳定性与缺失处理策略",
                ],
                "next": [
                    "若连续2-3天高风险，联动自动重训策略",
                    "将高风险样本纳入调优候选集做对比回测",
                ],
            },
        }
        return {
            **drift,
            "drift_summary": drift_summary,
            "worst_days": worst_days,
            "detailed_report": detailed_report,
        }


class RootCauseSubAgent:
    def __init__(self, executor: AgentToolExecutor) -> None:
        self.executor = executor

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        preload = context.get("preload", {})
        training_info = preload.get("latest_training")
        backtest = preload.get("latest_backtest")
        daily_results = backtest.get("daily_results") if isinstance(backtest, dict) else None
        args: Dict[str, Any] = {}
        if daily_results:
            args["daily_results"] = daily_results
        if training_info and isinstance(training_info, dict):
            args["training_info"] = training_info
        root = await self.executor.perform_root_cause_analysis(**args)
        try:
            root_causes = root.get("root_causes") if isinstance(root, dict) else None
            if root_causes:
                root["improvement_suggestions"] = await self.executor.generate_improvement_suggestions(
                    root_causes=root_causes
                )
        except Exception:
            pass
        if isinstance(root, dict) and not root.get("error"):
            root["detailed_report"] = self._build_detailed_report(root)
        return root

    @staticmethod
    def _build_detailed_report(root: Dict[str, Any]) -> Dict[str, Any]:
        checklist = root.get("checklist") if isinstance(root.get("checklist"), dict) else {}
        causes = root.get("root_causes") if isinstance(root.get("root_causes"), list) else []
        day_pattern = root.get("day_pattern_analysis") if isinstance(root.get("day_pattern_analysis"), dict) else {}
        suggestions_obj = root.get("improvement_suggestions") if isinstance(root.get("improvement_suggestions"), dict) else {}
        suggestions = suggestions_obj.get("suggestions") if isinstance(suggestions_obj.get("suggestions"), list) else []

        missing_inputs = []
        fi = checklist.get("feature_importance_change_check") if isinstance(checklist.get("feature_importance_change_check"), dict) else {}
        if fi.get("status") == "unknown":
            missing_inputs.append("feature_importance（特征重要性）")
        scatter = checklist.get("scatter_difference_check") if isinstance(checklist.get("scatter_difference_check"), dict) else {}
        if scatter.get("status") == "unknown":
            missing_inputs.append("y_true/y_pred（真实值与预测值序列）")
        training = checklist.get("model_training_status_check") if isinstance(checklist.get("model_training_status_check"), dict) else {}
        if training.get("status") == "unknown":
            missing_inputs.append("training_info（训练产物信息）")

        top = causes[0] if causes else {}
        top_conf = top.get("confidence", 0)
        try:
            top_conf_text = f"{float(top_conf) * 100:.0f}%"
        except Exception:
            top_conf_text = str(top_conf)

        workday_avg = day_pattern.get("workday_avg_smape")
        holiday_avg = day_pattern.get("holiday_avg_smape")
        gap = day_pattern.get("workday_holiday_gap")

        evidence_lines = []
        for idx, cause in enumerate(causes[:3], start=1):
            cause_type = cause.get("cause_type", "unknown")
            conf = cause.get("confidence", 0)
            impact = cause.get("impact", "unknown")
            evidence = cause.get("evidence", "-")
            try:
                conf_text = f"{float(conf) * 100:.0f}%"
            except Exception:
                conf_text = str(conf)
            evidence_lines.append(
                f"{idx}. {cause_type} | 置信度={conf_text} | 影响={impact} | 证据={evidence}"
            )

        action_now = [s for s in suggestions if s.get("priority") == "高"][:2]
        action_next = [s for s in suggestions if s.get("priority") in {"中", "低"}][:2]

        return {
            "executive_summary": (
                f"根因分析共识别 {len(causes)} 条候选根因，首要根因为 "
                f"{top.get('cause_type', 'unknown')}（置信度 {top_conf_text}）。"
            ),
            "key_evidence": evidence_lines,
            "impact_assessment": {
                "high_risk_count": len([c for c in causes if c.get("impact") == "high"]),
                "medium_risk_count": len([c for c in causes if c.get("impact") == "medium"]),
                "low_risk_count": len([c for c in causes if c.get("impact") == "low"]),
                "workday_vs_holiday": {
                    "workday_avg_smape": workday_avg,
                    "holiday_avg_smape": holiday_avg,
                    "gap": gap,
                },
            },
            "action_plan": {
                "immediate": [
                    {
                        "action": s.get("action"),
                        "expected_improvement": s.get("expected_improvement"),
                        "effort": s.get("effort"),
                    }
                    for s in action_now
                ],
                "next": [
                    {
                        "action": s.get("action"),
                        "expected_improvement": s.get("expected_improvement"),
                        "effort": s.get("effort"),
                    }
                    for s in action_next
                ],
            },
            "data_gaps": {
                "has_gap": bool(missing_inputs),
                "missing_inputs": missing_inputs,
                "note": "存在输入缺口时，根因排序可靠性会下降，建议先补齐再重跑根因分析。",
            },
            "next_step": "建议先执行 immediate 动作后重跑回测，再依据新结果决定是否触发自动重训/模板调优。",
        }


class RetrainSubAgent:
    def __init__(self, executor: AgentToolExecutor) -> None:
        self.executor = executor

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        request = context.get("request") or {}
        task_type = str(request.get("task_type") or "D")
        preload = context.get("preload", {})
        artifacts = context.get("artifacts") or {}
        root = artifacts.get("root_cause") if isinstance(artifacts, dict) else None
        drift_from_artifact = artifacts.get("drift") if isinstance(artifacts, dict) else None
        if not isinstance(root, dict):
            root = {}
        if not isinstance(drift_from_artifact, dict):
            drift_from_artifact = {}

        compliance = await self.executor.check_accuracy_compliance(task_type=task_type)
        drift = drift_from_artifact
        if not drift:
            drift = await self.executor.run_drift_detection(
                **({"workflow_id": preload.get("workflow_id")} if preload.get("workflow_id") else {})
            )

        day_pattern = root.get("day_pattern_analysis") if isinstance(root.get("day_pattern_analysis"), dict) else {}
        high_days = day_pattern.get("high_error_days") if isinstance(day_pattern.get("high_error_days"), list) else []
        consecutive_drop_days = 2 if len(high_days) >= 3 else 3

        compliance_rate = float(compliance.get("compliance_rate", 0) or 0) if isinstance(compliance, dict) and not compliance.get("error") else 0.0
        drift_risk = (drift or {}).get("risk_level", "unknown") if isinstance(drift, dict) else "unknown"
        should_trigger = drift_risk == "high" or compliance_rate < 80

        # 默认策略：每天重训；风险低时建议切到30天周期；风险中高时采用事件触发
        schedule_mode = "daily_retrain" if should_trigger else "every_30_days"
        new_policy = {
            "enabled": bool(request.get("activate_auto_retrain", False)),
            "task_type": task_type,
            "schedule_mode": schedule_mode,
            "event_trigger": {
                "enabled": True,
                "metric": "smape",
                "consecutive_drop_days": consecutive_drop_days,
                "drift_risk_threshold": "medium",
            },
            "fallback_schedule_days": 30 if schedule_mode == "every_30_days" else 1,
        }

        trigger_result: Dict[str, Any] = {
            "summary": "未触发实际重训（仅生成策略）",
            "decision": "skip",
        }
        if new_policy["enabled"] and should_trigger:
            # 仅在用户明确激活时触发，避免默认直接起训练任务
            trigger_result = await self.executor.trigger_auto_retrain(task_type=task_type, force=True)

        backtest_triggered = _should_trigger_backtest(request, "trigger_backtest_after_retrain")
        backtest_result: Dict[str, Any] = {"summary": "未触发回测（可通过 trigger_backtest_after_retrain=true 开启）"}
        if backtest_triggered:
            start_date, end_date = _infer_backtest_range(request, preload)
            backtest_result = await self.executor.trigger_load_forecast_backtest(
                task_type=task_type,
                start_date=start_date,
                end_date=end_date,
            )

        recommendation = (
            f"建议采用{'事件触发+日更' if should_trigger else '30天周期'}策略，"
            f"当精度连续{consecutive_drop_days}天下降触发重训。"
        )
        policy_reasoning = [
            f"drift_risk={drift_risk}",
            f"compliance_rate={round(compliance_rate, 2)}",
            f"high_error_days={len(high_days)}",
            f"artifact_drift_used={bool(drift_from_artifact)}",
        ]
        detailed_report = {
            "executive_summary": recommendation,
            "decision_inputs": {
                "drift_risk": drift_risk,
                "compliance_rate": round(compliance_rate, 2),
                "high_error_days": len(high_days),
                "consecutive_drop_days": consecutive_drop_days,
            },
            "key_evidence": policy_reasoning,
            "action_plan": {
                "immediate": [
                    "启用事件触发阈值并观察近7天稳定性" if should_trigger else "维持30天周期并保持监控",
                    "对高误差日做样本复盘，确认是否存在异常输入",
                ],
                "next": [
                    "若触发阈值持续命中，自动切换到日更重训",
                    "联动调优流程验证新策略对SMAPE的改善幅度",
                ],
            },
            "risk_and_rollback": {
                "risk": "重训频率过高可能带来过拟合或资源开销上升",
                "rollback": "若连续7天无改善或波动加剧，回滚到上一策略",
            },
        }
        return {
            "recommendation": recommendation,
            "policy_reasoning": policy_reasoning,
            "current_mechanism": {
                "default_schedule": "daily_retrain",
                "status": "active" if request.get("activate_auto_retrain") else "inactive",
            },
            "compliance": compliance,
            "drift": drift,
            "drift_used": bool(drift_from_artifact),
            "new_retrain_policy": new_policy,
            "trigger_result": trigger_result,
            "backtest_triggered": backtest_triggered,
            "backtest_result": backtest_result,
            "detailed_report": detailed_report,
        }


class TuningSubAgent:
    def __init__(self, executor: AgentToolExecutor) -> None:
        self.executor = executor

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        req = context.get("request") or {}
        task_type = str(req.get("task_type") or "D")
        n_trials = int(req.get("n_trials") or 20)
        cv_folds = int(req.get("cv_folds") or 5)
        preload = context.get("preload", {})
        artifacts = context.get("artifacts") or {}
        root = artifacts.get("root_cause") if isinstance(artifacts, dict) else None
        drift = artifacts.get("drift") if isinstance(artifacts, dict) else None
        root_causes = root.get("root_causes") if isinstance(root, dict) else None
        if not isinstance(root_causes, list):
            root_causes = []
        if not isinstance(drift, dict):
            drift = {}

        template_summary = preload.get("template_summary") if isinstance(preload.get("template_summary"), dict) else {}
        operator_ids = template_summary.get("operator_ids") if isinstance(template_summary.get("operator_ids"), list) else []

        improvement = await self.executor.generate_improvement_suggestions(root_causes=root_causes or None)
        suggestions = improvement.get("suggestions") if isinstance(improvement, dict) and isinstance(improvement.get("suggestions"), list) else []
        drift_risk = drift.get("risk_level", "unknown")
        top_causes = [c.get("cause_type", "unknown") for c in root_causes[:3]]
        tuning_rationale: List[str] = [
            f"drift_risk={drift_risk}",
            f"top_root_causes={top_causes}",
        ]

        template_actions = []
        if "feature_engineering_parallel_v2" in operator_ids or "feature_union" in operator_ids:
            template_actions.append("特征工程已具备并行编排条件，建议启用分支并在 feature_union 前增加标准化校验。")
        else:
            template_actions.append("模板中未检测到并行特征拼接算子，建议加入并行分支 + 拼接算子（如 feature_union）。")
        if "xgboost_forecast" in operator_ids:
            template_actions.append("建议基于回测结果优先调优 xgboost 参数（max_depth/learning_rate/n_estimators）。")
        if drift_risk in {"high", "medium"}:
            template_actions.append("检测到漂移风险，建议优先做稳健性参数调优（降低学习率、增大样本窗口、增强正则化）。")

        # 默认给出调优方案；仅当用户明确触发时才真正起调优训练
        trigger_tuning = bool(req.get("activate_tuning", False))
        tuning_result: Dict[str, Any] = {
            "summary": "未触发实际调优任务（仅生成方案）"
        }
        if trigger_tuning:
            tuning_result = await self.executor.trigger_model_tuning(
                task_type=task_type,
                n_trials=n_trials,
                cv_folds=cv_folds,
            )

        backtest_triggered = _should_trigger_backtest(req, "trigger_backtest_after_tuning")
        backtest_result: Dict[str, Any] = {"summary": "未触发回测（可通过 trigger_backtest_after_tuning=true 开启）"}
        if backtest_triggered:
            start_date, end_date = _infer_backtest_range(req, preload)
            backtest_result = await self.executor.trigger_load_forecast_backtest(
                task_type=task_type,
                start_date=start_date,
                end_date=end_date,
            )
        candidate_priority = []
        for idx, s in enumerate(suggestions[:5], start=1):
            candidate_priority.append(
                {
                    "rank": idx,
                    "action": s.get("action"),
                    "priority": s.get("priority"),
                    "reason": f"关联根因={s.get('related_cause', 'unknown')}, expected={s.get('expected_improvement', '-')}",
                }
            )

        detailed_report = {
            "executive_summary": "已基于漂移 + 根因联合生成调优方案。",
            "decision_inputs": {
                "drift_risk": drift_risk,
                "top_root_causes": top_causes,
                "operator_count": len(operator_ids),
            },
            "key_evidence": tuning_rationale,
            "action_plan": {
                "immediate": [x for x in template_actions[:2]],
                "next": [x for x in template_actions[2:4]],
            },
            "candidate_priority": candidate_priority[:3],
            "risk_and_rollback": {
                "risk": "参数过度激进可能导致短期指标改善但泛化变差",
                "rollback": "保留基线参数，若回测未提升则回退并缩小搜索空间",
            },
        }

        return {
            "recommendation": "已生成模板调优建议（含模板编排与参数方向）",
            "tuning_rationale": tuning_rationale,
            "drift_used": bool(drift),
            "template_actions": template_actions,
            "improvement_suggestions": suggestions[:8],
            "candidate_priority": candidate_priority,
            "tuning_plan": {
                "task_type": task_type,
                "n_trials": n_trials,
                "cv_folds": cv_folds,
                "triggered": trigger_tuning,
            },
            "tuning_result": tuning_result,
            "backtest_triggered": backtest_triggered,
            "backtest_result": backtest_result,
            "detailed_report": detailed_report,
        }

