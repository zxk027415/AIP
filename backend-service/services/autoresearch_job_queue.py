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
