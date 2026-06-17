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
        return path

    def load(self, run_id: str) -> Optional[Dict[str, Any]]:
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

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
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
        """服务重启时调用：扫描磁盘上所有 running/waiting_review 的 run，标记为 interrupted。
        返回被标记的 run_id 列表。"""
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
