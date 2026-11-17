#!/usr/bin/env python3
"""
AutoResearch Worker — 独立进程，从 job queue 领取任务并执行。

用法：
    python worker_autoresearch.py              # 前台运行，处理完一个 job 后退出
    python worker_autoresearch.py --loop       # 持续轮询，直到手动停止
    python worker_autoresearch.py --once       # 处理一个 job 后退出（默认）

Worker 与 FastAPI 通过 SQLite job queue + 磁盘 snapshot 通信：
- Worker 领取 pending job → 执行 AutoResearch → 写 snapshot/trial → 完成后标记 job
- Worker 每轮写 heartbeat，FastAPI 可检测 worker 是否存活
- FastAPI 写 cancel_requested=1，Worker 每轮检查并停止
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv

    _env_local = Path(__file__).resolve().parent / ".env.local"
    if _env_local.exists():
        load_dotenv(_env_local, override=False)
except Exception as exc:
    print(f"[Worker] .env.local 加载失败，继续使用当前环境变量: {exc}")

from services import autoresearch_job_queue as jq


_POLL_INTERVAL = 3  # 秒
_HEARTBEAT_INTERVAL = 15  # 秒
_shutdown = threading.Event()


def _signal_handler(signum, frame):
    print(f"\n[Worker] 收到信号 {signum}，准备退出...")
    _shutdown.set()


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _heartbeat_loop(run_id: str, stop_event: threading.Event):
    """后台线程：定期写心跳。"""
    while not stop_event.is_set():
        try:
            jq.heartbeat(run_id)
        except Exception as e:
            print(f"[Worker] heartbeat 写入失败: {e}")
        stop_event.wait(_HEARTBEAT_INTERVAL)


def _execute_job(job: Dict[str, Any]) -> None:
    """执行单个 AutoResearch job。"""
    run_id = job["run_id"]
    payload = job["payload"]
    print(f"[Worker] 开始执行 job: {run_id}")
    print(f"[Worker] baseline_workflow_id: {payload.get('baseline_workflow_id')}")
    print(f"[Worker] max_iterations: {payload.get('max_iterations')}")

    # 启动心跳线程
    hb_stop = threading.Event()
    hb_thread = threading.Thread(target=_heartbeat_loop, args=(run_id, hb_stop), daemon=True)
    hb_thread.start()

    # 构造 cancel_event：检查 job queue 的 cancel_requested + 全局 shutdown
    cancel_event = threading.Event()

    def _cancel_checker():
        while not cancel_event.is_set():
            if _shutdown.is_set() or jq.is_cancel_requested(run_id):
                cancel_event.set()
                break
            time.sleep(2)

    cancel_thread = threading.Thread(target=_cancel_checker, daemon=True)
    cancel_thread.start()

    final_status = "failed"
    try:
        # 延迟 import 避免顶层加载所有依赖
        from api.workflows_enhanced import (
            _auto_research_store,
            _auto_research_cancel_events,
            _auto_research_persister,
            _init_autoresearch_state,
            _run_autoresearch_task,
            _snapshot_autoresearch_state,
        )

        # 恢复或初始化内存状态
        existing_snapshot = _auto_research_persister.load_snapshot(run_id)
        if existing_snapshot:
            _auto_research_store[run_id] = existing_snapshot
            _auto_research_store[run_id]["status"] = "running"
            _auto_research_store[run_id]["error"] = None
        else:
            _init_autoresearch_state(run_id)
            _auto_research_store[run_id]["baseline_workflow_id"] = payload.get("baseline_workflow_id")
            _auto_research_store[run_id]["search_space"] = payload.get("search_space", {})
            _auto_research_store[run_id]["evaluation_contract"] = payload.get("evaluation_contract", {})
            _auto_research_store[run_id]["compare_config"] = payload.get("compare_config", {})

        _auto_research_cancel_events[run_id] = cancel_event

        # 执行主循环
        asyncio.run(
            _run_autoresearch_task(
                run_id=run_id,
                baseline_workflow_id=str(payload.get("baseline_workflow_id", "")),
                windows=payload.get("windows", []),
                evaluation_contract=payload.get("evaluation_contract", {}),
                search_space=payload.get("search_space", {}),
                max_iterations=int(payload.get("max_iterations", 12)),
                top_k=int(payload.get("top_k", 10)),
                policy=payload.get("policy", {}),
                compare_config=payload.get("compare_config", {}),
                cancel_event=cancel_event,
                start_iteration=int(payload.get("start_iteration", 1)),
                total_iterations=int(payload.get("total_iterations") or payload.get("max_iterations", 12)),
            )
        )

        # 判断最终状态
        state = _auto_research_store.get(run_id, {})
        final_status = str(state.get("status", "success")).lower()
        if final_status not in ("success", "failed", "cancelled"):
            final_status = "success"

    except Exception as e:
        print(f"[Worker] job {run_id} 执行异常: {e}")
        final_status = "failed"
    finally:
        hb_stop.set()
        hb_thread.join(timeout=5)
        cancel_event.set()

        jq.finish_job(run_id, final_status)
        print(f"[Worker] job {run_id} 完成，状态: {final_status}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AutoResearch Worker")
    parser.add_argument("--loop", action="store_true", help="持续轮询模式")
    parser.add_argument("--once", action="store_true", help="处理一个 job 后退出（默认）")
    args = parser.parse_args()

    loop_mode = args.loop
    print(f"[Worker] 启动，PID={os.getpid()}，模式={'loop' if loop_mode else 'once'}")
    print(f"[Worker] Job DB: {jq._DB_PATH}")

    while not _shutdown.is_set():
        job = jq.claim_job()
        if job:
            _execute_job(job)
            if not loop_mode:
                break
        else:
            if not loop_mode:
                print("[Worker] 无待处理 job，退出")
                break
            _shutdown.wait(_POLL_INTERVAL)

    print("[Worker] 退出")


if __name__ == "__main__":
    main()
