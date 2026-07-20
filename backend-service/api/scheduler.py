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
_load_forecast_repository: Optional[Any] = None
# @AI_GENERATED: pv_fault mock feeder 注入
_pv_mock_feeder: Optional[Any] = None


def set_pv_mock_feeder(feeder: Any) -> None:
    """由 main.py 注入 PvFaultMockFeeder，供手动喂数据端点使用。"""
    global _pv_mock_feeder
    _pv_mock_feeder = feeder
# @AI_GENERATED: end


def set_scheduler_engine(engine: SchedulerEngine) -> None:
    """由 main.py startup_event 调用，注入 SchedulerEngine 实例。"""
    global _scheduler_engine
    _scheduler_engine = engine


# @AI_GENERATED: platform StationData evidence dependency

def set_load_forecast_repository(repository: Any) -> None:
    """由 main.py 注入负荷预测仓储，供只读调度详情查询真实落库数据。"""
    global _load_forecast_repository
    _load_forecast_repository = repository
# @AI_GENERATED: end


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
      - cron_expr           — Cron 表达式；非 cron 调度时为 null
      - slot                — 关联部署槽位；用于确认任务实际读写的模型分区
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
        "cron_expr": t.cron_expr,
        "slot": t.slot,
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


# @AI_GENERATED: manual mock-feed control contract
_MOCK_DATA_FEED_TASK_ID = "mock_data_feed"
_DATA_PULL_TASK_ID = "lf_data_pull"


class ManualMockFeedRequest(BaseModel):
    """ManualMockFeedRequest — 手动模拟投喂请求。"""

    advance: bool = Field(
        default=False,
        description="advance — 是否已由用户确认推进到下一模拟业务日",
    )


def _get_mock_data_feeder() -> Any:
    """Resolve the startup-registered mock feeder without creating a second source."""
    engine = _get_engine()
    meta = engine._tasks.get(_MOCK_DATA_FEED_TASK_ID)
    feeder = getattr(meta.func, "__self__", None) if meta is not None else None
    if feeder is None or not hasattr(feeder, "get_manual_feed_preview"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "mock_feed_not_ready",
                "message": "模拟数据 feeder 尚未注册完成，请等待后端启动完成。",
            },
        )
    return feeder


def _record_manual_mock_feed_receipt(task_id: str) -> None:
    """Synchronize a completed manual feed to the existing scheduler task receipt."""
    task = _scheduler_store.get_task(task_id)
    if task is None:
        return
    completed_at = datetime.now().isoformat()
    _scheduler_store.upsert_task(
        task.model_copy(
            update={
                "last_execution_time": completed_at,
                "last_result": "success",
                "updated_at": completed_at,
            }
        )
    )


# @AI_GENERATED: platform StationData evidence helpers
def _get_load_forecast_repository() -> Any:
    if _load_forecast_repository is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "load_forecast_repository_not_ready",
                "message": "负荷预测数据仓储尚未就绪，请等待后端启动完成。",
            },
        )
    return _load_forecast_repository


def _serialize_data_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    def serialize_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        return {
            **row,
            "timestamp_utc": row["timestamp_utc"].isoformat(),
            "ingested_at": row["ingested_at"].isoformat(),
        }

    return {
        **evidence,
        "time_start": evidence["time_start"].isoformat() if evidence["time_start"] else None,
        "time_end": evidence["time_end"].isoformat() if evidence["time_end"] else None,
        "latest": serialize_row(evidence["latest"]),
        "samples": [serialize_row(row) for row in evidence["samples"]],
    }
# @AI_GENERATED: end
# @AI_GENERATED: end


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


# @AI_GENERATED: manual mock-feed control endpoints
@router.get("/tasks/mock_data_feed/feed-status")
async def get_mock_data_feed_status() -> Dict[str, Any]:
    """Read the current mock business-day gate without writing any source data."""
    preview = _get_mock_data_feeder().get_manual_feed_preview()
    return {"task_id": _MOCK_DATA_FEED_TASK_ID, "preview": preview.as_dict()}


