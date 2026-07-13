import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import autoresearch_paths as arp


TERMINAL_STATUSES = {"success", "failed", "cancelled"}
INTERRUPTIBLE_STATUSES = {"pending", "running", "waiting_review", "cancelling"}


class AutoResearchRunStore:
    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or arp.as_str(arp.runs_dir())
        self.legacy_root_dir = None if root_dir else arp.as_str(arp.legacy_runs_dir())
        os.makedirs(self.root_dir, exist_ok=True)

    def save(self, run_id: str, state: Dict[str, Any]) -> str:
        if not run_id:
            raise ValueError("run_id is required")
        payload = self._snapshot_payload(run_id, state)
        path = self.path_for(run_id)
        self._atomic_write(path, payload)
        # @AI_GENERATED: Phase 1 双写 — 写完 snapshot.json 后同步 upsert 到 MySQL experiment_run 表
        self._dual_write_run_to_db(run_id, payload)
        # @AI_GENERATED: end
        return path

    # @AI_GENERATED: Phase 1 双写 — experiment_run 表 upsert
    def _dual_write_run_to_db(self, run_id: str, payload: Dict[str, Any]) -> None:
        """把 run 快照同步 upsert 到 MySQL experiment_run 表。

        字段映射（从 state / snapshot_payload 提取）：
          - id                    ← run_id
          - slot                  ← state.slot / "default" 兜底
          - status                ← state.status
          - previous_status       ← state.previous_status
          - recoverable           ← state.recoverable（默认 True）
          - baseline_workflow_id  ← state.baseline_workflow_id
          - current_iteration     ← state.progress.iteration / state.iteration
          - total_iterations      ← state.progress.total_iterations / state.total_iterations
          - config                ← state.compare_config
          - runtime_patch         ← state.runtime_patch
          - snapshot_state        ← 整个 sanitized state（用于断点恢复）
          - run_insight           ← state.run_insight
          - error_message         ← state.error
          - started_at / finished_at / interrupted_at / resumed_at — 解析 ISO 时间戳

        失败降级：只 warning 不抛，保证 JSON 写入成功后主流程继续。
        """
        try:
            from services.db.repositories import get_autoresearch_repo, is_dual_write_enabled
            if not is_dual_write_enabled():
                return
            repo = get_autoresearch_repo()
            if repo is None:
                return

            state = payload.get("state") if isinstance(payload, dict) else None
            if not isinstance(state, dict):
                return

            progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
            current_iter = progress.get("iteration") or state.get("iteration")
            total_iter = progress.get("total_iterations") or state.get("total_iterations")

            def _parse_dt(value):
                if not value:
                    return None
                if isinstance(value, datetime):
                    return value
                try:
                    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except Exception:
                    return None

            error_msg = state.get("error")
            if isinstance(error_msg, str) and len(error_msg) > 2048:
                error_msg = error_msg[:2048]

            run_data = {
                "id": run_id,
                "slot": str(state.get("slot") or "default")[:64],
                "status": str(state.get("status") or "pending")[:32],
                "previous_status": (
                    str(state.get("previous_status"))[:32]
                    if state.get("previous_status") else None
                ),
                "recoverable": bool(state.get("recoverable", True)),
                "baseline_workflow_id": (
                    str(state.get("baseline_workflow_id"))[:128]
                    if state.get("baseline_workflow_id") else None
                ),
                "current_iteration": int(current_iter) if isinstance(current_iter, (int, float)) else None,
                "total_iterations": int(total_iter) if isinstance(total_iter, (int, float)) else None,
                "config": state.get("compare_config") if isinstance(state.get("compare_config"), dict) else None,
                "runtime_patch": state.get("runtime_patch") if isinstance(state.get("runtime_patch"), dict) else None,
                "snapshot_state": state,
                "run_insight": state.get("run_insight") if isinstance(state.get("run_insight"), dict) else None,
                "terminal_status": (
                    str(state.get("terminal_status"))[:32]
                    if state.get("terminal_status") else None
                ),
                "error_message": error_msg,
                "started_at": _parse_dt(state.get("started_at")) or _parse_dt(state.get("created_at")) or datetime.utcnow(),
                "finished_at": _parse_dt(state.get("finished_at")),
                "interrupted_at": _parse_dt(state.get("interrupted_at")),
                "resumed_at": _parse_dt(state.get("resumed_at")),
            }
            repo.upsert_run(run_data)
        except Exception as exc:
            try:
                import logging
                logging.getLogger(__name__).warning(
                    "AutoResearchRunStore dual-write to experiment_run failed (non-fatal): %s", exc
                )
            except Exception:
                pass
    # @AI_GENERATED: end

    def load(self, run_id: str) -> Optional[Dict[str, Any]]:
        # @AI_GENERATED: Phase 2 读切换 — DB 优先，miss/异常兜底 JSON
        db_state = self._load_from_db(run_id)
        if db_state is not None:
            return db_state
        # @AI_GENERATED: end
        path = self.path_for(run_id)
        if not os.path.exists(path):
            legacy_path = self.legacy_path_for(run_id)
            if legacy_path and os.path.exists(legacy_path):
                path = legacy_path
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        state = data.get("state")
        if isinstance(state, dict):
            state.setdefault("run_id", data.get("run_id") or run_id)
            state.setdefault("snapshot_meta", self._meta_from_snapshot(data))
            return state
        data.setdefault("run_id", run_id)
        return data

    # @AI_GENERATED: Phase 2 读切换 — 从 MySQL experiment_run.snapshot_state 读取
    def _load_from_db(self, run_id: str) -> Optional[Dict[str, Any]]:
        """读开关开启时，从 experiment_run.snapshot_state 恢复 state。

        返回 None 表示「未启用 / DB 不可用 / DB 里没有」，调用方继续走 JSON 兜底。
        """
        try:
            from services.db.repositories import get_autoresearch_repo, is_db_read_enabled
            if not is_db_read_enabled():
                return None
            repo = get_autoresearch_repo()
            if repo is None:
                return None
            row = repo.get_run(run_id)
            if row is None:
                return None
            state = row.snapshot_state if isinstance(row.snapshot_state, dict) else None
            if not state:
                # snapshot_state 为空（比如只迁移过 insight），退回 JSON
                return None
            state.setdefault("run_id", run_id)
            state.setdefault("snapshot_meta", {"source": "mysql", "schema_version": 1})
            # @AI_GENERATED: 表级字段是权威源，覆盖 snapshot_state 里可能过时的值
            state["status"] = row.status
            if row.previous_status:
                state["previous_status"] = row.previous_status
            if row.recoverable is not None:
                state["recoverable"] = row.recoverable
            if row.error_message:
                state["error"] = row.error_message
            if row.interrupted_at:
                state["interrupted_at"] = row.interrupted_at.isoformat()
            if row.resumed_at:
                state["resumed_at"] = row.resumed_at.isoformat()
            if row.current_iteration is not None:
                state.setdefault("progress", {})
                state["progress"]["iteration"] = row.current_iteration
            if row.total_iterations is not None:
                state.setdefault("progress", {})
                state["progress"]["total_iterations"] = row.total_iterations
            # @AI_GENERATED: end
            return state
        except Exception as exc:
            try:
                import logging
                logging.getLogger(__name__).warning(
                    "AutoResearchRunStore._load_from_db failed (fallback to JSON): %s", exc
                )
            except Exception:
                pass
            return None

    def _list_from_db(self, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
        """读开关开启时，从 experiment_run 表列出 runs（按 updated_at 倒序）。

        返回 None 表示「未启用 / DB 不可用」，调用方继续走 JSON。
        返回 [] 是合法结果（DB 里确实没有 run）。
        """
        try:
            from services.db.repositories import get_autoresearch_repo, is_db_read_enabled
            if not is_db_read_enabled():
                return None
            repo = get_autoresearch_repo()
            if repo is None:
                return None
            runs = repo.list_runs(limit=limit)
            rows: List[Dict[str, Any]] = []
            for r in runs:
                state = r.snapshot_state if isinstance(r.snapshot_state, dict) else {}
                rows.append({
                    "run_id": r.id,
                    "status": r.status,
                    "progress": state.get("progress") or {
                        "iteration": r.current_iteration,
                        "total_iterations": r.total_iterations,
                    },
                    "baseline_workflow_id": r.baseline_workflow_id or state.get("baseline_workflow_id"),
                    "created_at": (r.started_at.isoformat() if r.started_at else state.get("created_at")),
                    "updated_at": (r.updated_at.isoformat() if r.updated_at else None),
                    "snapshot_path": "mysql://experiment_run/" + str(r.id),
                })
            return rows
        except Exception as exc:
            try:
                import logging
                logging.getLogger(__name__).warning(
                    "AutoResearchRunStore._list_from_db failed (fallback to JSON): %s", exc
                )
            except Exception:
                pass
            return None
    # @AI_GENERATED: end

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        # @AI_GENERATED: Phase 2 读切换 — DB 优先列出 runs，异常/空时兜底 JSON
        db_rows = self._list_from_db(limit)
        if db_rows is not None:
            return db_rows
        # @AI_GENERATED: end
        rows: List[Dict[str, Any]] = []
        candidates: List[Path] = []
        try:
            root = Path(self.root_dir)
            for child in root.iterdir():
                if child.is_dir() and (child / "snapshot.json").is_file():
                    candidates.append(child / "snapshot.json")
                elif child.is_file() and child.name.endswith(".json"):
                    candidates.append(child)
        except FileNotFoundError:
            pass
        if self.legacy_root_dir and os.path.exists(self.legacy_root_dir):
            for name in os.listdir(self.legacy_root_dir):
                if name.endswith(".json"):
                    candidates.append(Path(self.legacy_root_dir) / name)
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        seen = set()
        for path_obj in candidates[: max(1, int(limit or 50)) * 3]:
            path = os.fspath(path_obj)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            state = data.get("state") if isinstance(data.get("state"), dict) else data
            run_id = data.get("run_id") or state.get("run_id") or self._run_id_from_path(path_obj)
            if not run_id or run_id in seen:
                continue
            seen.add(str(run_id))
            rows.append({
                "run_id": run_id,
                "status": state.get("status"),
                "progress": state.get("progress"),
                "baseline_workflow_id": state.get("baseline_workflow_id"),
                "created_at": state.get("created_at"),
                "updated_at": data.get("saved_at") or state.get("updated_at"),
                "snapshot_path": path,
            })
            if len(rows) >= max(1, int(limit or 50)):
                break
        rows.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
        return rows[: max(1, int(limit or 50))]

    def mark_interrupted(self, run_id: str, state: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        loaded = dict(state or self.load(run_id) or {})
        if not loaded:
            return None
        status = str(loaded.get("status") or "").lower()
        if status in INTERRUPTIBLE_STATUSES:
            loaded["previous_status"] = status
            loaded["status"] = "interrupted"
            loaded["recoverable"] = True
            loaded["interrupted_at"] = datetime.now().isoformat()
            loaded["error"] = loaded.get("error") or "服务重启或内存状态丢失，运行已中断"
            self.save(run_id, loaded)
        return loaded

    def load_for_status(self, run_id: str, active_in_memory: bool = False) -> Optional[Dict[str, Any]]:
        state = self.load(run_id)
        if state is None:
            return None
        status = str(state.get("status") or "").lower()
        if not active_in_memory and status in INTERRUPTIBLE_STATUSES:
            return self.mark_interrupted(run_id, state)
        return state

    def scan_and_mark_interrupted(self) -> List[str]:
        """服务重启时调用：扫描所有 running/waiting_review 的 run，标记为 interrupted。
        返回被标记的 run_id 列表。"""
        # @AI_GENERATED: Phase 2 — DB 读开关开启时走一条 SQL 批量标记，比逐个 load+save 快
        db_marked = self._scan_and_mark_via_db()
        if db_marked is not None:
            return db_marked
        # @AI_GENERATED: end
        marked: List[str] = []
        for row in self.list(limit=200):
            run_id = str(row.get("run_id") or "")
            status = str(row.get("status") or "").lower()
            if not run_id:
                continue
            if status in INTERRUPTIBLE_STATUSES:
                self.mark_interrupted(run_id)
                marked.append(run_id)
        return marked

    # @AI_GENERATED: Phase 2 — 断点恢复走 SQL
    def _scan_and_mark_via_db(self) -> Optional[List[str]]:
        """DB 路径：一次 SQL 批量标记所有 running/pending/waiting_review/cancelling 为 interrupted。

        返回 None 表示未启用或失败，调用方走原 JSON 逻辑。
        """
        try:
            from services.db.repositories import get_autoresearch_repo, is_db_read_enabled
            if not is_db_read_enabled():
                return None
            repo = get_autoresearch_repo()
            if repo is None:
                return None
            marked = repo.mark_interrupted_running_runs()
            # 同步写回 JSON（保持双写一致）
            for run_id in marked:
                try:
                    state = self.load(run_id)
                    if state and str(state.get("status") or "").lower() != "interrupted":
                        state["previous_status"] = state.get("status")
                        state["status"] = "interrupted"
                        state["recoverable"] = True
                        state["interrupted_at"] = datetime.now().isoformat()
                        state["error"] = state.get("error") or "服务重启或内存状态丢失，运行已中断"
                        # 直接写 JSON（不再调 save 避免循环双写）
                        payload = self._snapshot_payload(run_id, state)
                        path = self.path_for(run_id)
                        self._atomic_write(path, payload)
                except Exception:
                    pass  # JSON 回写失败不影响 DB 已标记
            return marked
        except Exception as exc:
            try:
                import logging
                logging.getLogger(__name__).warning(
                    "scan_and_mark_via_db failed (fallback to JSON): %s", exc
                )
            except Exception:
                pass
            return None
    # @AI_GENERATED: end

    def path_for(self, run_id: str) -> str:
        safe_id = arp.safe_id(run_id)
        return os.path.join(self.root_dir, safe_id, "snapshot.json")

    def legacy_path_for(self, run_id: str) -> Optional[str]:
        if not self.legacy_root_dir:
            return None
        safe_id = arp.safe_id(run_id)
        return os.path.join(self.legacy_root_dir, f"{safe_id}.json")

    def _run_id_from_path(self, path: Path) -> str:
        if path.name == "snapshot.json":
            return path.parent.name
        return path.stem

    def _snapshot_payload(self, run_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = self._sanitize(state)
        if not isinstance(sanitized, dict):
            sanitized = {"value": sanitized}
        sanitized.setdefault("run_id", run_id)
        return {
            "schema_version": 1,
            "run_id": run_id,
            "saved_at": datetime.now().isoformat(),
            "state": sanitized,
        }

    def _meta_from_snapshot(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "schema_version": data.get("schema_version"),
            "saved_at": data.get("saved_at"),
        }

    def _atomic_write(self, path: str, payload: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            dir=os.path.dirname(path),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

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
