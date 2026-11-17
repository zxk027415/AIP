from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .dataset_profiler_models import (
    CrossWindowPattern,
    CVFoldMetric,
    TestProfile,
    TrainProfile,
    TriDatasetDiagnosis,
    ValidationProfile,
)


PERIODS = {
    "morning_peak": (7, 11),
    "midday": (11, 14),
    "evening_peak": (17, 21),
    "night": None,
}


def _finite_float(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except Exception:
        return None
    return v if np.isfinite(v) else None


def _mape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    mask = np.abs(a) > 1e-8
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((a[mask] - p[mask]) / a[mask])) * 100.0)


def _rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(a - p))))


def _period_name(ts: pd.Timestamp) -> str:
    hour = int(ts.hour)
    if 7 <= hour < 11:
        return "morning_peak"
    if 11 <= hour < 14:
        return "midday"
    if 17 <= hour < 21:
        return "evening_peak"
    return "night"


def _coerce_time_load(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame({"timestamp": [], "load": []})
    cols = {str(c).lower(): c for c in df.columns}
    time_col = cols.get("timestamp") or cols.get("record_time") or cols.get("time")
    load_col = cols.get("load") or cols.get("true") or cols.get("value")
    if time_col is None or load_col is None:
        raise ValueError("train_data must contain timestamp/record_time and load columns")
    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df[time_col], errors="coerce"),
            "load": pd.to_numeric(df[load_col], errors="coerce"),
        }
    )
    return out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