@router.post("/tasks/mock_data_feed/manual-feed")
async def manual_mock_data_feed(payload: ManualMockFeedRequest) -> Dict[str, Any]:
    """Feed a new mock business day only after explicit user confirmation."""
    feeder = _get_mock_data_feeder()
    preview, result = feeder.feed_manually(advance=payload.advance)
    if result is None:
        if preview.exhausted:
            return {
                "task_id": _MOCK_DATA_FEED_TASK_ID,
                "status": "exhausted",
                "message": "CSV 模拟数据已全部投喂，不会写入新数据。",
                "preview": preview.as_dict(),
                "feed_result": None,
            }
        return {
            "task_id": _MOCK_DATA_FEED_TASK_ID,
            "status": "confirmation_required",
            "message": "当前模拟业务日已投喂；请确认后才会推进到下一业务日。",
            "preview": preview.as_dict(),
            "feed_result": None,
        }

    _record_manual_mock_feed_receipt(_MOCK_DATA_FEED_TASK_ID)
    return {
        "task_id": _MOCK_DATA_FEED_TASK_ID,
        "status": "fed",
        "message": "模拟业务日已投喂到公司数据源。",
        "preview": preview.as_dict(),
        "feed_result": result.as_dict(),
    }
# @AI_GENERATED: end


# @AI_GENERATED: scheduler platform-data evidence endpoint
@router.get("/tasks/{task_id}/data-evidence")
async def get_task_data_evidence(
    task_id: str,
    sample_limit: int = 48,
) -> Dict[str, Any]:
    """Return the persisted platform data evidence for lf_data_pull without running it."""
    if task_id != _DATA_PULL_TASK_ID:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "data_evidence_not_supported",
                "message": f"任务 '{task_id}' 不支持数据拉取证据查询。",
            },
        )
    task = _load_task_or_404(task_id)
    evidence = _get_load_forecast_repository().get_station_data_evidence(
        slot=task.slot,
        sample_limit=max(1, min(sample_limit, 200)),
    )
    return {
        "task_id": task_id,
        "slot": task.slot,
        "evidence": _serialize_data_evidence(evidence),
    }
# @AI_GENERATED: end


@router.post("/tasks/{task_id}/trigger-now")
async def trigger_task_now(task_id: str) -> Dict[str, Any]:
    """
    立即触发一次指定任务（不等待下次 cron 时间，不改变任务 status）。

    注意：本端点依赖后端 SchedulerEngine 在启动时已注册过该 task_id 的 func。
    如果后端刚重启且任务还没注册，返回 409 说明需要先调 /start。
    """
    if task_id == _MOCK_DATA_FEED_TASK_ID:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "manual_mock_feed_confirmation_required",
                "message": "模拟喂数据必须使用专用 manual-feed 接口完成业务日确认，不能通过通用立即触发推进。",
            },
        )

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
    # @AI_GENERATED: 控制面重新启动只恢复 cron，不补跑历史生产任务；补跑需使用显式 trigger-now。
    engine.start_pipeline(pipeline, catchup=False)
    # @AI_GENERATED: end
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


# @AI_GENERATED: pv_fault mock feed control endpoints
@router.get("/tasks/pv_mock_data_feed/feed-status")
async def get_pv_mock_feed_status() -> Dict[str, Any]:
    """返回光伏 mock 喂数据的当前业务日状态（只读，不写入数据）。

    返回：
      current_business_date — 上次已喂完的自然日
      next_business_date    — 下一个待喂的自然日
      requires_advance_confirmation — 是否需要人工确认才能推进
      exhausted             — parquet 数据是否已喂完
    """
    if _pv_mock_feeder is None:
        raise HTTPException(status_code=503, detail="PV mock feeder 尚未注入（需要重启后端）")
    preview = _pv_mock_feeder.get_manual_feed_preview()
    return {"task_id": "pv_mock_data_feed", "preview": preview.as_dict()}


class PvManualMockFeedRequest(BaseModel):
    """pv_fault 手动喂数据请求体。"""
    advance: bool = Field(
        default=False,
        description="advance — true 表示用户已确认推进到下一个光伏业务日",
    )


