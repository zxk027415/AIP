"""
autoresearch_novelty_gate.py
第六代 AutoResearch 新颖性前置门控（T5 产出）。

职责：
  - 在回测执行前判断候选 patch 是否值得消耗资源
  - 基于 patch_fingerprint、changed_variables、历史 evidence 做去重和降权
  - 输出结构化 reason，避免黑盒跳过

设计原则：
  - 同 patch_signature 已跑过 → skip
  - 同 changed_variables 组合重复过多 → deprioritize
  - 近邻 patch 已有 multi_window_rejected → skip（除非 profile 条件不同）
  - 同一 run 内同 action 连续无效 → cooldown
  - 默认只跳过强重复，避免误杀 profile 不同的实验
"""

import hashlib
from typing import Any, Dict, List, Optional, Tuple


class NoveltyGateResult:
    """门控结果。

    Attributes:
        decision（决策）: "pass" / "skip" / "deprioritize"
        reason（原因）: 人类可读的跳过/降权理由
        confidence（置信度）: 0.0~1.0，越高越确定应跳过
    """
    __slots__ = ("decision", "reason", "confidence")

    def __init__(self, decision: str = "pass", reason: str = "", confidence: float = 0.0):
        self.decision = decision
        self.reason = reason
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {"decision": self.decision, "reason": self.reason, "confidence": self.confidence}


class AutoResearchNoveltyGate:
    """新颖性前置门控。在每个候选 patch 进入回测前调用 evaluate()。"""

    def __init__(
        self,
        *,
        max_same_variables_count: int = 4,
        cooldown_after_consecutive_failures: int = 3,
    ):
        self._max_same_variables = max_same_variables_count
        self._cooldown_threshold = cooldown_after_consecutive_failures

    def evaluate(
        self,
        *,
        patch_fingerprint: str,
        changed_variables: List[str],
        action_id: str = "",
        profile_fingerprint: str = "",
        evidence_records: Optional[List[Dict[str, Any]]] = None,
        candidate_pool: Optional[List[Dict[str, Any]]] = None,
        run_iterations: Optional[List[Dict[str, Any]]] = None,
    ) -> NoveltyGateResult:
        """
        评估候选 patch 的新颖性。

        Args:
            patch_fingerprint（补丁指纹）: 当前 patch 内容哈希
            changed_variables（变更变量列表）: 本次改了哪些参数名
            action_id（动作 ID）: 关联的 ResearchAction
            profile_fingerprint（画像指纹）: 当前数据画像哈希
            evidence_records（历史证据列表）: 来自 run state 或 evidence ledger
            candidate_pool（候选池列表）: 已有候选
            run_iterations（当前 run 的迭代记录列表）: 用于 cooldown 检测

        Returns:
            NoveltyGateResult 含 decision, reason, confidence
        """
        evidences = evidence_records or []
        pool = candidate_pool or []
        iterations = run_iterations or []

        # ── Rule 1: 同 patch_fingerprint 已跑过 → skip ──
        existing_fps = set()
        for e in evidences:
            fp = str(e.get("patch_fingerprint") or "")
            if fp:
                existing_fps.add(fp)
        for c in pool:
            sig = str(c.get("candidate_signature") or c.get("patch_fingerprint") or "")
            if sig:
                existing_fps.add(sig)

        if patch_fingerprint and patch_fingerprint in existing_fps:
            return NoveltyGateResult(
                decision="skip",
                reason=f"exact_duplicate: patch_fingerprint={patch_fingerprint[:12]}... 已在历史 evidence/pool 中",
                confidence=1.0,
            )

        # ── Rule 2: 同 changed_variables 组合重复过多 → deprioritize ──
        if changed_variables:
            vars_key = self._variables_key(changed_variables)
            same_vars_count = sum(
                1 for e in evidences
                if isinstance(e, dict) and self._variables_key(e.get("changed_variables") or []) == vars_key
            )
            if same_vars_count >= self._max_same_variables:
                return NoveltyGateResult(
                    decision="deprioritize",
                    reason=f"variable_saturation: {changed_variables} 已被尝试 {same_vars_count} 次，降低优先级",
                    confidence=0.7,
                )

        # ── Rule 3: 近邻 patch 已有 multi_window_rejected → skip（除非 profile 不同） ──
        if changed_variables:
            vars_key = self._variables_key(changed_variables)
            for e in evidences:
                if not isinstance(e, dict):
                    continue
                if str(e.get("evidence_strength")) != "multi_window_rejected":
                    continue
                e_vars_key = self._variables_key(e.get("changed_variables") or [])
                if e_vars_key != vars_key:
                    continue
                # 同变量组合已被多窗口拒绝
                e_profile = str(e.get("profile_fingerprint") or "")
                if profile_fingerprint and e_profile and e_profile != profile_fingerprint:
                    # profile 不同，允许重试
                    continue
                return NoveltyGateResult(
                    decision="skip",
                    reason=f"rejected_neighbor: 同变量组合 {changed_variables} 已被 multi_window_rejected，profile 条件相同",
                    confidence=0.85,
                )

        # ── Rule 4: 同 action 连续无效 → cooldown ──
        if action_id and iterations:
            consecutive_failures = 0
            for it in reversed(iterations):
                if not isinstance(it, dict):
                    continue
                it_action = str(it.get("action_id") or "")
                if it_action != action_id:
                    break
                ev = it.get("evaluation") or {}
                mi = ev.get("mape_improvement")
                if mi is not None and float(mi) <= 0:
                    consecutive_failures += 1
                else:
                    break
            if consecutive_failures >= self._cooldown_threshold:
                return NoveltyGateResult(
                    decision="skip",
                    reason=f"cooldown: action={action_id} 连续 {consecutive_failures} 轮无正收益，进入冷却期",
                    confidence=0.75,
                )

        # ── 通过门控 ──
        return NoveltyGateResult(decision="pass", reason="novel", confidence=0.0)

    def _variables_key(self, variables: Any) -> str:
        """将 changed_variables 列表转为可比较的规范化 key。"""
        if not variables:
            return ""
        items = sorted(str(v).strip().lower() for v in variables if str(v).strip())
        return hashlib.md5("|".join(items).encode()).hexdigest()[:12]
