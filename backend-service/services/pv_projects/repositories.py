# @AI_GENERATED
"""按 `(project_id, slot)` 分区的 scoped 存储核心。

设计依据：`design.md` §7（legacy 只读映射、禁止 silent fallback）、
§16（registry 相对目录）、§26.3（最小数据模型）、§26.6（原子写 + 按 scope 写锁 + 幂等键）；
`requirements.md` R1.7、R1.10–R1.12、R3.6–R3.9、R6.10、R9.6、R9.8、R13.1–R13.4。

分区规则：
- 非 legacy 项目：`<root>/projects/<project_id>/<slot>/<filename>`（相对 backend-service）。
- legacy 项目：映射到现有 slot-only 文件 `<root>/<slot>/<filename>`，**只读**。
- 缺失对象：返回“当前项目未产出”空态或 None，**绝不**读取 legacy 同槽或其他项目补位。

本模块只提供通用核心（单文档 / 集合 / append-only 日志 + 原子写 + 写锁 + 幂等 + 迁移）。
具体对象类型（registry / candidate / execution / review / ...）在 `stores.py` 配置。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from services.pv_projects.errors import ScopeError
from services.pv_projects.paths import PROJECTS_SEGMENT, backend_dir
from services.pv_projects.scope import ScopeContext

# ---------------------------------------------------------------------------
# 时间、原子写、按 scope 写锁
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()

# 存储基目录（默认 backend-service）。测试可通过 set_storage_base() 重定向到临时目录，
# 从而在不触碰真实 data/ 的前提下验证隔离与迁移。
_STORAGE_BASE_OVERRIDE: Optional[Path] = None


def storage_base() -> Path:
    """scoped 存储的基目录；默认 backend-service，可被测试重定向。"""
    return _STORAGE_BASE_OVERRIDE if _STORAGE_BASE_OVERRIDE is not None else backend_dir()


def set_storage_base(path: Optional[Any]) -> None:
    """仅供测试：重定向 scoped 存储根到临时目录（传 None 复位）。"""
    global _STORAGE_BASE_OVERRIDE
    _STORAGE_BASE_OVERRIDE = Path(path) if path else None


def _scope_lock(partition: str) -> threading.RLock:
    """返回按分区字符串复用的可重入写锁（多项目并发下防止覆盖丢失）。"""
    with _LOCKS_GUARD:
        lock = _LOCKS.get(partition)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[partition] = lock
        return lock


def _write_lock(
    scope: ScopeContext,
    *,
    root: str,
    filename: str,
    include_slot: bool,
    include_version: bool = False,
) -> threading.RLock:
    """按**解析后的物理路径**复用写锁（P1-7）。

    锁键必须与物理路径同源。项目级 store（`include_slot=False`）对同一项目的两条 slot
    解析到**同一个文件**；若锁键仍用 `scope.partition()`（形如 `proj-1/pv_day`，含 slot），
    两条 slot 会拿到**两把不同的锁**去保护同一个文件，`append` / `replace` 的
    read-modify-write 互相覆盖 → 丢写。

    证据：`backend-service/tests/pv_projects/test_p1_gates.py::
    test_concurrent_append_to_project_level_store_loses_no_write` 在修复前实测报
    "丢写：只看到 {'dsv-day'}"。
    """
    key = str(
        _resolve_object_path(
            scope,
            root=root,
            filename=filename,
            include_slot=include_slot,
            include_version=include_version,
        )
    )
    return _scope_lock(key)


def _atomic_write_json(path: Path, payload: Any) -> None:
    """原子写 JSON：先写临时文件再替换，避免并发下读到半截文件。

    Windows 上 `os.replace` 可能因杀软 / 索引器 / 并发读的瞬时文件锁抛 PermissionError；
    这里做少量指数退避重试，超出后仍抛出（保持 fail-closed，不静默吞错）。
    """
    import time

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    last_exc: Optional[OSError] = None
    for attempt in range(5):
        try:
            os.replace(str(tmp), str(path))
            return
        except PermissionError as exc:  # Windows 瞬时锁
            last_exc = exc
            time.sleep(0.02 * (attempt + 1))
    # 重试用尽：清理临时文件后抛出，绝不静默丢弃写入。
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass
    raise last_exc if last_exc is not None else RuntimeError("atomic write failed")


def _read_json(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 路径解析（scoped vs legacy 只读）
# ---------------------------------------------------------------------------

def _resolve_object_path(
    scope: ScopeContext,
    *,
    root: str,
    filename: str,
    include_slot: bool,
    include_version: bool,
) -> Path:
    """解析对象文件的绝对路径（仅供运行时 I/O，不持久化）。

    - legacy：`<root>/<slot>/<filename>`（沿用现有 slot-only 布局）。
    - 非 legacy：`<root>/projects/<project_id>/<slot>[/<version>]/<filename>`。
    """
    base = storage_base()
    root_path = base / Path(root)
    if scope.is_legacy:
        parts = [root_path]
        if include_slot:
            parts.append(Path(scope.require_slot()))
        target_dir = _join(parts)
        return target_dir / filename
    parts = [root_path, Path(PROJECTS_SEGMENT), Path(scope.project_id)]
    if include_slot:
        parts.append(Path(scope.require_slot()))
    if include_version:
        parts.append(Path(scope.require_dataset_version()))
    return _join(parts) / filename


def _join(parts: list[Path]) -> Path:
    result = parts[0]
    for part in parts[1:]:
        result = result / part
    return result


# ---------------------------------------------------------------------------
# 单文档仓储（每个 scope 一份 JSON，例如 registry）
# ---------------------------------------------------------------------------

class ScopedDocRepository:
    """按 scope 存放单个 JSON 文档。"""

    def __init__(
        self,
        *,
        root: str,
        filename: str,
        doc_kind: str,
        include_slot: bool = True,
        include_version: bool = False,
    ) -> None:
        self.root = root
        self.filename = filename
        self.doc_kind = doc_kind
        self.include_slot = include_slot
        self.include_version = include_version

    def _path(self, scope: ScopeContext) -> Path:
        return _resolve_object_path(
            scope,
            root=self.root,
            filename=self.filename,
            include_slot=self.include_slot,
            include_version=self.include_version,
        )

    def read(self, scope: ScopeContext) -> Optional[dict[str, Any]]:
        """读取文档；不存在返回 None（**不 fallback**）。"""
        payload = _read_json(self._path(scope))
        if not isinstance(payload, dict):
            return None
        return payload

    def read_or_empty(
        self,
        scope: ScopeContext,
        *,
        empty_factory: Optional[Callable[[ScopeContext], dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """读取文档；不存在返回带 scope 回显的显式空态。"""
        doc = self.read(scope)
        if doc is not None:
            doc.setdefault("project_id", scope.project_id)
            if self.include_slot and scope.slot:
                doc.setdefault("slot", scope.slot)
            doc.setdefault("empty", False)
            return doc
        if empty_factory is not None:
            return empty_factory(scope)
        return {
            **scope.echo(),
            "empty": True,
            "doc_kind": self.doc_kind,
            "diagnostic": "当前项目未产出该对象",
        }

    def write(self, scope: ScopeContext, payload: dict[str, Any]) -> dict[str, Any]:
        """写入文档；legacy 只读则拒绝。"""
        scope.assert_writable()
        record = dict(payload)
        record["project_id"] = scope.project_id
        if self.include_slot and scope.slot:
            record["slot"] = scope.slot
        record["updated_at"] = _now_iso()
        record["empty"] = False
        with _write_lock(
            scope,
            root=self.root,
            filename=self.filename,
            include_slot=self.include_slot,
            include_version=self.include_version,
        ):
            _atomic_write_json(self._path(scope), record)
        return record


# ---------------------------------------------------------------------------
# 集合仓储（每个 scope 一个记录列表，例如 candidate / execution / review）
# ---------------------------------------------------------------------------

class ScopedCollectionRepository:
    """按 scope 存放记录列表，JSON 形状为 `{project_id, slot, <items_key>: [...]}`。"""

    def __init__(
        self,
        *,
        root: str,
        filename: str,
        items_key: str,
        id_field: str,
        include_slot: bool = True,
        include_version: bool = False,
    ) -> None:
        self.root = root
        self.filename = filename
        self.items_key = items_key
        self.id_field = id_field
        self.include_slot = include_slot
        self.include_version = include_version

    def _path(self, scope: ScopeContext) -> Path:
        return _resolve_object_path(
            scope,
            root=self.root,
            filename=self.filename,
            include_slot=self.include_slot,
            include_version=self.include_version,
        )

    def list(self, scope: ScopeContext) -> list[dict[str, Any]]:
        """列出该 scope 的记录；不存在返回空列表（**不 fallback**）。"""
        payload = _read_json(self._path(scope))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            items = payload.get(self.items_key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def find(self, scope: ScopeContext, id_value: str) -> Optional[dict[str, Any]]:
        """在**当前 scope 内**按 id 查找；不跨项目、不跨槽。"""
        target = str(id_value or "").strip()
        if not target:
            return None
        for item in self.list(scope):
            if str(item.get(self.id_field) or "") == target:
                return item
        return None

    def append(self, scope: ScopeContext, record: dict[str, Any]) -> dict[str, Any]:
        """追加一条记录并持久化；legacy 只读则拒绝。

        record 的 `project_id` / `slot` 由 **ScopeContext 强制覆盖**（非 setdefault），
        杜绝调用方传入其他 scope 的 record 被写进当前 scope（跨项目 / 跨槽串写）。
        """
        scope.assert_writable()
        entry = dict(record)
        entry["project_id"] = scope.project_id
        if self.include_slot and scope.slot:
            entry["slot"] = scope.slot
        with _write_lock(
            scope,
            root=self.root,
            filename=self.filename,
            include_slot=self.include_slot,
            include_version=self.include_version,
        ):
            items = self.list(scope)
            items.append(entry)
            self._save(scope, items)
        return entry

    def replace(self, scope: ScopeContext, id_value: str, record: dict[str, Any]) -> dict[str, Any]:
        """按 id 覆盖一条记录；不存在则追加。legacy 只读则拒绝。

        同 `append`：`project_id` / `slot` 由 ScopeContext 强制覆盖。
        """
        scope.assert_writable()
        target = str(id_value or "").strip()
        entry = dict(record)
        entry["project_id"] = scope.project_id
        if self.include_slot and scope.slot:
            entry["slot"] = scope.slot
        with _write_lock(
            scope,
            root=self.root,
            filename=self.filename,
            include_slot=self.include_slot,
            include_version=self.include_version,
        ):
            items = self.list(scope)
            replaced = False
            for idx, item in enumerate(items):
                if str(item.get(self.id_field) or "") == target:
                    items[idx] = entry
                    replaced = True
                    break
            if not replaced:
                items.append(entry)
            self._save(scope, items)
        return entry

    def _save(self, scope: ScopeContext, items: list[dict[str, Any]]) -> None:
        wrapper: dict[str, Any] = {"project_id": scope.project_id}
        if self.include_slot and scope.slot:
            wrapper["slot"] = scope.slot
        wrapper[self.items_key] = items
        wrapper["updated_at"] = _now_iso()
        _atomic_write_json(self._path(scope), wrapper)


# ---------------------------------------------------------------------------
# append-only 审计日志（promotions_log），只追加、支持幂等命中
# ---------------------------------------------------------------------------

class ScopedAppendOnlyLog(ScopedCollectionRepository):
    """append-only 审计日志：只追加事件，不改历史。"""

    def find_by_idempotency(self, scope: ScopeContext, idempotency_key: str) -> Optional[dict[str, Any]]:
        key = str(idempotency_key or "").strip()
        if not key:
            return None
        for event in self.list(scope):
            if str(event.get("idempotency_key") or "") == key:
                return event
        return None

    def replace(self, scope: ScopeContext, id_value: str, record: dict[str, Any]) -> dict[str, Any]:
        raise ScopeError(
            "append_only_log",
            "审计日志只追加，不允许覆盖历史事件。",
        )


# ---------------------------------------------------------------------------
# 幂等的元数据 / 索引迁移（不复制 legacy 记录）
# ---------------------------------------------------------------------------

_PROJECTS_INDEX_ROOT = "data/pv_projects"
_PROJECTS_INDEX_FILE = "projects_index.json"


def _projects_index_path() -> Path:
    return storage_base() / _PROJECTS_INDEX_ROOT / _PROJECTS_INDEX_FILE


def ensure_project_layout(scope: ScopeContext, *, roots: list[str]) -> None:
    """幂等地为一个真实项目创建 scoped 目录骨架（不写任何 legacy 数据）。"""
    if scope.is_legacy:
        return
    base = storage_base()
    for root in roots:
        target = base / Path(root) / PROJECTS_SEGMENT / scope.project_id
        if scope.slot:
            target = target / scope.slot
        target.mkdir(parents=True, exist_ok=True)


def read_projects_index() -> dict[str, Any]:
    """读取项目索引；不存在返回仅含 legacy 的最小视图（不复制 legacy 记录）。"""
    payload = _read_json(_projects_index_path())
    if isinstance(payload, dict) and isinstance(payload.get("projects"), list):
        return payload
    return {"projects": [], "legacy_read_only": True}


def migrate_projects_index() -> dict[str, Any]:
    """幂等索引迁移：确保索引文件存在并登记 legacy 为只读映射。

    **不复制** 现有 slot-only 记录到任何新项目；legacy 仍指向原始 slot-only 文件。
    """
    path = _projects_index_path()
    index = read_projects_index()
    known = {str(item.get("project_id")) for item in index.get("projects", []) if isinstance(item, dict)}
    if ScopeContext(project_id="legacy", is_legacy=True, read_only=True).project_id not in known:
        index.setdefault("projects", []).append(
            {
                "project_id": "legacy",
                "read_only": True,
                "source": "slot_only_compat",
                "note": "现有仅按 slot 分区的历史状态只读映射，不复制到新项目",
                "registered_at": _now_iso(),
            }
        )
    index["legacy_read_only"] = True
    index["migrated_at"] = _now_iso()
    _atomic_write_json(path, index)
    return index


def register_project_in_index(
    project_id: str,
    *,
    scenario_id: Optional[str] = None,
    solution_id: Optional[str] = None,
    project_name: Optional[str] = None,
    owner: Optional[str] = None,
) -> dict[str, Any]:
    """把一个新项目登记进索引（幂等）。不继承任何 legacy 状态。"""
    pid = str(project_id or "").strip()
    if not pid or pid == "legacy":
        raise ScopeError("invalid_project_id", f"不能登记项目 id={project_id!r}")
    path = _projects_index_path()
    with _scope_lock("__projects_index__"):
        index = read_projects_index()
        projects = index.setdefault("projects", [])
        for item in projects:
            if isinstance(item, dict) and str(item.get("project_id")) == pid:
                return item
        record = {
            "project_id": pid,
            "project_name": project_name,
            "owner": owner,
            "scenario_id": scenario_id,
            "solution_id": solution_id,
            "read_only": False,
            # 启用的诊断路径（intent）；None 表示尚未确认（应在 readiness 出来后确认）。
            "enabled_slots": None,
            "registered_at": _now_iso(),
        }
        projects.append(record)
        index["updated_at"] = _now_iso()
        _atomic_write_json(path, index)
        return record


def update_project_in_index(project_id: str, **fields: Any) -> dict[str, Any]:
    """更新索引里某个项目的元数据字段（如 `enabled_slots`）。

    只允许更新白名单字段；`legacy` 只读不可更新；项目不存在则报错（不隐式创建）。
    """
    allowed = {"project_name", "owner", "scenario_id", "solution_id", "enabled_slots"}
    bad = set(fields) - allowed
    if bad:
        raise ScopeError("invalid_project_fields", f"不允许更新字段：{sorted(bad)}")
    pid = str(project_id or "").strip()
    if not pid or pid == "legacy":
        raise ScopeError("invalid_project_id", f"不能更新项目 id={project_id!r}（legacy 只读）")
    path = _projects_index_path()
    with _scope_lock("__projects_index__"):
        index = read_projects_index()
        projects = index.setdefault("projects", [])
        for idx, item in enumerate(projects):
            if isinstance(item, dict) and str(item.get("project_id")) == pid:
                updated = {**item, **fields, "updated_at": _now_iso()}
                projects[idx] = updated
                index["updated_at"] = _now_iso()
                _atomic_write_json(path, index)
                return updated
        raise ScopeError("project_not_found", f"项目不存在：{pid}")


# @AI_GENERATED: end
