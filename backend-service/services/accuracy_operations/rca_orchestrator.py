# @AI_GENERATED
"""
accuracy_operations/rca_orchestrator.py — RCA 编排器

负责根因分析（RCA）的完整生命周期编排：
  - 冷却期检查（manual 触发跳过）
  - 幂等性检查（rca_running 状态下不重复触发）
  - 告警状态迁移（open → rca_running）
  - 创建初始 RCAReport（status=running）
  - 调用 RCASkillClient 执行分析
  - 成功后更新 RCAReport（status=succeeded）并设置冷却期
  - 失败/超时后回退告警状态（→ open），re-raise 异常

类：
  RCAOrchestrator
    __init__(rca_skill_client, store)
    trigger(slot, alert, trigger_type) -> RCAReport
    get_or_create_rca(slot, alert_id, trigger_type) -> Optional[RCAReport]

References: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 7.1, 7.6
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.accuracy_operations.models import (
    AccuracyAlert,
    RCAReport,
    RCAStatus,
)
from services.accuracy_operations.rca_skill_client import RCASkillClient
from services.accuracy_operations.store import AccuracyOperationsStore
from services.precision_ops.utils import now_iso

logger = logging.getLogger(__name__)


class RCAOrchestrator:
    """
    RCA 编排器。

    编排从"告警触发 RCA"到"RCAReport 落库"的全流程，
    包含冷却期检查、幂等性保护、状态迁移、skill 调用和异常回退。

    注入依赖：
      - rca_skill_client — 负责调用 operation_skill 子进程并返回 RCAReport
      - store            — 负责 alert / rca 的持久化读写
    """

    def __init__(
        self,
        rca_skill_client: RCASkillClient,
        store: AccuracyOperationsStore,
    ) -> None:
        """
        :param rca_skill_client: RCA Skill 子进程调用封装
        :param store: 精度运营持久化 Store
        """
        self._client = rca_skill_client
        self._store = store

    # ------------------------------------------------------------------
    # 主接口
    # ------------------------------------------------------------------

    def trigger(
        self,
        slot: str,
        alert: AccuracyAlert,
        trigger_type: str = "alert",
    ) -> RCAReport:
        """
        触发/恢复一次 RCA 分析，返回最终 RCAReport。

        流程：
          1. 冷却期检查（trigger_type != "manual" 时）
          2. 幂等性检查（alert.status == "rca_running" 时）
          3. 告警状态迁移 → rca_running
          4. 创建初始 RCAReport（status=running），保存，回填 alert.rca_report_id
          5. 调用 rca_skill_client.run_rca(...)
          6. 成功：更新 rca（status=succeeded），保存；更新 alert.cooldown_until
          7. 超时（subprocess.TimeoutExpired）：rca.status=timeout；alert.status=open；re-raise
          8. 其他异常：rca.status=failed；alert.status=open；re-raise

        :param slot: 槽位名称（分区键，如 "default"）
        :param alert: 触发本次 RCA 的 AccuracyAlert 实体
        :param trigger_type: 触发方式 — "alert"（默认）/ "scheduled" / "manual"
        :return: 已落库的 RCAReport
        :raises subprocess.TimeoutExpired: skill 执行超时
        :raises Exception: skill 执行失败或其他异常
        """
        # ----------------------------------------------------------------
        # 1. 冷却期检查（manual 触发跳过）
        # ----------------------------------------------------------------
        if trigger_type != "manual" and alert.cooldown_until:
            try:
                cooldown_dt = datetime.fromisoformat(alert.cooldown_until)
                # 确保带时区以便比较
                if cooldown_dt.tzinfo is None:
                    cooldown_dt = cooldown_dt.replace(tzinfo=timezone.utc)
                now_dt = datetime.now(tz=timezone.utc)
                if now_dt < cooldown_dt:
                    # 在冷却期内：尝试返回既有 RCAReport
                    existing_rca = self._store.get_rca_for_alert(
                        slot, alert.alert_id
                    )
                    if existing_rca is not None:
                        logger.info(
                            "[RCAOrchestrator] 冷却期内幂等返回既有 RCAReport "
                            "alert_id=%s rca_report_id=%s cooldown_until=%s",
                            alert.alert_id,
                            existing_rca.rca_report_id,
                            alert.cooldown_until,
                        )
                        return existing_rca
                    # 边缘情况：冷却期但没有既有 RCA → 继续执行
                    logger.warning(
                        "[RCAOrchestrator] 冷却期内但找不到既有 RCAReport，继续执行 "
                        "alert_id=%s",
                        alert.alert_id,
                    )
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "[RCAOrchestrator] 解析 cooldown_until 失败，跳过冷却检查 "
                    "alert_id=%s cooldown_until=%s err=%s",
                    alert.alert_id,
                    alert.cooldown_until,
                    exc,
                )

        # ----------------------------------------------------------------
        # 2. 幂等性检查（已在 rca_running 状态时）
        # ----------------------------------------------------------------
        if alert.status == "rca_running":
            existing_rca = self._store.get_rca_for_alert(slot, alert.alert_id)
            if existing_rca is not None and existing_rca.status == "running":
                logger.info(
                    "[RCAOrchestrator] alert 处于 rca_running 且已有 running RCA，"
                    "幂等返回 alert_id=%s rca_report_id=%s",
                    alert.alert_id,
                    existing_rca.rca_report_id,
                )
                return existing_rca

        # ----------------------------------------------------------------
        # 3. 状态迁移：alert → rca_running
        # ----------------------------------------------------------------
        alert.status = "rca_running"
        alert.updated_at = now_iso()
        self._store.update_alert(slot, alert)
        logger.info(
            "[RCAOrchestrator] alert 状态迁移为 rca_running alert_id=%s",
            alert.alert_id,
        )

        # ----------------------------------------------------------------
        # 4. 创建初始 RCAReport（status=running）
        # ----------------------------------------------------------------
        rca = RCAReport(
            alert_id=alert.alert_id,
            trigger_type=trigger_type,
            status=RCAStatus.running,
        )
        self._store.save_rca(slot, rca)
        logger.info(
            "[RCAOrchestrator] 创建初始 RCAReport rca_report_id=%s",
            rca.rca_report_id,
        )

        # ----------------------------------------------------------------
        # 5. 回填 alert.rca_report_id，再次保存 alert
        # ----------------------------------------------------------------
        alert.rca_report_id = rca.rca_report_id
        alert.updated_at = now_iso()
        self._store.update_alert(slot, alert)

        # ----------------------------------------------------------------
        # 6. 调用 skill，处理成功/超时/失败
        # ----------------------------------------------------------------
        try:
            result_rca: RCAReport = self._client.run_rca(
                slot=slot,
                alert=alert,
                rca_report_id=rca.rca_report_id,
                trigger_type=trigger_type,
            )

            # --- 成功：用返回数据更新本地 rca 对象 ---
            rca.root_cause = result_rca.root_cause
            rca.confidence = result_rca.confidence
            rca.reasoning = result_rca.reasoning
            rca.supporting_evidence = result_rca.supporting_evidence
            rca.undetermined = result_rca.undetermined
            rca.error_profile = result_rca.error_profile
            rca.data_quality_diagnosis = result_rca.data_quality_diagnosis
            rca.actionable_insights = result_rca.actionable_insights
            rca.candidate_strategies = result_rca.candidate_strategies
            rca.recommended_strategy_id = result_rca.recommended_strategy_id
            rca.artifacts_dir = result_rca.artifacts_dir
            rca.status = RCAStatus.succeeded
            self._store.save_rca(slot, rca)
            logger.info(
                "[RCAOrchestrator] RCA 成功 rca_report_id=%s root_cause=%s "
                "confidence=%.2f",
                rca.rca_report_id,
                rca.root_cause[:60] if rca.root_cause else "",
                rca.confidence,
            )

        except subprocess.TimeoutExpired:
            # --- 超时：rca → timeout；alert → open ---
            logger.error(
                "[RCAOrchestrator] RCA 超时 rca_report_id=%s alert_id=%s",
                rca.rca_report_id,
                alert.alert_id,
            )
            rca.status = "timeout"  # type: ignore[assignment]
            self._store.save_rca(slot, rca)
            alert.status = "open"
            alert.updated_at = now_iso()
            self._store.update_alert(slot, alert)
            raise

        except Exception:
            # --- 其他异常：rca → failed；alert → open ---
            logger.exception(
                "[RCAOrchestrator] RCA 失败 rca_report_id=%s alert_id=%s",
                rca.rca_report_id,
                alert.alert_id,
            )
            rca.status = "failed"  # type: ignore[assignment]
            self._store.save_rca(slot, rca)
            alert.status = "open"
            alert.updated_at = now_iso()
            self._store.update_alert(slot, alert)
            raise

        # ----------------------------------------------------------------
        # 7. 成功后更新冷却截止时间（24h）
        # ----------------------------------------------------------------
        cooldown_dt = datetime.now(tz=timezone.utc) + timedelta(hours=24)
        alert.cooldown_until = cooldown_dt.isoformat()
        alert.updated_at = now_iso()
        self._store.update_alert(slot, alert)
        logger.info(
            "[RCAOrchestrator] 设置冷却截止 alert_id=%s cooldown_until=%s",
            alert.alert_id,
            alert.cooldown_until,
        )

        alert.status = "open"
        alert.updated_at = now_iso()
        self._store.update_alert(slot, alert)
        logger.info(
            "[RCAOrchestrator] RCA 成功，告警保持 open 待仲裁 alert_id=%s",
            alert.alert_id,
        )

        return rca

    # ------------------------------------------------------------------
    # 便捷接口
    # ------------------------------------------------------------------

    def get_or_create_rca(
        self,
        slot: str,
        alert_id: str,
        trigger_type: str = "alert",
    ) -> Optional[RCAReport]:
        """
        通过 alert_id 加载告警并触发 RCA，若告警不存在则返回 None。

        :param slot: 槽位名称
        :param alert_id: 告警 ID — 格式 alert-{8hex}
        :param trigger_type: 触发方式，默认 "alert"
        :return: RCAReport，或 None（告警不存在时）
        """
        alert = self._store.get_alert(slot, alert_id)
        if alert is None:
            logger.warning(
                "[RCAOrchestrator] get_or_create_rca: 找不到 alert "
                "slot=%s alert_id=%s",
                slot,
                alert_id,
            )
            return None
        return self.trigger(slot, alert, trigger_type=trigger_type)
# @AI_GENERATED: end
