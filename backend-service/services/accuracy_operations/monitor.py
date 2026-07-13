# @AI_GENERATED
"""
accuracy_operations/monitor.py — 精度监控组件

负责对 production 和 shadow 形态的模型版本做退化检测，产出 AccuracyAlert。

职责：
  - evaluate(slot): 遍历 production + shadow 版本，按退化公式触发告警
  - get_monitoring_snapshot(slot): 返回当前各形态的精度快照（只读）

设计约定：
  - 对 prelaunch / AutoResearch 不产出 AccuracyAlert（只在 snapshot 里展示）
  - accuracy_tracker / version_registry 调用均包裹 try/except，失败静默跳过
  - 告警去重：同 slot + model_form + workflow_id 已有 open alert 则跳过
  - severity 分级：degradation_pct >= 2 × threshold → critical，否则 → warning
  - baseline_mape 来自 version_registry 注册值；若 None 或 0，回退为当前 rolling_mape
    （退化率 = 0，不触发告警）
  - cooldown_until: now + config.cooldown_hours（ISO8601）
  - degradation_trend 通过 _detect_trend 辅助方法判断

References: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.accuracy_operations.models import (
    AccuracyAlert,
    AlertSeverity,
    AlertStatus,
    DegradationTrend,
    ModelForm,
    gen_alert_id,
)
from services.accuracy_operations.store import AccuracyOperationsStore

logger = logging.getLogger(__name__)


class AccuracyMonitor:
    """
    AccuracyMonitor — 精度退化监控组件

    注入依赖：
      accuracy_tracker   — AccuracyTracker，提供 get_rolling_metrics(slot, workflow_id)
      version_registry   — VersionRegistry，提供 get_production / list_shadows
      config_manager     — ConfigManager，提供 load_config(slot) → SlotConfig
      store              — AccuracyOperationsStore，告警持久化与去重查询
      prelaunch_manager  — 可选，提供 list_prelaunches(slot)，用于 snapshot 展示

    参考: Requirements 1.1–1.6
    """

    def __init__(
        self,
        accuracy_tracker: Any,
        version_registry: Any,
        config_manager: Any,
        store: AccuracyOperationsStore,
        prelaunch_manager: Optional[Any] = None,
    ) -> None:
        """
        :param accuracy_tracker:  AccuracyTracker 实例 — 提供滚动精度指标查询
        :param version_registry:  VersionRegistry 实例 — 提供版本状态查询
        :param config_manager:    ConfigManager 实例 — 提供槽位配置读取
        :param store:             AccuracyOperationsStore 实例 — 告警持久化与去重
        :param prelaunch_manager: 可选，提供 list_prelaunches(slot)，
                                  供 get_monitoring_snapshot 填充 prelaunches 字段
        """
        self._tracker = accuracy_tracker
        self._registry = version_registry
        self._config_manager = config_manager
        self._store = store
        self._prelaunch_manager = prelaunch_manager

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def evaluate(self, slot: str) -> List[AccuracyAlert]:
        """
        对指定槽位的 production + shadow 版本执行精度退化检测。

        流程：
        1. 加载槽位配置（degradation_threshold_pct / cooldown_hours）
        2. 检查 production 版本 → 退化则产出告警
        3. 遍历所有 shadow 版本 → 各自独立退化检测
        4. 对 prelaunch / AutoResearch 不做告警（只在 snapshot 里展示）

        退化公式：
          (current_rolling_mape - baseline_mape) / baseline_mape * 100
          >= config.degradation_threshold_pct

        :param slot: 槽位名称（分区键）
        :return: 本次新产出的 AccuracyAlert 列表
        """
        alerts: List[AccuracyAlert] = []

        # 1. 加载槽位配置
        try:
            config = self._config_manager.load_config(slot)
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor.evaluate: 加载配置失败 slot=%s: %s；使用默认配置",
                slot, exc,
            )
            # 直接导入默认配置，避免循环依赖
            from services.precision_ops.config_manager import SlotConfig
            config = SlotConfig(slot=slot)

        threshold_pct: float = float(config.degradation_threshold_pct)

        # 2. 检查 production
        try:
            prod_entry = self._registry.get_production(slot)
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor.evaluate: get_production 失败 slot=%s: %s",
                slot, exc,
            )
            prod_entry = None

        if prod_entry is not None:
            alert = self._check_version(
                slot=slot,
                version_entry=prod_entry,
                model_form=ModelForm.production,
                threshold_pct=threshold_pct,
                config=config,
            )
            if alert is not None:
                alerts.append(alert)

        # 3. 检查所有 shadow 版本
        try:
            shadow_entries = self._registry.list_shadows(slot)
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor.evaluate: list_shadows 失败 slot=%s: %s",
                slot, exc,
            )
            shadow_entries = []

        for shadow_entry in shadow_entries:
            alert = self._check_version(
                slot=slot,
                version_entry=shadow_entry,
                model_form=ModelForm.shadow,
                threshold_pct=threshold_pct,
                config=config,
            )
            if alert is not None:
                alerts.append(alert)

        return alerts

    def get_monitoring_snapshot(self, slot: str) -> dict:
        """
        返回当前槽位所有形态的精度快照（只读，不产出告警）。

        返回结构：
          {
            "production":        <metrics dict | None>,
            "shadows":           [<metrics dict>, ...],
            "prelaunches":       [<metrics dict>, ...],  # 来自 prelaunch_manager
            "autoresearch_score": None                   # 暂不实现
          }

        每个 metrics dict 包含字段：
          workflow_id, version_tag, rolling_mape, rolling_mae,
          valid_cycle_count, status

        :param slot: 槽位名称
        :return: 精度快照字典
        """
        snapshot: dict = {
            "production": None,
            "shadows": [],
            "prelaunches": [],
            "autoresearch_score": None,
        }

        # production
        try:
            prod_entry = self._registry.get_production(slot)
            if prod_entry is not None:
                snapshot["production"] = self._build_metrics_dict(slot, prod_entry)
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor.get_monitoring_snapshot: get_production 失败 slot=%s: %s",
                slot, exc,
            )

        # shadows
        try:
            shadow_entries = self._registry.list_shadows(slot)
            for entry in shadow_entries:
                m = self._build_metrics_dict(slot, entry)
                if m is not None:
                    snapshot["shadows"].append(m)
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor.get_monitoring_snapshot: list_shadows 失败 slot=%s: %s",
                slot, exc,
            )

        # prelaunches（可选注入）
        if self._prelaunch_manager is not None:
            try:
                prelaunches = self._prelaunch_manager.list_prelaunches(slot)
                for entry in (prelaunches or []):
                    m = self._build_metrics_dict(slot, entry)
                    if m is not None:
                        snapshot["prelaunches"].append(m)
            except Exception as exc:
                logger.warning(
                    "AccuracyMonitor.get_monitoring_snapshot: list_prelaunches 失败 slot=%s: %s",
                    slot, exc,
                )

        return snapshot

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _check_version(
        self,
        slot: str,
        version_entry: dict,
        model_form: ModelForm,
        threshold_pct: float,
        config: Any,
    ) -> Optional[AccuracyAlert]:
        """
        对单个版本做退化检测，产出 AccuracyAlert 或返回 None。

        :param slot:          槽位名称
        :param version_entry: version_registry 返回的版本条目
        :param model_form:    模型形态（production / shadow）
        :param threshold_pct: 退化阈值（百分比）
        :param config:        SlotConfig 实例（含 cooldown_hours）
        :return: AccuracyAlert 或 None
        """
        workflow_id: str = version_entry.get("workflow_id", "")
        version_tag: str = version_entry.get("version_tag", "")

        if not workflow_id:
            return None

        # 获取滚动精度指标
        try:
            metrics = self._tracker.get_rolling_metrics(slot, workflow_id)
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor._check_version: get_rolling_metrics 失败 "
                "slot=%s workflow_id=%s: %s",
                slot, workflow_id, exc,
            )
            return None

        # metrics 为 None 或 status 不为 active → 跳过
        if metrics is None:
            return None
        if metrics.get("status") != "active":
            return None

        current_rolling_mape: float = float(metrics.get("rolling_mape", 0.0))

        # baseline_mape：来自 version_registry；None 或 0 时回退为 current_rolling_mape
        raw_baseline = version_entry.get("baseline_mape")
        if raw_baseline is None or float(raw_baseline) == 0.0:
            # 回退：baseline = current → degradation_pct = 0 → 不触发告警
            baseline_mape: float = current_rolling_mape
        else:
            baseline_mape = float(raw_baseline)

        # 退化公式
        if baseline_mape == 0.0:
            # 极端保护：baseline 为 0 时无法计算百分比，跳过
            return None

        degradation_pct: float = (
            (current_rolling_mape - baseline_mape) / baseline_mape * 100
        )

        if degradation_pct < threshold_pct:
            return None

        # 告警去重
        try:
            already_open = self._store.has_open_alert(
                slot, model_form.value if hasattr(model_form, "value") else str(model_form), workflow_id
            )
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor._check_version: has_open_alert 失败 "
                "slot=%s workflow_id=%s: %s",
                slot, workflow_id, exc,
            )
            already_open = False

        if already_open:
            return None

        # severity 分级
        if degradation_pct >= 2 * threshold_pct:
            severity = AlertSeverity.critical
        else:
            severity = AlertSeverity.warning

        # degradation_trend
        trend = self._detect_trend(slot, workflow_id, degradation_pct, threshold_pct)

        # cooldown_until
        cooldown_until: str = (
            datetime.now(tz=timezone.utc)
            + timedelta(hours=float(config.cooldown_hours))
        ).isoformat()

        # 构建告警
        model_form_str = model_form.value if hasattr(model_form, "value") else str(model_form)
        alert = AccuracyAlert(
            alert_id=gen_alert_id(),
            slot=slot,
            model_form=model_form,
            workflow_id=workflow_id,
            version_tag=version_tag,
            baseline_mape=baseline_mape,
            current_rolling_mape=current_rolling_mape,
            degradation_pct=degradation_pct,
            degradation_trend=trend,
            severity=severity,
            status=AlertStatus.open,
            cooldown_until=cooldown_until,
        )

        # 持久化
        try:
            self._store.save_alert(slot, alert)
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor._check_version: save_alert 失败 "
                "slot=%s alert_id=%s: %s",
                slot, alert.alert_id, exc,
            )

        logger.info(
            "AccuracyMonitor: 产出新告警 alert_id=%s slot=%s "
            "model_form=%s workflow_id=%s degradation_pct=%.2f severity=%s",
            alert.alert_id, slot, model_form_str, workflow_id,
            degradation_pct, severity.value if hasattr(severity, "value") else str(severity),
        )
        return alert

    def _detect_trend(
        self,
        slot: str,
        workflow_id: str,
        degradation_pct: float,
        threshold_pct: float,
    ) -> DegradationTrend:
        """
        判断退化趋势：sudden / gradual / stable。

        启发式规则：
        1. 若 degradation_pct < 5%（绝对低水位）→ stable
        2. 查询 store 中该 slot + workflow_id 的历史告警记录：
           - 若存在历史 open/closed 告警（同 workflow_id）→ gradual（已持续一段时间）
           - 若无历史告警 → sudden（单周期骤升）
        3. 若 store 查询失败 → 默认 sudden

        :param slot:           槽位名称
        :param workflow_id:    工作流 ID
        :param degradation_pct: 当前退化百分比
        :param threshold_pct:  退化阈值
        :return: DegradationTrend 枚举值
        """
        # 规则1：绝对低退化量 → stable
        if degradation_pct < 5.0:
            return DegradationTrend.stable

        # 规则2：查历史告警推断趋势
        try:
            # 读取该 slot 下所有告警（不限 status）
            all_alerts = self._store.list_alerts(slot, status=None, limit=200)
            # 过滤出同 workflow_id 的历史告警（不含当前刚生成、尚未入库的那条）
            history = [
                a for a in all_alerts
                if a.workflow_id == workflow_id
            ]
            if history:
                # 存在历史告警 → 表明退化已发生过，趋势为渐进
                return DegradationTrend.gradual
            else:
                # 无历史告警 → 首次出现，视为骤升
                return DegradationTrend.sudden
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor._detect_trend: 查询历史告警失败 "
                "slot=%s workflow_id=%s: %s",
                slot, workflow_id, exc,
            )
            return DegradationTrend.sudden

    def _build_metrics_dict(
        self,
        slot: str,
        version_entry: dict,
    ) -> Optional[Dict[str, Any]]:
        """
        根据 version_entry 构建 snapshot 中单条 metrics 字典。

        返回格式：
          {
            "workflow_id":       str,
            "version_tag":       str,
            "rolling_mape":      float | None,
            "rolling_mae":       float | None,
            "valid_cycle_count": int | None,
            "status":            str | None,
          }

        :param slot:          槽位名称
        :param version_entry: version_registry 返回的版本条目
        :return: metrics dict，若 workflow_id 为空则返回 None
        """
        workflow_id: str = version_entry.get("workflow_id", "")
        version_tag: str = version_entry.get("version_tag", "")

        if not workflow_id:
            return None

        try:
            metrics = self._tracker.get_rolling_metrics(slot, workflow_id)
        except Exception as exc:
            logger.warning(
                "AccuracyMonitor._build_metrics_dict: get_rolling_metrics 失败 "
                "slot=%s workflow_id=%s: %s",
                slot, workflow_id, exc,
            )
            metrics = None

        if metrics is not None:
            return {
                "workflow_id": workflow_id,
                "version_tag": version_tag,
                "rolling_mape": metrics.get("rolling_mape"),
                "rolling_mae": metrics.get("rolling_mae"),
                "valid_cycle_count": metrics.get("valid_cycle_count"),
                "status": metrics.get("status"),
            }
        else:
            # metrics 不存在，仍返回 entry 基本信息，精度字段置 None
            return {
                "workflow_id": workflow_id,
                "version_tag": version_tag,
                "rolling_mape": None,
                "rolling_mae": None,
                "valid_cycle_count": None,
                "status": None,
            }
# @AI_GENERATED: end
