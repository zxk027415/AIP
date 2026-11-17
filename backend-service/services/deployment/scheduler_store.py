# @AI_GENERATED
"""
services/deployment/scheduler_store.py — 定时调度任务 JSON 持久化服务

职责：
  - 提供 ScheduledTask 的加载、查询、创建/更新（upsert）、删除、批量覆盖接口
  - 存储路径：data/scheduler/tasks.json（相对于 backend-service/ 目录）
  - 原子写入：先写同目录临时文件，再 os.replace 到目标文件，
    避免并发读取观察到中间状态
  - 线程安全：所有写操作在进程内使用 threading.Lock 串行化

存储结构：
  {
    "tasks": [ ScheduledTask 的 JSON 表示, ... ]
  }

**存什么**：全平台所有已配置的定时调度任务，按 task_id 唯一。
**为什么单独存**：调度任务与部署槽位分开管理，同一个 pipeline 可以有多份调度定义；
                 JSON 文件存储保持与项目其它模块（precision_ops、workflow_enhanced 等）一致。
**按什么维度分区**：单文件多任务，通过 task 对象中的 slot 字段做逻辑分区（复用已有 slot 概念）。
**路径/介质**：backend-service/data/scheduler/tasks.json，路径由本文件位置动态计算，
              绝不硬编码绝对路径。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from services.deployment.scheduler_models import ScheduledTask

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径常量（相对路径动态计算，不硬编码绝对路径）
# ---------------------------------------------------------------------------
# 本文件位于 backend-service/services/deployment/scheduler_store.py
# 向上两级到 backend-service/，再拼接 data/scheduler/tasks.json
_THIS_DIR = Path(__file__).resolve().parent           # .../services/deployment/
_BACKEND_DIR = _THIS_DIR.parent.parent                # .../backend-service/
_DATA_DIR: Path = _BACKEND_DIR / "data" / "scheduler"
_TASKS_FILE: Path = _DATA_DIR / "tasks.json"

# 进程内锁保护并发写；跨进程一致性依赖 os.replace 的原子性
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 底层 IO 工具
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, data: Any) -> None:
    """
    原子写入 JSON 文件。

    先将序列化内容写入同目录下的临时文件，再通过 os.replace() 原子替换目标文件，
    确保并发读取方不会观察到部分写入状态。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    dir_str = str(path.parent)
    fd, tmp_path = tempfile.mkstemp(dir=dir_str, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # 写入失败时清理临时文件（best-effort），再抛出原异常
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_raw() -> Dict[str, Any]:
    """
    从磁盘读取原始 JSON。

    文件不存在返回空结构；文件损坏或结构非法时记录 warning 并返回空结构，
    不抛出异常（避免调度器主循环因单个损坏文件而无法启动）。
    """
    if not _TASKS_FILE.exists():
        return {"tasks": []}
    try:
        with open(_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "scheduler_store: 无法读取 %s (%s)，本次视为空列表",
            _TASKS_FILE, exc,
        )
        return {"tasks": []}
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        logger.warning(
            "scheduler_store: %s 结构异常，期望 {'tasks': [...]}，"
            "本次视为空列表",
            _TASKS_FILE,
        )
        return {"tasks": []}
    return data


# ---------------------------------------------------------------------------
# SchedulerStore
# ---------------------------------------------------------------------------

class SchedulerStore:
    """
    定时调度任务 JSON 存储。

    使用方式：
        store = SchedulerStore()
        tasks = store.list_tasks()
        task  = store.get_task("sched-001")
        store.upsert_task(task)          # 新增或按 task_id 覆盖更新
        store.delete_task("sched-001")

    并发说明：进程内 threading.Lock 串行写；跨进程依赖 os.replace 原子性。
    """

    # ------------------------------------------------------------------
    # 元信息
    # ------------------------------------------------------------------

    @staticmethod
    def data_file() -> Path:
        """返回底层 tasks.json 路径（用于测试或调试，不建议直接读写）。"""
        return _TASKS_FILE

    @staticmethod
    def data_dir() -> Path:
        """返回底层 data/scheduler/ 目录路径。"""
        return _DATA_DIR

    # ------------------------------------------------------------------
    # 读取接口
    # ------------------------------------------------------------------

    def list_tasks(self) -> List[ScheduledTask]:
        """
        加载全部调度任务。

        对每条 JSON 逐条反序列化，跳过失败条目并记录 warning，
        避免单条数据损坏导致整个调度器无法启动。
        """
        with _lock:
            raw = _load_raw()
        result: List[ScheduledTask] = []
        for idx, item in enumerate(raw.get("tasks", [])):
            try:
                result.append(ScheduledTask.model_validate(item))
            except ValidationError as exc:
                logger.warning(
                    "scheduler_store: 跳过第 %d 条无效任务 (task_id=%s): %s",
                    idx, item.get("task_id") if isinstance(item, dict) else None, exc,
                )
        return result

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """按 task_id 查找单个任务，找不到返回 None。"""
        for t in self.list_tasks():
            if t.task_id == task_id:
                return t
        return None

    def list_by_pipeline(self, pipeline: str) -> List[ScheduledTask]:
        """按 pipeline 筛选任务（便于按管线聚合展示）。"""
        return [t for t in self.list_tasks() if t.pipeline == pipeline]

    def list_by_slot(self, slot: str) -> List[ScheduledTask]:
        """按 slot（槽位）筛选任务（复用已有 slot 分区概念）。"""
        return [t for t in self.list_tasks() if t.slot == slot]

    # ------------------------------------------------------------------
    # 写入接口
    # ------------------------------------------------------------------

    def upsert_task(self, task: ScheduledTask) -> ScheduledTask:
        """
        插入或按 task_id 覆盖更新一个任务。

        - 若磁盘中已存在相同 task_id，则整条替换
        - 否则追加到列表尾部
        - 返回持久化后的对象（当前实现返回入参本身）
        """
        with _lock:
            raw = _load_raw()
            tasks: List[Dict[str, Any]] = list(raw.get("tasks", []))
            payload = task.model_dump()
            replaced = False
            for i, existing in enumerate(tasks):
                if isinstance(existing, dict) and existing.get("task_id") == task.task_id:
                    tasks[i] = payload
                    replaced = True
                    break
            if not replaced:
                tasks.append(payload)
            _atomic_write_json(_TASKS_FILE, {"tasks": tasks})
        logger.info(
            "scheduler_store.upsert_task: task_id=%s pipeline=%s schedule_type=%s (%s)",
            task.task_id, task.pipeline, task.schedule_type,
            "replaced" if replaced else "created",
        )
        # @AI_GENERATED: Phase 1 双写 — 写完 tasks.json 后同步 upsert scheduler_task
        _dual_write_task_to_db(task)
        # @AI_GENERATED: end
        return task

    def delete_task(self, task_id: str) -> bool:
        """
        按 task_id 删除任务。

        :return: 存在并删除成功返回 True，条目不存在返回 False。
        """
        with _lock:
            raw = _load_raw()
            tasks: List[Dict[str, Any]] = list(raw.get("tasks", []))
            new_tasks = [
                t for t in tasks
                if not (isinstance(t, dict) and t.get("task_id") == task_id)
            ]
            if len(new_tasks) == len(tasks):
                return False
            _atomic_write_json(_TASKS_FILE, {"tasks": new_tasks})
        logger.info("scheduler_store.delete_task: task_id=%s", task_id)
        return True

    def replace_all(self, tasks: List[ScheduledTask]) -> None:
        """
        一次性覆盖写入全部任务（用于批量导入 / 迁移场景）。
        """
        with _lock:
            _atomic_write_json(
                _TASKS_FILE,
                {"tasks": [t.model_dump() for t in tasks]},
            )
        logger.info("scheduler_store.replace_all: 写入 %d 条任务", len(tasks))
        # @AI_GENERATED: Phase 1 双写 — 批量导入时逐条同步到 DB
        for _t in tasks:
            _dual_write_task_to_db(_t)
        # @AI_GENERATED: end
# @AI_GENERATED: end


# @AI_GENERATED: Phase 1 双写辅助函数 — Cron 任务 → MySQL scheduler_task
def _dual_write_task_to_db(task: "ScheduledTask") -> None:
    """把 ScheduledTask 同步 upsert 到 MySQL scheduler_task 表。

    字段映射：
      - task_id / name / slot ← 同名
      - task_type             ← task.pipeline
      - cron_expression       ← task.cron_expr（rolling_daily 类型用 trigger_time 兜底转 cron）
      - enabled               ← task.status == 'running'
      - last_execution_time   ← 解析 ISO 字符串
      - last_result_json      ← task.last_result（如果有）
      - payload_json          ← schedule_type / trigger_time / max_window_days 等其余字段

    失败降级 warning，不阻塞 tasks.json 写入。
    """
    try:
        from services.db.repositories import get_deployment_repo, is_dual_write_enabled
        if not is_dual_write_enabled():
            return
        repo = get_deployment_repo()
        if repo is None:
            return

        payload = task.model_dump()

        # cron 表达式：cron 类型直接用 cron_expr；rolling_daily 用 trigger_time 转成 cron
        cron_expr = payload.get("cron_expr")
        if not cron_expr:
            trigger = payload.get("trigger_time") or "02:00"
            try:
                hh, mm = trigger.split(":")
                cron_expr = f"{int(mm)} {int(hh)} * * *"
            except Exception:
                cron_expr = "0 2 * * *"

        last_exec = payload.get("last_execution_time")
        last_exec_dt = None
        if last_exec:
            from datetime import datetime as _dt
            try:
                last_exec_dt = _dt.fromisoformat(str(last_exec).replace("Z", "+00:00"))
            except Exception:
                last_exec_dt = None

        last_result = payload.get("last_result")
        if not isinstance(last_result, dict):
            last_result = None

        extra_keys = ("schedule_type", "trigger_time", "max_window_days",
                      "next_scheduled_time", "retry_on_failure", "max_retries",
                      "created_at", "updated_at")
        payload_json = {k: payload.get(k) for k in extra_keys if payload.get(k) is not None}

        repo.upsert_task({
            "task_id": str(payload.get("task_id"))[:64],
            "name": str(payload.get("name") or payload.get("task_id"))[:128],
            "task_type": str(payload.get("pipeline") or "unknown")[:64],
            "slot": str(payload.get("slot") or payload.get("pipeline") or "load_forecast")[:64],
            "cron_expression": str(cron_expr)[:64],
            "enabled": str(payload.get("status") or "").lower() == "running",
            "payload_json": payload_json,
            "last_execution_time": last_exec_dt,
            "last_result_json": last_result,
        })
    except Exception as exc:
        logger.warning("scheduler dual-write task → DB failed (non-fatal): %s", exc)
# @AI_GENERATED: end
