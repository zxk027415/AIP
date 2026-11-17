import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from . import autoresearch_paths as arp


LAYER_DIRS = {
    "L1": "raw_cases",
    "L2": "patterns",
    "L3": "anti_patterns",
    "L4": "hypothesis_templates",
}
LAYER_WEIGHTS = {"L1": 0.5, "L2": 1.0, "L3": 1.5, "L4": 2.0}
TYPE_MULTIPLIERS = {
    "causal_candidate": 2.0,
    "correlational": 1.0,
    "anti_pattern": 1.5,
    "hypothesis_template": 2.0,
}
KNOWLEDGE_STATUSES = {"candidate", "active", "stale", "rejected", "conflicted"}


@dataclass
class ClaimKey:
    target_param: str
    recommended_value: Any = None
    direction: Optional[str] = None
    metric: str = "mape"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeClaim:
    claim_key: ClaimKey
    claim: str
    condition: Dict[str, Any]
    evidence: List[str] = field(default_factory=list)
    counter_evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    knowledge_type: str = "correlational"
    layer: str = "L2"
    last_validated_at: Optional[str] = None
    status: str = "candidate"
    scenario_condition_hash: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.claim_key, dict):
            self.claim_key = ClaimKey(**self.claim_key)
        if not self.scenario_condition_hash:
            self.scenario_condition_hash = condition_hash(self.condition)
        if not self.last_validated_at:
            self.last_validated_at = datetime.utcnow().isoformat()
        self.confidence = round(float(self.confidence), 6)
        if self.status not in KNOWLEDGE_STATUSES:
            self.status = "candidate"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["claim_key"] = self.claim_key.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeClaim":
        return cls(**data)


@dataclass
class KnowledgeConflict:
    left: KnowledgeClaim
    right: KnowledgeClaim
    winner: Optional[KnowledgeClaim] = None
    unresolved: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "winner": self.winner.to_dict() if self.winner else None,
            "unresolved": self.unresolved,
            "reason": self.reason,
        }


