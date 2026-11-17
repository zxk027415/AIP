import json
import math
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class AutoResearchMemoryStore:
    def __init__(
        self,
        path: str,
        lock: Optional[threading.RLock] = None,
        max_cases: int = 800,
        legacy_path: Optional[str] = None,
    ):
        self.path = path
        self.lock = lock or threading.RLock()
        self.max_cases = max_cases
        self.legacy_path = legacy_path

    def load(self) -> List[Dict[str, Any]]:
        path = self.path
        if not os.path.exists(path) and self.legacy_path and os.path.exists(self.legacy_path):
            path = self.legacy_path
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            rows = data.get("cases") if isinstance(data, dict) else None
            return list(rows) if isinstance(rows, list) else []
        except Exception:
            return []

    def save(self, cases: List[Dict[str, Any]]) -> None:
        with self.lock:
            self._atomic_write_json({"cases": cases[-self.max_cases:]})

    def append(self, case: Dict[str, Any]) -> None:
        with self.lock:
            cases = self.load()
            cases.append(case)
            self._atomic_write_json({"cases": cases[-self.max_cases:]})

    def compute_scenario_fingerprint(
        self,
        state: Dict[str, Any],
        windows: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        evaluation_contract = state.get("evaluation_contract") or {}
        tags = [str(tag).strip().lower() for tag in (state.get("scenario_tags") or []) if str(tag).strip()]

        horizon = evaluation_contract.get("daily_horizon")
        try:
            horizon_value = int(horizon) if horizon is not None else 1
        except (TypeError, ValueError):
            horizon_value = 1
        granularity = "intraday" if horizon_value > 1 else "daily"

        span_days: Optional[int] = None
        if windows:
            span_days = self._span_days_from_windows(windows)

        load_type = next((tag for tag in tags if tag in ("industrial", "commercial", "residential", "mixed")), None)
        seasonality = next((tag for tag in tags if tag in ("summer_peak", "winter_peak", "flat", "seasonal")), None)
        weekend_sensitivity = "high" if any("weekend" in tag for tag in tags) else "normal"

        anomaly_ratio = self._anomaly_ratio_from_iterations(state.get("iterations") or [])

        return {
            "granularity": granularity,
            "span_days": span_days,
            "load_type": load_type,
            "seasonality": seasonality,
            "weekend_sensitivity": weekend_sensitivity,
            "anomaly_ratio": anomaly_ratio,
            "backtest_mode": evaluation_contract.get("backtest_mode"),
            "train_days": evaluation_contract.get("train_days") or evaluation_contract.get("backtest_train_days"),
        }

    def retrieve(
        self,
        baseline_workflow_id: str,
        scenario_tags: List[str],
        *,
        limit: int = 5,
        query_fingerprint: Optional[Dict[str, Any]] = None,
        query_diagnosis: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        tags = set(str(tag).strip() for tag in (scenario_tags or []) if str(tag).strip())
        matched: List[Dict[str, Any]] = []
        for case in self.load():
            if not isinstance(case, dict):
                continue
            if str(case.get("baseline_workflow_id") or "") != str(baseline_workflow_id or ""):
                continue
            case_tags = set(str(tag).strip() for tag in (case.get("scenario_tags") or []) if str(tag).strip())
            if tags and case_tags and len(tags.intersection(case_tags)) == 0:
                continue
            matched.append(case)

        ranked: List[Dict[str, Any]] = []
        for case in matched:
            outcome = case.get("outcome") or {}
            case_tags = set(str(tag).strip() for tag in (case.get("scenario_tags") or []) if str(tag).strip())
            intersection = len(tags.intersection(case_tags)) if tags else 0
            union = len(tags.union(case_tags)) if (tags or case_tags) else 0
            tag_score = (intersection / union) if union > 0 else (0.5 if not tags else 0.0)
            improved_score = 1.0 if bool(outcome.get("improved")) else 0.0
            delta_score = max(0.0, min(1.0, self._safe_float(outcome.get("mape_delta"), 0.0) / 5.0))
            constraints_score = 1.0 if bool(outcome.get("meets_constraints")) else 0.0
            freshness = self._recency_score(case.get("created_at"))
            fingerprint_similarity = self.fingerprint_similarity(query_fingerprint, case.get("fingerprint"))
            diagnosis_score = 0.0
            if query_diagnosis:
                case_diagnosis = str((case.get("outcome") or {}).get("primary_error_source") or "")
                if case_diagnosis and case_diagnosis == query_diagnosis:
                    diagnosis_score = 1.0
            score = (
                0.20 * tag_score
                + 0.15 * fingerprint_similarity
                + 0.15 * diagnosis_score
                + 0.25 * improved_score
                + 0.15 * delta_score
                + 0.05 * constraints_score
                + 0.05 * freshness
            )
            row = dict(case)
            row["retrieval_score"] = round(score, 6)
            row["fingerprint_similarity"] = round(fingerprint_similarity, 4)
            ranked.append(row)

        ranked.sort(
            key=lambda item: (
                -self._safe_float(item.get("retrieval_score"), 0.0),
                -self._safe_float((item.get("outcome") or {}).get("mape_delta"), -1e9),
            )
        )
        return ranked[: max(0, int(limit))]

    def fingerprint_similarity(self, fp_a: Optional[Dict[str, Any]], fp_b: Optional[Dict[str, Any]]) -> float:
        if not fp_a or not fp_b:
            return 0.5
        score = 0.0
        weight_total = 0.0
        for key, weight in [
            ("granularity", 0.2),
            ("load_type", 0.15),
            ("seasonality", 0.1),
            ("weekend_sensitivity", 0.1),
            ("backtest_mode", 0.1),
        ]:
            va, vb = fp_a.get(key), fp_b.get(key)
            weight_total += weight
            if va is None or vb is None:
                score += weight * 0.5
            elif va == vb:
                score += weight
        for key, weight, scale in [
            ("train_days", 0.15, 30.0),
            ("span_days", 0.1, 90.0),
            ("anomaly_ratio", 0.1, 0.3),
        ]:
            va, vb = fp_a.get(key), fp_b.get(key)
            weight_total += weight
            if va is None or vb is None:
                score += weight * 0.5
            else:
                try:
                    diff = abs(float(va) - float(vb)) / max(scale, 1e-6)
                    score += weight * max(0.0, 1.0 - diff)
                except (TypeError, ValueError):
                    score += weight * 0.5
        return score / weight_total if weight_total > 0 else 0.5

    def _span_days_from_windows(self, windows: List[dict]) -> Optional[int]:
        from datetime import date

        values: List[str] = []
        for window in windows:
            if not isinstance(window, dict):
                continue
            for key in ("start_date", "start"):
                value = window.get(key)
                if value:
                    values.append(str(value))
                    break
            for key in ("end_date", "end"):
                value = window.get(key)
                if value:
                    values.append(str(value))
                    break
        parsed = []
        for value in values:
            try:
                parsed.append(date.fromisoformat(value[:10]))
            except Exception:
                pass
        if not parsed:
            return None
        return (max(parsed) - min(parsed)).days + 1

    def _anomaly_ratio_from_iterations(self, iterations: List[Dict[str, Any]]) -> Optional[float]:
        high_error_counts: List[int] = []
        total_day_counts: List[int] = []
        for item in iterations[-5:]:
            if not isinstance(item, dict):
                continue
            error_profile = item.get("error_profile") or {}
            data_coverage = item.get("data_coverage") or {}
            high_error = error_profile.get("high_error_days_count")
            total_days = data_coverage.get("total_days")
            if high_error is not None and total_days:
                try:
                    high_error_counts.append(int(high_error))
                    total_day_counts.append(int(total_days))
                except (TypeError, ValueError):
                    pass
        if not high_error_counts or not total_day_counts:
            return None
        total_high_error = sum(high_error_counts)
        total_days = sum(total_day_counts)
        return round(total_high_error / total_days, 4) if total_days > 0 else None

    def _recency_score(self, created_at: Any) -> float:
        if not created_at:
            return 0.0
        try:
            dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            days = max(0.0, (now - dt).total_seconds() / 86400.0)
            return float(math.exp(-days / 45.0))
        except Exception:
            return 0.0

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _atomic_write_json(self, payload: Any) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp_path = f"{self.path}.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
