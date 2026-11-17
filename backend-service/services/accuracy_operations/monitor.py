# @AI_GENERATED
"""精度运营监控：只读取部署槽位，生成告警与诊断输入，不维护发布状态。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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
    """对部署中的 production/shadow 执行版本级 7 天退化监测。

    ``DeploymentSlotStore`` 是 production、shadow 与 prelaunch 身份的唯一真源。
    ``VersionRegistry`` 仅作为未迁移旧槽位的只读兼容回退，绝不由本组件写入。
    """

    def __init__(
        self,
        accuracy_tracker: Any,
        version_registry: Any,
        config_manager: Any,
        store: AccuracyOperationsStore,
        prelaunch_manager: Optional[Any] = None,
        deployment_slot_store: Optional[Any] = None,
    ) -> None:
        self._tracker = accuracy_tracker
        self._registry = version_registry
        self._config_manager = config_manager
        self._store = store
        self._prelaunch_manager = prelaunch_manager
        self._deployment_slot_store = deployment_slot_store

    def evaluate(self, slot: str) -> List[AccuracyAlert]:
        """扫描部署 production 与 shadow；阈值使用配置，比较优先使用 WMAPE。"""
        try:
            config = self._config_manager.load_config(slot)
        except Exception as exc:
            from services.precision_ops.config_manager import SlotConfig
            logger.warning("AccuracyMonitor.evaluate: 配置读取失败 slot=%s: %s", slot, exc)
            config = SlotConfig(slot=slot)

        threshold_pct = float(config.degradation_threshold_pct)
        production, shadows, _ = self._deployed_entries(slot)
        created: List[AccuracyAlert] = []
        if production is not None:
            alert = self._check_version(slot, production, ModelForm.production, threshold_pct, config)
            if alert is not None:
                created.append(alert)
        for shadow in shadows:
            alert = self._check_version(slot, shadow, ModelForm.shadow, threshold_pct, config)
            if alert is not None:
                created.append(alert)
        return created

    def get_monitoring_snapshot(self, slot: str) -> dict:
        """返回部署版本及其版本级指标，不对指标或状态产生写副作用。"""
        production, shadows, prelaunches = self._deployed_entries(slot)
        return {
            "production": self._build_metrics_dict(slot, production) if production else None,
            "shadows": [item for entry in shadows if (item := self._build_metrics_dict(slot, entry)) is not None],
            "prelaunches": [item for entry in prelaunches if (item := self._build_metrics_dict(slot, entry)) is not None],
            "autoresearch_score": None,
        }

    def _deployed_entries(self, slot: str) -> Tuple[Optional[dict], List[dict], List[dict]]:
        """优先从部署槽位转成监控输入；旧 registry 只作为兼容回退。"""
        if self._deployment_slot_store is not None:
            try:
                slot_obj = self._deployment_slot_store.get(slot)
                if slot_obj is not None:
                    production = slot_obj.production_model.model_dump() if slot_obj.production_model else None
                    shadows = [model.model_dump() for model in slot_obj.shadow_models if model.status == "shadow"]
                    prelaunches = [model.model_dump() for model in slot_obj.prelaunch_models if model.status == "prelaunch"]
                    return production, shadows, prelaunches
            except Exception as exc:
                logger.warning("AccuracyMonitor: 读取部署槽位失败 slot=%s: %s", slot, exc)

        try:
            production = self._registry.get_production(slot)
            shadows = self._registry.list_shadows(slot)
        except Exception as exc:
            logger.warning("AccuracyMonitor: 读取旧版本登记失败 slot=%s: %s", slot, exc)
            production, shadows = None, []
        prelaunches: List[dict] = []
        if self._prelaunch_manager is not None:
            try:
                prelaunches = list(self._prelaunch_manager.list_prelaunches(slot) or [])
            except Exception as exc:
                logger.warning("AccuracyMonitor: 读取预上线列表失败 slot=%s: %s", slot, exc)
        return production, shadows, prelaunches

    def _check_version(
        self,
        slot: str,
        version_entry: dict,
        model_form: ModelForm,
        threshold_pct: float,
        config: Any,
    ) -> Optional[AccuracyAlert]:
        workflow_id = str(version_entry.get("workflow_id") or "")
        version_tag = str(version_entry.get("version_tag") or "")
        if not workflow_id:
            return None
        try:
            metrics = self._tracker.get_rolling_metrics(slot, workflow_id, version_tag)
        except Exception as exc:
            logger.warning("AccuracyMonitor: 读取指标失败 slot=%s version=%s@%s: %s", slot, workflow_id, version_tag, exc)
            return None
        if metrics is None or metrics.get("status") != "active":
            return None

        mape = float(metrics.get("rolling_mape", 0.0))
        wmape = metrics.get("rolling_wmape")
        raw_baseline_wmape = version_entry.get("baseline_wmape")
        try:
            use_wmape = (
                wmape is not None
                and raw_baseline_wmape is not None
                and float(raw_baseline_wmape) > 0
            )
        except (TypeError, ValueError):
            use_wmape = False
        metric_name = "wmape" if use_wmape else "mape"
        current_metric = float(wmape) if use_wmape else mape
        raw_baseline = raw_baseline_wmape if use_wmape else version_entry.get("baseline_mape")
        if raw_baseline is None or float(raw_baseline) <= 0:
            # 首个有效窗口只能建立观测基线，不能凭自身触发退化告警。
            return None
        baseline_metric = float(raw_baseline)
        degradation_pct = (current_metric - baseline_metric) / baseline_metric * 100
        if degradation_pct < threshold_pct:
            return None

        model_form_value = model_form.value if hasattr(model_form, "value") else str(model_form)
        if self._store.has_open_alert(slot, model_form_value, workflow_id, version_tag):
            return None
        severity = AlertSeverity.critical if degradation_pct >= threshold_pct * 2 else AlertSeverity.warning
        alert = AccuracyAlert(
            alert_id=gen_alert_id(),
            slot=slot,
            model_form=model_form,
            workflow_id=workflow_id,
            version_tag=version_tag,
            baseline_mape=float(version_entry.get("baseline_mape") or baseline_metric),
            current_rolling_mape=mape,
            metric_name=metric_name,
            baseline_metric=baseline_metric,
            current_metric=current_metric,
            degradation_pct=degradation_pct,
            degradation_trend=self._detect_trend(slot, workflow_id, version_tag, degradation_pct),
            severity=severity,
            status=AlertStatus.open,
            cooldown_until=(datetime.now(tz=timezone.utc) + timedelta(hours=float(config.cooldown_hours))).isoformat(),
        )
        self._store.save_alert(slot, alert)
        logger.info(
            "AccuracyMonitor: alert=%s slot=%s version=%s@%s metric=%s degradation=%.2f%%",
            alert.alert_id, slot, workflow_id, version_tag, metric_name, degradation_pct,
        )
        return alert

    def _detect_trend(self, slot: str, workflow_id: str, version_tag: str, degradation_pct: float) -> DegradationTrend:
        """基于同一完整版本的历史告警判定首次骤升或持续退化。"""
        if degradation_pct < 5.0:
            return DegradationTrend.stable
        try:
            seen = any(
                alert.workflow_id == workflow_id and alert.version_tag == version_tag
                for alert in self._store.list_alerts(slot, limit=200)
            )
            return DegradationTrend.gradual if seen else DegradationTrend.sudden
        except Exception:
            return DegradationTrend.sudden

    def _build_metrics_dict(self, slot: str, version_entry: Optional[dict]) -> Optional[Dict[str, Any]]:
        if not version_entry:
            return None
        workflow_id = str(version_entry.get("workflow_id") or "")
        version_tag = str(version_entry.get("version_tag") or "")
        if not workflow_id:
            return None
        metrics = self._tracker.get_rolling_metrics(slot, workflow_id, version_tag)
        base: Dict[str, Any] = {
            "workflow_id": workflow_id,
            "version_tag": version_tag,
            "baseline_mape": version_entry.get("baseline_mape"),
            "baseline_wmape": version_entry.get("baseline_wmape"),
        }
        if metrics is None:
            return {**base, "rolling_mape": None, "rolling_wmape": None, "rolling_mae": None, "valid_cycle_count": None, "coverage_rate": None, "window_days": None, "status": None, "daily_mape_series": [], "rolling_mape_pooled": None, "rolling_mape_method": None}
        return {
            **base,
            "rolling_mape": metrics.get("rolling_mape"),
            "rolling_wmape": metrics.get("rolling_wmape"),
            "rolling_mape_pooled": metrics.get("rolling_mape_pooled"),
            "rolling_mape_method": metrics.get("rolling_mape_method"),
            "daily_mape_series": metrics.get("daily_mape_series") or [],
            "rolling_mae": metrics.get("rolling_mae"),
            "valid_cycle_count": metrics.get("valid_cycle_count"),
            "total_cycle_count": metrics.get("total_cycle_count"),
            "coverage_rate": metrics.get("coverage_rate"),
            "window_days": metrics.get("window_days"),
            "status": metrics.get("status"),
        }
# @AI_GENERATED: end
