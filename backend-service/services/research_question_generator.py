import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .analyst_agent import ErrorAttribution
from .dataset_profiler_models import CrossWindowPattern


@dataclass
class ResearchQuestion:
    question: str
    evidence: List[str]
    candidate_causes: List[str]
    next_experiment_goal: str
    recurring: bool = False
    priority: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResearchQuestionGenerator:
    def generate(
        self,
        error_attribution: ErrorAttribution,
        cross_window_pattern: Optional[CrossWindowPattern] = None,
        knowledge_layer: Optional[Any] = None,
        recent_questions: Optional[List[ResearchQuestion]] = None,
        conflicts: Optional[List[Dict[str, Any]]] = None,
    ) -> List[ResearchQuestion]:
        questions: List[ResearchQuestion] = []
        cause = error_attribution.primary_cause

        dominant_period = None
        if cross_window_pattern:
            worst_periods = cross_window_pattern.periodic_error_pattern.get("worst_periods", [])
            dominant_period = self._same_period_at_least(worst_periods, 3)
            if dominant_period:
                questions.append(
                    ResearchQuestion(
                        question=f"为什么{dominant_period}误差持续偏高？",
                        evidence=[f"{dominant_period} is worst period in >=3 windows"],
                        candidate_causes=["period_specific_error", *error_attribution.contributing_factors],
                        next_experiment_goal=f"验证{dominant_period}相关特征或训练窗口调整是否降低误差",
                    )
                )
            if float(cross_window_pattern.drift_signal or 0.0) > 0:
                questions.append(
                    ResearchQuestion(
                        question="如何应对近期数据漂移导致的误差上升？",
                        evidence=[f"drift_signal={cross_window_pattern.drift_signal}"],
                        candidate_causes=["drift_signal", cause],
                        next_experiment_goal="验证缩短训练窗口或提高近期样本权重是否改善泛化",
                    )
                )

        if cause == "confirmed_overfit":
            questions.append(
                ResearchQuestion(
                    question="如何降低当前配置的过拟合风险？",
                    evidence=list(error_attribution.evidence),
                    candidate_causes=["confirmed_overfit", *error_attribution.contributing_factors],
                    next_experiment_goal="验证降低模型复杂度或增加正则化是否缩小验证-测试误差差距",
                )
            )

        for conflict in conflicts or []:
            param = conflict.get("target_param") or conflict.get("param") or "参数"
            questions.append(
                ResearchQuestion(
                    question=f"如何解决{param}的矛盾建议？",
                    evidence=[str(conflict)],
                    candidate_causes=["knowledge_conflict"],
                    next_experiment_goal=f"设计单变量实验验证{param}方向",
                )
            )

        anti_patterns = self._lookup_anti_patterns(knowledge_layer, cause)
        if anti_patterns and questions:
            for q in questions:
                q.candidate_causes.extend(anti_patterns)

        if not questions:
            questions.append(
                ResearchQuestion(
                    question="当前误差是否已进入参数饱和区间？",
                    evidence=list(error_attribution.evidence),
                    candidate_causes=[cause],
                    next_experiment_goal="验证继续微调参数是否仍有可测量收益",
                )
            )

        filtered: List[ResearchQuestion] = []
        suppressed = 0
        recent = recent_questions or []
        for question in questions:
            if self._is_suppressed_by_lifecycle(question, recent):
                suppressed += 1
                continue
            if self._is_recurring(question, recent_questions or []):
                question.recurring = True
                question.priority = 1.5
            filtered.append(question)

        if not filtered and suppressed > 0:
            filtered.append(
                ResearchQuestion(
                    question="已验证无效的问题是否应暂停并切换研究方向？",
                    evidence=["recent research questions are stale or resolved"],
                    candidate_causes=["stale_question_saturation"],
                    next_experiment_goal="切换到未充分覆盖的特征、模型、数据或风险方向",
                    priority=1.2,
                )
            )

        return filtered[:3]

    def _same_period_at_least(self, periods: Sequence[str], n: int) -> Optional[str]:
        if not periods:
            return None
        counts: Dict[str, int] = {}
        for period in periods:
            counts[period] = counts.get(period, 0) + 1
            if counts[period] >= n:
                return period
        return None

    def _lookup_anti_patterns(self, knowledge_layer: Optional[Any], cause: str) -> List[str]:
        if knowledge_layer is None or not hasattr(knowledge_layer, "search"):
            return []
        try:
            rows = knowledge_layer.search(layer="L3", knowledge_type="anti_pattern")
        except TypeError:
            rows = knowledge_layer.search({"layer": "L3", "knowledge_type": "anti_pattern"})
        except Exception:
            return []
        out = []
        for item in rows or []:
            text = item.get("claim") if isinstance(item, dict) else str(item)
            if cause in text or text:
                out.append(text)
        return out[:3]

    def _is_recurring(self, question: ResearchQuestion, recent: List[ResearchQuestion]) -> bool:
        tokens = self._keywords(question.question)
        if not tokens:
            return False
        for old in recent[-5:]:
            other = self._keywords(old.question if hasattr(old, "question") else str(old))
            if not other:
                continue
            overlap = len(tokens & other) / max(len(tokens | other), 1)
            if overlap > 0.8:
                return True
        return False

    def _is_suppressed_by_lifecycle(self, question: ResearchQuestion, recent: List[Any]) -> bool:
        for old in recent[-20:]:
            status = self._field(old, "status")
            if status not in {"stale", "resolved"}:
                continue
            if self._same_question_family(question, old):
                return True
        return False

    def _same_question_family(self, question: ResearchQuestion, old: Any) -> bool:
        old_question = str(self._field(old, "question") or "")
        old_goal = str(self._field(old, "next_experiment_goal") or "")
        old_causes = self._field(old, "candidate_causes") or []
        if self._normalize(question.question) == self._normalize(old_question):
            return True
        question_cause = question.candidate_causes[0] if question.candidate_causes else ""
        old_cause = old_causes[0] if isinstance(old_causes, list) and old_causes else ""
        return (
            bool(question_cause)
            and str(question_cause) == str(old_cause)
            and self._normalize(question.next_experiment_goal) == self._normalize(old_goal)
        )

    def _field(self, item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    def _keywords(self, text: str) -> Set[str]:
        return {x for x in re.split(r"[\W_]+", text.lower()) if x}

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(text or "").lower())
