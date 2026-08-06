# @AI_GENERATED
"""实验劣化注入场景的本地 RCA：不依赖 operation_skill，直接读 StationData 劣化快照。"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from services.accuracy_operations.degradation_experiment import _snapshot_path
from services.accuracy_operations.models import (
    AccuracyAlert,
    ActionableInsight,
    DataQualityDiagnosis,
    InsightPriority,
    InsightType,
    RCAReport,
    RCAStatus,
)
from services.precision_ops.utils import load_json_safe

logger = logging.getLogger(__name__)

_MODE_LABELS = {
    "noise": "噪声污染",
    "missing": "真值缺失",
    "zero_spike": "置零尖峰",
    "metric_rewrite": "指标改写（演示）",
}


def _alert_matches_snapshot(alert: AccuracyAlert, snap: Dict[str, Any]) -> bool:
    if str(snap.get("workflow_id") or "") != alert.workflow_id:
        return False
    if str(snap.get("version_tag") or "") != alert.version_tag:
        return False
    return True


def try_build_experiment_inject_rca(
    slot: str,
    alert: AccuracyAlert,
    rca_report_id: str,
    trigger_type: str,
) -> Optional[RCAReport]:
    """若告警来自数据层劣化实验，返回带 data_quality_diagnosis 的 RCAReport。"""
    evidence = alert.recovery_evidence if isinstance(alert.recovery_evidence, dict) else {}
    snap = load_json_safe(_snapshot_path(slot), default=None)
    from_experiment = isinstance(evidence, dict) and evidence.get("type") == "experiment_inject"
    snap_active = isinstance(snap, dict) and bool(snap.get("active"))

    if not from_experiment and not (snap_active and _alert_matches_snapshot(alert, snap)):
        return None

    if not isinstance(snap, dict):
        snap = {}

    mode = str(snap.get("mode") or evidence.get("mode") or "unknown")
    mode_label = _MODE_LABELS.get(mode, mode)
    corruption = snap.get("data_corruption") if isinstance(snap.get("data_corruption"), dict) else {}
    rows_touched = int(corruption.get("rows_touched") or 0)
    rows_deleted = int(corruption.get("rows_deleted") or 0)
    rows_updated = int(corruption.get("rows_updated") or 0)
    window_start = corruption.get("window_start")
    window_end = corruption.get("window_end")
    station_id = corruption.get("station_id")
    feature_name = corruption.get("feature_name")

    baseline_online = float(
        alert.baseline_metric
        or evidence.get("baseline_online_mape")
        or snap.get("rolling_mape_before")
        or 0
    )
    current_mape = float(
        alert.current_metric
        or evidence.get("current_mape")
        or snap.get("post_train_rolling_mape")
        or alert.current_rolling_mape
        or 0
    )
    degradation_pct = float(alert.degradation_pct or snap.get("experiment_alert_degradation_pct") or 0)

    total_in_window = max(rows_touched, rows_deleted + rows_updated, 1)
    missing_rate = round(rows_deleted / total_in_window, 4) if rows_deleted else 0.0
    outlier_rate = round(rows_updated / total_in_window, 4) if mode in {"noise", "zero_spike"} else 0.0
    if mode == "missing" and rows_touched:
        missing_rate = round(min(1.0, rows_deleted / total_in_window if rows_deleted else rows_touched / (rows_touched + 96)), 4)

    supporting = [
        f"精度运营实验注入 mode={mode}（{mode_label}）",
        f"StationData 站点={station_id} 特征={feature_name}",
        f"劣化窗口 {window_start} ~ {window_end}",
        f"触达行数 rows_touched={rows_touched}（更新={rows_updated} 删除={rows_deleted}）",
        f"注入前线上 MAPE={baseline_online:.4f}% → 注入后={current_mape:.4f}%（+{degradation_pct:.2f}%）",
    ]
    if snap.get("daily_rolling_cycle_id"):
        supporting.append(f"注入后日滚 cycle={snap.get('daily_rolling_cycle_id')}")
    elif (snap.get("pipeline") or {}).get("daily_rolling_skip_reason"):
        supporting.append(f"日滚说明：{(snap.get('pipeline') or {}).get('daily_rolling_skip_reason')}")

    reasoning = (
        f"告警来自数据层劣化实验（{mode_label}）。系统在业务水位内改写了 platform StationData，"
        f"随后执行 gap-1 日滚与精度回填。线上 MAPE 相对注入前上升 {degradation_pct:.2f}%，"
        f"根因应优先排查实测真值质量（缺失/噪声/尖峰），而非模型结构或超参。"
    )

    insights = [
        ActionableInsight(
            insight_type=InsightType.data_sourcing,
            priority=InsightPriority.high,
            description=(
                f"检查 {station_id}/{feature_name} 在 {window_start}~{window_end} 的 StationData："
                f"当前注入为「{mode_label}」，请核对采集链路、补数任务与 mock 喂数是否异常。"
            ),
            supporting_evidence=supporting[:3],
        ),
        ActionableInsight(
            insight_type=InsightType.observation,
            priority=InsightPriority.medium,
            description="实验结束后在精度运营面板点击「恢复」，还原 StationData 并重新日滚，避免劣化真值污染后续评估。",
            supporting_evidence=[f"快照 injected_at={snap.get('injected_at')}"],
        ),
    ]
    if degradation_pct >= 30:
        insights.append(
            ActionableInsight(
                insight_type=InsightType.model_retraining_signal,
                priority=InsightPriority.medium,
                description="劣化幅度较大，建议在真值恢复并确认数据质量后再评估是否需要重训或回滚模型版本。",
                supporting_evidence=[f"相对注入前 MAPE +{degradation_pct:.2f}%"],
            )
        )

    report = RCAReport(
        rca_report_id=rca_report_id,
        alert_id=alert.alert_id,
        trigger_type=trigger_type,  # type: ignore[arg-type]
        root_cause="数据层真值劣化（StationData 异常）",
        confidence=0.93 if rows_touched > 0 else 0.75,
        reasoning=reasoning,
        supporting_evidence=supporting,
        undetermined=False,
        error_profile=None,
        data_quality_diagnosis=DataQualityDiagnosis(
            missing_rate=missing_rate,
            outlier_rate=outlier_rate,
            feature_drift_detected=mode in {"noise", "zero_spike"},
            feature_drift_details=[
                {
                    "feature_name": str(feature_name or "load"),
                    "drift_magnitude": round(degradation_pct / 100.0, 4),
                    "drift_direction": mode_label,
                }
            ]
            if mode in {"noise", "zero_spike", "missing"}
            else [],
            data_freshness_lag_hours=0.0,
        ),
        actionable_insights=insights,
        candidate_strategies=[],
        recommended_strategy_id=None,
        artifacts_dir="",
        status=RCAStatus.succeeded,
    )
    logger.info(
        "experiment_rca: 本地 RCA 完成 alert=%s mode=%s missing_rate=%.2f%% outlier_rate=%.2f%%",
        alert.alert_id,
        mode,
        missing_rate * 100,
        outlier_rate * 100,
    )
    return report

# @AI_GENERATED: end
