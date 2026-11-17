import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


QUESTION_STATUSES = {"open", "testing", "resolved", "stale"}


class AutoResearchQuestionLifecycle:
    def question_key(self, question: str) -> str:
        text = re.sub(r"\s+", "", str(question or "").lower())
        text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else "unknown"

    def question_key_from_item(self, item: Dict[str, Any]) -> str:
        causes = [
            str(c).strip().lower()
            for c in item.get("candidate_causes") or []
            if str(c or "").strip()
        ]
        goal = self._normalize_key_text(str(item.get("next_experiment_goal") or ""))
        question = self._normalize_key_text(str(item.get("question") or ""))
        if causes and (goal or question):
            return self.question_key("|".join([causes[0], goal or question]))
        return self.question_key(str(item.get("question") or ""))

    def merge_questions(
        self,
        existing: List[Dict[str, Any]],
        new_questions: List[Dict[str, Any]],
        *,
        iteration: int,
        patch_fingerprint: Optional[str] = None,
        evidence_records: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        by_key: Dict[str, Dict[str, Any]] = {}
        ordered: List[Dict[str, Any]] = []
        for item in existing or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("question_key") or self.question_key_from_item(item))
            row = dict(item)
            row["question_key"] = key
            if row.get("iteration") is None:
                row["iteration"] = int(row.get("last_seen_iteration") or row.get("first_seen_iteration") or 0)
            by_key[key] = row
            ordered.append(row)

        evidence_keys = [
            str(e.get("patch_fingerprint") or "")
            for e in evidence_records or []
            if isinstance(e, dict) and e.get("patch_fingerprint")
        ]
        has_confirming_evidence = any(
            str(e.get("evidence_strength")) == "multi_window_confirmed"
            for e in evidence_records or []
            if isinstance(e, dict)
        )
        for item in new_questions or []:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            key = str(item.get("question_key") or self.question_key_from_item(item))
            row = by_key.get(key)
            if row is None:
                row = {
                    "question_key": key,
                    "question": question,
                    "iteration": int(iteration or 0),
                    "status": "open",
                    "first_seen_iteration": int(iteration or 0),
                    "last_seen_iteration": int(iteration or 0),
                    "evidence_count": 0,
                    "tested_patch_fingerprints": [],
                    "linked_knowledge_claims": [],
                    "next_experiment_goal": item.get("next_experiment_goal") or "",
                    "candidate_causes": list(item.get("candidate_causes") or []),
                    "evidence": list(item.get("evidence") or []),
                    "created_at": now,
                    "updated_at": now,
                    "recurring": False,
                    "priority": item.get("priority", 1.0),
                }
                for extra_key in (
                    "proposal_source",
                    "audit_status",
                    "target_direction",
                    "target_layer",
                    "evidence_refs",
                    "expected_patch_intent",
                    "novelty_reason",
                    "risk_level",
                ):
                    if item.get(extra_key) is not None:
                        row[extra_key] = item.get(extra_key)
                by_key[key] = row
                ordered.append(row)
            else:
                if str(row.get("status") or "") in {"stale", "resolved"} and not has_confirming_evidence:
                    row["suppressed_seen_count"] = int(row.get("suppressed_seen_count") or 0) + 1
                    row["last_suppressed_iteration"] = int(iteration or row.get("last_suppressed_iteration") or 0)
                    row["updated_at"] = now
                    continue
                row["last_seen_iteration"] = int(iteration or row.get("last_seen_iteration") or 0)
                row["iteration"] = row["last_seen_iteration"]
                row["updated_at"] = now
                row["recurring"] = True
                row["priority"] = max(float(row.get("priority") or 1.0), float(item.get("priority") or 1.0))
                if item.get("next_experiment_goal"):
                    row["next_experiment_goal"] = item.get("next_experiment_goal")
                row["candidate_causes"] = self._merge_list(row.get("candidate_causes"), item.get("candidate_causes"))
                row["evidence"] = self._merge_list(row.get("evidence"), item.get("evidence"))
                for extra_key in (
                    "proposal_source",
                    "audit_status",
                    "target_direction",
                    "target_layer",
                    "expected_patch_intent",
                    "novelty_reason",
                    "risk_level",
                ):
                    if item.get(extra_key) is not None:
                        row[extra_key] = item.get(extra_key)
                if item.get("evidence_refs") is not None:
                    row["evidence_refs"] = self._merge_list(row.get("evidence_refs"), item.get("evidence_refs"))

            tested = list(row.get("tested_patch_fingerprints") or [])
            for fp in [patch_fingerprint, *evidence_keys]:
                if fp and fp not in tested:
                    tested.append(str(fp))
            row["tested_patch_fingerprints"] = tested[-20:]
            if tested and row.get("status") == "open":
                row["status"] = "testing"
            row["evidence_count"] = int(row.get("evidence_count") or 0) + len(evidence_keys)

        self.apply_evidence(ordered, evidence_records or [], iteration=iteration)
        return ordered[-100:]

    def apply_evidence(
        self,
        questions: List[Dict[str, Any]],
        evidence_records: List[Dict[str, Any]],
        *,
        iteration: int,
    ) -> None:
        positive_confirmed = any(
            str(e.get("evidence_strength")) == "multi_window_confirmed"
            for e in evidence_records or []
            if isinstance(e, dict)
        )
        rejected_or_negative = any(
            str(e.get("evidence_strength")) in {"multi_window_rejected", "single_window_negative"}
            for e in evidence_records or []
            if isinstance(e, dict)
        )
        for row in questions or []:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "open")
            if positive_confirmed and status in {"open", "testing"}:
                row["status"] = "resolved"
                row["resolution_reason"] = "multi_window_confirmed"
                row["evidence_status"] = "resolved_positive"
            elif rejected_or_negative and status == "testing":
                first = int(row.get("first_seen_iteration") or iteration or 0)
                if int(iteration or 0) - first >= 3:
                    row["status"] = "stale"
                    row["resolution_reason"] = "counter_evidence_or_repeated_negative"
                    row["evidence_status"] = "stale_with_counter_evidence"
            if status not in QUESTION_STATUSES:
                row["status"] = "open"

    def _merge_list(self, left: Any, right: Any) -> List[Any]:
        out: List[Any] = []
        for seq in (left, right):
            for item in seq or []:
                if item not in out:
                    out.append(item)
        return out

    def _normalize_key_text(self, value: str) -> str:
        text = re.sub(r"\s+", "", str(value or "").lower())
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
