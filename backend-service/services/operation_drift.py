# -*- coding: utf-8 -*-
"""
漂移与概念漂移分析：基于回测 y_true/y_pred 及可选历史负荷序列，不依赖外部服务。
- 残差分布漂移（后半程 vs 前半程）
- 预测偏差随时间趋势
- 可选：输入侧负荷分布 PSI（需提供两组值）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


def _psi(expected: np.ndarray, actual: np.ndarray, n_bins: int = 10) -> float:
    """Population Stability Index."""
    e = np.asarray(expected, dtype=float)
    a = np.asarray(actual, dtype=float)
    e = e[np.isfinite(e)]
    a = a[np.isfinite(a)]
    if len(e) < 5 or len(a) < 5:
        return 0.0
    bins = np.percentile(e, np.linspace(0, 100, n_bins + 1))
    bins[0] = -np.inf
    bins[-1] = np.inf
    e_counts, _ = np.histogram(e, bins=bins)
    a_counts, _ = np.histogram(a, bins=bins)
    e_pct = e_counts / max(e_counts.sum(), 1e-9)
    a_pct = a_counts / max(a_counts.sum(), 1e-9)
    psi = 0.0
    for i in range(len(e_pct)):
        ae, aa = max(e_pct[i], 1e-6), max(a_pct[i], 1e-6)
        psi += (aa - ae) * np.log(aa / ae)
    return float(np.round(psi, 4))


def drift_report_from_daily_results(
    daily_results: Sequence[Dict[str, Any]],
    metric_key: str = "smape",
) -> Dict[str, Any]:
    """
    使用逐日指标与逐日残差统计检测「概念漂移」迹象（精度下行、残差分布变化）。
    """
    days = [d for d in daily_results if d.get("status") == "success" and d.get("metrics")]
    if len(days) < 4:
        return {
            "summary": "有效回测日不足，无法可靠检测漂移（建议至少 4 个成功日）。",
            "concept_drift": {"level": "unknown", "detail": "样本不足"},
            "residual_drift": {},
            "metric_trend": {},
        }
    metrics = [float(d["metrics"].get(metric_key) or 0) for d in days]
    n = len(metrics)
    half = n // 2
    first, second = metrics[:half], metrics[half:]
    m1, m2 = float(np.mean(first)), float(np.mean(second))
    trend = (m2 - m1) / max(m1, 1e-6) * 100.0

    residuals_early: List[float] = []
    residuals_late: List[float] = []
    for i, d in enumerate(days):
        yt = d.get("y_true") or []
        yp = d.get("y_pred") or []
        if not yt or not yp:
            continue
        yta = np.asarray(yt, dtype=float)
        ypa = np.asarray(yp, dtype=float)
        m = min(len(yta), len(ypa))
        r = np.abs(ypa[:m] - yta[:m])
        bucket = residuals_early if i < half else residuals_late
        bucket.extend(r.tolist())
    psi_r = 0.0
    if len(residuals_early) > 20 and len(residuals_late) > 20:
        psi_r = _psi(np.array(residuals_early), np.array(residuals_late))

    level = "none"
    detail_parts = []
    if trend > 5:
        level = "moderate"
        detail_parts.append(f"后半程 {metric_key.upper()} 较前半程上升约 {trend:.1f}%")
    elif trend > 2:
        level = "mild"
        detail_parts.append(f"后半程指标较前升约 {trend:.1f}%")
    if psi_r > 0.2:
        level = "moderate" if level == "none" else level
        detail_parts.append(f"残差分布 PSI={psi_r:.3f}（>0.2 提示分布偏移）")
    elif psi_r > 0.1:
        detail_parts.append(f"残差 PSI={psi_r:.3f}（轻度）")
    if not detail_parts:
        detail_parts.append("未观察到显著指标或残差漂移")

    return {
        "summary": "；".join(detail_parts),
        "concept_drift": {
            "level": level,
            "metric": metric_key,
            "first_half_mean": round(m1, 4),
            "second_half_mean": round(m2, 4),
            "relative_change_pct": round(trend, 2),
            "detail": detail_parts[0] if detail_parts else "",
        },
        "residual_drift": {
            "psi": psi_r,
            "interpretation": "显著" if psi_r > 0.2 else ("轻度" if psi_r > 0.1 else "可忽略"),
        },
        "metric_trend": {"per_day": [round(x, 4) for x in metrics]},
    }


def drift_report_from_load_series(
    reference_values: Sequence[float],
    current_values: Sequence[float],
    n_bins: int = 10,
) -> Dict[str, Any]:
    """输入侧负荷分布漂移（PSI）。"""
    ref = np.asarray(reference_values, dtype=float)
    cur = np.asarray(current_values, dtype=float)
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    psi = _psi(ref, cur, n_bins=n_bins)
    level = "severe" if psi > 0.25 else ("moderate" if psi > 0.2 else ("mild" if psi > 0.1 else "none"))
    return {
        "data_drift": {
            "psi": psi,
            "level": level,
            "reference_n": len(ref),
            "current_n": len(cur),
        },
        "summary": f"负荷分布 PSI={psi}，等级: {level}",
    }
