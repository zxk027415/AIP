# @AI_GENERATED
"""精度劣化实验：人工抬高滚动指标以触发真实 AccuracyMonitor，并可恢复。

设计约束：
  - 只改 AccuracyTracker 中的滚动指标，不伪造告警 JSON
  - 注入后必须调用 AccuracyMonitor.evaluate()，与 cron 同路径
  - 注入前落快照，restore 可写回；不自动回滚已执行的通道 A 切换
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from services.precision_ops.accuracy_tracker import AccuracyTracker
from services.precision_ops.utils import BASE_DATA_DIR, _atomic_write_json, ensure_data_dir, load_json_safe, now_iso
from services.precision_ops.versioning import make_version_key

logger = logging.getLogger(__name__)

SNAPSHOT_FILENAME = "degradation_inject_snapshot.json"


def _experiment_dir(slot: str) -> Path:
    path = BASE_DATA_DIR / slot / "accuracy_ops" / "experiments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_path(slot: str) -> Path:
    return _experiment_dir(slot) / SNAPSHOT_FILENAME


def _metrics_as_dict(metrics: Any) -> Optional[Dict[str, Any]]:
    if metrics is None:
        return None
    if isinstance(metrics, dict):
        return dict(metrics)
    # TypedDict / 对象兜底
    keys = (
        "rolling_mape",
        "rolling_wmape",
        "rolling_mae",
        "valid_cycle_count",
        "total_cycle_count",
        "coverage_rate",
        "window_days",
        "last_evaluated_at",
        "status",
    )
    out: Dict[str, Any] = {}
    for key in keys:
        if hasattr(metrics, key):
            out[key] = getattr(metrics, key)
        elif isinstance(metrics, dict) and key in metrics:
            out[key] = metrics[key]
    return out or None


def get_degradation_status(
    slot: str,
    tracker: AccuracyTracker,
    slot_store: Any,
) -> Dict[str, Any]:
    """返回当前是否处于注入态，以及生产版本相对基线的劣化%."""
    snap = load_json_safe(_snapshot_path(slot), default=None)
    active = isinstance(snap, dict) and bool(snap.get("active"))
    production = None
    try:
        slot_obj = slot_store.get(slot)
        production = slot_obj.production_model if slot_obj else None
    except Exception as exc:
        logger.warning("degradation_status: 读部署槽位失败 slot=%s: %s", slot, exc)

    current_degradation_pct = None
    workflow_id = None
    version_tag = None
    baseline = None
    current_mape = None
    status = None
    if production is not None:
        workflow_id = production.workflow_id
        version_tag = production.version_tag
        baseline = getattr(production, "baseline_mape", None)
        metrics = _metrics_as_dict(tracker.get_rolling_metrics(slot, workflow_id, version_tag))
        if metrics:
            status = metrics.get("status")
            current_mape = float(metrics.get("rolling_mape") or 0.0)
            if baseline is not None and float(baseline) > 0:
                current_degradation_pct = (current_mape - float(baseline)) / float(baseline) * 100

    return {
        "slot": slot,
        "injected": active,
        "snapshot": snap if active else None,
        "production": {
            "workflow_id": workflow_id,
            "version_tag": version_tag,
            "baseline_mape": baseline,
            "rolling_mape": current_mape,
            "status": status,
            "degradation_pct": current_degradation_pct,
        },
    }


def _resolve_target(
    slot: str,
    slot_store: Any,
    model_form: str,
    workflow_id: Optional[str],
    version_tag: Optional[str],
) -> Tuple[str, str, float, Any]:
    slot_obj = slot_store.get(slot)
    if slot_obj is None:
        raise ValueError(f"部署槽位不存在: {slot}")

    if workflow_id and version_tag:
        target = None
        if model_form == "shadow":
            target = next(
                (m for m in slot_obj.shadow_models if m.workflow_id == workflow_id and m.version_tag == version_tag),
                None,
            )
        else:
            if (
                slot_obj.production_model
                and slot_obj.production_model.workflow_id == workflow_id
                and slot_obj.production_model.version_tag == version_tag
            ):
                target = slot_obj.production_model
        if target is None:
            raise ValueError(f"未找到目标版本 {workflow_id}@{version_tag}")
    elif model_form == "shadow":
        shadows = [m for m in slot_obj.shadow_models if m.status == "shadow"]
        if not shadows:
            raise ValueError("当前槽位没有 shadow 版本")
        target = shadows[0]
    else:
        if slot_obj.production_model is None:
            raise ValueError("当前槽位没有 production 模型")
        target = slot_obj.production_model

    baseline = getattr(target, "baseline_mape", None)
    if baseline is None or float(baseline) <= 0:
        raise ValueError(
            f"目标版本缺少有效 baseline_mape（当前={baseline}），无法计算劣化率；请先在部署页登记基线"
        )
    return target.workflow_id, target.version_tag, float(baseline), target


def inject_degradation(
    *,
    slot: str,
    tracker: AccuracyTracker,
    monitor: Any,
    slot_store: Any,
    target_degradation_pct: float = 20.0,
    model_form: str = "production",
    workflow_id: Optional[str] = None,
    version_tag: Optional[str] = None,
    note: str = "",
    run_monitor: bool = True,
) -> Dict[str, Any]:
    """抬高滚动 MAPE 使劣化率达到目标，再跑真实监控。"""
    if target_degradation_pct <= 0:
        raise ValueError("target_degradation_pct 必须 > 0")

    existing = load_json_safe(_snapshot_path(slot), default=None)
    if isinstance(existing, dict) and existing.get("active"):
        raise ValueError(
            "已有未恢复的劣化注入快照；请先调用 restore-degradation，避免叠写"
        )

    wf_id, v_tag, baseline, _target = _resolve_target(
        slot, slot_store, model_form, workflow_id, version_tag
    )
    metrics = _metrics_as_dict(tracker.get_rolling_metrics(slot, wf_id, v_tag))
    if metrics is None:
        raise ValueError(
            f"指标不存在: {wf_id}@{v_tag}。请先 bootstrap / 回填使版本有滚动指标"
        )
    if metrics.get("status") != "active":
        raise ValueError(
            f"指标尚未激活（status={metrics.get('status')}）。"
            "请先运行 bootstrap_load_forecast_slot.py --activate-metrics 或完成回填"
        )

    new_mape = baseline * (1.0 + target_degradation_pct / 100.0)
    old_wmape = metrics.get("rolling_wmape")
    new_wmape = None
    if old_wmape is not None and float(baseline) > 0:
        # 同步抬高 WMAPE，保持与 MAPE 同劣化幅度（若基线用 WMAPE）
        new_wmape = float(old_wmape) * (new_mape / max(float(metrics.get("rolling_mape") or baseline), 1e-9))

    snapshot = {
        "active": True,
        "slot": slot,
        "model_form": model_form,
        "workflow_id": wf_id,
        "version_tag": v_tag,
        "version_key": make_version_key(wf_id, v_tag),
        "baseline_mape": baseline,
        "target_degradation_pct": float(target_degradation_pct),
        "metrics_before": metrics,
        "note": note or "",
        "injected_at": now_iso(),
    }
    ensure_data_dir(slot)
    _atomic_write_json(_snapshot_path(slot), snapshot)

    patch: Dict[str, Any] = {
        "rolling_mape": float(new_mape),
        "status": "active",
        "last_evaluated_at": now_iso(),
        "experiment_injected": True,
    }
    if new_wmape is not None:
        patch["rolling_wmape"] = float(new_wmape)
    # 保留周期计数，避免 monitor 因字段丢失误判
    for keep in ("rolling_mae", "valid_cycle_count", "total_cycle_count", "coverage_rate", "window_days"):
        if keep in metrics and keep not in patch:
            patch[keep] = metrics[keep]

    tracker.update_metrics(slot, wf_id, patch, version_tag=v_tag)

    alerts = []
    if run_monitor and monitor is not None:
        alerts = monitor.evaluate(slot) or []

    degradation_pct = (float(new_mape) - baseline) / baseline * 100
    return {
        "slot": slot,
        "injected": True,
        "workflow_id": wf_id,
        "version_tag": v_tag,
        "baseline_mape": baseline,
        "rolling_mape_before": float(metrics.get("rolling_mape") or 0.0),
        "rolling_mape_after": float(new_mape),
        "degradation_pct": degradation_pct,
        "alerts_created": [
            (a.dict() if hasattr(a, "dict") else a.model_dump() if hasattr(a, "model_dump") else a)
            for a in alerts
        ],
        "snapshot": {
            "injected_at": snapshot["injected_at"],
            "target_degradation_pct": snapshot["target_degradation_pct"],
            "note": snapshot.get("note") or "",
        },
    }


def restore_degradation(
    *,
    slot: str,
    tracker: AccuracyTracker,
    store: Any,
    close_open_alerts: bool = True,
) -> Dict[str, Any]:
    """按快照恢复指标；可选关闭仍 open 的实验相关告警。"""
    path = _snapshot_path(slot)
    snap = load_json_safe(path, default=None)
    if not isinstance(snap, dict) or not snap.get("active"):
        raise ValueError("没有可恢复的劣化注入快照")

    wf_id = str(snap["workflow_id"])
    v_tag = str(snap["version_tag"])
    before = snap.get("metrics_before") or {}
    if not isinstance(before, dict) or not before:
        raise ValueError("快照缺少 metrics_before，无法恢复")

    restore_patch = {k: v for k, v in before.items()}
    restore_patch["experiment_injected"] = False
    restore_patch["last_evaluated_at"] = now_iso()
    tracker.update_metrics(slot, wf_id, restore_patch, version_tag=v_tag)

    closed_alert_ids = []
    if close_open_alerts and store is not None:
        model_form = str(snap.get("model_form") or "production")
        try:
            for alert in store.list_alerts(slot, status="open") or []:
                if (
                    getattr(alert, "workflow_id", None) == wf_id
                    and getattr(alert, "version_tag", None) == v_tag
                ):
                    store.transition_alert_status(
                        slot,
                        alert.alert_id,
                        "closed",
                        recovery_evidence={
                            "type": "experiment_restore",
                            "ref": snap.get("injected_at"),
                            "at": now_iso(),
                            "model_form": model_form,
                        },
                    )
                    closed_alert_ids.append(alert.alert_id)
        except Exception as exc:
            logger.warning("restore_degradation: 关闭告警失败 slot=%s: %s", slot, exc)

    snap["active"] = False
    snap["restored_at"] = now_iso()
    snap["closed_alert_ids"] = closed_alert_ids
    _atomic_write_json(path, snap)

    return {
        "slot": slot,
        "restored": True,
        "workflow_id": wf_id,
        "version_tag": v_tag,
        "closed_alert_ids": closed_alert_ids,
        "metrics_restored": restore_patch,
    }


def activate_slot_metrics_from_deployment(
    *,
    slot: str,
    tracker: AccuracyTracker,
    slot_store: Any,
    min_valid_cycles: int = 3,
) -> Dict[str, Any]:
    """把部署槽位中 production/shadow 的指标写成 active，便于运营演示。

    防穿越说明：本函数只改 accuracy_metrics.json，不读写 StationData / PredictionResult，
    不会把未来真值提前暴露给训练。它不能替代真实 gap-1 日滚 + 回填验收。
    """
    slot_obj = slot_store.get(slot)
    if slot_obj is None:
        raise ValueError(f"部署槽位不存在: {slot}")

    updated = []
    models = []
    if slot_obj.production_model is not None:
        models.append(slot_obj.production_model)
    models.extend([m for m in slot_obj.shadow_models if m.status == "shadow"])

    for model in models:
        baseline = getattr(model, "baseline_mape", None)
        mape = float(baseline) if baseline is not None else float(getattr(model, "accuracy_score", None) or 5.0)
        existing = _metrics_as_dict(tracker.get_rolling_metrics(slot, model.workflow_id, model.version_tag)) or {}
        patch = {
            "rolling_mape": float(existing.get("rolling_mape") or mape),
            "rolling_mae": float(existing.get("rolling_mae") or 0.0),
            "valid_cycle_count": max(int(existing.get("valid_cycle_count") or 0), int(min_valid_cycles)),
            "total_cycle_count": max(int(existing.get("total_cycle_count") or 0), int(min_valid_cycles)),
            "coverage_rate": float(existing.get("coverage_rate") or 1.0),
            "window_days": int(existing.get("window_days") or 7),
            "status": "active",
            "last_evaluated_at": now_iso(),
            "activated_for_ops_at": now_iso(),
            "activation_mode": "ops_demo_no_future_leak",
        }
        if existing.get("rolling_wmape") is not None:
            patch["rolling_wmape"] = existing["rolling_wmape"]
        tracker.update_metrics(slot, model.workflow_id, patch, version_tag=model.version_tag)
        updated.append({
            "workflow_id": model.workflow_id,
            "version_tag": model.version_tag,
            "rolling_mape": patch["rolling_mape"],
            "valid_cycle_count": patch["valid_cycle_count"],
            "status": "active",
        })

    return {
        "slot": slot,
        "activated": updated,
        "count": len(updated),
        "no_leak_note": (
            "metrics-only activation; does not expose future StationData; "
            "real acceptance still requires gap-1 daily rolling + backfill"
        ),
    }# @AI_GENERATED: end
