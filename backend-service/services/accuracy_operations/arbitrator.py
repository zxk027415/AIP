# @AI_GENERATED
"""精度运营恢复仲裁器：生成建议，并委托部署状态机执行通道 A。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from services.accuracy_operations.models import AccuracyAlert, AlertStatus, DecisionStatus, RCAReport, RecoveryChannel, RecoveryDecision
from services.accuracy_operations.store import AccuracyOperationsStore
from services.precision_ops.utils import now_iso

logger = logging.getLogger(__name__)

CONF_GATE = 0.6
_SLA = {"shadow_switch": 2, "observe": 12}


class RecoveryArbitrator:
    """基于 RCA 和版本级指标推荐恢复动作；发布状态只由部署服务变更。"""

    def __init__(
        self,
        version_registry: Any,
        accuracy_tracker: Any,
        config_manager: Any,
        switch_engine: Any,
        store: AccuracyOperationsStore,
        deployment_slot_store: Optional[Any] = None,
    ) -> None:
        self._version_registry = version_registry
        self._accuracy_tracker = accuracy_tracker
        self._config_manager = config_manager
        self._switch_engine = switch_engine
        self._store = store
        self._deployment_slot_store = deployment_slot_store

    def decide(self, slot: str, rca_report_id: str) -> RecoveryDecision:
        """保存通道 A/观察建议；不会在此处变更部署槽位。"""
        rca = self._store.get_rca(slot, rca_report_id)
        if rca is None or rca.status != "succeeded":
            raise ValueError(f"RCAReport 不存在或未成功：slot={slot!r}, rca_report_id={rca_report_id!r}")
        alert = self._store.get_alert(slot, rca.alert_id)
        if alert is None:
            raise ValueError(f"关联告警不存在：slot={slot!r}, alert_id={rca.alert_id!r}")

        if rca.confidence < CONF_GATE or rca.undetermined:
            return self._finalize(slot, self._build_decision(rca, RecoveryChannel.observe, "RCA 置信度不足或根因未确定", False), alert)
        if "external" in (rca.root_cause or "").lower():
            return self._finalize(slot, self._build_decision(rca, RecoveryChannel.observe, "外部因素，先观察而不切换模型", True), alert)
        if self._store.has_active_switch(slot):
            return self._finalize(slot, self._build_decision(rca, RecoveryChannel.observe, "已有执行中的通道 A 建议，等待部署结果", True), alert)

        qualified = self._find_qualified_shadow(slot)
        if qualified is None:
            return self._finalize(slot, self._build_decision(rca, RecoveryChannel.observe, "无满足多窗口优势和最小样本门槛的影子版本", True), alert)

        shadow, metrics = qualified
        target_workflow_id = shadow["workflow_id"]
        target_version_tag = shadow.get("version_tag") or ""
        score = self._comparison_metric(metrics)
        decision = self._build_decision(
            rca,
            RecoveryChannel.shadow_switch,
            f"影子版本 {target_workflow_id}@{target_version_tag} 的 7 天指标为 {score:.4f}，满足通道 A 条件",
            True,
            target_workflow_id=target_workflow_id,
            target_version_tag=target_version_tag,
        )
        return self._finalize(slot, decision, alert)

    def execute_switch(self, slot: str, decision: RecoveryDecision, alert: AccuracyAlert) -> RecoveryDecision:
        """将已批准建议交给部署 ``SwitchDecisionEngine`` 执行和审计。"""
        if decision.channel != RecoveryChannel.shadow_switch.value:
            raise ValueError("只有 shadow_switch 决策可以执行通道 A")
        if not decision.target_workflow_id:
            raise ValueError("通道 A 决策缺少 target_workflow_id")

        decision.status = DecisionStatus.executing
        decision.updated_at = now_iso()
        self._store.save_decision(slot, decision)
        try:
            event = self._switch_engine.execute_switch(
                slot=slot,
                target_workflow_id=decision.target_workflow_id,
                target_version_tag=decision.target_version_tag,
                trigger_type="auto",
                reason=f"精度运营建议；RCA={decision.rca_report_id}；decision={decision.decision_id}",
            )
            decision.switch_event_id = event.event_id if hasattr(event, "event_id") else event["event_id"]
            decision.status = DecisionStatus.succeeded
            decision.updated_at = now_iso()
            self._store.save_decision(slot, decision)
            alert.status = AlertStatus.recovering
            alert.updated_at = now_iso()
            self._store.save_alert(slot, alert)
            return decision
        except Exception:
            decision.status = DecisionStatus.failed
            decision.updated_at = now_iso()
            self._store.save_decision(slot, decision)
            alert.status = AlertStatus.open
            alert.updated_at = now_iso()
            self._store.save_alert(slot, alert)
            raise

    def _deployed_versions(self, slot: str) -> Tuple[Optional[dict], list[dict]]:
        """从部署槽位获取 production/shadow；旧 registry 只读兼容回退。"""
        if self._deployment_slot_store is not None:
            slot_obj = self._deployment_slot_store.get(slot)
            if slot_obj is not None:
                production = slot_obj.production_model.model_dump() if slot_obj.production_model else None
                shadows = [model.model_dump() for model in slot_obj.shadow_models if model.status == "shadow"]
                return production, shadows
        return self._version_registry.get_production(slot), self._version_registry.list_shadows(slot)

    @staticmethod
    def _comparison_metric(metrics: dict) -> float:
        """通道 A 与监控保持一致：优先 WMAPE、缺失回退 MAPE。"""
        value = metrics.get("rolling_wmape")
        return float(value) if value is not None else float(metrics.get("rolling_mape", 0.0))

    def _find_qualified_shadow(self, slot: str) -> Optional[Tuple[dict, dict]]:
        """选出已满足样本门槛且比生产优于最低分差的最佳影子版本。"""
        try:
            config = self._config_manager.load_config(slot)
            production, shadows = self._deployed_versions(slot)
        except Exception as exc:
            logger.warning("无法读取部署版本或配置 slot=%s: %s", slot, exc)
            return None
        if production is None:
            return None
        production_metrics = self._accuracy_tracker.get_rolling_metrics(slot, production["workflow_id"], production.get("version_tag"))
        if production_metrics is None or production_metrics.get("status") != "active":
            return None
        production_score = self._comparison_metric(production_metrics)
        if production_score <= 0:
            return None

        candidates: list[Tuple[dict, dict]] = []
        for shadow in shadows:
            metrics = self._accuracy_tracker.get_rolling_metrics(slot, shadow["workflow_id"], shadow.get("version_tag"))
            if metrics is None or metrics.get("status") != "active":
                continue
            if int(metrics.get("valid_cycle_count", 0)) < int(config.min_valid_cycles):
                continue
            shadow_score = self._comparison_metric(metrics)
            margin_pct = (production_score - shadow_score) / production_score * 100
            if shadow_score < production_score and margin_pct >= float(config.switch_margin_pct):
                candidates.append((shadow, metrics))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (self._comparison_metric(item[1]), -int(item[1].get("valid_cycle_count", 0))))
        return candidates[0]

    def _build_decision(
        self,
        rca: RCAReport,
        channel: RecoveryChannel,
        reason: str,
        confidence_gate_passed: bool,
        target_workflow_id: Optional[str] = None,
        target_version_tag: Optional[str] = None,
    ) -> RecoveryDecision:
        now = datetime.now(tz=timezone.utc)
        return RecoveryDecision(
            alert_id=rca.alert_id,
            rca_report_id=rca.rca_report_id,
            channel=channel,
            decision_reason=reason,
            confidence_gate_passed=confidence_gate_passed,
            target_workflow_id=target_workflow_id,
            target_version_tag=target_version_tag,
            sla_deadline=(now + timedelta(hours=_SLA[channel.value])).isoformat(),
            status=DecisionStatus.pending,
        )

    def _finalize(self, slot: str, decision: RecoveryDecision, alert: AccuracyAlert) -> RecoveryDecision:
        self._store.save_decision(slot, decision)
        alert.status = AlertStatus.recovering if decision.channel == RecoveryChannel.shadow_switch.value else AlertStatus.observing
        alert.recovery_decision_id = decision.decision_id
        alert.updated_at = now_iso()
        self._store.save_alert(slot, alert)
        return decision
# @AI_GENERATED: end
