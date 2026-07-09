"""
Scheduler Status API — 调度器状态与管线控制端点

Endpoints（管线级，向后兼容）:
  GET  /api/scheduler/status              — 返回所有管线的运行状态
  POST /api/scheduler/{pipeline}/start    — 启动指定管线（load_forecast | pv_fault）
  POST /api/scheduler/{pipeline}/stop     — 停止指定管线

Endpoints（任务级，新增，Task 6.2 / Requirements 2.1, 2.2, 2.4）:
  GET  /api/scheduler/tasks               — 列出所有调度任务（摘要模式）
  POST /api/scheduler/tasks               — 创建新调度任务
  GET  /api/scheduler/tasks/{task_id}     — 获取单个任务详情
  POST /api/scheduler/tasks/{task_id}/start — 启动任务（置为 running）
  POST /api/scheduler/tasks/{task_id}/stop  — 停止任务（置为 stopped）

依赖：
  - SchedulerEngine 单例：管线级端点使用；由 main.py 在启动时通过
    set_scheduler_engine() 注入。
  - SchedulerStore：任务级端点使用；持久化到 data/scheduler/tasks.json。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# @AI_GENERATED
from services.deployment.scheduler_models import ScheduledTask
from services.deployment.scheduler_store import SchedulerStore
# @AI_GENERATED: end
from services.scheduler.engine import SchedulerEngine

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

# ---------------------------------------------------------------------------
# Module-level singleton — injected by main.py at startup
# ---------------------------------------------------------------------------

_scheduler_engine: Optional[SchedulerEngine] = None


def set_scheduler_engine(engine: SchedulerEngine) -> None:
    """由 main.py startup_event 调用，注入 SchedulerEngine 实例。"""
    global _scheduler_engine
    _scheduler_engine = engine


def get_scheduler_engine() -> Optional[SchedulerEngine]:
    """返回当前注入的 SchedulerEngine 实例；未初始化时返回 None。"""
    return _scheduler_engine


def _get_engine() -> SchedulerEngine:
    if _scheduler_engine is None:
        raise HTTPException(status_code=503, detail="SchedulerEngine 尚未初始化")
    return _scheduler_engine


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

_VALID_PIPELINES = {"load_forecast", "pv_fault"}


def _fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    """将 datetime 格式化为 ISO 8601 字符串，None 保持 None。"""
    return dt.isoformat() if dt is not None else None


def _serialize_failure(failure: Any) -> Dict[str, Any]:
    return {
        "task_id": failure.task_id,
        "trigger_time": _fmt_dt(failure.trigger_time),
        "error_message": failure.error_message,
        "is_retry": failure.is_retry,
    }


def _serialize_task_status(ts: Any) -> Dict[str, Any]:
    return {
        "task_id": ts.task_id,
        "last_execution_time": _fmt_dt(ts.last_execution_time),
        "next_scheduled_time": _fmt_dt(ts.next_scheduled_time),
        "last_result": ts.last_result,
        "recent_failures": [_serialize_failure(f) for f in ts.recent_failures],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_scheduler_status() -> Dict[str, Any]:
    """返回所有管线的运行状态及任务历史。

    Response schema:
    {
      "pipelines": {
        "<pipeline_name>": {
          "running": bool,
          "tasks": [
            {
              "task_id": str,
              "last_execution_time": "ISO8601 | null",
              "next_scheduled_time": "ISO8601 | null",
              "last_result": "success | failed | skipped",
              "recent_failures": [...]
            }
          ]
        }
      }
    }
    """
    engine = _get_engine()
    all_status = engine.get_all_status()

    pipelines: Dict[str, Any] = {}
    for pipeline_name, status in all_status.items():
        pipelines[pipeline_name] = {
            "running": status.running,
            "tasks": [_serialize_task_status(t) for t in status.tasks],
        }

    return {"pipelines": pipelines}


# ---------------------------------------------------------------------------
# 任务级端点（Task 6.2 / Requirements 2.1, 2.2, 2.4）
#
# 注意：这些 /tasks* 路由必须声明在 /{pipeline}/... 之前，
# 否则 FastAPI 会把 "tasks" 当成 pipeline 参数匹配到 /{pipeline}/start。
# ---------------------------------------------------------------------------

# @AI_GENERATED
_scheduler_store: SchedulerStore = SchedulerStore()


class ScheduledTaskCreate(BaseModel):
    """
    ScheduledTaskCreate — POST /api/scheduler/tasks 请求体。

    与 ScheduledTask 相比省略了由后端自动生成的字段：
      - task_id     — 服务端生成的唯一 ID（形如 "sched-<hex12>"）
      - created_at  — 创建时间（服务端填充 ISO 8601）
      - updated_at  — 更新时间（服务端填充 ISO 8601）
    """

    name: str = Field(..., min_length=1, description="name — 任务名称（人类可读）")
    pipeline: str = Field(..., min_length=1, description="pipeline — 所属管线，如 'load_forecast'")
    schedule_type: str = Field(
        ...,
        description="schedule_type — 调度策略：rolling_daily | cron | interval",
    )
    cron_expr: Optional[str] = Field(
        default=None,
        description="cron_expr — cron 表达式，仅在 schedule_type='cron' 时使用",
    )
    trigger_time: str = Field(
        default="02:00",
        description="trigger_time — 每日触发时间 HH:MM，用于 rolling_daily 类型",
    )
    max_window_days: Optional[int] = Field(
        default=365,
        description="max_window_days — 滚动训练窗口最大天数；None 表示不限制",
    )
    slot: str = Field(
        default="default",
        description="slot — 关联的部署槽位（复用已有 slot 分区概念）",
    )
    status: str = Field(
        default="stopped",
        description="status — 初始运行状态；新建默认 stopped，需显式 /start 启动",
    )
    retry_on_failure: bool = Field(
        default=True,
        description="retry_on_failure — 失败后是否自动重试",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="max_retries — 最大重试次数，0 表示不重试",
    )


def _task_summary(t: ScheduledTask) -> Dict[str, Any]:
    """
    构造任务摘要字典（用于 GET /tasks 列表返回）。

    字段说明（英文 key — 中文含义）：
      - task_id             — 任务唯一 ID
      - name                — 任务名称
      - pipeline            — 所属管线
      - schedule_type       — 调度类型 rolling_daily | cron | interval
      - status              — 当前运行状态 running | stopped | failed
      - last_execution      — 上次执行结果（对应模型的 last_result 字段）
      - last_execution_time — 上次执行完成时间 ISO 8601
      - next_scheduled_time — 下次预计触发时间 ISO 8601
      - max_window_days     — 滚动训练窗口最大天数
    """
    return {
        "task_id": t.task_id,
        "name": t.name,
        "pipeline": t.pipeline,
        "schedule_type": t.schedule_type,
        "status": t.status,
        "last_execution": t.last_result,  # design: response uses 'last_execution'
        "last_execution_time": t.last_execution_time,
        "next_scheduled_time": t.next_scheduled_time,
        "max_window_days": t.max_window_days,
    }


def _load_task_or_404(task_id: str) -> ScheduledTask:
    """按 task_id 加载任务；找不到抛 404，含结构化 detail。"""
    task = _scheduler_store.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "task_not_found",
                "message": f"任务不存在：task_id={task_id}",
            },
        )
    return task


@router.get("/tasks")
async def list_scheduled_tasks() -> Dict[str, Any]:
    """
    列出所有调度任务（摘要模式）。

    用途：前端"定时调度"面板加载列表；每行仅展示核心状态字段，
    详细配置需再调用 GET /tasks/{task_id}。

    Response schema:
        { "tasks": [ _task_summary(...), ... ] }
    """
    tasks = _scheduler_store.list_tasks()
    return {"tasks": [_task_summary(t) for t in tasks]}


@router.post("/tasks")
async def create_scheduled_task(payload: ScheduledTaskCreate) -> Dict[str, Any]:
    """
    创建新调度任务。

    - task_id 由服务端生成（"sched-<12 位 hex>"）
    - created_at / updated_at 使用当前时间（ISO 8601）
    - 新建任务默认 status="stopped"，需显式调用 /start 后才会由引擎调度
    - 请求体字段校验交由 ScheduledTask 完成（schedule_type、trigger_time、
      max_window_days 等在模型层做 Literal / 范围校验）
    """
    now = datetime.now().isoformat()
    try:
        task = ScheduledTask(
            task_id=f"sched-{uuid.uuid4().hex[:12]}",
            name=payload.name,
            pipeline=payload.pipeline,
            schedule_type=payload.schedule_type,  # Literal 校验在 ScheduledTask
            cron_expr=payload.cron_expr,
            trigger_time=payload.trigger_time,
            max_window_days=payload.max_window_days,
            slot=payload.slot,
            status=payload.status,  # Literal 校验在 ScheduledTask
            retry_on_failure=payload.retry_on_failure,
            max_retries=payload.max_retries,
            created_at=now,
            updated_at=now,
        )
    except ValueError as exc:
        # Pydantic 校验错误 → 400
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_task_payload", "message": str(exc)},
        )
    _scheduler_store.upsert_task(task)
    return task.model_dump()


@router.get("/tasks/{task_id}")
async def get_scheduled_task(task_id: str) -> Dict[str, Any]:
    """获取单个调度任务的完整字段（用于详情弹窗 / 编辑表单预填）。"""
    task = _load_task_or_404(task_id)
    return task.model_dump()


# @AI_GENERATED: 阶段 3 — start/stop 真正调 SchedulerEngine + PATCH cron + trigger-now

class ScheduledTaskUpdate(BaseModel):
    """
    PATCH /api/scheduler/tasks/{task_id} 请求体 —— 局部更新调度任务配置。

    改动后立即热更新 SchedulerEngine：
      - cron_expr 改变 → 重新 register_task（新 trigger 立即生效）
      - trigger_time 改变 → 重新注册
      - max_window_days / retry 参数只写入 tasks.json，下次触发时生效

    字段（均可选，None 表示不修改）：
      - cron_expr        — 新 cron 表达式（仅 schedule_type=cron 时有效）
      - trigger_time     — 每日触发时间 HH:MM（schedule_type=rolling_daily 时用）
      - max_window_days  — 滚动训练窗口最大天数
      - retry_on_failure — 是否失败后自动重试
      - max_retries      — 最大重试次数
    """

    cron_expr: Optional[str] = Field(default=None, description="cron_expr — 新 cron 表达式")
    trigger_time: Optional[str] = Field(
        default=None, description="trigger_time — 每日触发时间 HH:MM"
    )
    max_window_days: Optional[int] = Field(
        default=None, ge=1, le=3650, description="max_window_days — 滚动窗口最大天数"
    )
    retry_on_failure: Optional[bool] = None
    max_retries: Optional[int] = Field(default=None, ge=0, le=20)


@router.patch("/tasks/{task_id}")
async def update_scheduled_task(task_id: str, payload: ScheduledTaskUpdate) -> Dict[str, Any]:
    """
    局部更新调度任务配置，并立即热更新 SchedulerEngine。

    cron_expr 或 trigger_time 改变时：
      - 如果任务当前 status="running"，立即从 SchedulerEngine 移除旧 job，
        注册新 job（新 cron trigger 立即生效）。
      - 如果任务 status="stopped"，只写入 tasks.json，下次 start 时用新配置。
    """
    task = _load_task_or_404(task_id)

    update_dict: Dict[str, Any] = {"updated_at": datetime.now().isoformat()}
    need_re_register = False

    if payload.cron_expr is not None:
        update_dict["cron_expr"] = payload.cron_expr
        need_re_register = True
    if payload.trigger_time is not None:
        update_dict["trigger_time"] = payload.trigger_time
        need_re_register = True
    if payload.max_window_days is not None:
        update_dict["max_window_days"] = payload.max_window_days
    if payload.retry_on_failure is not None:
        update_dict["retry_on_failure"] = payload.retry_on_failure
    if payload.max_retries is not None:
        update_dict["max_retries"] = payload.max_retries

    updated = task.model_copy(update=update_dict)
    _scheduler_store.upsert_task(updated)

    # 热更新 SchedulerEngine（如果任务在运行且 cron/trigger_time 有变化）
    if need_re_register and updated.status == "running":
        engine = _scheduler_engine
        if engine is not None:
            _re_register_task_in_engine(engine, updated)
            next_time = _get_next_run_from_engine(engine, task_id)
            if next_time:
                refreshed = updated.model_copy(update={"next_scheduled_time": next_time})
                _scheduler_store.upsert_task(refreshed)
                updated = refreshed

    return updated.model_dump()


@router.post("/tasks/{task_id}/trigger-now")
async def trigger_task_now(task_id: str) -> Dict[str, Any]:
    """
    立即触发一次指定任务（不等待下次 cron 时间，不改变任务 status）。

    注意：本端点依赖后端 SchedulerEngine 在启动时已注册过该 task_id 的 func。
    如果后端刚重启且任务还没注册，返回 409 说明需要先调 /start。
    """
    engine = _scheduler_engine
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "engine_not_ready",
                "message": "SchedulerEngine 尚未初始化，请稍等后端启动完成或检查服务日志",
            },
        )

    meta = engine._tasks.get(task_id)
    if meta is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_not_registered",
                "message": (
                    f"任务 '{task_id}' 未在 SchedulerEngine 中注册。"
                    "可能原因：后端启动时 DB 初始化失败导致 SchedulerEngine 未完成注册。"
                    "请重启后端服务后再试。"
                ),
            },
        )

    import threading
    import logging as _logging

    _log = _logging.getLogger(__name__)

    def _run_once():
        try:
            engine._run_with_protection(meta, is_retry=False)
            # 执行完后同步更新 tasks.json 的 last_execution_time 和 last_result
            try:
                task = _scheduler_store.get_task(task_id)
                if task is not None:
                    update_fields = {
                        "last_execution_time": meta.last_execution_time.isoformat() if meta.last_execution_time else datetime.now().isoformat(),
                        "last_result": meta.last_result or "success",
                        "updated_at": datetime.now().isoformat(),
                    }
                    updated = task.model_copy(update=update_fields)
                    _scheduler_store.upsert_task(updated)
            except Exception as _store_exc:
                _log.warning("trigger_task_now: 写回 tasks.json 失败: %s", _store_exc)
        except Exception as exc:
            _log.warning("trigger_task_now: task_id=%s 触发失败: %s", task_id, exc)
            # 写入失败状态
            try:
                task = _scheduler_store.get_task(task_id)
                if task is not None:
                    updated = task.model_copy(update={
                        "last_execution_time": datetime.now().isoformat(),
                        "last_result": "failed",
                        "updated_at": datetime.now().isoformat(),
                    })
                    _scheduler_store.upsert_task(updated)
            except Exception:
                pass

    t = threading.Thread(target=_run_once, daemon=True)
    t.start()

    return {
        "task_id": task_id,
        "status": "triggered",
        "message": "任务已在后台触发，执行结果将写入 last_result（刷新后可见）",
    }


@router.post("/tasks/{task_id}/start")
async def start_scheduled_task(task_id: str) -> Dict[str, Any]:
    """
    启动指定任务：
      1. status → "running"，写入 tasks.json
      2. 确保 SchedulerEngine 中已注册并运行该任务的 cron job

    若任务在 SchedulerEngine 中不存在（如首次启动或引擎重启后），
    会尝试重新注册（register_task）。
    """
    task = _load_task_or_404(task_id)
    updated = task.model_copy(update={
        "status": "running",
        "updated_at": datetime.now().isoformat(),
    })
    _scheduler_store.upsert_task(updated)

    engine = _scheduler_engine
    if engine is not None:
        _re_register_task_in_engine(engine, updated)

    return {"task_id": task_id, "status": "running"}


@router.post("/tasks/{task_id}/stop")
async def stop_scheduled_task(task_id: str) -> Dict[str, Any]:
    """
    停止指定任务：
      1. status → "stopped"，写入 tasks.json
      2. 从 SchedulerEngine 的对应 pipeline scheduler 中移除该任务的 cron job

    正在执行的批次仍会跑完并写入 last_result，不会强制中止。
    """
    task = _load_task_or_404(task_id)
    updated = task.model_copy(update={
        "status": "stopped",
        "updated_at": datetime.now().isoformat(),
    })
    _scheduler_store.upsert_task(updated)

    engine = _scheduler_engine
    if engine is not None:
        try:
            scheduler = engine._schedulers.get(task.pipeline)
            if scheduler is not None:
                try:
                    scheduler.remove_job(task_id)
                except Exception:
                    pass  # job 可能不存在，忽略
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning(
                "stop_scheduled_task: 从 engine 移除 job 失败（非致命）: %s", exc
            )

    return {"task_id": task_id, "status": "stopped"}


def _re_register_task_in_engine(engine, task) -> None:
    """
    将 tasks.json 里的 task 记录重新注册到 SchedulerEngine（热更新）。

    只处理 schedule_type="cron" 的任务（有确定的 cron_expr）；
    rolling_daily 类型的任务由 SchedulerEngine 内部的 run_due_tasks 驱动，
    只需保证 status="running" 即可，不需要在 APScheduler 层注册 cron job。
    """
    if not task.cron_expr:
        return  # rolling_daily 不注册到 APScheduler

    import logging as _log
    log = _log.getLogger(__name__)

    # 确保 pipeline scheduler 存在
    from apscheduler.schedulers.background import BackgroundScheduler
    if task.pipeline not in engine._schedulers:
        sched = BackgroundScheduler()
        engine._schedulers[task.pipeline] = sched

    scheduler = engine._schedulers[task.pipeline]
    if not scheduler.running:
        scheduler.start()
        engine._pipeline_running[task.pipeline] = True

    # 查找内部 _TaskMeta（若存在则复用 func）
    meta = engine._tasks.get(task.task_id)
    if meta is None:
        log.warning(
            "_re_register_task_in_engine: task_id=%s 在 engine._tasks 中不存在，"
            "无法自动注册（需要重启后端使任务重新绑定 func）",
            task.task_id,
        )
        return

    meta.cron_expr = task.cron_expr
    engine._add_job_to_scheduler(scheduler, meta)
    log.info(
        "_re_register_task_in_engine: task_id=%s cron=%s 已热更新",
        task.task_id, task.cron_expr,
    )


def _get_next_run_from_engine(engine, task_id: str) -> Optional[str]:
    """从 SchedulerEngine 读取下次触发时间（ISO8601 字符串）。"""
    try:
        meta = engine._tasks.get(task_id)
        if meta is None:
            return None
        scheduler = engine._schedulers.get(meta.pipeline)
        next_dt = engine._get_next_run_time(scheduler, task_id)
        return next_dt.isoformat() if next_dt else None
    except Exception:
        return None
# @AI_GENERATED: end


@router.post("/{pipeline}/start")
async def start_pipeline(pipeline: str) -> Dict[str, str]:
    """启动指定管线的调度器。

    Path params:
      pipeline — 管线名称，支持 load_forecast | pv_fault
    """
    if pipeline not in _VALID_PIPELINES:
        raise HTTPException(
            status_code=400,
            detail=f"未知管线 '{pipeline}'，支持: {sorted(_VALID_PIPELINES)}",
        )
    engine = _get_engine()
    engine.start_pipeline(pipeline)
    return {"status": "started", "pipeline": pipeline}


@router.post("/{pipeline}/stop")
async def stop_pipeline(pipeline: str) -> Dict[str, str]:
    """停止指定管线的调度器。

    Path params:
      pipeline — 管线名称，支持 load_forecast | pv_fault
    """
    if pipeline not in _VALID_PIPELINES:
        raise HTTPException(
            status_code=400,
            detail=f"未知管线 '{pipeline}'，支持: {sorted(_VALID_PIPELINES)}",
        )
    engine = _get_engine()
    engine.stop_pipeline(pipeline)
    return {"status": "stopped", "pipeline": pipeline}
