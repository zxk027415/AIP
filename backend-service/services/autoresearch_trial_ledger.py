import json
import math
import os
import tempfile
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import autoresearch_paths as arp


class AutoResearchTrialLedger:
    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or arp.as_str(arp.runs_dir())
        self.legacy_root_dir = None if root_dir else arp.as_str(arp.legacy_runs_dir())
        self._lock = threading.RLock()
        os.makedirs(self.root_dir, exist_ok=True)

    def append_trial(self, study_id: str, trial: Dict[str, Any]) -> Dict[str, Any]:
        if not study_id:
            raise ValueError("study_id is required")
        row = self._sanitize(dict(trial or {}))
        if not isinstance(row, dict):
            row = {"payload": row}
        row.setdefault("id", self._trial_id(study_id, row))
        row.setdefault("study_id", study_id)
        row.setdefault("created_at", datetime.now().isoformat())
        self._append_jsonl(self._path(study_id, "trials.jsonl"), row)
        return row

    def append_decision(self, study_id: str, decision: Dict[str, Any]) -> Dict[str, Any]:
        if not study_id:
            raise ValueError("study_id is required")
        row = self._sanitize(dict(decision or {}))
        if not isinstance(row, dict):
            row = {"payload": row}
        row.setdefault("id", self._decision_id(study_id, row))
        row.setdefault("study_id", study_id)
        row.setdefault("created_at", datetime.now().isoformat())
        self._append_jsonl(self._path(study_id, "decisions.jsonl"), row)
        return row

    def list_trials(self, study_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self._read_jsonl(self._path(study_id, "trials.jsonl"), limit=limit)
        if rows:
            return rows
        legacy = self._legacy_path(study_id, "trials.jsonl")
        return self._read_jsonl(legacy, limit=limit) if legacy else []

    def list_decisions(self, study_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self._read_jsonl(self._path(study_id, "decisions.jsonl"), limit=limit)
        if rows:
            return rows
        legacy = self._legacy_path(study_id, "decisions.jsonl")
        return self._read_jsonl(legacy, limit=limit) if legacy else []

    def stats(self) -> Dict[str, Any]:
        total_trials = 0
        success_trials = 0
        failed_trials = 0
        pruned_trials = 0
        improvements: List[float] = []
        param_effects: Dict[str, List[float]] = {}
        decision_counts: Dict[str, int] = {}

        for study_id in self._study_ids():
            for trial in self.list_trials(study_id, limit=100000):
                total_trials += 1
                status = str(trial.get("status") or "").lower()
                if status == "success":
                    success_trials += 1
                elif status in ("failed", "error"):
                    failed_trials += 1
                elif status == "pruned":
                    pruned_trials += 1
                improvement = trial.get("mape_improvement")
                try:
                    if improvement is not None:
                        improvements.append(float(improvement))
                except (TypeError, ValueError):
                    pass
                override = trial.get("override") if isinstance(trial.get("override"), dict) else {}
                for key in override.keys():
                    if improvement is None:
                        continue
                    try:
                        param_effects.setdefault(str(key), []).append(float(improvement))
                    except (TypeError, ValueError):
                        continue
            for decision in self.list_decisions(study_id, limit=100000):
                dtype = str(decision.get("decision_type") or "unknown")
                decision_counts[dtype] = decision_counts.get(dtype, 0) + 1

        avg_improvement = sum(improvements) / len(improvements) if improvements else None
        top_params = []
        for key, values in param_effects.items():
            if not values:
                continue
            top_params.append({
                "param_key": key,
                "trial_count": len(values),
                "avg_mape_improvement": round(sum(values) / len(values), 6),
            })
        top_params.sort(key=lambda x: x["avg_mape_improvement"], reverse=True)
        return {
            "total_trials": total_trials,
            "success_trials": success_trials,
            "failed_trials": failed_trials,
            "pruned_trials": pruned_trials,
            "avg_mape_improvement": round(avg_improvement, 6) if avg_improvement is not None else None,
            "decision_counts": decision_counts,
            "top_params": top_params[:20],
        }

    def _path(self, study_id: str, filename: str) -> str:
        safe_id = arp.safe_id(study_id)
        return os.path.join(self.root_dir, safe_id, filename)

    def _legacy_path(self, study_id: str, filename: str) -> Optional[str]:
        if not self.legacy_root_dir:
            return None
        safe_id = arp.safe_id(study_id)
        return os.path.join(self.legacy_root_dir, safe_id, filename)

    def _study_ids(self) -> List[str]:
        out = set()
        for root_dir in [self.root_dir, self.legacy_root_dir]:
            if not root_dir or not os.path.exists(root_dir):
                continue
            for name in os.listdir(root_dir):
                path = os.path.join(root_dir, name)
                if os.path.isdir(path):
                    out.add(name)
        return sorted(out)

    def _append_jsonl(self, path: str, row: Dict[str, Any]) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            existing = ""
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    existing = f.read()
            fd, tmp_path = tempfile.mkstemp(
                prefix=f".{os.path.basename(path)}.",
                suffix=".tmp",
                dir=os.path.dirname(path),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    if existing:
                        f.write(existing)
                        if not existing.endswith("\n"):
                            f.write("\n")
                    json.dump(row, f, ensure_ascii=False, sort_keys=True)
                    f.write("\n")
                os.replace(tmp_path, path)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

    def _read_jsonl(self, path: str, limit: int = 200) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        rows: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        return rows[-max(1, int(limit or 200)) :]

    def _trial_id(self, study_id: str, row: Dict[str, Any]) -> str:
        iteration = row.get("iteration_no") or row.get("iteration") or "x"
        group = row.get("candidate_group_idx")
        suffix = f"-g{group}" if group is not None else ""
        return f"{study_id}:trial-{iteration}{suffix}"

    def _decision_id(self, study_id: str, row: Dict[str, Any]) -> str:
        dtype = row.get("decision_type") or "decision"
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{study_id}:{dtype}:{ts}"

    def _sanitize(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {str(k): self._sanitize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._sanitize(v) for v in value]
        if hasattr(value, "item"):
            try:
                return self._sanitize(value.item())
            except Exception:
                return str(value)
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        return str(value)