def condition_hash(condition: Dict[str, Any]) -> str:
    raw = json.dumps(condition or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize_scenario_fingerprint(fingerprint: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Canonical scenario fields used by both knowledge ingestion and injection."""
    if not isinstance(fingerprint, dict):
        return {}
    allowed = (
        "granularity",
        "span_days",
        "load_type",
        "seasonality",
        "weekend_sensitivity",
        "anomaly_ratio",
        "backtest_mode",
        "train_days",
        "baseline_workflow_id",
        "registry_id",
    )
    return {
        key: fingerprint.get(key)
        for key in allowed
        if fingerprint.get(key) not in (None, "", [], {})
    }


class KnowledgeLayer:
    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or arp.as_str(arp.knowledge_dir())
        self._legacy_root_dir = arp.as_str(arp.legacy_knowledge_dir()) if root_dir is None else None
        for subdir in LAYER_DIRS.values():
            os.makedirs(os.path.join(self.root_dir, subdir), exist_ok=True)

    def ingest_run_insight(self, run_insight: Dict[str, Any]) -> List[KnowledgeClaim]:
        run_id = str(run_insight.get("run_id") or run_insight.get("id") or datetime.utcnow().timestamp())
        base_condition = normalize_scenario_fingerprint(run_insight.get("scenario_fingerprint"))
        if not isinstance(base_condition, dict):
            base_condition = normalize_scenario_fingerprint({
                "baseline_workflow_id": run_insight.get("baseline_workflow_id"),
                "registry_id": run_insight.get("registry_id"),
            })
        base_condition = {k: v for k, v in base_condition.items() if v not in (None, "", [], {})}
        claims: List[KnowledgeClaim] = []
        for item in run_insight.get("learned_rules", []) or []:
            claims.append(self._claim_from_insight(item, run_id, "L2", "correlational", base_condition))
        for item in run_insight.get("ineffective_attempts", []) or []:
            claims.append(self._claim_from_insight(item, run_id, "L3", "anti_pattern", base_condition))
        for claim in claims:
            self.save_claim(claim)
        return claims

    def ingest_evidence(self, evidence: Dict[str, Any]) -> Optional[KnowledgeClaim]:
        if not isinstance(evidence, dict):
            return None
        strength = str(evidence.get("evidence_strength") or "insufficient_evidence")
        if strength in {"insufficient_evidence", "single_window_negative"}:
            return None
        target = self._target_from_evidence(evidence)
        claim = KnowledgeClaim(
            claim_key=ClaimKey(
                target_param=target,
                recommended_value=evidence.get("patch_fingerprint"),
                direction="positive" if strength in {"single_window_positive", "multi_window_confirmed"} else "negative",
                metric="mape",
            ),
            claim=f"{target} evidence={strength} mape_improvement={evidence.get('mape_improvement')}",
            condition=normalize_scenario_fingerprint(evidence.get("scenario_fingerprint")) or {
                k: v for k, v in {
                    "target_direction": evidence.get("target_direction"),
                    "target_layer": evidence.get("target_layer"),
                }.items()
                if v not in (None, "", [], {})
            },
            evidence=[self._evidence_id(evidence)] if strength in {"single_window_positive", "multi_window_confirmed"} else [],
            counter_evidence=[self._evidence_id(evidence)] if strength == "multi_window_rejected" else [],
            knowledge_type="causal_candidate" if strength == "multi_window_confirmed" else "correlational",
            layer="L2" if strength != "multi_window_rejected" else "L3",
            status="active" if strength == "multi_window_confirmed" else "candidate",
        )
        return self.update_evidence(claim, self._evidence_id(evidence), supports=strength != "multi_window_rejected")

    def search(
        self,
        scenario_condition_hash: Optional[str] = None,
        layer: Optional[str] = None,
        knowledge_type: Optional[str] = None,
        target_param: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[Dict[str, Any]]:
        claims = self._load_claims(layer=layer)
        out = []
        for claim in claims:
            if scenario_condition_hash and claim.scenario_condition_hash != scenario_condition_hash:
                continue
            if knowledge_type and claim.knowledge_type != knowledge_type:
                continue
            if target_param and claim.claim_key.target_param != target_param:
                continue
            if claim.confidence < min_confidence:
                continue
            if claim.status == "rejected":
                continue
            out.append(claim.to_dict())
        return sorted(out, key=lambda x: x.get("confidence", 0.0), reverse=True)

    def get_injection_candidates(
        self,
        scenario_fingerprint: Optional[Dict[str, Any]] = None,
        min_confidence: float = 0.0,
    ) -> List[Dict[str, Any]]:
        current_hash = condition_hash(normalize_scenario_fingerprint(scenario_fingerprint))
        candidates = []
        for claim in self._load_claims():
            if claim.confidence < min_confidence:
                continue
            if claim.status == "rejected":
                continue
            layer_weight = LAYER_WEIGHTS.get(claim.layer, 1.0)
            type_multiplier = TYPE_MULTIPLIERS.get(claim.knowledge_type, 1.0)
            scenario_multiplier = 1.0 if claim.scenario_condition_hash == current_hash else 0.3
            if claim.status == "stale":
                scenario_multiplier *= 0.5
            if claim.status == "candidate":
                scenario_multiplier *= 0.65
            if claim.status == "conflicted":
                scenario_multiplier *= 0.25
            weight = layer_weight * type_multiplier * scenario_multiplier
            item = claim.to_dict()
            item["injection_weight"] = round(weight, 6)
            candidates.append(item)
        return sorted(candidates, key=lambda x: x["injection_weight"], reverse=True)

    def update_evidence(
        self,
        claim: KnowledgeClaim,
        run_id: str,
        supports: bool = True,
    ) -> KnowledgeClaim:
        target = self._find_existing(claim) or claim
        if supports:
            if run_id not in target.evidence:
                target.evidence.append(run_id)
            target.last_validated_at = datetime.utcnow().isoformat()
        else:
            if run_id not in target.counter_evidence:
                target.counter_evidence.append(run_id)
        target.confidence = self._confidence(target)
        if target.counter_evidence and len(target.counter_evidence) >= len(target.evidence or []):
            target.status = "conflicted" if target.evidence else "rejected"
        elif target.status == "active":
            target.status = "active"
        elif target.status in {"candidate", "stale"} and target.confidence >= 0.3 and len(target.evidence) >= 2:
            target.status = "active"
        elif len(target.evidence) < 2 and target.status not in {"conflicted", "rejected"}:
            target.status = "candidate"
        self.save_claim(target)
        return target

    def apply_decay(self, now: Optional[datetime] = None, decay_rate: float = 0.1) -> List[KnowledgeClaim]:
        now = now or datetime.utcnow()
        updated = []
        for claim in self._load_claims():
            if claim.layer not in ("L2", "L4") or not claim.last_validated_at:
                continue
            try:
                last = datetime.fromisoformat(claim.last_validated_at)
            except Exception:
                continue
            periods = int((now - last).days // 30)
            if periods <= 0:
                continue
            claim.confidence = round(max(0.0, claim.confidence - periods * decay_rate), 6)
            if claim.confidence < 0.3:
                claim.status = "stale"
            self.save_claim(claim, recompute_confidence=False)
            updated.append(claim)
        return updated

    def resolve_conflicts(self) -> List[KnowledgeConflict]:
        claims = self._load_claims()
        conflicts = []
        for i, left in enumerate(claims):
            for right in claims[i + 1 :]:
                if not self._is_conflict(left, right):
                    continue
                winner, reason = self._choose_winner(left, right)
                if winner is None:
                    left.status = "conflicted"
                    right.status = "conflicted"
                    self.save_claim(left, recompute_confidence=False)
                    self.save_claim(right, recompute_confidence=False)
                conflicts.append(
                    KnowledgeConflict(
                        left=left,
                        right=right,
                        winner=winner,
                        unresolved=winner is None,
                        reason=reason,
                    )
                )
        return conflicts

    def save_claim(self, claim: KnowledgeClaim, recompute_confidence: bool = True) -> None:
        if recompute_confidence and (claim.evidence or claim.counter_evidence):
            claim.confidence = self._confidence(claim)
        subdir = LAYER_DIRS.get(claim.layer, "patterns")
        filename = self._filename(claim)
        path = os.path.join(self.root_dir, subdir, filename)
        self._atomic_write(path, claim.to_dict())
        # @AI_GENERATED: Phase 1 双写 — 写完 JSON 后同步 upsert 到 MySQL knowledge_claim 表
        self._dual_write_claim_to_db(claim, filename)
        # @AI_GENERATED: end

    # @AI_GENERATED: Phase 1 双写 — knowledge_claim 表 upsert
    def _dual_write_claim_to_db(self, claim: KnowledgeClaim, filename: str) -> None:
        """把 KnowledgeClaim 同步 upsert 到 MySQL knowledge_claim 表。

        字段映射：
          - id                    ← filename 去 .json 后缀（复用文件名 hash，跟 JSON 保持一致）
          - slot                  ← condition.slot / baseline_workflow_id / "default" 兜底
          - scenario_fingerprint  ← claim.scenario_condition_hash
          - claim_type            ← claim.knowledge_type
          - claim_data            ← claim.to_dict() 整体
          - confidence            ← claim.confidence
          - source_run_id         ← claim.evidence[0]（第一条证据的 run_id）
          - decayed_at            ← status='stale' 时设置为当前时间，否则 None

        失败降级：只 warning 不抛，保证 JSON 写入成功后主流程继续。
        """
        try:
            from services.db.repositories import get_autoresearch_repo, is_dual_write_enabled
            if not is_dual_write_enabled():
                return
            repo = get_autoresearch_repo()
            if repo is None:
                return

            claim_dict = claim.to_dict()
            condition = claim.condition or {}
            slot = (
                condition.get("slot")
                or condition.get("baseline_workflow_id")
                or "default"
            )
            source_run_id = None
            if claim.evidence:
                source_run_id = str(claim.evidence[0])[:64]

            decayed_at = None
            if str(claim.status).lower() == "stale":
                decayed_at = datetime.utcnow()

            repo.upsert_claim({
                "id": filename[:-5] if filename.endswith(".json") else filename,
                "slot": str(slot)[:64],
                "scenario_fingerprint": (claim.scenario_condition_hash or "")[:256],
                "claim_type": str(claim.knowledge_type)[:64],
                "claim_data": claim_dict,
                "confidence": float(claim.confidence or 0.0),
                "source_run_id": source_run_id,
                "decayed_at": decayed_at,
            })
        except Exception as exc:
            # 只 warning 不 raise —— DB 写入失败不能阻塞 JSON 写入路径
            try:
                import logging
                logging.getLogger(__name__).warning(
                    "KnowledgeLayer dual-write to knowledge_claim failed (non-fatal): %s", exc
                )
            except Exception:
                pass
    # @AI_GENERATED: end

    def _claim_from_insight(
        self,
        item: Any,
        run_id: str,
        layer: str,
        knowledge_type: str,
        base_condition: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeClaim:
        if isinstance(item, str):
            item = {"claim": item, "description": item}
        elif not isinstance(item, dict):
            item = {"claim": str(item), "description": str(item)}
        key = item.get("claim_key") or {}
        if not isinstance(key, dict):
            key = {}
        if "target_param" not in key:
            key["target_param"] = item.get("target_param") or item.get("param") or f"{knowledge_type}_text"
        if key.get("target_param") == f"{knowledge_type}_text" and key.get("recommended_value") is None:
            claim_text = str(item.get("claim") or item.get("description") or item)
            key["recommended_value"] = hashlib.sha256(claim_text.encode("utf-8")).hexdigest()[:12]
        condition = item.get("condition")
        if not isinstance(condition, dict):
            condition = dict(base_condition or {})
        claim = KnowledgeClaim(
            claim_key=ClaimKey(**key),
            claim=str(item.get("claim") or item.get("description") or item),
            condition=condition,
            evidence=[run_id],
            knowledge_type=knowledge_type,
            layer=layer,
            status="candidate",
        )
        claim.confidence = self._confidence(claim)
        if len(claim.evidence) >= 2 and claim.confidence >= 0.3:
            claim.status = "active"
        return claim

    def _load_claims(self, layer: Optional[str] = None) -> List[KnowledgeClaim]:
        layers = [layer] if layer else list(LAYER_DIRS)
        claims = []
        seen_filenames: set = set()
        for item_layer in layers:
            subdir_name = LAYER_DIRS.get(item_layer, "patterns")
            # 优先读新路径
            subdir = os.path.join(self.root_dir, subdir_name)
            if os.path.isdir(subdir):
                for name in os.listdir(subdir):
                    if not name.endswith(".json"):
                        continue
                    seen_filenames.add((item_layer, name))
                    path = os.path.join(subdir, name)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        claims.append(KnowledgeClaim.from_dict(data))
                    except Exception:
                        continue
            # 旧路径兜底：只读新路径里没有的文件
            legacy_subdir = os.path.join(self._legacy_root_dir, subdir_name) if self._legacy_root_dir else ""
            if legacy_subdir and legacy_subdir != subdir and os.path.isdir(legacy_subdir):
                for name in os.listdir(legacy_subdir):
                    if not name.endswith(".json"):
                        continue
                    if (item_layer, name) in seen_filenames:
                        continue
                    path = os.path.join(legacy_subdir, name)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        claims.append(KnowledgeClaim.from_dict(data))
                    except Exception:
                        continue
        return claims

    def _find_existing(self, claim: KnowledgeClaim) -> Optional[KnowledgeClaim]:
        for existing in self._load_claims(layer=claim.layer):
            if existing.claim_key.to_dict() == claim.claim_key.to_dict():
                return existing
        return None

    def _confidence(self, claim: KnowledgeClaim) -> float:
        e = len(set(claim.evidence))
        c = len(set(claim.counter_evidence))
        text_targets = {"correlational_text", "anti_pattern_text"}
        if claim.claim_key.target_param in text_targets and e < 2:
            return 0.2 if e else 0.0
        if e >= 3 and c == 0:
            return 0.85
        total = e + c
        if total == 0:
            return float(claim.confidence)
        return round(max(0.0, min(1.0, e / total)), 6)

    def _target_from_evidence(self, evidence: Dict[str, Any]) -> str:
        changed = evidence.get("changed_variables")
        if isinstance(changed, list) and changed:
            return str(changed[0])
        return str(evidence.get("target_direction") or evidence.get("target_layer") or "unknown")

    def _evidence_id(self, evidence: Dict[str, Any]) -> str:
        return (
            f"{evidence.get('run_id')}:iter{evidence.get('iteration')}:"
            f"group{evidence.get('group_idx')}:{evidence.get('patch_fingerprint')}"
        )

    def _is_conflict(self, left: KnowledgeClaim, right: KnowledgeClaim) -> bool:
        if left.claim_key.target_param != right.claim_key.target_param:
            return False
        if left.claim_key.direction and right.claim_key.direction:
            if left.claim_key.direction != right.claim_key.direction:
                return True
        return left.claim_key.recommended_value != right.claim_key.recommended_value

    def _choose_winner(
        self,
        left: KnowledgeClaim,
        right: KnowledgeClaim,
    ) -> Tuple[Optional[KnowledgeClaim], str]:
        left_specificity = len(left.condition or {})
        right_specificity = len(right.condition or {})
        if left_specificity != right_specificity:
            return (left if left_specificity > right_specificity else right), "condition_specificity"

        left_time = self._parse_time(left.last_validated_at)
        right_time = self._parse_time(right.last_validated_at)
        if left_time != right_time:
            return (left if left_time > right_time else right), "recency"

        if left.confidence != right.confidence:
            return (left if left.confidence > right.confidence else right), "confidence"
        return None, "unresolved"

    def _parse_time(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.min
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return datetime.min

    def _filename(self, claim: KnowledgeClaim) -> str:
        raw = json.dumps(claim.claim_key.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16] + ".json"

    def _atomic_write(self, path: str, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
