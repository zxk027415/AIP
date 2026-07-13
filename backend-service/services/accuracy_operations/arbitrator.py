# @AI_GENERATED
"""
accuracy_operations/arbitrator.py — 恢复仲裁器

职责：
  - 基于 RCA 报告和影子池状态做出恢复通道决策（RecoveryDecision）
  - 仅支持通道A（shadow_switch）和观察通道（observe），无通道B
  - 执行通道A 切换（execute_switch），委托 switch_engine 完成实际切换

依赖注入（不在内部创建依赖）：
  version_registry  — VersionRegistry 实例，读取生产/影子版本列表
  accuracy_tracker  — AccuracyTracker 实例，读取滚动精度指标
  config_manager    — ConfigManager 实例，加载槽位配置
  switch_engine     — SwitchDecisionEngine 实例，执行版本切换
  store             — AccuracyOperationsStore 实例，持久化告警/RCA/决策

禁止导入或引用：candidate_pool、verification_queue、knowledge_layer

References: Requirements 4.1-4.8, 5.1-5.4, 6.1-6.4
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from services.accuracy_operations.models import (
    AccuracyAlert,
    AlertStatus,
    DecisionStatus,
    RCAReport,
    RecoveryChannel,
    RecoveryDecision,
)
from services.accuracy_operations.store import AccuracyOperationsStore
from services.precision_ops.utils import now_iso

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CONF_GATE: float = 0.6
"""
CONF_GATE — 置信度门控阈值（0.6）

RCA 报告的 confidence 低于此值，或 undetermined=True 时，
仲裁器直接选择 observe 通道，不尝试执行切换。
"""

_SLA: dict = {
    "shadow_switch": 2,    # 通道A — 影子切换 SLA（小时）
    "observe": 12,         # 观察通道 SLA（小时）
}
"""
_SLA — 各通道 SLA 时长（小时）

