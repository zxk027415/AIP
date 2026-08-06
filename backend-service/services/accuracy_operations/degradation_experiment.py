# @AI_GENERATED
"""精度劣化实验：默认改 StationData（缺失/噪声），再回填指标并走真实 AccuracyMonitor。

设计约束：
  - 默认数据层注入（missing / noise / zero_spike），让 RCA 能看到数据问题
  - mode=metric_rewrite 保留旧「直接改滚动 MAPE」路径（无 DB 单测 / 紧急演示）
  - 注入前落快照，restore 可写回；不自动回滚已执行的通道 A 切换
  - 不写入未来真值；只改已有业务水位内的历史 StationData
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.precision_ops.accuracy_tracker import AccuracyTracker
from services.precision_ops.utils import BASE_DATA_DIR, _atomic_write_json, ensure_data_dir, load_json_safe, now_iso
from services.precision_ops.versioning import make_version_key

logger = logging.getLogger(__name__)

SNAPSHOT_FILENAME = "degradation_inject_snapshot.json"
DEFAULT_STATION_ID = "yARGkDuq"
DEFAULT_FEATURE_NAME = "load"


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


def _window_mape_from_daily_series(
    daily_series: Optional[List[Dict[str, Any]]],
    *,
    window_start: Optional[str],
    window_end: Optional[str],
) -> Optional[float]:
    """劣化窗口内按 point_count 加权的 pooled daily MAPE。"""
    if not daily_series or not window_start or not window_end:
        return None
    try:
        ws = datetime.fromisoformat(str(window_start)).date()
        we = datetime.fromisoformat(str(window_end)).date()
    except (TypeError, ValueError):
        return None
    selected = []
    for item in daily_series:
        if not isinstance(item, dict):
            continue
        day_raw = item.get("business_day")
        mape = item.get("daily_mape")
        if day_raw is None or mape is None:
            continue
        try:
            day = datetime.fromisoformat(str(day_raw)).date()
        except (TypeError, ValueError):
            continue
        if ws <= day <= we:
            weight = int(item.get("point_count") or item.get("evaluated_point_count") or 1)
            selected.append((float(mape), max(weight, 1)))
    if not selected:
        return None
    total_w = sum(w for _, w in selected)
    return round(sum(m * w for m, w in selected) / total_w, 6)


def _compute_pooled_mape_in_timestamp_window(
    *,
    slot: str,
    workflow_id: str,
    version_tag: str,
    window_start: datetime,
    window_end: datetime,
) -> Optional[float]:
    """对指定时间窗内已评估预测点计算 pooled MAPE。"""
    from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
    from services.db.models.load_forecast import PredictionResult
    from services.precision_ops.daily_mape import compute_pooled_mape

    if not _is_db_enabled():
        return None
    repo = _get_lf_repo()
    if repo is None:
        return None
    with repo._adapter.get_sync_session() as session:
        rows = (
            session.query(PredictionResult)
            .filter(
                PredictionResult.slot == slot,
                PredictionResult.workflow_id == workflow_id,
                PredictionResult.version_tag == version_tag,
                PredictionResult.forecast_timestamp >= window_start,
                PredictionResult.forecast_timestamp <= window_end,
                PredictionResult.actual_value.isnot(None),
            )
            .all()
        )
        session.expunge_all()
    if not rows:
        return None
    return compute_pooled_mape(rows)


def _get_evaluated_prediction_window(
    slot: str,
    workflow_id: str,
    version_tag: str,
) -> Tuple[Optional[str], Optional[str]]:
    """返回该版本已有 actual 的最老/最新预测时间戳（ISO 字符串），供注入 MAPE 展示用。

    若无回填数据则返回 (None, None)，调用方回退到 StationData 注入窗口。
    """
    # @AI_GENERATED
    try:
        from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
        from services.db.models.load_forecast import PredictionResult
        from sqlalchemy import func

        if not _is_db_enabled():
            return None, None
        repo = _get_lf_repo()
        if repo is None:
            return None, None
        with repo._adapter.get_sync_session() as session:
            row = session.query(
                func.min(PredictionResult.forecast_timestamp),
                func.max(PredictionResult.forecast_timestamp),
            ).filter(
                PredictionResult.slot == slot,
                PredictionResult.workflow_id == workflow_id,
                PredictionResult.version_tag == version_tag,
                PredictionResult.actual_value.isnot(None),
                PredictionResult.status == "evaluated",
            ).one_or_none()
            if row and row[0] and row[1]:
                min_ts = row[0]
                max_ts = row[1]
                if getattr(min_ts, "tzinfo", None) is not None:
                    min_ts = min_ts.replace(tzinfo=None)
                if getattr(max_ts, "tzinfo", None) is not None:
                    max_ts = max_ts.replace(tzinfo=None)
                return min_ts.isoformat(), max_ts.isoformat()
    except Exception as exc:
        logger.warning("_get_evaluated_prediction_window 失败: %s", exc)
    return None, None
    # @AI_GENERATED: end


def _build_inject_mape_summary(
    *,
    baseline: float,
    metrics_before: Optional[Dict[str, Any]],
    metrics_after: Dict[str, Any],
    corruption_window: Optional[Dict[str, Any]] = None,
    pipeline_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """汇总注入前后 MAPE，供 API / 快照 / UI 统一展示。"""
    mape_before = float((metrics_before or {}).get("rolling_mape") or 0.0)
    mape_after = float(metrics_after.get("rolling_mape") or mape_before)
    method = metrics_after.get("rolling_mape_method") or (metrics_before or {}).get("rolling_mape_method")
    pooled_after = metrics_after.get("rolling_mape_pooled")

    window_start = (corruption_window or {}).get("window_start")
    window_end = (corruption_window or {}).get("window_end")
    # @AI_GENERATED: window_before 只从注入前快照算，window_after 实时 DB 查询
    # 若都用同一个 _compute_pooled_mape，注入前后结果一样（DB 已被修改），delta 永远为 0
    window_before = _window_mape_from_daily_series(
        (metrics_before or {}).get("daily_mape_series") if isinstance((metrics_before or {}).get("daily_mape_series"), list) else None,
        window_start=window_start,
        window_end=window_end,
    )
    if window_before is None:
        # 没有 daily series 时用注入前 rolling_mape 作为 window_before（已是历史快照值）
        window_before = mape_before if mape_before > 0 else None

    # window_after：总是从 DB 实时查（才能反映注入后的变化）
    window_after = None
    if window_start and window_end:
        try:
            ws = datetime.fromisoformat(str(window_start))
            we = datetime.fromisoformat(str(window_end))
            wf_id = (corruption_window or {}).get("workflow_id")
            v_tag = (corruption_window or {}).get("version_tag")
            if wf_id and v_tag:
                window_after = _compute_pooled_mape_in_timestamp_window(
                    slot=str((corruption_window or {}).get("slot") or ""),
                    workflow_id=str(wf_id),
                    version_tag=str(v_tag),
                    window_start=ws,
                    window_end=we,
                )
        except (TypeError, ValueError):
            pass
    if window_after is None:
        # fallback：从注入后 daily series 里找
        window_after = _window_mape_from_daily_series(
            metrics_after.get("daily_mape_series") if isinstance(metrics_after.get("daily_mape_series"), list) else None,
            window_start=window_start,
            window_end=window_end,
        )
    if window_after is None:
        window_after = mape_after
    # @AI_GENERATED: end

    # 实验主展示：优先劣化窗口 MAPE（对注入敏感）
    display_after = window_after
    display_before = window_before if window_before is not None else mape_before

    degradation_vs_baseline = None
    if baseline and float(baseline) > 0:
        degradation_vs_baseline = (display_after - float(baseline)) / float(baseline) * 100
    delta_vs_before = None
    if display_before and display_before > 0:
        delta_vs_before = (display_after - display_before) / display_before * 100

    daily_roll_skipped = pipeline_result is not None and not pipeline_result.get("daily_rolling_cycle_id")
    skip_reason = None
    if daily_roll_skipped:
        skip_reason = pipeline_result.get("daily_rolling_skip_reason") or "history_not_ready_or_no_new_cycle"

    return {
        "rolling_mape_before": round(mape_before, 6),
        "post_train_rolling_mape": round(display_after, 6),
        "rolling_mape_after": round(mape_after, 6),
        "post_train_window_mape": window_after,
        "rolling_mape_window_before": window_before,
        "rolling_mape_window_after": window_after,
        "rolling_mape_method": method,
        "rolling_mape_pooled_after": (
            round(float(pooled_after), 6) if pooled_after is not None else None
        ),
        "degradation_pct": (
            round(degradation_vs_baseline, 6) if degradation_vs_baseline is not None else None
        ),
        "mape_delta_pct": round(delta_vs_before, 6) if delta_vs_before is not None else None,
        "daily_rolling_cycle_id": (pipeline_result or {}).get("daily_rolling_cycle_id"),
        "daily_rolling_skipped": daily_roll_skipped,
        "daily_rolling_skip_reason": skip_reason,
        "experiment_alert_baseline": round(mape_before, 6) if mape_before > 0 else None,
        "experiment_alert_current": round(
            max(
                float(display_after or 0),
                float(pooled_after or 0) if pooled_after is not None else 0,
                float(mape_after or 0),
            ),
            6,
        ) if mape_before > 0 else None,
        "experiment_alert_degradation_pct": round(
            (
                max(
                    float(display_after or 0),
                    float(pooled_after or 0) if pooled_after is not None else 0,
                    float(mape_after or 0),
                )
                - mape_before
            )
            / mape_before
            * 100,
            6,
        )
        if mape_before > 0
        else None,
    }


def _evaluate_experiment_alerts(
    *,
    slot: str,
    store: Any,
    monitor: Any,
    wf_id: str,
    v_tag: str,
    model_form: str,
    ar_baseline_mape: float,
    mape_summary: Dict[str, Any],
    threshold_pct: float = 15.0,
    cooldown_hours: float = 48.0,
) -> List[Any]:
    """实验注入告警：相对「注入前线上 rolling MAPE」判定，而非 AR 回测基线。"""
    from datetime import timezone

    from services.accuracy_operations.models import (
        AccuracyAlert,
        AlertSeverity,
        AlertStatus,
        DegradationTrend,
        ModelForm,
        gen_alert_id,
    )

    baseline_online = float(mape_summary.get("experiment_alert_baseline") or mape_summary.get("rolling_mape_before") or 0)
    current = float(mape_summary.get("experiment_alert_current") or 0)
    if baseline_online <= 0 or current <= 0:
        return []

    degradation_pct = (current - baseline_online) / baseline_online * 100
    if degradation_pct < threshold_pct:
        return []

    model_form_enum = ModelForm.shadow if str(model_form) == "shadow" else ModelForm.production
    # @AI_GENERATED: 只看「同版本的实验注入告警」是否已存在，不让普通运营告警阻止实验
    has_experiment_alert = False
    for existing in (store.list_alerts(slot, status="open") or []):
        if (
            getattr(existing, "workflow_id", None) == wf_id
            and getattr(existing, "version_tag", None) == v_tag
        ):
            ev = getattr(existing, "recovery_evidence", None) or {}
            if isinstance(ev, dict) and ev.get("type") == "experiment_inject":
                has_experiment_alert = True
                break
    if has_experiment_alert:
        return []
    # @AI_GENERATED: end

    severity = AlertSeverity.critical if degradation_pct >= threshold_pct * 2 else AlertSeverity.warning
    trend = DegradationTrend.sudden
    if monitor is not None and hasattr(monitor, "_detect_trend"):
        try:
            trend = monitor._detect_trend(slot, wf_id, v_tag, degradation_pct)
        except Exception:
            pass

    alert = AccuracyAlert(
        alert_id=gen_alert_id(),
        slot=slot,
        model_form=model_form_enum,
        workflow_id=wf_id,
        version_tag=v_tag,
        metric_name = "mape",
        baseline_metric=baseline_online,
        current_metric=current,
        baseline_mape=float(ar_baseline_mape),
        current_rolling_mape=current,
        degradation_pct=degradation_pct,
        degradation_trend=trend,
        severity=severity,
        status=AlertStatus.open,
        cooldown_until=(
            datetime.now(tz=timezone.utc) + timedelta(hours=float(cooldown_hours))
        ).isoformat(),
        recovery_evidence={
            "type": "experiment_inject",
            "ref": "pre_inject_online_mape_baseline",
            "at": now_iso(),
            "baseline_online_mape": baseline_online,
            "current_mape": current,
        },
    )
    store.save_alert(slot, alert)
    logger.info(
        "degradation_experiment: alert=%s slot=%s version=%s@%s experiment_degradation=%.2f%% "
        "(baseline_online=%.4f current=%.4f)",
        alert.alert_id,
        slot,
        wf_id,
        v_tag,
        degradation_pct,
        baseline_online,
        current,
    )
    return [alert]


def get_degradation_status(
    slot: str,
    tracker: AccuracyTracker,
    slot_store: Any,
) -> Dict[str, Any]:
    """返回当前是否处于注入态，以及生产版本相对基线的劣化%。"""
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
    inject_outcome: Optional[Dict[str, Any]] = None
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

    if active and isinstance(snap, dict):
        snap_before = snap.get("metrics_before") if isinstance(snap.get("metrics_before"), dict) else {}
        snap_after = snap.get("metrics_after") if isinstance(snap.get("metrics_after"), dict) else {}
        if not snap_after and snap.get("post_train_rolling_mape") is not None:
            snap_after = {"rolling_mape": snap.get("post_train_rolling_mape")}
        inject_outcome = {
            "injected_at": snap.get("injected_at"),
            "mode": snap.get("mode"),
            "rerun_pipeline": snap.get("rerun_pipeline"),
            "rolling_mape_before": snap.get("rolling_mape_before"),
            "post_train_rolling_mape": snap.get("post_train_rolling_mape") or snap.get("rolling_mape_after"),
            "post_train_window_mape": snap.get("post_train_window_mape") or snap.get("rolling_mape_window_after"),
            "rolling_mape_window_before": snap.get("rolling_mape_window_before"),
            "rolling_mape_window_after": snap.get("rolling_mape_window_after"),
            "rolling_mape_after": snap.get("rolling_mape_after") or snap.get("post_train_rolling_mape"),
            "rolling_mape_method": snap.get("rolling_mape_method") or snap_after.get("rolling_mape_method"),
            "rolling_mape_pooled_after": snap.get("rolling_mape_pooled_after"),
            "degradation_pct": snap.get("degradation_pct"),
            "mape_delta_pct": snap.get("mape_delta_pct"),
            "baseline_mape": snap.get("baseline_mape"),
            "daily_rolling_cycle_id": snap.get("daily_rolling_cycle_id") or (snap.get("pipeline") or {}).get("daily_rolling_cycle_id"),
            "daily_rolling_skipped": snap.get("daily_rolling_skipped"),
            "daily_rolling_skip_reason": snap.get("daily_rolling_skip_reason") or (snap.get("pipeline") or {}).get("daily_rolling_skip_reason"),
            "experiment_alert_baseline": snap.get("experiment_alert_baseline"),
            "experiment_alert_current": snap.get("experiment_alert_current"),
            "experiment_alert_degradation_pct": snap.get("experiment_alert_degradation_pct"),
            "corruption_window": {
                "window_start": (snap.get("data_corruption") or {}).get("window_start"),
                "window_end": (snap.get("data_corruption") or {}).get("window_end"),
            },
            "pipeline": snap.get("pipeline"),
        }
        if inject_outcome["post_train_rolling_mape"] is None and current_mape is not None:
            inject_outcome["post_train_rolling_mape"] = current_mape

    return {
        "slot": slot,
        "injected": active,
        "mode": (snap or {}).get("mode") if active else None,
        "snapshot": snap if active else None,
        "inject_outcome": inject_outcome,
        "production": {
            "workflow_id": workflow_id,
            "version_tag": version_tag,
            "baseline_mape": baseline,
            "rolling_mape": current_mape,
            "status": status,
            "degradation_pct": current_degradation_pct,
            "post_train_rolling_mape": (
                inject_outcome.get("post_train_rolling_mape") if inject_outcome else None
            ),
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
        # 数据层注入不强制 baseline；metric_rewrite 才需要
        baseline = float(getattr(target, "accuracy_score", None) or 0.0) or 5.0
    return target.workflow_id, target.version_tag, float(baseline), target


def _inject_metric_rewrite(
    *,
    slot: str,
    tracker: AccuracyTracker,
    monitor: Any,
    wf_id: str,
    v_tag: str,
    baseline: float,
    target_degradation_pct: float,
    model_form: str,
    note: str,
    run_monitor: bool,
) -> Dict[str, Any]:
    metrics = _metrics_as_dict(tracker.get_rolling_metrics(slot, wf_id, v_tag))
    if metrics is None:
        raise ValueError(
            f"指标不存在: {wf_id}@{v_tag}。请先 bootstrap / 回填使版本有滚动指标"
        )
    if metrics.get("status") != "active":
        raise ValueError(
            f"指标尚未激活（status={metrics.get('status')}）。"
            "请先运行 activate-metrics 或完成回填"
        )

    new_mape = baseline * (1.0 + target_degradation_pct / 100.0)
    old_wmape = metrics.get("rolling_wmape")
    new_wmape = None
    if old_wmape is not None and float(baseline) > 0:
        new_wmape = float(old_wmape) * (
            new_mape / max(float(metrics.get("rolling_mape") or baseline), 1e-9)
        )

    snapshot = {
        "active": True,
        "mode": "metric_rewrite",
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

    patch: Dict[str, Any] = {
        "rolling_mape": float(new_mape),
        "status": "active",
        "last_evaluated_at": now_iso(),
        "experiment_injected": True,
    }
    if new_wmape is not None:
        patch["rolling_wmape"] = float(new_wmape)
    for keep in ("rolling_mae", "valid_cycle_count", "total_cycle_count", "coverage_rate", "window_days"):
        if keep in metrics and keep not in patch:
            patch[keep] = metrics[keep]

    tracker.update_metrics(slot, wf_id, patch, version_tag=v_tag)

    metrics_after = _metrics_as_dict(tracker.get_rolling_metrics(slot, wf_id, v_tag)) or {}
    mape_summary = _build_inject_mape_summary(
        baseline=baseline,
        metrics_before=metrics,
        metrics_after={**metrics, **patch, **metrics_after},
    )
    degradation_pct = mape_summary.get("degradation_pct") or 0.0
    snapshot.update(
        {
            **mape_summary,
            "metrics_after": metrics_after,
            "degradation_pct": degradation_pct,
            "rerun_pipeline": False,
        }
    )
    ensure_data_dir(slot)
    _atomic_write_json(_snapshot_path(slot), snapshot)

    alerts = []
    if run_monitor and monitor is not None:
        alerts = monitor.evaluate(slot) or []

    degradation_pct = mape_summary.get("degradation_pct") or 0.0
    return {
        "slot": slot,
        "injected": True,
        "mode": "metric_rewrite",
        "workflow_id": wf_id,
        "version_tag": v_tag,
        "baseline_mape": baseline,
        **mape_summary,
        "degradation_pct": degradation_pct,
        "inject_outcome": {
            **mape_summary,
            "injected_at": snapshot["injected_at"],
            "mode": "metric_rewrite",
            "rerun_pipeline": False,
        },
        "alerts_created": [
            (a.dict() if hasattr(a, "dict") else a.model_dump() if hasattr(a, "model_dump") else a)
            for a in alerts
        ],
        "snapshot": {
            "injected_at": snapshot["injected_at"],
            "target_degradation_pct": snapshot["target_degradation_pct"],
            "note": snapshot.get("note") or "",
            "mode": "metric_rewrite",
        },
    }


def _resolve_station_feature(
    slot: str,
    station_id: Optional[str],
    feature_name: Optional[str],
) -> Tuple[str, str]:
    """解析劣化目标站点/特征：优先入参，否则取该 slot 下点数最多的 (station, feature)。"""
    from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
    from services.db.models.load_forecast import StationData
    from sqlalchemy import func

    if station_id and feature_name:
        return station_id, feature_name
    if not _is_db_enabled():
        return station_id or DEFAULT_STATION_ID, feature_name or DEFAULT_FEATURE_NAME
    repo = _get_lf_repo()
    if repo is None:
        return station_id or DEFAULT_STATION_ID, feature_name or DEFAULT_FEATURE_NAME
    with repo._adapter.get_sync_session() as session:
        q = session.query(
            StationData.station_id,
            StationData.feature_name,
            func.count(StationData.id).label("cnt"),
        ).filter(StationData.slot == slot)
        if station_id:
            q = q.filter(StationData.station_id == station_id)
        # 未指定 feature 时优先 load（负荷故事线），避免误打到 pv 特征
        prefer_feature = feature_name or DEFAULT_FEATURE_NAME
        q_pref = q.filter(StationData.feature_name == prefer_feature)
        row = (
            q_pref.group_by(StationData.station_id, StationData.feature_name)
            .order_by(func.count(StationData.id).desc())
            .first()
        )
        if row is None:
            if feature_name:
                q = q.filter(StationData.feature_name == feature_name)
            row = (
                q.group_by(StationData.station_id, StationData.feature_name)
                .order_by(func.count(StationData.id).desc())
                .first()
            )
    if row is None:
        raise ValueError(
            f"slot={slot} 无 StationData"
            + (f"（station={station_id}）" if station_id else "")
            + (f"（feature={feature_name}）" if feature_name else "")
            + "，请先 mock 喂数 / pull"
        )
    return str(row[0]), str(row[1])


def _run_load_forecast_pipeline_after_data_change(
    *,
    slot: str,
    station_id: str,
    feature_name: str,
    slot_store: Any,
) -> Dict[str, Any]:
    """StationData 变更后走真实 gap-1 日滚 + 精度回填，产出新预测与指标。"""
    from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
    from services.precision_ops.production_registry import ProductionRegistry
    from services.precision_ops.version_registry import VersionRegistry
    from services.scheduler.tasks.load_forecast_tasks import (
        make_accuracy_backfill_task,
        make_daily_rolling_task,
    )

    if not _is_db_enabled():
        return {"skipped": True, "reason": "db_disabled"}
    repo = _get_lf_repo()
    if repo is None:
        return {"skipped": True, "reason": "no_repo"}

    daily = make_daily_rolling_task(
        repo,
        slot,
        station_id=station_id,
        feature_name=feature_name,
        slot_store=slot_store,
        production_registry=ProductionRegistry(),
        version_registry=VersionRegistry(),
        relax_history_readiness=True,
    )
    cycle_id = daily()
    backfill = make_accuracy_backfill_task(
        repo,
        slot,
        station_id=station_id,
        feature_name=feature_name,
        slot_store=slot_store,
    )
    updated = backfill()
    skip_reason = None
    if cycle_id is None:
        skip_reason = (
            "daily_rolling_returned_none：劣化后 history 不完整或无可跑业务日；"
            "experiment 模式已放宽门禁，若仍为 null 请看后端日志"
        )
    return {
        "skipped": False,
        "daily_rolling_cycle_id": cycle_id,
        "daily_rolling_skip_reason": skip_reason,
        "backfill_updated_versions": int(updated or 0),
    }


def _corrupt_station_data(
    *,
    slot: str,
    mode: str,
    days: int,
    fraction: float,
    noise_pct: float,
    station_id: Optional[str],
    feature_name: Optional[str],
    seed: int = 42,
) -> Dict[str, Any]:
    """改写/删除业务水位内最近 days 天的 StationData，返回可恢复快照片段。"""
    from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
    from services.db.models.load_forecast import StationData

    if not _is_db_enabled():
        raise ValueError("数据库未启用，无法做数据层劣化；请改用 mode=metric_rewrite")

    repo = _get_lf_repo()
    if repo is None:
        raise ValueError("LoadForecastRepository 不可用，无法做数据层劣化")

    station_id, feature_name = _resolve_station_feature(slot, station_id, feature_name)
    rng = random.Random(seed)
    affected: List[Dict[str, Any]] = []
    deleted_ids: List[int] = []
    updated = 0

    with repo._adapter.get_sync_session() as session:
        # @AI_GENERATED: 窗口锚点改为「有已回填 actual 的最新预测时间戳」
        # 而不是 StationData 末端——末端附近数据极稀疏，注入 1 行改不了 MAPE
        from services.db.models.load_forecast import PredictionResult
        anchored_ts = (
            session.query(PredictionResult.forecast_timestamp)
            .filter(
                PredictionResult.slot == slot,
                PredictionResult.actual_value.isnot(None),
                PredictionResult.status == "evaluated",
            )
            .order_by(PredictionResult.forecast_timestamp.desc())
            .limit(1)
            .scalar()
        )
        if anchored_ts is not None:
            if getattr(anchored_ts, "tzinfo", None) is not None:
                anchored_ts = anchored_ts.replace(tzinfo=None)
            inject_end = anchored_ts
        else:
            # 没有已回填数据时回退到 StationData 水位
            inject_end = (
                session.query(StationData.timestamp_utc)
                .filter(
                    StationData.slot == slot,
                    StationData.station_id == station_id,
                    StationData.feature_name == feature_name,
                )
                .order_by(StationData.timestamp_utc.desc())
                .limit(1)
                .scalar()
            )
            if inject_end is None:
                raise ValueError(
                    f"slot={slot} 无 StationData（station={station_id}, feature={feature_name}），"
                    "请先 mock 喂数 / pull"
                )
            if getattr(inject_end, "tzinfo", None) is not None:
                inject_end = inject_end.replace(tzinfo=None)
        # @AI_GENERATED: end

        max_ts = inject_end
        window_start = max_ts - timedelta(days=max(1, int(days)))

        rows = (
            session.query(StationData)
            .filter(
                StationData.slot == slot,
                StationData.station_id == station_id,
                StationData.feature_name == feature_name,
                StationData.timestamp_utc >= window_start,
                StationData.timestamp_utc <= max_ts,
            )
            .order_by(StationData.timestamp_utc.asc())
            .all()
        )
        if not rows:
            raise ValueError("选定时间窗内无 StationData 行可劣化")

        for row in rows:
            if rng.random() > max(0.01, min(1.0, float(fraction))):
                continue
            affected.append({
                "id": int(row.id),
                "station_id": row.station_id,
                "timestamp_utc": row.timestamp_utc.isoformat() if row.timestamp_utc else None,
                "feature_name": row.feature_name,
                "value": float(row.value),
                "slot": row.slot,
            })
            if mode == "missing":
                deleted_ids.append(int(row.id))
                session.delete(row)
            elif mode == "zero_spike":
                row.value = 0.0
                updated += 1
            else:  # noise
                scale = float(noise_pct) / 100.0
                delta = float(row.value) * scale * (rng.random() * 2.0 - 1.0)
                row.value = float(row.value) + delta
                updated += 1
        session.commit()

    return {
        "mode": mode,
        "station_id": station_id,
        "feature_name": feature_name,
        "window_start": window_start.isoformat(),
        "window_end": max_ts.isoformat(),
        "rows_touched": len(affected),
        "rows_updated": updated,
        "rows_deleted": len(deleted_ids),
        "station_rows_before": affected,
        "deleted_ids": deleted_ids,
    }


def _rebind_prediction_actuals_and_metrics(
    *,
    slot: str,
    tracker: AccuracyTracker,
    slot_store: Any,
    station_id: str,
    feature_name: str,
    window_days: int = 7,
) -> Dict[str, Any]:
    """用当前 StationData 重绑 PredictionResult.actual，并按 version 重算滚动 MAPE/WMAPE。"""
    import statistics
    from collections import defaultdict

    from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
    from services.db.models.load_forecast import PredictionResult, StationData

    if not _is_db_enabled():
        return {"rebound": 0, "versions_updated": 0}

    repo = _get_lf_repo()
    if repo is None:
        return {"rebound": 0, "versions_updated": 0}

    rebound = 0
    with repo._adapter.get_sync_session() as session:
        max_ts = (
            session.query(StationData.timestamp_utc)
            .filter(StationData.slot == slot, StationData.station_id == station_id)
            .order_by(StationData.timestamp_utc.desc())
            .limit(1)
            .scalar()
        )
        if max_ts is None:
            return {"rebound": 0, "versions_updated": 0}
        if getattr(max_ts, "tzinfo", None) is not None:
            max_ts = max_ts.replace(tzinfo=None)
        window_start = max_ts - timedelta(days=max(1, int(window_days)))

        preds = (
            session.query(PredictionResult)
            .filter(
                PredictionResult.slot == slot,
                PredictionResult.forecast_timestamp >= window_start,
                PredictionResult.forecast_timestamp <= max_ts,
                PredictionResult.status.in_(["pending", "evaluated", "failed"]),
            )
            .all()
        )
        for pred in preds:
            actual = (
                session.query(StationData.value)
                .filter(
                    StationData.slot == slot,
                    StationData.station_id == station_id,
                    StationData.feature_name == feature_name,
                    StationData.timestamp_utc == pred.forecast_timestamp,
                )
                .order_by(StationData.ingested_at.desc())
                .limit(1)
                .scalar()
            )
            if actual is None:
                # missing：清空 actual，覆盖率下降
                if pred.actual_value is not None:
                    pred.actual_value = None
                    pred.status = "pending"
                    rebound += 1
                continue
            pred.actual_value = float(actual)
            pred.status = "evaluated"
            pred.evaluated_at = datetime.utcnow()
            rebound += 1
        session.commit()

        rows = (
            session.query(PredictionResult)
            .filter(
                PredictionResult.slot == slot,
                PredictionResult.actual_value.isnot(None),
                PredictionResult.forecast_timestamp >= window_start,
            )
            .all()
        )
        session.expunge_all()

    groups: Dict[Tuple[str, str], list] = defaultdict(list)
    for row in rows:
        groups[(row.workflow_id, row.version_tag)].append(row)

    updated = 0
    mape_by_wf: Dict[str, float] = {}
    for (wf_id, v_tag), preds in groups.items():
        valid = [p for p in preds if p.actual_value not in (None, 0)]
        if not valid:
            continue
        mape = statistics.mean(
            abs(float(p.predicted_value) - float(p.actual_value)) / abs(float(p.actual_value)) * 100
            for p in valid
        )
        abs_err = sum(abs(float(p.predicted_value) - float(p.actual_value)) for p in valid)
        abs_act = sum(abs(float(p.actual_value)) for p in valid)
        wmape = (abs_err / abs_act * 100) if abs_act else None
        existing = _metrics_as_dict(tracker.get_rolling_metrics(slot, wf_id, v_tag)) or {}
        patch = {
            "rolling_mape": float(mape),
            "rolling_wmape": float(wmape) if wmape is not None else existing.get("rolling_wmape"),
            "valid_cycle_count": len(valid),
            "total_cycle_count": len(preds),
            "coverage_rate": len(valid) / max(len(preds), 1),
            "window_days": int(window_days),
            "status": "active",
            "last_evaluated_at": now_iso(),
            "experiment_injected": True,
        }
        tracker.update_metrics(slot, wf_id, patch, version_tag=v_tag)
        mape_by_wf[wf_id] = float(mape)
        updated += 1

    if slot_store is not None and mape_by_wf:
        try:
            from services.scheduler.tasks.load_forecast_tasks import _post_backfill_slot_update

            _post_backfill_slot_update(slot, slot_store, mape_by_wf)
        except Exception as exc:
            logger.warning("data degradation: post_backfill_slot_update 失败: %s", exc)

    return {"rebound": rebound, "versions_updated": updated, "mape_by_workflow": mape_by_wf}


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
    mode: str = "noise",
    days: int = 5,
    fraction: float = 0.6,
    noise_pct: float = 45.0,
    station_id: Optional[str] = None,
    feature_name: Optional[str] = None,
    rerun_pipeline: bool = True,
) -> Dict[str, Any]:
    """注入劣化。默认改 StationData 并日滚重训；mode=metric_rewrite 时只改滚动指标。"""
    existing = load_json_safe(_snapshot_path(slot), default=None)
    if isinstance(existing, dict) and existing.get("active"):
        raise ValueError(
            "已有未恢复的劣化注入快照；请先调用 restore-degradation，避免叠写"
        )

    mode_norm = str(mode or "noise").strip().lower()
    if mode_norm not in {"noise", "missing", "zero_spike", "metric_rewrite"}:
        raise ValueError(f"不支持的 mode={mode!r}，可选 noise|missing|zero_spike|metric_rewrite")

    wf_id, v_tag, baseline, _target = _resolve_target(
        slot, slot_store, model_form, workflow_id, version_tag
    )

    if mode_norm == "metric_rewrite":
        if target_degradation_pct <= 0:
            raise ValueError("metric_rewrite 模式下 target_degradation_pct 必须 > 0")
        return _inject_metric_rewrite(
            slot=slot,
            tracker=tracker,
            monitor=monitor,
            wf_id=wf_id,
            v_tag=v_tag,
            baseline=baseline,
            target_degradation_pct=target_degradation_pct,
            model_form=model_form,
            note=note,
            run_monitor=run_monitor,
        )

    metrics_before = _metrics_as_dict(tracker.get_rolling_metrics(slot, wf_id, v_tag))
    data_snap = _corrupt_station_data(
        slot=slot,
        mode=mode_norm,
        days=days,
        fraction=fraction,
        noise_pct=noise_pct,
        station_id=station_id,
        feature_name=feature_name,
    )
    resolved_station = str(data_snap.get("station_id") or DEFAULT_STATION_ID)
    resolved_feature = str(data_snap.get("feature_name") or DEFAULT_FEATURE_NAME)
    pipeline_result: Optional[Dict[str, Any]] = None
    rebind: Dict[str, Any]
    if rerun_pipeline:
        pipeline_result = _run_load_forecast_pipeline_after_data_change(
            slot=slot,
            station_id=resolved_station,
            feature_name=resolved_feature,
            slot_store=slot_store,
        )
        # @AI_GENERATED: pipeline 完成后强制 rebind 确保 tracker 指标同步
        # 即使 backfill_updated_versions=0（新 cycle 无 actual），
        # 历史已有 actual 的 cycle 受 StationData 劣化影响，需重算 MAPE
        _rebind_result = _rebind_prediction_actuals_and_metrics(
            slot=slot,
            tracker=tracker,
            slot_store=slot_store,
            station_id=resolved_station,
            feature_name=resolved_feature,
            window_days=30,  # 大窗口确保覆盖历史已回填 cycle
        )
        rebind = {
            "rebound": _rebind_result.get("rebound", 0),
            "versions_updated": max(
                pipeline_result.get("backfill_updated_versions", 0),
                _rebind_result.get("versions_updated", 0),
            ),
            "pipeline": pipeline_result,
            "rebind_after_pipeline": _rebind_result,
        }
        # @AI_GENERATED: end
    else:
        rebind = _rebind_prediction_actuals_and_metrics(
            slot=slot,
            tracker=tracker,
            slot_store=slot_store,
            station_id=resolved_station,
            feature_name=resolved_feature,
            window_days=max(7, int(days) + 2),
        )

    metrics_after = _metrics_as_dict(tracker.get_rolling_metrics(slot, wf_id, v_tag)) or {}
    # @AI_GENERATED: 用「已有回填 actual 的预测时间范围」作为展示窗口
    # StationData 注入窗（corruption_window）是真值时间戳范围，
    # PredictionResult.forecast_timestamp 是预测目标时间，两者可能不重合。
    # 用 PredictionResult 已回填区间算 MAPE 才对注入敏感。
    _display_window_start, _display_window_end = _get_evaluated_prediction_window(
        slot=slot, workflow_id=wf_id, version_tag=v_tag
    )
    mape_summary = _build_inject_mape_summary(
        baseline=baseline,
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        corruption_window={
            "slot": slot,
            "workflow_id": wf_id,
            "version_tag": v_tag,
            "window_start": _display_window_start or data_snap.get("window_start"),
            "window_end": _display_window_end or data_snap.get("window_end"),
        },
        pipeline_result=pipeline_result,
    )
    # @AI_GENERATED: end
    degradation_pct = mape_summary.get("degradation_pct")

    snapshot = {
        "active": True,
        "mode": mode_norm,
        "slot": slot,
        "model_form": model_form,
        "workflow_id": wf_id,
        "version_tag": v_tag,
        "version_key": make_version_key(wf_id, v_tag),
        "baseline_mape": baseline,
        "target_degradation_pct": float(target_degradation_pct),
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "data_corruption": data_snap,
        "rebind": rebind,
        "pipeline": pipeline_result,
        "rerun_pipeline": bool(rerun_pipeline),
        **mape_summary,
        "degradation_pct": degradation_pct,
        "note": note or "",
        "injected_at": now_iso(),
    }
    ensure_data_dir(slot)
    _atomic_write_json(_snapshot_path(slot), snapshot)

    alerts = []
    if run_monitor and monitor is not None:
        threshold_pct = 15.0
        cooldown_hours = 48.0
        try:
            cfg = monitor._config_manager.load_config(slot)
            threshold_pct = float(cfg.degradation_threshold_pct)
            cooldown_hours = float(cfg.cooldown_hours)
        except Exception:
            pass
        alerts = _evaluate_experiment_alerts(
            slot=slot,
            store=monitor._store,
            monitor=monitor,
            wf_id=wf_id,
            v_tag=v_tag,
            model_form=model_form,
            ar_baseline_mape=baseline,
            mape_summary=mape_summary,
            threshold_pct=threshold_pct,
            cooldown_hours=cooldown_hours,
        )
        if not alerts:
            alerts = monitor.evaluate(slot) or []

    return {
        "slot": slot,
        "injected": True,
        "mode": mode_norm,
        "workflow_id": wf_id,
        "version_tag": v_tag,
        "baseline_mape": baseline,
        **mape_summary,
        "degradation_pct": degradation_pct,
        "inject_outcome": {
            **mape_summary,
            "injected_at": snapshot["injected_at"],
            "mode": mode_norm,
            "rerun_pipeline": bool(rerun_pipeline),
            "pipeline": pipeline_result,
        },
        "data_corruption": {
            "rows_touched": data_snap.get("rows_touched"),
            "rows_updated": data_snap.get("rows_updated"),
            "rows_deleted": data_snap.get("rows_deleted"),
            "window_start": data_snap.get("window_start"),
            "window_end": data_snap.get("window_end"),
        },
        "rebind": rebind,
        "pipeline": pipeline_result,
        "rerun_pipeline": bool(rerun_pipeline),
        "alerts_created": [
            (a.dict() if hasattr(a, "dict") else a.model_dump() if hasattr(a, "model_dump") else a)
            for a in alerts
        ],
        "snapshot": {
            "injected_at": snapshot["injected_at"],
            "mode": mode_norm,
            "note": snapshot.get("note") or "",
        },
        "note": (
            "已改 StationData；"
            + (
                "已触发 gap-1 日滚 + 精度回填，预测基于劣化后数据重训。"
                if rerun_pipeline
                else "已重绑 PredictionResult.actual / 滚动指标（未重训）。"
            )
            + " RCA 应能看到数据问题。恢复请调用 restore-degradation。"
        ),
    }


def restore_degradation(
    *,
    slot: str,
    tracker: AccuracyTracker,
    store: Any,
    close_open_alerts: bool = True,
    slot_store: Any = None,
    rerun_pipeline: bool = True,
) -> Dict[str, Any]:
    """按快照恢复：数据层写回 StationData；metric_rewrite 写回指标。"""
    path = _snapshot_path(slot)
    snap = load_json_safe(path, default=None)
    if not isinstance(snap, dict) or not snap.get("active"):
        raise ValueError("没有可恢复的劣化注入快照")

    mode = str(snap.get("mode") or "metric_rewrite")
    wf_id = str(snap["workflow_id"])
    v_tag = str(snap["version_tag"])
    closed_alert_ids: List[str] = []

    if mode == "metric_rewrite":
        before = snap.get("metrics_before") or {}
        if not isinstance(before, dict) or not before:
            raise ValueError("快照缺少 metrics_before，无法恢复")
        restore_patch = {k: v for k, v in before.items()}
        restore_patch["experiment_injected"] = False
        restore_patch["last_evaluated_at"] = now_iso()
        tracker.update_metrics(slot, wf_id, restore_patch, version_tag=v_tag)
        metrics_restored = restore_patch
        data_restored = None
    else:
        data_restored = _restore_station_data(snap.get("data_corruption") or {})
        station_id = (snap.get("data_corruption") or {}).get("station_id") or DEFAULT_STATION_ID
        feature_name = (snap.get("data_corruption") or {}).get("feature_name") or DEFAULT_FEATURE_NAME
        pipeline_result: Optional[Dict[str, Any]] = None
        if rerun_pipeline and slot_store is not None:
            pipeline_result = _run_load_forecast_pipeline_after_data_change(
                slot=slot,
                station_id=str(station_id),
                feature_name=str(feature_name),
                slot_store=slot_store,
            )
            data_restored["pipeline"] = pipeline_result
            metrics_restored = _metrics_as_dict(tracker.get_rolling_metrics(slot, wf_id, v_tag))
            tracker.update_metrics(
                slot, wf_id, {"experiment_injected": False}, version_tag=v_tag
            )
        else:
            rebind = _rebind_prediction_actuals_and_metrics(
                slot=slot,
                tracker=tracker,
                slot_store=slot_store,
                station_id=str(station_id),
                feature_name=str(feature_name),
                window_days=14,
            )
            before = snap.get("metrics_before")
            if isinstance(before, dict) and before:
                restore_patch = {k: v for k, v in before.items()}
                restore_patch["experiment_injected"] = False
                restore_patch["last_evaluated_at"] = now_iso()
                tracker.update_metrics(slot, wf_id, restore_patch, version_tag=v_tag)
                metrics_restored = restore_patch
            else:
                metrics_restored = _metrics_as_dict(tracker.get_rolling_metrics(slot, wf_id, v_tag))
            data_restored["rebind"] = rebind

    if close_open_alerts and store is not None:
        model_form = str(snap.get("model_form") or "production")
        try:
            for alert in store.list_alerts(slot, status="open") or []:
                if (
                    getattr(alert, "workflow_id", None) == wf_id
                    and getattr(alert, "version_tag", None) == v_tag
                ):
                    # @AI_GENERATED: 实验 restore 直接 force_close，不走 transition 状态机
                    # 正常运营告警需要走完整状态机路径
                    evidence = {
                        "type": "experiment_restore",
                        "ref": snap.get("injected_at"),
                        "at": now_iso(),
                        "model_form": model_form,
                    }
                    if hasattr(store, "force_close_alert"):
                        store.force_close_alert(slot, alert.alert_id, recovery_evidence=evidence)
                    else:
                        # 降级：直接修改 alert 状态
                        alert.status = "closed"   # type: ignore[assignment]
                        store.save_alert(slot, alert)
                    closed_alert_ids.append(alert.alert_id)
                    # @AI_GENERATED: end
        except Exception as exc:
            logger.warning("restore_degradation: 关闭告警失败 slot=%s: %s", slot, exc)

    snap["active"] = False
    snap["restored_at"] = now_iso()
    snap["closed_alert_ids"] = closed_alert_ids
    _atomic_write_json(path, snap)

    return {
        "slot": slot,
        "restored": True,
        "mode": mode,
        "workflow_id": wf_id,
        "version_tag": v_tag,
        "closed_alert_ids": closed_alert_ids,
        "metrics_restored": metrics_restored,
        "data_restored": data_restored,
    }


def _restore_station_data(data_corruption: Dict[str, Any]) -> Dict[str, Any]:
    # @AI_GENERATED: 分批 commit（每 200 行一次），避免快照行数多时长事务阻塞
    from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled
    from services.db.models.load_forecast import StationData

    if not _is_db_enabled():
        raise ValueError("数据库未启用，无法恢复 StationData")
    repo = _get_lf_repo()
    if repo is None:
        raise ValueError("LoadForecastRepository 不可用")

    rows_before = data_corruption.get("station_rows_before") or []
    BATCH_SIZE = 200  # 每批最多 200 行，避免单事务过长阻塞
    restored = 0
    reinserted = 0
    batch_count = 0

    for batch_start in range(0, max(len(rows_before), 1), BATCH_SIZE):
        batch = rows_before[batch_start : batch_start + BATCH_SIZE]
        if not batch:
            break
        with repo._adapter.get_sync_session() as session:
            for item in batch:
                if not isinstance(item, dict):
                    continue
                row_id = item.get("id")
                value = item.get("value")
                if row_id is not None:
                    row = session.get(StationData, int(row_id))
                    if row is not None:
                        row.value = float(value)
                        restored += 1
                        continue
                # missing 删除后：按原字段重插
                ts_raw = item.get("timestamp_utc")
                if not ts_raw:
                    continue
                try:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    if getattr(ts, "tzinfo", None) is not None:
                        ts = ts.replace(tzinfo=None)
                except Exception:
                    continue
                session.add(
                    StationData(
                        station_id=str(item.get("station_id") or DEFAULT_STATION_ID),
                        timestamp_utc=ts,
                        feature_name=str(item.get("feature_name") or DEFAULT_FEATURE_NAME),
                        value=float(value),
                        slot=str(item.get("slot") or ""),
                        ingested_at=datetime.utcnow(),
                    )
                )
                reinserted += 1
            session.commit()
        batch_count += 1

    return {"values_restored": restored, "rows_reinserted": reinserted, "batches": batch_count}
    # @AI_GENERATED: end


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
    }
# @AI_GENERATED: end