class DatasetProfiler:
    def compute_train_profile(
        self,
        train_data: pd.DataFrame,
        train_fit_mape: Optional[float] = None,
    ) -> TrainProfile:
        df = _coerce_time_load(train_data)
        load = df["load"].to_numpy(dtype=float) if not df.empty else np.asarray([], dtype=float)
        finite = load[np.isfinite(load)]

        stats = {
            "mean": _finite_float(np.mean(finite)) if finite.size else None,
            "std": _finite_float(np.std(finite)) if finite.size else None,
            "skew": _finite_float(pd.Series(finite).skew()) if finite.size > 2 else 0.0,
            "kurtosis": _finite_float(pd.Series(finite).kurt()) if finite.size > 3 else 0.0,
        }

        missing_rate = float(np.mean(~np.isfinite(load))) if load.size else 0.0
        z = np.abs((finite - np.mean(finite)) / (np.std(finite) + 1e-8)) if finite.size else []
        data_quality = {
            "missing_rate": round(missing_rate, 6),
            "outlier_ratio": round(float(np.mean(np.asarray(z) > 3.0)) if finite.size else 0.0, 6),
            "max_consecutive_missing": float(self._max_consecutive_missing(load)),
        }

        daily = df.set_index("timestamp")["load"].resample("D")
        peak_counts = []
        valley_counts = []
        amplitudes = []
        for _, series in daily:
            arr = series.dropna().to_numpy(dtype=float)
            if arr.size < 3:
                continue
            prominence = max(float(np.std(arr)) * 0.5, 1e-8)
            peaks, _ = find_peaks(arr, prominence=prominence, distance=4)
            valleys, _ = find_peaks(-arr, prominence=prominence, distance=4)
            peak_counts.append(len(peaks))
            valley_counts.append(len(valleys))
            amplitudes.append(float(np.max(arr) - np.min(arr)))
        peak_valley_distribution = {
            "avg_daily_peak_count": round(float(np.mean(peak_counts)) if peak_counts else 0.0, 6),
            "avg_daily_valley_count": round(float(np.mean(valley_counts)) if valley_counts else 0.0, 6),
            "avg_peak_valley_amplitude": round(float(np.mean(amplitudes)) if amplitudes else 0.0, 6),
        }

        series = pd.Series(load).dropna().reset_index(drop=True)
        periodicity_strength = {
            "daily_autocorr": self._autocorr(series, 96),
            "weekly_autocorr": self._autocorr(series, 96 * 7),
        }

        period_distribution = self._period_distribution(df)
        weekday_weekend_gap = self._weekday_weekend_gap(df)
        dominant_pattern = self._dominant_pattern(weekday_weekend_gap)
        source_days = 0
        if not df.empty:
            source_days = int(df["timestamp"].dt.date.nunique())
        profile_quality = {
            "source": "time_load_dataframe",
            "point_count": int(load.size),
            "valid_point_count": int(finite.size),
            "source_days": source_days,
            "is_empty": bool(load.size == 0),
            "has_real_load_curve": bool(finite.size >= 96),
            "has_periodicity_signal": bool(periodicity_strength.get("daily_autocorr") is not None),
            "has_weekday_weekend_signal": bool(weekday_weekend_gap is not None),
        }

        return TrainProfile(
            load_curve_stats=stats,
            peak_valley_distribution=peak_valley_distribution,
            data_quality=data_quality,
            periodicity_strength=periodicity_strength,
            period_distribution=period_distribution,
            dominant_pattern=dominant_pattern,
            weekday_weekend_gap=weekday_weekend_gap,
            train_fit_mape=_finite_float(train_fit_mape),
            profile_quality=profile_quality,
        )

    def compute_validation_profile(
        self,
        cv_fold_metrics: List[CVFoldMetric],
    ) -> ValidationProfile:
        folds = [m.to_dict() if hasattr(m, "to_dict") else dict(m) for m in (cv_fold_metrics or [])]
        losses = []
        val_mapes = []
        gaps = []
        for item in folds:
            train_loss = float(item.get("train_loss", 0.0))
            val_loss = float(item.get("val_loss", 0.0))
            gap = val_loss - train_loss
            losses.append(
                {
                    "fold_id": int(item.get("fold_id", len(losses) + 1)),
                    "train_loss": train_loss,
                    "val_loss": val_loss,
                    "gap": gap,
                }
            )
            val_mapes.append(float(item.get("val_mape", 0.0)))
            gaps.append(gap)

        avg_train = float(np.mean([x["train_loss"] for x in losses])) if losses else 0.0
        avg_gap = float(np.mean(gaps)) if gaps else 0.0
        ratio = avg_gap / max(avg_train, 1e-8)
        eps = 1e-9
        if ratio > 0.5 + eps:
            overfit = "high"
        elif ratio >= 0.2 - eps:
            overfit = "moderate"
        else:
            overfit = "low"

        val_losses = [x["val_loss"] for x in losses]
        trend = self._trend(val_losses)
        return ValidationProfile(
            cv_fold_losses=losses,
            cv_val_mape=round(float(np.mean(val_mapes)), 6) if val_mapes else None,
            overfit_indicator=overfit,
            cv_loss_trend=trend,
        )

    def compute_test_profile(
        self,
        actual: np.ndarray,
        predicted: np.ndarray,
        timestamps: List[str],
    ) -> TestProfile:
        actual_arr = np.asarray(actual, dtype=float).reshape(-1)
        pred_arr = np.asarray(predicted, dtype=float).reshape(-1)
        n = min(actual_arr.size, pred_arr.size, len(timestamps))
        actual_arr = actual_arr[:n]
        pred_arr = pred_arr[:n]
        ts = pd.to_datetime(timestamps[:n], errors="coerce")
        ape = np.zeros(n, dtype=float)
        mask = np.abs(actual_arr) > 1e-8
        ape[mask] = np.abs((actual_arr[mask] - pred_arr[mask]) / actual_arr[mask]) * 100.0

        rows = [
            {
                "timestamp": str(timestamps[i]),
                "actual": float(actual_arr[i]),
                "predicted": float(pred_arr[i]),
                "abs_pct_error": float(ape[i]),
            }
            for i in range(n)
        ]
        max_idx = int(np.argmax(ape)) if n else 0
        period_error_breakdown = self._period_error_breakdown(actual_arr, pred_arr, ts)
        peak_error_ratio, valley_error_ratio, high_at_extremes = self._extreme_error_ratios(actual_arr, ape)

        day_type = "unknown"
        valid_ts = [x for x in ts if not pd.isna(x)]
        if valid_ts:
            day_type = "weekend" if valid_ts[0].weekday() >= 5 else "weekday"

        return TestProfile(
            actual_vs_predicted=rows,
            overall_mape=round(_mape(actual_arr, pred_arr), 6),
            overall_rmse=round(_rmse(actual_arr, pred_arr), 6),
            max_single_point_error={
                "timestamp": str(timestamps[max_idx]) if n else None,
                "error_pct": round(float(ape[max_idx]), 6) if n else 0.0,
            },
            period_error_breakdown=period_error_breakdown,
            peak_error_ratio=round(peak_error_ratio, 6),
            valley_error_ratio=round(valley_error_ratio, 6),
            high_error_at_extremes=bool(high_at_extremes),
            day_type=day_type,
        )

    def compute_tri_dataset_diagnosis(
        self,
        train_profile: TrainProfile,
        validation_profile: Optional[ValidationProfile],
        test_profile: TestProfile,
    ) -> TriDatasetDiagnosis:
        day_type = getattr(test_profile, "day_type", "unknown")
        expected = "weekend_dominant" if day_type == "weekend" else "weekday_dominant"
        pattern_status = "consistent"
        if day_type in ("weekday", "weekend") and train_profile.dominant_pattern not in (expected, "mixed"):
            pattern_status = "pattern_mismatch"
        pattern_consistency = {
            "status": pattern_status,
            "train_pattern": train_profile.dominant_pattern,
            "test_day_type": day_type,
        }

        test_mape = float(test_profile.overall_mape)
        overfit_detection = "overfit_unknown"
        cv_val = validation_profile.cv_val_mape if validation_profile else None
        if cv_val is not None:
            overfit_detection = "confirmed_overfit" if test_mape > float(cv_val) * 1.5 else "not_confirmed"
        elif train_profile.train_fit_mape is not None:
            overfit_detection = (
                "confirmed_overfit"
                if test_mape > float(train_profile.train_fit_mape) * 1.5
                else "not_confirmed"
            )

        chain = [train_profile.train_fit_mape]
        if cv_val is not None:
            chain.append(cv_val)
        chain.append(test_mape)
        diffs = self._relative_adjacent_diffs([x for x in chain if x is not None])
        max_diff = max(diffs) if diffs else 0.0
        if max_diff > 0.5:
            generalization = "poor"
        elif max_diff >= 0.2:
            generalization = "moderate"
        else:
            generalization = "good"

        parts = []
        if pattern_status == "pattern_mismatch":
            parts.append("训练/测试模式不一致，建议调整训练窗口选择策略")
        if overfit_detection == "confirmed_overfit":
            parts.append("测试误差显著高于拟合或验证误差，建议降低模型复杂度或增加正则化")
        parts.append(f"泛化能力评估为{generalization}")
        conclusion = "；".join(parts)[:200]

        return TriDatasetDiagnosis(
            pattern_consistency=pattern_consistency,
            overfit_detection=overfit_detection,
            generalization_assessment=generalization,
            diagnosis_conclusion=conclusion,
        )

    def compute_cross_window_pattern(
        self,
        window_profiles: List[TestProfile],
    ) -> CrossWindowPattern:
        profiles = window_profiles or []
        mapes = [float(p.overall_mape) for p in profiles]
        period_counts: Dict[str, int] = {}
        periodic: Dict[str, Any] = {"worst_periods": []}
        for profile in profiles:
            worst = profile.period_error_breakdown.get("worst_period")
            if worst:
                periodic["worst_periods"].append(worst)
                period_counts[worst] = period_counts.get(worst, 0) + 1
        if period_counts:
            periodic["dominant_worst_period"] = max(period_counts, key=period_counts.get)
        else:
            periodic["dominant_worst_period"] = None

        consistently_bad = []
        for period in PERIODS:
            hits = 0
            for profile in profiles:
                avg = float(profile.overall_mape)
                value = profile.period_error_breakdown.get(period)
                if value is not None and float(value) > avg * 1.5:
                    hits += 1
            if profiles and hits / len(profiles) > 0.6:
                consistently_bad.append(period)

        return CrossWindowPattern(
            error_trend=self._trend(mapes),
            periodic_error_pattern=periodic,
            drift_signal=round(max(0.0, mapes[-1] - mapes[0]), 6) if len(mapes) >= 2 else 0.0,
            consistently_bad_periods=consistently_bad,
        )

    def _period_distribution(self, df: pd.DataFrame) -> Dict[str, Dict[str, Optional[float]]]:
        if df.empty:
            return {p: {"mean": None, "std": None, "ratio": 0.25} for p in PERIODS}
        total = float(df["load"].sum())
        out: Dict[str, Dict[str, Optional[float]]] = {}
        ratios = []
        for period in PERIODS:
            sub = df[df["timestamp"].map(_period_name) == period]["load"].dropna()
            ratio = float(sub.sum() / total) if abs(total) > 1e-8 else 0.0
            ratios.append(ratio)
            out[period] = {
                "mean": _finite_float(sub.mean()) if len(sub) else None,
                "std": _finite_float(sub.std(ddof=0)) if len(sub) else None,
                "ratio": ratio,
            }
        ratio_sum = sum(ratios)
        if ratio_sum > 1e-8:
            for period in PERIODS:
                out[period]["ratio"] = round(float(out[period]["ratio"]) / ratio_sum, 6)
        else:
            for period in PERIODS:
                out[period]["ratio"] = 0.25
        return out

    def _weekday_weekend_gap(self, df: pd.DataFrame) -> Optional[float]:
        if df.empty:
            return None
        weekday = df[df["timestamp"].dt.weekday < 5]["load"].dropna()
        weekend = df[df["timestamp"].dt.weekday >= 5]["load"].dropna()
        if weekday.empty or weekend.empty:
            return None
        denom = max(abs(float(weekday.mean())), abs(float(weekend.mean())), 1e-8)
        return round(float((weekday.mean() - weekend.mean()) / denom), 6)

    def _dominant_pattern(self, gap: Optional[float]) -> str:
        if gap is None:
            return "mixed"
        if gap > 0.1:
            return "weekday_dominant"
        if gap < -0.1:
            return "weekend_dominant"
        return "mixed"

    def _autocorr(self, series: pd.Series, lag: int) -> Optional[float]:
        if len(series) <= lag:
            return None
        return _finite_float(series.autocorr(lag=lag))

    def _max_consecutive_missing(self, values: Iterable[float]) -> int:
        longest = 0
        current = 0
        for value in values:
            if not np.isfinite(value):
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        return longest

    def _trend(self, values: List[float]) -> str:
        if len(values) < 2:
            return "stable"
        x = np.arange(len(values), dtype=float)
        slope = float(np.polyfit(x, np.asarray(values, dtype=float), 1)[0])
        threshold = max(float(np.mean(np.abs(values))) * 0.05, 1e-8)
        if slope > threshold:
            return "increasing"
        if slope < -threshold:
            return "decreasing"
        return "stable"

    def _period_error_breakdown(
        self,
        actual: np.ndarray,
        predicted: np.ndarray,
        timestamps: Sequence[pd.Timestamp],
    ) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for period in PERIODS:
            idx = [i for i, ts in enumerate(timestamps) if not pd.isna(ts) and _period_name(ts) == period]
            values[period] = round(_mape(actual[idx], predicted[idx]), 6) if idx else 0.0
        values["worst_period"] = max(PERIODS.keys(), key=lambda p: values[p])
        return values

    def _extreme_error_ratios(self, actual: np.ndarray, ape: np.ndarray):
        if actual.size < 3:
            return 0.0, 0.0, False
        prominence = max(float(np.std(actual)) * 0.5, 1e-8)
        peaks, _ = find_peaks(actual, prominence=prominence, distance=4)
        valleys, _ = find_peaks(-actual, prominence=prominence, distance=4)
        avg_error = max(float(np.mean(ape)), 1e-8)
        peak_ratio = float(np.mean(ape[peaks]) / avg_error) if len(peaks) else 0.0
        valley_ratio = float(np.mean(ape[valleys]) / avg_error) if len(valleys) else 0.0
        return peak_ratio, valley_ratio, bool(max(peak_ratio, valley_ratio) > 1.5)

    def _relative_adjacent_diffs(self, values: List[float]) -> List[float]:
        diffs = []
        for prev, current in zip(values, values[1:]):
            diffs.append(abs(float(current) - float(prev)) / max(abs(float(prev)), 1e-8))
        return diffs
