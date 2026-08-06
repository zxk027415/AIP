# @AI_GENERATED
"""日 MAPE 与滚动 MAPE（7 日 daily median）计算工具。"""
from __future__ import annotations

import statistics
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence


def _as_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def compute_point_mape(predicted: float, actual: float) -> Optional[float]:
    if actual == 0:
        return None
    return abs(float(predicted) - float(actual)) / abs(float(actual)) * 100.0


def compute_daily_metrics_for_rows(rows: Sequence[Any]) -> Optional[Dict[str, Any]]:
    """对单个 prediction_cycle 的 PredictionResult 行计算日 MAPE/WMAPE。"""
    evaluated = [r for r in rows if getattr(r, "actual_value", None) is not None]
    if not evaluated:
        return None

    mapes: List[float] = []
    abs_err = 0.0
    abs_actual = 0.0
    dates: List[date] = []
    cycle_id = None

    for row in evaluated:
        pred = getattr(row, "predicted_value", None)
        actual = getattr(row, "actual_value", None)
        if pred is None or actual is None:
            continue
        pred_f = float(pred)
        actual_f = float(actual)
        mape = compute_point_mape(pred_f, actual_f)
        if mape is not None:
            mapes.append(mape)
        abs_err += abs(pred_f - actual_f)
        abs_actual += abs(actual_f)
        ts = getattr(row, "forecast_timestamp", None)
        d = _as_date(ts)
        if d is not None:
            dates.append(d)
        if cycle_id is None:
            cycle_id = getattr(row, "prediction_cycle_id", None)

    if not mapes:
        return None

    business_day = min(dates).isoformat() if dates else None
    return {
        "prediction_cycle_id": str(cycle_id) if cycle_id else None,
        "business_day": business_day,
        "daily_mape": round(statistics.mean(mapes), 6),
        "daily_wmape": round(abs_err / abs_actual * 100.0, 6) if abs_actual else None,
        "point_count": len(mapes),
        "evaluated_point_count": len(evaluated),
    }


def build_daily_series_from_predictions(rows: Sequence[Any]) -> List[Dict[str, Any]]:
    """按 prediction_cycle_id 分组，返回多条日指标（按 business_day 升序）。"""
    by_cycle: Dict[str, List[Any]] = {}
    for row in rows:
        cid = str(getattr(row, "prediction_cycle_id", "") or "")
        if not cid:
            continue
        by_cycle.setdefault(cid, []).append(row)

    series: List[Dict[str, Any]] = []
    for _cid, cycle_rows in by_cycle.items():
        item = compute_daily_metrics_for_rows(cycle_rows)
        if item is not None:
            series.append(item)
    series.sort(key=lambda x: (x.get("business_day") or "", x.get("prediction_cycle_id") or ""))
    return series


def merge_daily_series(
    existing: Optional[List[Dict[str, Any]]],
    fresh: List[Dict[str, Any]],
    *,
    keep_days: int = 30,
) -> List[Dict[str, Any]]:
    """按 business_day + cycle_id 合并；保留最近 keep_days 个自然日。"""
    merged: Dict[str, Dict[str, Any]] = {}
    for item in list(existing or []) + list(fresh or []):
        if not isinstance(item, dict):
            continue
        key = f"{item.get('business_day')}|{item.get('prediction_cycle_id')}"
        merged[key] = item
    out = sorted(
        merged.values(),
        key=lambda x: (x.get("business_day") or "", x.get("prediction_cycle_id") or ""),
    )
    if not out:
        return []
    days = sorted({str(x.get("business_day")) for x in out if x.get("business_day")})
    if len(days) > keep_days:
        keep = set(days[-keep_days:])
        out = [x for x in out if str(x.get("business_day")) in keep]
    return out


def rolling_mape_from_daily_series(
    daily_series: Sequence[Dict[str, Any]],
    *,
    window_days: int = 7,
    method: str = "median",
) -> Optional[float]:
    """取最近 window_days 个 business_day 的 daily_mape 聚合（默认 median）。"""
    by_day: Dict[str, float] = {}
    for item in daily_series:
        day = item.get("business_day")
        mape = item.get("daily_mape")
        if day is None or mape is None:
            continue
        # 同一 business_day 若有多条（不应常见），取平均
        by_day[str(day)] = float(mape) if str(day) not in by_day else statistics.mean(
            [by_day[str(day)], float(mape)]
        )
    if not by_day:
        return None
    days_sorted = sorted(by_day.keys())
    window = days_sorted[-window_days:]
    values = [by_day[d] for d in window]
    if not values:
        return None
    m = str(method or "median").strip().lower()
    if m == "mean":
        return round(statistics.mean(values), 6)
    return round(statistics.median(values), 6)


def compute_pooled_mape(rows: Sequence[Any]) -> Optional[float]:
    """7 天窗口内所有点 pooled MAPE（旧口径，保留为参考）。"""
    mapes: List[float] = []
    for row in rows:
        pred = getattr(row, "predicted_value", None)
        actual = getattr(row, "actual_value", None)
        if pred is None or actual is None:
            continue
        mape = compute_point_mape(float(pred), float(actual))
        if mape is not None:
            mapes.append(mape)
    if not mapes:
        return None
    return round(statistics.mean(mapes), 6)


def compute_pooled_wmape(rows: Sequence[Any]) -> Optional[float]:
    evaluated = [r for r in rows if getattr(r, "actual_value", None) is not None]
    if not evaluated:
        return None
    abs_err = sum(
        abs(float(r.predicted_value) - float(r.actual_value))
        for r in evaluated
        if r.predicted_value is not None
    )
    abs_actual = sum(abs(float(r.actual_value)) for r in evaluated)
    if abs_actual == 0:
        return None
    return round(abs_err / abs_actual * 100.0, 6)
# @AI_GENERATED: end
