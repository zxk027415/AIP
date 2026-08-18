# @AI_GENERATED
# -*- coding: utf-8 -*-
"""按路径 Challenger 重训触发与严格精度守门。

所有训练产物先登记为 Challenger；只有评测样本、划分、随机种子、指标和生产契约完全同口径，
且指标严格优于当前 Champion 加 margin，才调用 PVModelRegistry 的路径内晋升。该服务从不修改
``production_path`` — 当前生产路径。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import math
from typing import Any, Dict, Optional

from services.iterative_labeling.pv_model_registry import (
    LifecycleOperationResult,
    ModelRegistration,
    PVModelRegistry,
)


@dataclass(frozen=True)
class RetrainTriggerDecision:
    """自动/手动 Challenger 重训触发判定。"""

    should_trigger: bool
    trigger_reason: Optional[str]
    pending_change_count: int
    threshold: int
    period_days: int


@dataclass(frozen=True)
class EvaluationContract:
    """Champion/Challenger 必须一致的评测合同。"""

    sample_digest: str
    split_digest: str
    random_seed: int
    metric_name: str
    production_contract_digest: str
    production_contract_valid: bool
    seq_len: Optional[int] = None
    trained_full_day: Optional[bool] = None

    def validate(self, modeling_path: str) -> Optional[str]:
        if not all(
            str(value or "").strip()
            for value in (
                self.sample_digest,
                self.split_digest,
                self.metric_name,
                self.production_contract_digest,
            )
        ):
            return "evaluation_contract_incomplete"
        if (
            not isinstance(self.random_seed, int)
            or isinstance(self.random_seed, bool)
            or self.random_seed < 0
        ):
            return "random_seed_invalid"
        if not isinstance(self.production_contract_valid, bool):
            return "production_contract_valid_not_boolean"
        if not self.production_contract_valid:
            return "production_contract_failed"
        if modeling_path == "seq_annotation":
            if self.seq_len != 288 or self.trained_full_day is not True:
                return "seq_288_full_day_contract_failed"
        return None


class AccuracyGatedRetrainer:
    """重训触发与 PVModelRegistry 路径内模型治理协调器。"""

    def __init__(
        self,
        registry: PVModelRegistry,
        *,
        retrain_change_threshold: int = 200,
        retrain_period_days: int = 7,
        promotion_margin: float = 0.0,
    ) -> None:
        if retrain_change_threshold < 1:
            raise ValueError("retrain_change_threshold 必须大于 0")
        if retrain_period_days < 1:
            raise ValueError("retrain_period_days 必须大于 0")
        if promotion_margin < 0:
            raise ValueError("promotion_margin 不能为负数")
        self._registry = registry
        self._threshold = int(retrain_change_threshold)
        self._period_days = int(retrain_period_days)
        self._margin = float(promotion_margin)

    def maybe_trigger(
        self,
        *,
        pending_change_count: int,
        last_retrained_at: Optional[datetime],
        now: Optional[datetime] = None,
        manual: bool = False,
    ) -> RetrainTriggerDecision:
        """自动触发必须同时满足变更阈值和周期；手动仅要求存在未消费变更。"""

        pending = max(0, int(pending_change_count))
        current = now or datetime.utcnow()
        period_elapsed = (
            last_retrained_at is None
            or current - last_retrained_at >= timedelta(days=self._period_days)
        )
        if manual:
            reason = "manual" if pending > 0 else None
        elif pending >= self._threshold and period_elapsed:
            reason = "auto_threshold_and_period"
        else:
            reason = None
        return RetrainTriggerDecision(
            should_trigger=reason is not None,
            trigger_reason=reason,
            pending_change_count=pending,
            threshold=self._threshold,
            period_days=self._period_days,
        )

    def register_challenger(
        self,
        modeling_path: str,
        *,
        slot: str,
        model_ref: str,
        evaluation_id: str,
        gate_metric_value: float,
        contract: EvaluationContract,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LifecycleOperationResult:
        """先登记 Challenger；合同不合法时保留候选并写阻断原因。"""

        metric_value = float(gate_metric_value)
        if not math.isfinite(metric_value):
            raise ValueError("gate_metric_value 必须是有限数值")
        registration = ModelRegistration(
            model_ref=str(model_ref),
            evaluation_id=str(evaluation_id),
            gate_metric_value=metric_value,
            registered_at=datetime.utcnow().isoformat(),
            metric_name=contract.metric_name,
            metadata={
                **dict(metadata or {}),
                "evaluation_contract": asdict(contract),
            },
        )
        return self._registry.register_challenger(
            modeling_path,
            registration,
            slot=slot,
            qualification_validator=lambda *_: (
                contract.validate(modeling_path) is None,
                contract.validate(modeling_path),
            ),
        )

    def promote_if_qualified(
        self,
        modeling_path: str,
        evaluation_id: str,
        *,
        slot: str,
        metric_direction: str = "higher_is_better",
    ) -> LifecycleOperationResult:
        """同口径且严格更优时路径内晋升；平局在 margin=0 时也拒绝。"""

        def validate_contract(candidate, champion, path, _slot):  # type: ignore[no-untyped-def]
            raw = dict(candidate.metadata.get("evaluation_contract") or {})
            try:
                candidate_contract = EvaluationContract(**raw)
            except (TypeError, ValueError):
                return False, "evaluation_contract_incomplete"
            invalid = candidate_contract.validate(path)
            if invalid:
                return False, invalid
            if candidate.metric_name != candidate_contract.metric_name:
                return False, "candidate_metric_name_mismatch"
            if champion is None:
                return True, None
            champion_raw = dict(champion.metadata.get("evaluation_contract") or {})
            try:
                champion_contract = EvaluationContract(**champion_raw)
            except (TypeError, ValueError):
                return False, "champion_evaluation_contract_missing"
            comparable_fields = (
                "sample_digest",
                "split_digest",
                "random_seed",
                "metric_name",
                "production_contract_digest",
            )
            if any(
                getattr(candidate_contract, field) != getattr(champion_contract, field)
                for field in comparable_fields
            ):
                return False, "evaluation_contract_not_comparable"
            return True, None

        return self._registry.promote_within_path(
            modeling_path,
            evaluation_id,
            slot=slot,
            promotion_margin=self._margin,
            metric_direction=metric_direction,
            production_contract_validator=validate_contract,
        )

    def register_and_evaluate(
        self,
        modeling_path: str,
        *,
        slot: str,
        model_ref: str,
        evaluation_id: str,
        gate_metric_value: float,
        contract: EvaluationContract,
        metric_direction: str = "higher_is_better",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, LifecycleOperationResult]:
        """按“先 Challenger、后路径内门控”顺序执行，绝不跨路径切换。"""

        registered = self.register_challenger(
            modeling_path,
            slot=slot,
            model_ref=model_ref,
            evaluation_id=evaluation_id,
            gate_metric_value=gate_metric_value,
            contract=contract,
            metadata=metadata,
        )
        if registered.status in {"evaluation_id_conflict", "registered_blocked"}:
            promoted = LifecycleOperationResult(
                status="rejected",
                changed=False,
                reason=registered.reason or registered.status,
                registration=registered.registration,
            )
        else:
            promoted = self.promote_if_qualified(
                modeling_path,
                evaluation_id,
                slot=slot,
                metric_direction=metric_direction,
            )
        return {"registration": registered, "promotion": promoted}


__all__ = [
    "AccuracyGatedRetrainer",
    "EvaluationContract",
    "RetrainTriggerDecision",
]
# @AI_GENERATED: end
