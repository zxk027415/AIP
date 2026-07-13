"""
AutoResearch Job Queue — SQLite 轻量任务队列。

职责：
- FastAPI 写入 job（pending）
- Worker 领取 job（running）、写 heartbeat
- FastAPI 查询 job 状态、发送 cancel 标记
- Worker 崩溃后 heartbeat 超时，FastAPI 可标记 interrupted

表结构：
    jobs(run_id TEXT PK, status TEXT, pid INT, payload TEXT,
         created_at TEXT, started_at TEXT, finished_at TEXT,
         heartbeat_at TEXT, cancel_requested INT DEFAULT 0)
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import autoresearch_paths as arp

_DB_PATH = arp.as_str(arp.AUTORESEARCH_DIR / "jobs.sqlite")
_HEARTBEAT_TIMEOUT_SECONDS = 120  # worker 超过 2 分钟没心跳视为死亡
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            pid INTEGER,
            payload TEXT,
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            heartbeat_at TEXT,
            cancel_requested INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def submit_job(run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """FastAPI 调用：提交一个新 job。"""
    now = datetime.now().isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO jobs (run_id, status, payload, created_at, cancel_requested) VALUES (?, ?, ?, ?, 0)",
                (run_id, "pending", json.dumps(payload, ensure_ascii=False), now),
            )
            conn.commit()
        finally:
            conn.close()
    return {"run_id": run_id, "status": "pending", "created_at": now}


def claim_job() -> Optional[Dict[str, Any]]:
    """Worker 调用：领取一个 pending job，标记为 running。"""
    now = datetime.now().isoformat()
    pid = os.getpid()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT run_id, payload FROM jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            run_id = row["run_id"]
            conn.execute(
                "UPDATE jobs SET status = 'running', pid = ?, started_at = ?, heartbeat_at = ? WHERE run_id = ?",
                (pid, now, now, run_id),
            )
            conn.commit()
            return {"run_id": run_id, "payload": json.loads(row["payload"] or "{}")}
        finally:
            conn.close()


def heartbeat(run_id: str) -> None:
    """Worker 调用：更新心跳时间。"""
    now = datetime.now().isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute("UPDATE jobs SET heartbeat_at = ? WHERE run_id = ?", (now, run_id))
            conn.commit()
        finally:
            conn.close()


def is_cancel_requested(run_id: str) -> bool:
    """Worker 调用：检查是否收到取消请求。"""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT cancel_requested FROM jobs WHERE run_id = ?", (run_id,)).fetchone()
            return bool(row and row["cancel_requested"])
        finally:
            conn.close()


def request_cancel(run_id: str) -> bool:
    """FastAPI 调用：标记取消。"""
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute("UPDATE jobs SET cancel_requested = 1 WHERE run_id = ?", (run_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def finish_job(run_id: str, status: str) -> None:
    """Worker 调用：标记 job 完成（success/failed/cancelled）。"""
    now = datetime.now().isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, heartbeat_at = ? WHERE run_id = ?",
                (status, now, now, run_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_job(run_id: str) -> Optional[Dict[str, Any]]:
    """查询单个 job 状态。"""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                return None
            return dict(row)
        finally:
            conn.close()


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    """列出最近的 jobs。"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def mark_dead_workers() -> List[str]:
    """FastAPI 启动时调用：心跳超时的 running job 标记为 interrupted。"""
    cutoff = (datetime.now() - timedelta(seconds=_HEARTBEAT_TIMEOUT_SECONDS)).isoformat()
    marked: List[str] = []
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT run_id FROM jobs WHERE status = 'running' AND (heartbeat_at IS NULL OR heartbeat_at < ?)",
                (cutoff,),
            ).fetchall()
            for row in rows:
                run_id = row["run_id"]
                conn.execute(
                    "UPDATE jobs SET status = 'interrupted', finished_at = ? WHERE run_id = ?",
                    (datetime.now().isoformat(), run_id),
                )
                marked.append(run_id)
            conn.commit()
        finally:
            conn.close()
    return marked

# @AI_GENERATED: Phase 2 — MySQL backend 代理层
# 环境变量 AUTORESEARCH_JOB_QUEUE_BACKEND=mysql 时走 MySQL（autoresearch_job 表），
# 否则走原 SQLite 逻辑。支持跨机器 worker 领任务。