@router.post("/tasks/pv_mock_data_feed/manual-feed")
async def manual_pv_mock_data_feed(payload: PvManualMockFeedRequest) -> Dict[str, Any]:
    """光伏 mock 喂数据：首次或确认推进后才写入，否则返回"需要确认"。

    跨日推进需要 advance=True（人工确认当日已处理完）。
    写入时 label=NULL，模拟真实场景下数据库新收到的原始光伏观测。
    """
    if _pv_mock_feeder is None:
        raise HTTPException(status_code=503, detail="PV mock feeder 尚未注入（需要重启后端）")

    preview, result = _pv_mock_feeder.feed_manually(advance=payload.advance)

    if result is None:
        if preview.exhausted:
            return {
                "task_id": "pv_mock_data_feed",
                "status": "exhausted",
                "message": "Parquet 模拟数据已全部投喂，不会写入新数据。",
                "preview": preview.as_dict(),
                "feed_result": None,
            }
        return {
            "task_id": "pv_mock_data_feed",
            "status": "confirmation_required",
            "message": f"当前业务日 {preview.current_business_date} 已投喂；"
                       f"下一日 {preview.next_business_date} 需要确认后才能推进。",
            "preview": preview.as_dict(),
            "feed_result": None,
        }

    # 同步写入 tasks.json（让调度面板显示最新执行时间）
    try:
        task = _scheduler_store.get_task("pv_mock_data_feed")
        if task is not None:
            now_str = datetime.now().isoformat()
            _scheduler_store.upsert_task(task.model_copy(update={
                "last_execution_time": now_str,
                "last_result": "success",
                "updated_at": now_str,
            }))
    except Exception:
        pass

    return {
        "task_id": "pv_mock_data_feed",
        "status": "fed",
        "message": f"光伏业务日 {result.business_date} 已成功写入 training_samples。",
        "preview": preview.as_dict(),
        "feed_result": result.as_dict(),
    }
# @AI_GENERATED: end


# @AI_GENERATED: pv_mock_data_feed 已写入数据预览端点
@router.get("/tasks/pv_mock_data_feed/data-evidence")
async def get_pv_mock_feed_data_evidence(
    sample_limit: int = 50,
) -> dict:
    """返回 pv_mock_data_feed 最近写入 training_samples 的数据样本，供前端核对。

    从 training_samples 表读取：
      - total_rows       — 总行数
      - latest_time      — 最新观测时间
      - earliest_time    — 最早观测时间
      - device_count     — 设备数
      - date_count       — 自然日数
      - samples          — 最新 sample_limit 行（按 time desc）
    """
    from services.db.models.pv_fault import TrainingSample
    from sqlalchemy import select, func

    if _pv_mock_feeder is None:
        raise HTTPException(status_code=503, detail="PV mock feeder 尚未注入")

    # 复用 DBAdapter，但 feeder 没直接暴露 adapter；通过 pv_repo 获取（如已注入）
    from api.iterative_labeling import _pv_repo_instance as pv_repo
    if pv_repo is None:
        raise HTTPException(status_code=503, detail="PVFaultRepository 尚未注入，无法查询数据证据")

    adapter = pv_repo._adapter
    sample_limit = max(1, min(int(sample_limit), 200))

    try:
        with adapter.get_sync_session() as session:
            total = session.execute(select(func.count(TrainingSample.id))).scalar() or 0
            earliest = session.execute(select(func.min(TrainingSample.time))).scalar()
            latest_time = session.execute(select(func.max(TrainingSample.time))).scalar()
            device_count = session.execute(
                select(func.count(func.distinct(TrainingSample.device_id)))
            ).scalar() or 0

            rows = session.execute(
                select(
                    TrainingSample.id,
                    TrainingSample.time,
                    TrainingSample.site_id,
                    TrainingSample.device_id,
                    TrainingSample.branch_id,
                    TrainingSample.value,
                    TrainingSample.i_cal,
                    TrainingSample.label,
                )
                .order_by(TrainingSample.time.desc(), TrainingSample.id.desc())
                .limit(sample_limit)
            ).mappings().all()

        samples = []
        for row in rows:
            samples.append({
                "id": row["id"],
                "time": row["time"].isoformat() if row["time"] else None,
                "site_id": row["site_id"],
                "device_id": row["device_id"],
                "branch_id": str(row["branch_id"]),
                "value": float(row["value"]) if row["value"] is not None else None,
                "i_cal": float(row["i_cal"]) if row["i_cal"] is not None else None,
                "label": int(row["label"]) if row["label"] is not None else None,
            })

        # 计算已覆盖的自然日数
        if earliest and latest_time:
            from datetime import timedelta
            date_count = (latest_time.date() - earliest.date()).days + 1
        else:
            date_count = 0

        # 同时返回 feeder 的最新喂数状态
        preview = _pv_mock_feeder.get_manual_feed_preview()

        return {
            "task_id": "pv_mock_data_feed",
            "evidence": {
                "total_rows": int(total),
                "device_count": int(device_count),
                "date_count": date_count,
                "earliest_time": earliest.isoformat() if earliest else None,
                "latest_time": latest_time.isoformat() if latest_time else None,
                "samples": samples,
            },
            "feed_preview": preview.as_dict(),
        }
    except Exception as exc:
        logger.exception("pv_mock_data_feed data-evidence 查询失败")
        raise HTTPException(status_code=500, detail=str(exc))
# @AI_GENERATED: end
