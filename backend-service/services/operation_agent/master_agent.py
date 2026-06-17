import logging
import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

from services.agent_tools import get_tool_executor
from services.operation_agent.preloader import OperationContextPreloader
from services.operation_agent.router import OperationRouter
from services.operation_agent.sub_agents import (
    DriftSubAgent,
    RetrainSubAgent,
    RootCauseSubAgent,
    TuningSubAgent,
)

logger = logging.getLogger(__name__)


class OperationMasterAgent:
    """运营 Master Agent：强制预读取 + 混合路由 + 依赖补全 + 子Agent执行。"""

    def __init__(self) -> None:
        executor = get_tool_executor()
        self.preloader = OperationContextPreloader()
        self.router = OperationRouter()
        self.sub_agents = {
            "drift": DriftSubAgent(executor),
            "root_cause": RootCauseSubAgent(executor),
            "retrain": RetrainSubAgent(executor),
            "tuning": TuningSubAgent(executor),
        }

    async def process(
        self,
        message: str,
        context: Dict[str, Any],
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        async def _emit(msg: str) -> None:
            if not on_progress:
                return
            try:
                await on_progress(msg)
            except Exception:
                logger.debug("operation progress callback failed", exc_info=True)

        await _emit("### 任务理解")
        await _emit("我先理解你的目标，并准备把模板结构和最近结果一起纳入判断。")
        preload = await self.preloader.load(message, context)
        tpl_summary = preload.get("template_summary") or {}
        await _emit(
            "我已拿到模板上下文，"
            f"其中节点数={tpl_summary.get('node_count', 0)}、连线数={tpl_summary.get('edge_count', 0)}，"
            "接下来会基于你的问题语义判断应先分析哪一层。"
        )
        await _emit("### 路径判断")
        await _emit("我正在综合规则线索与语义理解做路由判断，并自动补全必要前置步骤。")
        route = await self.router.route(message, preload)
        execution_plan: List[str] = route.get("execution_plan") or []
        ranked = route.get("ranked") or []
        top_choice = ranked[0][0] if ranked else "-"
        top_score = ranked[0][1] if ranked and len(ranked[0]) > 1 else 0
        await _emit(
            "当前判断最相关目标是 "
            f"{top_choice}（score={top_score:.2f}），"
            f"因此执行顺序为：{' -> '.join(execution_plan) if execution_plan else '-'}。"
        )

        if route.get("confirmation_needed"):
            resp = (
                "我还不能高置信判断你要执行哪个运营子 Agent。\n\n"
                "请确认你想执行：\n"
                "- 漂移分析（drift）\n"
                "- 根因分析（root_cause）\n"
                "- 自动重训（retrain）\n"
                "- 模板调优（tuning）\n\n"
                "如果你愿意，也可以直接说：`先做根因分析，再给重训建议`。"
            )
            reasoning = self._build_reasoning(preload, route, [], {})
            observability = self._build_observability(preload, route, execution_plan, {})
            await _emit("当前意图置信度不足，我需要你确认具体分析目标后再继续，以避免误判。")
            return {
                "response": resp,
                "reasoning": reasoning,
                "intent": route,
                "sub_agent_results": {},
                "observability": observability,
                "suggested_actions": [
                    {"label": "漂移分析", "action": "drift"},
                    {"label": "根因分析", "action": "rootCause"},
                    {"label": "自动重训", "action": "autoRetrain"},
                    {"label": "模板调优", "action": "tuneModel"},
                ],
            }

        op_context = {
            "request": {
                "message": message,
                "task_type": context.get("task_type"),
                "n_trials": context.get("n_trials"),
                "cv_folds": context.get("cv_folds"),
                "backtest_start_date": context.get("backtest_start_date"),
                "backtest_end_date": context.get("backtest_end_date"),
                "trigger_backtest_after_retrain": context.get("trigger_backtest_after_retrain"),
                "trigger_backtest_after_tuning": context.get("trigger_backtest_after_tuning"),
            },
            "preload": preload,
            "route": route,
            "artifacts": {},
        }
        outputs: Dict[str, Any] = {}
        await asyncio.sleep(0.18)
        await _emit("我已完成路径选择，下面进入证据归纳。")
        await _emit("### 证据归纳")
        for agent_name in execution_plan:
            try:
                await _emit(f"我先进入 {agent_name} 分析，并把前一步结果作为当前推理依据。")
                outputs[agent_name] = await self.sub_agents[agent_name].run(op_context)
            except Exception as e:
                logger.exception("Operation sub-agent failed: %s", agent_name)
                outputs[agent_name] = {"error": str(e)}
            if isinstance(outputs.get(agent_name), dict) and outputs[agent_name].get("error"):
                await _emit(f"{agent_name} 在分析时出现异常，我会保留错误信息并继续给出可用结论。")
            else:
                payload = outputs.get(agent_name) if isinstance(outputs.get(agent_name), dict) else {}
                stage_hint = payload.get("summary") or payload.get("recommendation") or "已产出结构化结论"
                await _emit(f"{agent_name} 已得到阶段结论：{stage_hint}")
            op_context["artifacts"][agent_name] = outputs[agent_name]
            await asyncio.sleep(0.14)

        await asyncio.sleep(0.18)
        await _emit("证据归纳已完成，我将基于这些证据输出最终决策。")
        await _emit("### 最终决策")
        await _emit("我正在把各阶段证据合并，生成最终结论、建议和可执行动作。")
        response = self._build_response(preload, execution_plan, outputs)
        reasoning = self._build_reasoning(preload, route, execution_plan, outputs)
        observability = self._build_observability(preload, route, execution_plan, outputs)
        await _emit("分析完成，下面给你完整汇报。")
        return {
            "response": response,
            "reasoning": reasoning,
            "intent": route,
            "sub_agent_results": outputs,
            "observability": observability,
            "suggested_actions": self._build_suggested_actions(execution_plan),
        }

    @staticmethod
    def _build_suggested_actions(plan: List[str]) -> List[Dict[str, Any]]:
        actions = []
        if "root_cause" not in plan:
            actions.append({"label": "补充根因分析", "action": "rootCause"})
        if "retrain" not in plan:
            actions.append({"label": "生成重训策略", "action": "autoRetrain"})
        if "tuning" not in plan:
            actions.append({"label": "生成调优建议", "action": "tuneModel"})
        if "drift" not in plan:
            actions.append({"label": "补充漂移分析", "action": "drift"})
        return actions[:4]

    @staticmethod
    def _build_response(preload: Dict[str, Any], plan: List[str], outputs: Dict[str, Any]) -> str:
        summary = preload.get("template_summary") or {}
        template_payload = preload.get("template_payload") or {}
        lines = [
            "## 运营分析结果",
            "",
            (
                f"- 预读模板：`{summary.get('template_name') or preload.get('workflow_id') or '-'}` "
                f"(source={template_payload.get('source') or '-'}, "
                f"nodes={summary.get('node_count', 0)}, edges={summary.get('edge_count', 0)})"
            ),
            f"- 执行计划：`{' -> '.join(plan)}`",
            "",
        ]
        if not template_payload.get("found"):
            lines.append(f"- ⚠ 模板未命中：{template_payload.get('error') or 'unknown'}")
            lines.append("- 建议在请求上下文中传入 workflow_id/template_id 以获得更精准分析。")
            lines.append("")

        for name in plan:
            payload = outputs.get(name, {})
            lines.append(f"### {name}")
            if isinstance(payload, dict) and payload.get("error"):
                lines.append(f"- 状态：失败")
                lines.append(f"- 错误：{payload.get('error')}")
                lines.append("")
                continue
            if name == "drift":
                drift = (payload or {}).get("drift_summary") if isinstance(payload, dict) else None
                lines.append(f"- 漂移结论：{drift or '已完成，详见结构化结果'}")
                lines.append(f"- 风险等级：{(payload or {}).get('risk_level', '-') if isinstance(payload, dict) else '-'}")
                lines.append(f"- 漂移建议：{(payload or {}).get('recommendation', '-') if isinstance(payload, dict) else '-'}")
                worst_days = (payload or {}).get("worst_days") if isinstance(payload, dict) else None
                if isinstance(worst_days, list) and worst_days:
                    lines.append("- 高风险日期（Top3）：")
                    for item in worst_days[:3]:
                        lines.append(f"  - {item.get('date', '-')}: SMAPE={item.get('smape', '-')}")
                detailed_report = (payload or {}).get("detailed_report") if isinstance(payload, dict) else None
                if isinstance(detailed_report, dict):
                    lines.append("- 漂移分析汇报（详细版）：")
                    lines.append(f"  - 结论：{detailed_report.get('executive_summary', '-')}")
                    evidence = detailed_report.get("key_evidence")
                    if isinstance(evidence, list) and evidence:
                        lines.append("  - 关键证据：")
                        for item in evidence[:3]:
                            lines.append(f"    - {item}")
                    actions = detailed_report.get("action_plan") if isinstance(detailed_report.get("action_plan"), dict) else {}
                    immediate = actions.get("immediate") if isinstance(actions.get("immediate"), list) else []
                    if immediate:
                        lines.append("  - 建议动作（立即执行）：")
                        for item in immediate[:2]:
                            lines.append(f"    - {item}")
                lines.append("#### 最终输出（drift）")
                lines.append(
                    f"- 结论：risk={((payload or {}).get('risk_level', '-'))}，"
                    f"concept={(((payload or {}).get('concept_drift') or {}).get('level', '-') if isinstance((payload or {}).get('concept_drift'), dict) else '-')}"
                )
                lines.append(f"- 动作：{((payload or {}).get('recommendation', '优先排查高风险日期并校验关键特征稳定性'))}")
            elif name == "root_cause":
                causes = (payload or {}).get("root_causes") if isinstance(payload, dict) else None
                count = len(causes) if isinstance(causes, list) else 0
                deferred_suggestion_lines: List[str] = []
                lines.append(f"- 根因条目：{count}")
                detailed_report = (payload or {}).get("detailed_report") if isinstance(payload, dict) else None
                if isinstance(detailed_report, dict):
                    lines.append("")
                    lines.append("#### 根因分析汇报（详细版）")
                    lines.append(f"- 结论：{detailed_report.get('executive_summary', '-')}")
                    evidence = detailed_report.get("key_evidence")
                    if isinstance(evidence, list) and evidence:
                        lines.append("- 关键证据：")
                        for item in evidence[:3]:
                            lines.append(f"  - {item}")
                    impact = detailed_report.get("impact_assessment") if isinstance(detailed_report.get("impact_assessment"), dict) else {}
                    wh = impact.get("workday_vs_holiday") if isinstance(impact.get("workday_vs_holiday"), dict) else {}
                    lines.append(
                        f"- 影响评估：high={impact.get('high_risk_count', 0)}, "
                        f"medium={impact.get('medium_risk_count', 0)}, low={impact.get('low_risk_count', 0)}"
                    )
                    if wh:
                        lines.append(
                            f"- 工作日/节假日：workday_avg_smape={wh.get('workday_avg_smape', '-')}, "
                            f"holiday_avg_smape={wh.get('holiday_avg_smape', '-')}, gap={wh.get('gap', '-')}"
                        )
                    plan = detailed_report.get("action_plan") if isinstance(detailed_report.get("action_plan"), dict) else {}
                    immediate = plan.get("immediate") if isinstance(plan.get("immediate"), list) else []
                    if immediate:
                        deferred_suggestion_lines.append("- 建议动作（立即执行）：")
                        for item in immediate[:2]:
                            deferred_suggestion_lines.append(
                                f"  - {item.get('action', '-')} "
                                f"(预期={item.get('expected_improvement', '-')}, 成本={item.get('effort', '-')})"
                            )
                    nxt = plan.get("next") if isinstance(plan.get("next"), list) else []
                    if nxt:
                        deferred_suggestion_lines.append("- 建议动作（下一步）：")
                        for item in nxt[:2]:
                            deferred_suggestion_lines.append(
                                f"  - {item.get('action', '-')} "
                                f"(预期={item.get('expected_improvement', '-')}, 成本={item.get('effort', '-')})"
                            )
                    gaps = detailed_report.get("data_gaps") if isinstance(detailed_report.get("data_gaps"), dict) else {}
                    if gaps.get("has_gap"):
                        miss = gaps.get("missing_inputs") if isinstance(gaps.get("missing_inputs"), list) else []
                        lines.append(f"- 数据缺口：{', '.join(miss) if miss else '-'}")
                        lines.append(f"- 说明：{gaps.get('note', '-')}")
                    lines.append(f"- 下一步：{detailed_report.get('next_step', '-')}")
                checklist = (payload or {}).get("checklist") if isinstance(payload, dict) else None
                if isinstance(checklist, dict):
                    lines.append("- 四项检查：")
                    for k in (
                        "data_issue_check",
                        "feature_importance_change_check",
                        "scatter_difference_check",
                        "model_training_status_check",
                    ):
                        item = checklist.get(k) or {}
                        status = item.get("status", "unknown")
                        detail = item.get("detail", "")
                        lines.append(f"  - {k}: {status} | {detail}")
                if isinstance(causes, list) and causes:
                    lines.append("- 主要根因Top3：")
                    for cause in causes[:3]:
                        ctype = cause.get("cause_type", "unknown")
                        conf = cause.get("confidence", 0)
                        evidence = cause.get("evidence", "")
                        try:
                            conf_text = f"{float(conf) * 100:.0f}%"
                        except Exception:
                            conf_text = str(conf)
                        lines.append(f"  - {ctype}（{conf_text}）：{evidence}")
                suggestions = (payload or {}).get("improvement_suggestions", {}) if isinstance(payload, dict) else {}
                items = suggestions.get("suggestions") if isinstance(suggestions, dict) else None
                if isinstance(items, list) and items:
                    deferred_suggestion_lines.append("- 改进建议Top3：")
                    for s in items[:3]:
                        deferred_suggestion_lines.append(
                            f"  - [{s.get('priority', '-')}] {s.get('action', '-')}"
                            f"（预期：{s.get('expected_improvement', '-')}）"
                        )
                if deferred_suggestion_lines:
                    lines.append("- 最终建议（汇总）：")
                    lines.extend(deferred_suggestion_lines)
                lines.append("#### 最终输出（root_cause）")
                top_cause = causes[0] if isinstance(causes, list) and causes else {}
                lines.append(
                    f"- 结论：首要根因={top_cause.get('cause_type', '-')}，"
                    f"置信度={top_cause.get('confidence', '-')}"
                )
                if deferred_suggestion_lines:
                    first_action = next((x for x in deferred_suggestion_lines if isinstance(x, str) and x.strip().startswith("- [")), None)
                    if first_action:
                        lines.append(f"- 动作：{first_action.replace('- ', '', 1)}")
            elif name == "retrain":
                lines.append(f"- 重训建议：{(payload or {}).get('recommendation', '已生成') if isinstance(payload, dict) else '已生成'}")
                lines.append(f"- 是否使用漂移结果：{(payload or {}).get('drift_used', False) if isinstance(payload, dict) else False}")
                policy = (payload or {}).get("new_retrain_policy") if isinstance(payload, dict) else None
                if isinstance(policy, dict):
                    event = policy.get("event_trigger") if isinstance(policy.get("event_trigger"), dict) else {}
                    lines.append(
                        f"- 新策略：schedule={policy.get('schedule_mode')}，"
                        f"连续下降触发天数={event.get('consecutive_drop_days', '-')}"
                    )
                    lines.append(
                        f"- 策略配置：enabled={policy.get('enabled')}，"
                        f"fallback_schedule_days={policy.get('fallback_schedule_days', '-')}"
                    )
                trigger_result = (payload or {}).get("trigger_result") if isinstance(payload, dict) else None
                if isinstance(trigger_result, dict):
                    lines.append(f"- 触发结果：{trigger_result.get('summary', '-')}")
                backtest_result = (payload or {}).get("backtest_result") if isinstance(payload, dict) else None
                if isinstance(backtest_result, dict):
                    lines.append(f"- 回测触发：{backtest_result.get('summary', '-')}")
                detailed_report = (payload or {}).get("detailed_report") if isinstance(payload, dict) else None
                if isinstance(detailed_report, dict):
                    lines.append("- 重训策略汇报（详细版）：")
                    lines.append(f"  - 结论：{detailed_report.get('executive_summary', '-')}")
                    decision_inputs = detailed_report.get("decision_inputs") if isinstance(detailed_report.get("decision_inputs"), dict) else {}
                    if decision_inputs:
                        lines.append(
                            "  - 决策依据："
                            f"drift_risk={decision_inputs.get('drift_risk', '-')}, "
                            f"compliance_rate={decision_inputs.get('compliance_rate', '-')}, "
                            f"high_error_days={decision_inputs.get('high_error_days', '-')}"
                        )
                    risk = detailed_report.get("risk_and_rollback") if isinstance(detailed_report.get("risk_and_rollback"), dict) else {}
                    if risk:
                        lines.append(f"  - 风险：{risk.get('risk', '-')}")
                        lines.append(f"  - 回滚：{risk.get('rollback', '-')}")
                lines.append("#### 最终输出（retrain）")
                lines.append(f"- 结论：{(payload or {}).get('recommendation', '-') if isinstance(payload, dict) else '-'}")
                lines.append(
                    f"- 动作：设置 schedule={((payload or {}).get('new_retrain_policy') or {}).get('schedule_mode', '-') if isinstance((payload or {}).get('new_retrain_policy'), dict) else '-'}，"
                    f"连续下降触发={((((payload or {}).get('new_retrain_policy') or {}).get('event_trigger') or {}).get('consecutive_drop_days', '-') if isinstance((((payload or {}).get('new_retrain_policy') or {}).get('event_trigger')), dict) else '-')}"
                )
            elif name == "tuning":
                lines.append(f"- 调优建议：{(payload or {}).get('recommendation', '已生成') if isinstance(payload, dict) else '已生成'}")
                lines.append(f"- 是否使用漂移结果：{(payload or {}).get('drift_used', False) if isinstance(payload, dict) else False}")
                actions = (payload or {}).get("template_actions") if isinstance(payload, dict) else None
                if isinstance(actions, list) and actions:
                    lines.append("- 模板编排建议：")
                    for action in actions[:3]:
                        lines.append(f"  - {action}")
                tuning_plan = (payload or {}).get("tuning_plan") if isinstance(payload, dict) else None
                if isinstance(tuning_plan, dict):
                    lines.append(
                        f"- 调优计划：task_type={tuning_plan.get('task_type', '-')}, "
                        f"n_trials={tuning_plan.get('n_trials', '-')}, "
                        f"cv_folds={tuning_plan.get('cv_folds', '-')}, "
                        f"triggered={tuning_plan.get('triggered', False)}"
                    )
                imp = (payload or {}).get("improvement_suggestions") if isinstance(payload, dict) else None
                if isinstance(imp, list) and imp:
                    lines.append("- 参数/策略优化建议Top3：")
                    for s in imp[:3]:
                        lines.append(f"  - [{s.get('priority', '-')}] {s.get('action', '-')}")
                backtest_result = (payload or {}).get("backtest_result") if isinstance(payload, dict) else None
                if isinstance(backtest_result, dict):
                    lines.append(f"- 回测触发：{backtest_result.get('summary', '-')}")
                detailed_report = (payload or {}).get("detailed_report") if isinstance(payload, dict) else None
                if isinstance(detailed_report, dict):
                    lines.append("- 调优汇报（详细版）：")
                    lines.append(f"  - 结论：{detailed_report.get('executive_summary', '-')}")
                    decision_inputs = detailed_report.get("decision_inputs") if isinstance(detailed_report.get("decision_inputs"), dict) else {}
                    if decision_inputs:
                        lines.append(
                            "  - 决策依据："
                            f"drift_risk={decision_inputs.get('drift_risk', '-')}, "
                            f"top_root_causes={decision_inputs.get('top_root_causes', [])}"
                        )
                    cands = detailed_report.get("candidate_priority") if isinstance(detailed_report.get("candidate_priority"), list) else []
                    if cands:
                        lines.append("  - 候选优先级Top3：")
                        for c in cands[:3]:
                            lines.append(f"    - Rank{c.get('rank', '-')}: {c.get('action', '-')} | {c.get('reason', '-')}")
                lines.append("#### 最终输出（tuning）")
                lines.append(f"- 结论：{(payload or {}).get('recommendation', '-') if isinstance(payload, dict) else '-'}")
                first_tpl_action = (actions[0] if isinstance(actions, list) and actions else "按候选优先级执行调优并回测验证")
                lines.append(f"- 动作：{first_tpl_action}")
            lines.append("")

        # 统一收口：把最终结论与动作放在最后，避免阅读上前后跳转
        final_conclusions: List[str] = []
        final_actions: List[str] = []
        for name in plan:
            payload = outputs.get(name, {}) if isinstance(outputs.get(name), dict) else {}
            if not isinstance(payload, dict) or payload.get("error"):
                continue
            if name == "drift":
                final_conclusions.append(
                    f"漂移风险={payload.get('risk_level', '-')}"
                    f"，概念漂移={(payload.get('concept_drift') or {}).get('level', '-') if isinstance(payload.get('concept_drift'), dict) else '-'}"
                )
                rec = payload.get("recommendation")
                if rec:
                    final_actions.append(f"[漂移] {rec}")
            elif name == "root_cause":
                top = (payload.get("root_causes") or [])
                if isinstance(top, list) and top:
                    c = top[0] if isinstance(top[0], dict) else {}
                    final_conclusions.append(
                        f"首要根因={c.get('cause_type', '-')}"
                        f"（置信度={c.get('confidence', '-')}, 影响={c.get('impact', '-')})"
                    )
                report = payload.get("detailed_report") if isinstance(payload.get("detailed_report"), dict) else {}
                plan_obj = report.get("action_plan") if isinstance(report.get("action_plan"), dict) else {}
                immediate = plan_obj.get("immediate") if isinstance(plan_obj.get("immediate"), list) else []
                for item in immediate[:2]:
                    if isinstance(item, dict):
                        final_actions.append(f"[根因] {item.get('action', '-')}")
            elif name == "retrain":
                policy = payload.get("new_retrain_policy") if isinstance(payload.get("new_retrain_policy"), dict) else {}
                event = policy.get("event_trigger") if isinstance(policy.get("event_trigger"), dict) else {}
                final_conclusions.append(
                    f"重训策略={policy.get('schedule_mode', '-')}"
                    f"，连续下降触发={event.get('consecutive_drop_days', '-')}"
                )
                rec = payload.get("recommendation")
                if rec:
                    final_actions.append(f"[重训] {rec}")
            elif name == "tuning":
                plan_obj = payload.get("tuning_plan") if isinstance(payload.get("tuning_plan"), dict) else {}
                final_conclusions.append(
                    f"调优计划=trials:{plan_obj.get('n_trials', '-')}, cv:{plan_obj.get('cv_folds', '-')}, triggered:{plan_obj.get('triggered', False)}"
                )
                actions = payload.get("template_actions")
                if isinstance(actions, list):
                    for a in actions[:2]:
                        final_actions.append(f"[调优] {a}")

        if final_conclusions or final_actions:
            lines.append("## 最终输出（汇总）")
            lines.append("")
            if final_conclusions:
                lines.append("- 最终结论：")
                for item in final_conclusions[:6]:
                    lines.append(f"  - {item}")
            if final_actions:
                lines.append("- 最终动作（建议按顺序执行）：")
                dedup: List[str] = []
                for action in final_actions:
                    if action not in dedup:
                        dedup.append(action)
                for item in dedup[:8]:
                    lines.append(f"  - {item}")
        return "\n".join(lines).strip()

    @staticmethod
    def _build_reasoning(
        preload: Dict[str, Any],
        route: Dict[str, Any],
        plan: List[str],
        outputs: Dict[str, Any],
    ) -> str:
        summary = preload.get("template_summary") or {}
        src = preload.get("workflow_id_source") or "-"
        return (
            "1) 已强制预读取模板与结果上下文；"
            f" workflow_id 来源={src}；"
            f" template nodes={summary.get('node_count', 0)}, edges={summary.get('edge_count', 0)}。\n"
            "2) 使用混合打分路由（rule + llm）选择目标子Agent。"
            f" ranked={route.get('ranked')}。\n"
            f"3) 依赖补全后执行计划：{plan}。\n"
            f"4) 各子Agent结构化输出键：{list(outputs.keys())}。"
        )

    @staticmethod
    def _build_stage_summary(agent_name: str, payload: Any) -> str:
        if not isinstance(payload, dict):
            return "已执行"
        if payload.get("error"):
            return f"失败：{payload.get('error')}"
        if agent_name == "drift":
            return str(payload.get("drift_summary") or "已生成漂移分析")
        if agent_name == "root_cause":
            causes = payload.get("root_causes")
            if isinstance(causes, list):
                return f"已识别根因 {len(causes)} 条"
            return "已完成根因分析"
        if agent_name in {"retrain", "tuning"}:
            return str(payload.get("recommendation") or "已生成建议")
        return "已执行"

    def _build_observability(
        self,
        preload: Dict[str, Any],
        route: Dict[str, Any],
        plan: List[str],
        outputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        template_payload = preload.get("template_payload") or {}
        template_summary = preload.get("template_summary") or {}
        preloading = {
            "workflow_id": preload.get("workflow_id"),
            "workflow_id_source": preload.get("workflow_id_source"),
            "template_found": bool(template_payload.get("found")),
            "template_source": template_payload.get("source"),
            "template_path": template_payload.get("path"),
            "template_error": template_payload.get("error"),
            "node_count": template_summary.get("node_count", 0),
            "edge_count": template_summary.get("edge_count", 0),
            "operator_ids": template_summary.get("operator_ids", []),
            "operator_param_keys": template_summary.get("operator_param_keys", {}),
            "backtest_loaded": isinstance(preload.get("latest_backtest"), dict) and not preload.get("latest_backtest", {}).get("error"),
            "training_loaded": isinstance(preload.get("latest_training"), dict) and not preload.get("latest_training", {}).get("error"),
        }
        routing = {
            "rule_scores": route.get("rule_scores") or {},
            "llm_scores": route.get("llm_scores") or {},
            "final_scores": route.get("final_scores") or {},
            "ranked": route.get("ranked") or [],
            "selected_targets": route.get("selected_targets") or [],
            "execution_plan": plan,
            "confirmation_needed": bool(route.get("confirmation_needed")),
            "llm_reason": route.get("llm_reason"),
        }
        stages: List[Dict[str, Any]] = []
        for agent_name in plan:
            payload = outputs.get(agent_name)
            details: Dict[str, Any] = {}
            if isinstance(payload, dict):
                if agent_name == "drift":
                    details = {
                        "risk_level": payload.get("risk_level"),
                        "recommendation": payload.get("recommendation"),
                        "worst_days": payload.get("worst_days"),
                        "detailed_report": payload.get("detailed_report"),
                    }
                elif agent_name == "root_cause":
                    details = {
                        "summary": payload.get("summary"),
                        "checklist": payload.get("checklist"),
                        "day_pattern_analysis": payload.get("day_pattern_analysis"),
                        "top_root_causes": (payload.get("root_causes") or [])[:3],
                        "detailed_report": payload.get("detailed_report"),
                    }
                elif agent_name == "retrain":
                    details = {
                        "recommendation": payload.get("recommendation"),
                        "drift_used": payload.get("drift_used"),
                        "policy_reasoning": payload.get("policy_reasoning"),
                        "new_retrain_policy": payload.get("new_retrain_policy"),
                        "trigger_result": payload.get("trigger_result"),
                        "backtest_triggered": payload.get("backtest_triggered"),
                        "backtest_result": payload.get("backtest_result"),
                        "detailed_report": payload.get("detailed_report"),
                    }
                elif agent_name == "tuning":
                    details = {
                        "recommendation": payload.get("recommendation"),
                        "drift_used": payload.get("drift_used"),
                        "tuning_rationale": payload.get("tuning_rationale"),
                        "template_actions": payload.get("template_actions"),
                        "tuning_plan": payload.get("tuning_plan"),
                        "candidate_priority": (payload.get("candidate_priority") or [])[:5],
                        "improvement_suggestions": (payload.get("improvement_suggestions") or [])[:5],
                        "backtest_triggered": payload.get("backtest_triggered"),
                        "backtest_result": payload.get("backtest_result"),
                        "detailed_report": payload.get("detailed_report"),
                    }
            stages.append(
                {
                    "agent": agent_name,
                    "status": "failed" if isinstance(payload, dict) and payload.get("error") else "success",
                    "summary": self._build_stage_summary(agent_name, payload),
                    "result_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
                    "details": details,
                }
            )
        return {
            "preloading": preloading,
            "routing": routing,
            "execution": {"plan": plan, "stages": stages},
        }


_operation_master_agent: OperationMasterAgent = None


def get_operation_master_agent() -> OperationMasterAgent:
    global _operation_master_agent
    if _operation_master_agent is None:
        _operation_master_agent = OperationMasterAgent()
    return _operation_master_agent