def _use_mysql() -> bool:
    """判断 Job Queue 是否走 MySQL backend。"""
    val = os.getenv("AUTORESEARCH_JOB_QUEUE_BACKEND", "sqlite").strip().lower()
    return val in ("mysql", "db", "database")


def _mysql_repo():
    """惰性获取 AutoResearchRepository（提供 job CRUD）。"""
    from services.db.repositories import get_autoresearch_repo
    return get_autoresearch_repo()


# --- 以下覆盖原模块级函数，在 import 时根据 backend 决定走哪条路径 ---
# 策略：把原函数重命名为 _sqlite_xxx，新函数同名，先判断 backend 再分发

_orig_submit_job = submit_job
_orig_claim_job = claim_job
_orig_heartbeat = heartbeat
_orig_is_cancel_requested = is_cancel_requested
_orig_request_cancel = request_cancel
_orig_finish_job = finish_job
_orig_get_job = get_job
_orig_list_jobs = list_jobs
_orig_mark_dead_workers = mark_dead_workers


def submit_job(run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:  # type: ignore[no-redef]
    """提交 job：MySQL backend 开启时走 DB，否则 SQLite。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            obj = repo.submit_job(run_id, payload)
            return {"run_id": obj.run_id, "status": "pending", "created_at": str(obj.created_at)}
    return _orig_submit_job(run_id, payload)


def claim_job() -> Optional[Dict[str, Any]]:  # type: ignore[no-redef]
    """Worker 领 job：MySQL backend 开启时走 DB。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            return repo.claim_job(pid=os.getpid())
    return _orig_claim_job()


def heartbeat(run_id: str) -> None:  # type: ignore[no-redef]
    """Worker 心跳。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            repo.heartbeat(run_id)
            return
    _orig_heartbeat(run_id)


def is_cancel_requested(run_id: str) -> bool:  # type: ignore[no-redef]
    """检查取消标记。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            return repo.is_cancel_requested(run_id)
    return _orig_is_cancel_requested(run_id)


def request_cancel(run_id: str) -> bool:  # type: ignore[no-redef]
    """标记取消。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            return repo.request_cancel(run_id)
    return _orig_request_cancel(run_id)


def finish_job(run_id: str, status: str) -> None:  # type: ignore[no-redef]
    """Worker 完成 job。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            repo.finish_job(run_id, status)
            return
    _orig_finish_job(run_id, status)


def get_job(run_id: str) -> Optional[Dict[str, Any]]:  # type: ignore[no-redef]
    """查询单个 job 状态。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            obj = repo.get_job(run_id)
            if obj is not None:
                return {
                    "run_id": obj.run_id,
                    "status": obj.status,
                    "pid": obj.pid,
                    "host": obj.host,
                    "created_at": str(obj.created_at) if obj.created_at else None,
                    "started_at": str(obj.started_at) if obj.started_at else None,
                    "finished_at": str(obj.finished_at) if obj.finished_at else None,
                    "heartbeat_at": str(obj.heartbeat_at) if obj.heartbeat_at else None,
                    "cancel_requested": int(obj.cancel_requested or 0),
                    "payload": json.dumps(obj.payload_json or {}, ensure_ascii=False),
                }
            return None
    return _orig_get_job(run_id)


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:  # type: ignore[no-redef]
    """列出 jobs。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            objs = repo.list_jobs(limit=limit)
            return [
                {
                    "run_id": o.run_id,
                    "status": o.status,
                    "pid": o.pid,
                    "host": o.host,
                    "created_at": str(o.created_at) if o.created_at else None,
                    "started_at": str(o.started_at) if o.started_at else None,
                    "finished_at": str(o.finished_at) if o.finished_at else None,
                    "heartbeat_at": str(o.heartbeat_at) if o.heartbeat_at else None,
                    "cancel_requested": int(o.cancel_requested or 0),
                }
                for o in objs
            ]
    return _orig_list_jobs(limit)


def mark_dead_workers() -> List[str]:  # type: ignore[no-redef]
    """标记心跳超时的 running job。"""
    if _use_mysql():
        repo = _mysql_repo()
        if repo is not None:
            return repo.mark_dead_workers()
    return _orig_mark_dead_workers()
# @AI_GENERATED: end
