import json
from typing import Any, Dict, List, Tuple

from services.llm_service import get_llm_service


RULE_KEYWORDS = {
    "drift": ["漂移", "drift", "分布变化", "概念漂移", "残差漂移"],
    "root_cause": ["根因", "原因", "为什么", "偏低", "特征重要性", "数据质量", "散点"],
    "retrain": ["重训", "重新训练", "再训练", "触发重训", "自动重训"],
    "tuning": ["调优", "调参", "优化参数", "模板调优", "候选参数"],
}

DEPENDENCIES = {
    "drift": [],
    "root_cause": ["drift"],
    "retrain": ["drift", "root_cause"],
    "tuning": ["drift", "root_cause"],
}


class OperationRouter:
    def __init__(self) -> None:
        self.rule_weight = 0.55
        self.llm_weight = 0.45
        self.direct_threshold = 0.65
        self.confirm_threshold = 0.45

    def _rule_scores(self, message: str) -> Dict[str, float]:
        msg = (message or "").lower()
        result: Dict[str, float] = {}
        for name, keywords in RULE_KEYWORDS.items():
            hit = sum(1 for kw in keywords if kw.lower() in msg)
            result[name] = min(1.0, hit / 2.0)  # 2+ hits => full score
        return result

    async def _llm_scores(self, message: str, context_hint: Dict[str, Any]) -> Tuple[Dict[str, float], str]:
        llm = await get_llm_service()
        if not llm:
            return {k: 0.0 for k in RULE_KEYWORDS}, "llm unavailable"
        prompt = (
            "你是意图路由器。请把用户需求分别打分到 drift/root_cause/retrain/tuning，"
            "每项 0~1，只返回 JSON。"
        )
        user_content = json.dumps(
            {
                "message": message,
                "context_hint": {
                    "workflow_id": context_hint.get("workflow_id"),
                    "template_summary": context_hint.get("template_summary"),
                },
                "targets": list(RULE_KEYWORDS.keys()),
                "format": {"scores": {"drift": 0.0, "root_cause": 0.0, "retrain": 0.0, "tuning": 0.0}, "reason": "text"},
            },
            ensure_ascii=False,
        )
        try:
            rsp = await llm.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_tokens=300,
            )
            raw = (rsp.get("content") or "").strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
            data = json.loads(raw)
            scores = data.get("scores") or {}
            normalized = {}
            for key in RULE_KEYWORDS:
                try:
                    v = float(scores.get(key, 0.0))
                except Exception:
                    v = 0.0
                normalized[key] = max(0.0, min(1.0, v))
            return normalized, str(data.get("reason") or "")
        except Exception as e:
            return {k: 0.0 for k in RULE_KEYWORDS}, f"llm parse failed: {e}"

    @staticmethod
    def _expand_dependencies(targets: List[str]) -> List[str]:
        ordered: List[str] = []

        def add_with_deps(t: str) -> None:
            for d in DEPENDENCIES.get(t, []):
                if d not in ordered:
                    add_with_deps(d)
            if t not in ordered:
                ordered.append(t)

        for target in targets:
            add_with_deps(target)
        return ordered

    async def route(self, message: str, preload_context: Dict[str, Any]) -> Dict[str, Any]:
        rule = self._rule_scores(message)
        llm, llm_reason = await self._llm_scores(message, preload_context)
        final = {
            k: self.rule_weight * rule.get(k, 0.0) + self.llm_weight * llm.get(k, 0.0)
            for k in RULE_KEYWORDS
        }
        ranked = sorted(final.items(), key=lambda x: x[1], reverse=True)
        selected = [name for name, score in ranked if score >= self.direct_threshold]
        if not selected and ranked and ranked[0][1] >= self.confirm_threshold:
            selected = [ranked[0][0]]
        confirmation_needed = not selected
        plan = self._expand_dependencies(selected)
        return {
            "rule_scores": rule,
            "llm_scores": llm,
            "final_scores": final,
            "ranked": ranked,
            "selected_targets": selected,
            "execution_plan": plan,
            "confirmation_needed": confirmation_needed,
            "llm_reason": llm_reason,
        }

