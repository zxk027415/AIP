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
        # @AI_GENERATED: Phase 1 双写 — 写完 trials.jsonl 后同步 insert experiment_trial
        self._dual_write_trial_to_db(study_id, row)
        # @AI_GENERATED: end
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
        # @AI_GENERATED: Phase 1 双写 — 写完 decisions.jsonl 后同步 insert experiment_decision
        self._dual_write_decision_to_db(study_id, row)
        # @AI_GENERATED: end
        return row

    # @AI_GENERATED: Phase 1 双写 — experiment_trial / experiment_decision
    def _dual_write_trial_to_db(self, run_id: str, row: Dict[str, Any]) -> None:
        """把 trial 行同步 insert 到 MySQL experiment_trial 表。

        字段映射：
          - run_id            ← study_id（AutoResearch 里 study_id 即 run_id）
          - iteration_no      ← row.iteration_no / row.iteration
          - status            ← row.status
          - override_json     ← row.override / row.global_config_patch
          - evidence_json     ← 从 windows_* / failure_reason / score_advantage 等抽取
          - mape_improvement / baseline_mape / challenger_mape ← 同名字段

        失败降级 warning，不阻塞 JSON 写入。
        """
        try:
            from services.db.repositories import get_autoresearch_repo, is_dual_write_enabled
            if not is_dual_write_enabled():
                return
            repo = get_autoresearch_repo()
            if repo is None:
                return

            iter_no = row.get("iteration_no")
            if iter_no is None:
                iter_no = row.get("iteration")
            if iter_no is None:
                return  # 无 iteration_no 的 trial 不入 experiment_trial（唯一约束需要）

            override = row.get("override") or row.get("global_config_patch") or {}
            evidence = {
                k: row.get(k)
                for k in ("windows_total", "windows_comparable", "windows_challenger_better",
                          "failure_reason", "score_advantage", "hypothesis_verification")
                if row.get(k) is not None
            }

            def _f(v):
                return float(v) if isinstance(v, (int, float)) else None

            repo.append_trial(run_id, {
                "iteration_no": int(iter_no),
                "status": str(row.get("status") or "success")[:32],
                "override_json": override if isinstance(override, dict) else {},
                "evidence_json": evidence,
                "mape_improvement": _f(row.get("mape_improvement")),
                "baseline_mape": _f(row.get("baseline_mape")),
                "challenger_mape": _f(row.get("challenger_mape")),
            })
        except Exception as exc:
            self._warn_dual_write("experiment_trial", exc)

    def _dual_write_decision_to_db(self, run_id: str, row: Dict[str, Any]) -> None:
        """把 decision 行同步 insert 到 MySQL experiment_decision 表。"""
        try:
            from services.db.repositories import get_autoresearch_repo, is_dual_write_enabled
            if not is_dual_write_enabled():
                return
            repo = get_autoresearch_repo()
            if repo is None:
                return

            decision_type = str(row.get("decision_type") or "unknown")[:64]
            actor = str(row.get("actor") or "system")[:64]
            payload = {
                k: v for k, v in row.items()
                if k not in ("decision_type", "actor", "created_at", "id", "study_id")
            }
            repo.append_decision(run_id, decision_type, payload, actor=actor)
        except Exception as exc:
            self._warn_dual_write("experiment_decision", exc)

    @staticmethod
    def _warn_dual_write(table: str, exc: Exception) -> None:
        try:
            import logging
            logging.getLogger(__name__).warning(
                "AutoResearchTrialLedger dual-write to %s failed (non-fatal): %s", table, exc
            )
        except Exception:
            pass
    # @AI_GENERATED: end

    def list_trials(self, study_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        # @AI_GENERATED: Phase 2 读切换 — DB 优先
        db_rows = self._list_trials_from_db(study_id, limit)
        if db_rows is not None:
            return db_rows
        # @AI_GENERATED: end
        rows = self._read_jsonl(self._path(study_id, "trials.jsonl"), limit=limit)
        if rows:
            return rows
        legacy = self._legacy_path(study_id, "trials.jsonl")
        return self._read_jsonl(legacy, limit=limit) if legacy else []

    def list_decisions(self, study_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        # @AI_GENERATED: Phase 2 读切换 — DB 优先
        db_rows = self._list_decisions_from_db(study_id, limit)
        if db_rows is not None:
            return db_rows
        # @AI_GENERATED: end
        rows = self._read_jsonl(self._path(study_id, "decisions.jsonl"), limit=limit)
        if rows:
            return rows
        legacy = self._legacy_path(study_id, "decisions.jsonl")
        return self._read_jsonl(legacy, limit=limit) if legacy else []

    # @AI_GENERATED: Phase 2 读切换 — 从 experiment_trial / experiment_decision 读
    def _list_trials_from_db(self, run_id: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        try:
            from services.db.repositories import get_autoresearch_repo, is_db_read_enabled
            if not is_db_read_enabled():
                return None
            repo = get_autoresearch_repo()
            if repo is None:
                return None
            trials = repo.list_trials(run_id, limit=limit)
            if not trials:
                return None  # DB 里没有则退回 JSON（可能是双写前的老 run）
            out: List[Dict[str, Any]] = []
            for t in trials:
                row = {
                    "id": f"{run_id}:trial-{t.iteration_no}",
                    "study_id": run_id,
                    "iteration_no": t.iteration_no,
                    "status": t.status,
                    "override": t.override_json or {},
                    "mape_improvement": t.mape_improvement,
                    "baseline_mape": t.baseline_mape,
                    "challenger_mape": t.challenger_mape,
                    "created_at": (t.created_at.isoformat() if t.created_at else None),
                }
                if isinstance(t.evidence_json, dict):
                    row.update(t.evidence_json)
                out.append(row)
            return out
        except Exception as exc:
            self._warn_read_fallback("experiment_trial", exc)
            return None

    def _list_decisions_from_db(self, run_id: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        try:
            from services.db.repositories import get_autoresearch_repo, is_db_read_enabled
            if not is_db_read_enabled():
                return None
            repo = get_autoresearch_repo()
            if repo is None:
                return None
            decisions = repo.list_decisions(run_id, limit=limit)
            if not decisions:
                return None
            out: List[Dict[str, Any]] = []
            for d in decisions:
                row = {
                    "id": f"{run_id}:{d.decision_type}:{d.seq}",
                    "study_id": run_id,
                    "decision_type": d.decision_type,
                    "actor": d.actor,
                    "created_at": (d.created_at.isoformat() if d.created_at else None),
                }
                if isinstance(d.payload_json, dict):
                    row.update(d.payload_json)
                out.append(row)
            return out
        except Exception as exc:
            self._warn_read_fallback("experiment_decision", exc)
            return None

    @staticmethod
    def _warn_read_fallback(table: str, exc: Exception) -> None:
        try:
            import logging
            logging.getLogger(__name__).warning(
                "AutoResearchTrialLedger read from %s failed (fallback to JSON): %s", table, exc
            )
        except Exception:
            pass
    # @AI_GENERATED: end

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