- shadow_switch（通道A）：2 小时内应完成切换
- observe（观察通道）：12 小时内应等待 AutoResearch 产出或人工介入
"""


# ---------------------------------------------------------------------------
# RecoveryArbitrator
# ---------------------------------------------------------------------------

class RecoveryArbitrator:
    """
    恢复仲裁器 — 基于 RCA 结论和影子池状态决定恢复通道。

    仲裁决策树（按优先级顺序）：
    1. RCA 置信度门控：confidence < CONF_GATE 或 undetermined=True → observe
    2. 外部根因：root_cause 含 "external" → observe
    3. 同 slot 活跃切换检查：has_active_switch → observe
    4. 影子达标检查：找到达标影子 → shadow_switch；无 → observe

    References: Requirements 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
    """

    def __init__(
        self,
        version_registry,
        accuracy_tracker,
        config_manager,
        switch_engine,
        store: AccuracyOperationsStore,
    ) -> None:
        """
        :param version_registry:  VersionRegistry 实例 — 读取/查询版本状态
        :param accuracy_tracker:  AccuracyTracker 实例 — 读取滚动精度指标
        :param config_manager:    ConfigManager 实例 — 加载槽位配置
        :param switch_engine:     SwitchDecisionEngine 实例 — 执行影子切换
        :param store:             AccuracyOperationsStore 实例 — 持久化三类实体
        """
        self._version_registry = version_registry
        self._accuracy_tracker = accuracy_tracker
        self._config_manager = config_manager
        self._switch_engine = switch_engine
        self._store = store

    # ------------------------------------------------------------------
    # 主仲裁入口
    # ------------------------------------------------------------------

    def decide(self, slot: str, rca_report_id: str) -> RecoveryDecision:
        """
        基于 RCA 报告做出恢复决策，并持久化至 store。

        流程：
        1. 加载 RCAReport（status 必须为 succeeded）
        2. 加载关联 AccuracyAlert
        3. 置信度门控检查
        4. 外部根因检查
        5. 活跃切换检查
        6. 寻找达标影子版本
        7. 构建 RecoveryDecision，保存，更新告警状态，返回

        :param slot:          槽位名称（分区键，如 "default"）
        :param rca_report_id: RCA 报告 ID（格式 rca-{8hex}），必须已存在且 succeeded
        :return: 保存后的 RecoveryDecision 实体
        :raises ValueError: RCAReport 不存在/未完成，或关联告警不存在
        """
        # ---- Step 1: 加载 RCAReport ----
        rca = self._store.get_rca(slot, rca_report_id)
        if rca is None:
            raise ValueError(
                f"RCAReport 不存在：slot={slot!r}, rca_report_id={rca_report_id!r}"
            )
        if rca.status != "succeeded":
            raise ValueError(
                f"RCAReport 状态不为 succeeded（当前状态={rca.status!r}），"
                f"无法进行仲裁：slot={slot!r}, rca_report_id={rca_report_id!r}"
            )

        # ---- Step 2: 加载关联告警 ----
        alert = self._store.get_alert(slot, rca.alert_id)
        if alert is None:
            raise ValueError(
                f"关联告警不存在：slot={slot!r}, alert_id={rca.alert_id!r}"
            )

        # ---- Step 3: 置信度门控 ----
        if rca.confidence < CONF_GATE or rca.undetermined:
            decision = self._build_decision(
                rca=rca,
                channel=RecoveryChannel.observe,
                decision_reason="RCA 置信度不足或根因未确定",
                confidence_gate_passed=False,
            )
            return self._finalize(slot, decision, alert)

        # ---- Step 4: 外部根因检查 ----
        if "external" in (rca.root_cause or "").lower():
            decision = self._build_decision(
                rca=rca,
                channel=RecoveryChannel.observe,
                decision_reason="外部因素，大概率自愈",
                confidence_gate_passed=True,
            )
            return self._finalize(slot, decision, alert)

        # ---- Step 5: 活跃切换检查 ----
        if self._store.has_active_switch(slot):
            decision = self._build_decision(
                rca=rca,
                channel=RecoveryChannel.observe,
                decision_reason="同 slot 已有执行中的影子切换，等待完成",
                confidence_gate_passed=True,
            )
            return self._finalize(slot, decision, alert)

        # ---- Step 6: 寻找达标影子 ----
        config = self._config_manager.load_config(slot)
        qualified = self._find_qualified_shadow(slot, config)

        if qualified is not None:
            shadow_entry, shadow_metrics = qualified
            target_wf = shadow_entry["workflow_id"]
            target_tag = shadow_entry.get("version_tag", target_wf)
            reason = (
                f"影子版本 {target_tag} MAPE({shadow_metrics['rolling_mape']:.4f}) "
                f"达标，执行切换（RCA={rca_report_id}）"
            )
            decision = self._build_decision(
                rca=rca,
                channel=RecoveryChannel.shadow_switch,
                decision_reason=reason,
                confidence_gate_passed=True,
                target_workflow_id=target_wf,
            )
        else:
            decision = self._build_decision(
                rca=rca,
                channel=RecoveryChannel.observe,
                decision_reason="无达标影子，等待 AutoResearch 产出",
                confidence_gate_passed=True,
            )

        return self._finalize(slot, decision, alert)

    # ------------------------------------------------------------------
    # 通道A 执行
    # ------------------------------------------------------------------

    def execute_switch(
        self,
        slot: str,
        decision: RecoveryDecision,
        alert: AccuracyAlert,
    ) -> RecoveryDecision:
        """
        执行通道A 切换操作。

        在 decide() 返回 channel=shadow_switch 的决策后调用。
        重新定位达标影子（避免在 RecoveryDecision 中额外存储 target_workflow_id），
        调用 switch_engine.execute_switch()，更新决策和告警状态。

        失败时将 decision.status 置为 failed，告警回退为 open，重新抛出异常。

        :param slot:     槽位名称（分区键）
        :param decision: decide() 返回的 RecoveryDecision（channel=shadow_switch）
        :param alert:    关联 AccuracyAlert 实体
        :return: 更新后的 RecoveryDecision（status=succeeded）
        :raises Exception: switch_engine 调用失败时原样抛出
        """
        # ---- 定位目标影子 ----
        config = self._config_manager.load_config(slot)
        qualified = self._find_qualified_shadow(slot, config)

        if qualified is None:
            # 达标影子已消失（极罕见竞态），降为 failed
            decision.status = DecisionStatus.failed
            decision.updated_at = now_iso()
            self._store.save_decision(slot, decision)
            alert.status = AlertStatus.open
            alert.updated_at = now_iso()
            self._store.save_alert(slot, alert)
            raise ValueError(
                f"execute_switch: 无达标影子可用（slot={slot!r}），"
                f"决策 {decision.decision_id} 标记为 failed"
            )

        shadow_entry, _ = qualified
        target_workflow_id: str = shadow_entry["workflow_id"]

        # ---- 更新决策状态为 executing ----
        decision.status = DecisionStatus.executing
        decision.updated_at = now_iso()
        self._store.save_decision(slot, decision)

        try:
            # ---- 调用 switch_engine 执行切换 ----
            event = self._switch_engine.execute_switch(
                slot=slot,
                target_workflow_id=target_workflow_id,
                trigger_type="automatic",
                reason=f"精度运营仲裁: RCA={decision.rca_report_id}",
            )

            # ---- 更新决策为 succeeded ----
            decision.switch_event_id = event["event_id"]
            decision.status = DecisionStatus.succeeded
            decision.updated_at = now_iso()
            self._store.save_decision(slot, decision)

            # ---- 更新告警状态为 recovering ----
            alert.status = AlertStatus.recovering
            alert.updated_at = now_iso()
            self._store.save_alert(slot, alert)

            logger.info(
                "execute_switch: 切换成功 slot=%s target=%s event_id=%s decision_id=%s",
                slot,
                target_workflow_id,
                event["event_id"],
                decision.decision_id,
            )
            return decision

        except Exception as exc:
            logger.error(
                "execute_switch: 切换失败 slot=%s target=%s decision_id=%s: %s",
                slot,
                target_workflow_id,
                decision.decision_id,
                exc,
            )
            # ---- 失败：决策标记 failed，告警回退 open ----
            decision.status = DecisionStatus.failed
            decision.updated_at = now_iso()
            self._store.save_decision(slot, decision)

            alert.status = AlertStatus.open
            alert.updated_at = now_iso()
            self._store.save_alert(slot, alert)

            raise

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _find_qualified_shadow(
        self,
        slot: str,
        config,
    ) -> Optional[Tuple[dict, dict]]:
        """
        寻找满足达标条件的最优影子版本。

        达标条件：
        1. 生产版本精度数据有效（metrics 存在且 status=active）
        2. 影子版本满足 valid_cycle_count >= config.min_valid_cycles
        3. (prod_mape - shadow_mape) / prod_mape * 100 >= config.switch_margin_pct

        多个达标候选时：选滚动 MAPE 最低的；相同（差异 < 0.0001）时选 valid_cycle_count 最大的。

        依赖不可达（异常）时降为 observe，由调用方检查返回 None 的含义。

        :param slot:   槽位名称
        :param config: SlotConfig 实例
        :return: (shadow_entry, shadow_metrics) 元组，或 None（无达标影子）
        """
        # ---- 获取生产版本 ----
        try:
            prod = self._version_registry.get_production(slot)
        except Exception as exc:
            logger.warning(
                "_find_qualified_shadow: version_registry 不可达（slot=%s）: %s", slot, exc
            )
            return None

        if prod is None:
            logger.info("_find_qualified_shadow: slot=%s 无生产版本", slot)
            return None

        # ---- 获取生产版本精度指标 ----
        try:
            prod_metrics = self._accuracy_tracker.get_rolling_metrics(
                slot, prod["workflow_id"]
            )
        except Exception as exc:
            logger.warning(
                "_find_qualified_shadow: accuracy_tracker 不可达（slot=%s prod=%s）: %s",
                slot,
                prod["workflow_id"],
                exc,
            )
            return None

        if prod_metrics is None or prod_metrics.get("status") != "active":
            logger.info(
                "_find_qualified_shadow: slot=%s 生产版本精度数据不足或不活跃", slot
            )
            return None

        prod_mape: float = prod_metrics["rolling_mape"]
        if prod_mape == 0.0:
            logger.info(
                "_find_qualified_shadow: slot=%s 生产版本 prod_mape=0，无法计算分差", slot
            )
            return None

        # ---- 遍历影子版本 ----
        try:
            shadows = self._version_registry.list_shadows(slot)
        except Exception as exc:
            logger.warning(
                "_find_qualified_shadow: list_shadows 不可达（slot=%s）: %s", slot, exc
            )
            return None

        candidates = []
        for shadow in shadows:
            try:
                metrics = self._accuracy_tracker.get_rolling_metrics(
                    slot, shadow["workflow_id"]
                )
            except Exception as exc:
                logger.warning(
                    "_find_qualified_shadow: 获取影子 %s 指标失败: %s",
                    shadow.get("workflow_id"),
                    exc,
                )
                continue

            if metrics is None:
                continue

            # 有效周期数检查
            if metrics.get("valid_cycle_count", 0) < config.min_valid_cycles:
                continue

            shadow_mape: float = metrics["rolling_mape"]
            margin_pct = (prod_mape - shadow_mape) / prod_mape * 100

            if margin_pct >= config.switch_margin_pct:
                candidates.append((shadow, metrics))

        if not candidates:
            return None

        # ---- 选最优：MAPE 最低，相同则 valid_cycle_count 最大 ----
        candidates.sort(
            key=lambda x: (
                round(x[1]["rolling_mape"] / 0.0001) * 0.0001,
                -x[1].get("valid_cycle_count", 0),
            )
        )
        return candidates[0]

    def _build_decision(
        self,
        rca: RCAReport,
        channel: RecoveryChannel,
        decision_reason: str,
        confidence_gate_passed: bool,
        target_workflow_id: Optional[str] = None,
    ) -> RecoveryDecision:
        """
        构建 RecoveryDecision 实体（含 sla_deadline 计算）。

        :param rca:                  关联 RCAReport
        :param channel:              选定恢复通道
        :param decision_reason:      决策理由（中文）
        :param confidence_gate_passed: 是否通过置信度门控
        :param target_workflow_id:   目标影子 workflow_id（仅 shadow_switch 时有值，
                                     此处追加到 reason 便于 execute_switch 重新定位）
        :return: 未持久化的 RecoveryDecision 实体
        """
        sla_hours = _SLA[channel.value if isinstance(channel, RecoveryChannel) else channel]
        now_dt = datetime.now(tz=timezone.utc)
        sla_deadline = (now_dt + timedelta(hours=sla_hours)).isoformat()

        return RecoveryDecision(
            alert_id=rca.alert_id,
            rca_report_id=rca.rca_report_id,
            channel=channel,
            decision_reason=decision_reason,
            confidence_gate_passed=confidence_gate_passed,
            sla_deadline=sla_deadline,
            status=DecisionStatus.pending,
        )

    def _finalize(
        self,
        slot: str,
        decision: RecoveryDecision,
        alert: AccuracyAlert,
    ) -> RecoveryDecision:
        """
        持久化决策，更新告警状态，返回决策。

        状态迁移：
          shadow_switch → alert.status = recovering
          observe       → alert.status = observing

        :param slot:     槽位名称
        :param decision: 已构建的 RecoveryDecision
        :param alert:    关联 AccuracyAlert
        :return: 已持久化的 RecoveryDecision
        """
        # 保存决策
        self._store.save_decision(slot, decision)

        # 更新告警状态
        channel_val = (
            decision.channel.value
            if isinstance(decision.channel, RecoveryChannel)
            else decision.channel
        )
        if channel_val == RecoveryChannel.shadow_switch.value:
            alert.status = AlertStatus.recovering
        else:
            alert.status = AlertStatus.observing

        alert.recovery_decision_id = decision.decision_id
        alert.updated_at = now_iso()
        self._store.save_alert(slot, alert)

        logger.info(
            "_finalize: slot=%s channel=%s decision_id=%s alert_id=%s alert_status=%s",
            slot,
            channel_val,
            decision.decision_id,
            alert.alert_id,
            alert.status,
        )
        return decision
# @AI_GENERATED: end
