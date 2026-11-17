import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional


QUESTION_DIRECTIONS = {"parameter", "feature", "model", "data", "risk"}


@dataclass
class GLMQuestionResult:
    questions: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "rule"
    llm_used: bool = False
    llm_error: Optional[str] = None
    disabled_reason: Optional[str] = None


class AutoResearchGLMQuestionGenerator:
    """Controlled GLM question generator.

    GLM is only allowed to propose research questions. The auditor keeps
    lifecycle, evidence, and executable-direction constraints in code.
    """

    def __init__(
        self,
        glm_chat_json: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
        *,
        enabled: bool = False,
    ):
        self.glm_chat_json = glm_chat_json
        self.enabled = bool(enabled)

    async def generate(
        self,
        *,
        context: Dict[str, Any],
        fallback_questions: List[Dict[str, Any]],
        recent_questions: List[Dict[str, Any]],
    ) -> GLMQuestionResult:
        fallback = self._mark_fallback(fallback_questions)
        if not self.enabled:
            return GLMQuestionResult(
                questions=fallback,
                source="rule",
                llm_used=False,
                disabled_reason="GLM_RESEARCH_QUESTIONS_ENABLE_or_GLM_ENABLE_not_enabled",
            )
        if self.glm_chat_json is None:
            return GLMQuestionResult(
                questions=fallback,
                source="rule",
                llm_used=False,
                disabled_reason="glm_chat_json_unavailable",
            )

        try:
            response = await self._call_glm(context=context, recent_questions=recent_questions)
            raw_candidates = self._extract_candidates(response)
            accepted, rejected = self.audit_candidates(
                raw_candidates,
                context=context,
                recent_questions=recent_questions,
            )
            if accepted:
                return GLMQuestionResult(
                    questions=accepted,
                    rejected=rejected,
                    source="glm",
                    llm_used=True,
                )
            return GLMQuestionResult(
                questions=self._mark_fallback(fallback_questions, source="glm_fallback"),
                rejected=rejected,
                source="glm_fallback",
                llm_used=True,
                llm_error="no_accepted_questions",
            )
        except Exception as exc:
            return GLMQuestionResult(
                questions=self._mark_fallback(fallback_questions, source="glm_fallback"),
                rejected=[],
                source="glm_fallback",
                llm_used=True,
                llm_error=str(exc)[:300],
            )

    def audit_candidates(
        self,
        candidates: List[Dict[str, Any]],
        *,
        context: Dict[str, Any],
        recent_questions: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        evidence_context = {
            "evidence": context.get("evidence") or [],
            "tri_dataset_diagnosis": context.get("tri_dataset_diagnosis") or {},
            "dataset_profile": context.get("dataset_profile") or {},
            "cross_window_pattern": context.get("cross_window_pattern") or {},
            "evidence_records": context.get("evidence_records") or [],
            "evaluation": context.get("evaluation") or {},
            "exploration_health": context.get("exploration_health") or {},
        }
        evidence_text = self._normalize(json.dumps(evidence_context, ensure_ascii=False, sort_keys=True))
        active_layers = set(str(x) for x in context.get("active_layers") or [])
        for idx, item in enumerate(candidates or []):
            row = dict(item) if isinstance(item, dict) else {}
            reason = self._reject_reason(row, evidence_text=evidence_text, recent_questions=recent_questions)
            direction = str(row.get("target_direction") or "").strip()
            target_layer = str(row.get("target_layer") or direction or "").strip()
            if reason:
                row["audit_status"] = "rejected"
                row["reject_reason"] = reason
                row["candidate_index"] = idx
                rejected.append(row)
                continue
            row["audit_status"] = "accepted"
            row["proposal_source"] = "glm"
            row["target_direction"] = direction
            row["target_layer"] = target_layer or direction
            # soft check: evidence_refs 是否在上下文中可验证（不阻止，仅标记）
            if evidence_text and not any(self._normalize(ref) in evidence_text for ref in self._as_str_list(row.get("evidence_refs"))):
                row.setdefault("audit_warning", "evidence_refs_unverified")
            if active_layers and row["target_layer"] not in active_layers and direction != "risk":
                row["audit_warning"] = "target_layer_not_currently_active"
            row["candidate_causes"] = self._as_str_list(row.get("candidate_causes"))
            row["evidence_refs"] = self._as_str_list(row.get("evidence_refs"))
            row["evidence"] = row["evidence_refs"]
            row["risk_level"] = str(row.get("risk_level") or "medium")
            row["recurring"] = False
            row["priority"] = float(row.get("priority") or 1.2)
            accepted.append(row)
        return accepted[:3], rejected[:10]

    async def _call_glm(
        self,
        *,
        context: Dict[str, Any],
        recent_questions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        system_prompt = (
            "你是 AutoResearch 的 Questioner Agent。你只能输出 JSON。"
            "你的任务是提出可验证、可执行、非重复的研究问题，不允许直接写 patch。"
        )
        user_prompt = json.dumps(
            {
                "task": "generate_research_questions",
                "allowed_target_direction": sorted(QUESTION_DIRECTIONS),
                "required_fields": [
                    "question",
                    "target_direction",
                    "target_layer",
                    "candidate_causes",
                    "evidence_refs",
                    "next_experiment_goal",
                    "expected_patch_intent",
                    "novelty_reason",
                    "risk_level",
                ],
                "rules": [
                    "每个问题必须能映射到一次后续实验目标",
                    "不要重复 recent_questions 中 stale 或 resolved 的同族问题",
                    "优先覆盖 direction_coverage 较低的方向",
                    "不要生成泛泛而谈的问题",
                    "输出 3 到 6 个候选，放在 questions 数组中",
                ],
                "context": context,
                "recent_questions": recent_questions[-20:],
            },
            ensure_ascii=False,
        )
        result = self.glm_chat_json(system_prompt, user_prompt, temperature=0.25)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, dict) else {}

    def _extract_candidates(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        obj = response
        content = response.get("content") if isinstance(response, dict) else None
        if isinstance(content, str):
            parsed = self._parse_json_text(content)
            if isinstance(parsed, dict):
                obj = parsed
        rows = obj.get("questions") or obj.get("research_questions") or obj.get("candidates") if isinstance(obj, dict) else None
        if not isinstance(rows, list):
            rows = []
        return [dict(x) for x in rows if isinstance(x, dict)]

    def _reject_reason(
        self,
        row: Dict[str, Any],
        *,
        evidence_text: str,
        recent_questions: List[Dict[str, Any]],
    ) -> Optional[str]:
        question = str(row.get("question") or "").strip()
        direction = str(row.get("target_direction") or "").strip()
        goal = str(row.get("next_experiment_goal") or "").strip()
        evidence_refs = self._as_str_list(row.get("evidence_refs") or row.get("evidence"))
        if not question:
            return "missing_question"
        if direction not in QUESTION_DIRECTIONS:
            return "invalid_target_direction"
        if not goal:
            return "missing_next_experiment_goal"
        if not evidence_refs:
            return "missing_evidence_refs"
        # 放宽审计：evidence_refs 非空即可，不再要求精确子串匹配。
        # GLM 自由生成的引用名称不可能和 state 字段名完全一致，
        # 强制精确匹配会导致所有 GLM 问题被拒。改为 warning 而非 reject。
        if self._is_stale_or_resolved_duplicate(row, recent_questions):
            return "duplicate_stale_or_resolved_question"
        return None

    def _is_stale_or_resolved_duplicate(self, row: Dict[str, Any], recent_questions: List[Dict[str, Any]]) -> bool:
        row_question = self._normalize(str(row.get("question") or ""))
        row_goal = self._normalize(str(row.get("next_experiment_goal") or ""))
        row_cause = self._as_str_list(row.get("candidate_causes"))
        primary_cause = row_cause[0] if row_cause else ""
        for old in recent_questions[-50:]:
            if not isinstance(old, dict):
                continue
            if str(old.get("status") or "") not in {"stale", "resolved"}:
                continue
            old_question = self._normalize(str(old.get("question") or ""))
            if old_question and old_question == row_question:
                return True
            old_causes = self._as_str_list(old.get("candidate_causes"))
            old_cause = old_causes[0] if old_causes else ""
            old_goal = self._normalize(str(old.get("next_experiment_goal") or ""))
            if primary_cause and old_cause == primary_cause and old_goal == row_goal:
                return True
        return False

    def _mark_fallback(self, rows: List[Dict[str, Any]], *, source: str = "rule") -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item.setdefault("proposal_source", source)
            item.setdefault("audit_status", "fallback" if source != "glm" else "accepted")
            item.setdefault("target_direction", self._infer_direction(item))
            item.setdefault("target_layer", item.get("target_direction"))
            out.append(item)
        return out

    def _infer_direction(self, row: Dict[str, Any]) -> str:
        causes = " ".join(self._as_str_list(row.get("candidate_causes")))
        text = f"{causes} {row.get('question') or ''} {row.get('next_experiment_goal') or ''}".lower()
        if "period" in text or "feature" in text or "特征" in text:
            return "feature"
        if "data" in text or "drift" in text or "漂移" in text:
            return "data"
        if "model" in text or "过拟合" in text:
            return "model"
        return "parameter"

    def _parse_json_text(self, text: str) -> Optional[Dict[str, Any]]:
        cleaned = str(text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            obj = json.loads(cleaned)
            return obj if isinstance(obj, dict) else None
        except Exception:
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            if not match:
                return None
            try:
                obj = json.loads(match.group(0))
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None

    def _as_str_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(x) for x in value if str(x or "").strip()]
        if value is None:
            return []
        return [str(value)] if str(value).strip() else []

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(text or "").lower())
