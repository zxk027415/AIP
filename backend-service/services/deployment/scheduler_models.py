# @AI_GENERATED
"""
services/deployment/scheduler_models.py — 定时调度任务数据模型

职责：
  - 定义 ScheduledTask（定时调度任务配置）Pydantic 模型
  - 支持三种调度类型：
      * rolling_daily — 每日按 trigger_time（HH:MM）滚动训练
      * cron          — 由 cron_expr 表达式驱动
      * interval      — 周期性触发（周期时长由调度引擎结合任务上下文解析）
  - max_window_days（最大窗口天数）— 控制滚动训练窗口的最大长度，
    超出该长度的历史数据自动从窗口最早端截断；None 表示不限制
  - 与 slot（槽位，复用系统已有分区概念）字段对齐，方便按槽位分区管理

字段一览（更详细的中文说明见每个 Field 的 description）：
  task_id、name、pipeline、schedule_type、cron_expr、trigger_time、
  max_window_days、slot、status、last_execution_time、last_result、
  next_scheduled_time、retry_on_failure、max_retries、created_at、updated_at

关联接口：
  GET  /api/scheduler/tasks               — 列出所有调度任务（摘要）
  POST /api/scheduler/tasks               — 创建新调度任务
  GET  /api/scheduler/tasks/{task_id}     — 获取单个任务详情
  POST /api/scheduler/tasks/{task_id}/start
  POST /api/scheduler/tasks/{task_id}/stop
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 合法的调度类型集合
ScheduleType = Literal["rolling_daily", "cron", "interval"]

# 合法的任务运行状态集合
TaskStatus = Literal["running", "stopped", "failed"]

# 合法的上次执行结果集合
LastResult = Literal["success", "failed", "skipped"]


class ScheduledTask(BaseModel):
    """
    ScheduledTask — 定时调度任务配置。

    持久化位置：data/scheduler/tasks.json（相对于 backend-service/ 目录）。
    一条记录对应一个 pipeline 的一份调度定义；同一 pipeline 可有多条任务。

    滚动训练窗口语义（rolling_daily）：
      - 每日 trigger_time 触发后，训练窗口自动纳入截至 T-1 日的所有可用数据
      - Gap-One-Day：训练数据严格 ≤ T-1，绝不使用 T 日当天数据
      - max_window_days 生效时，若历史数据超过该天数则从最早端截断
      - 预测目标为 T+1 日，待 T+1 实际值到达后计算精度（MAPE、RMSE 等）
    """

    # Pydantic v2 配置：字符串自动去首尾空白，未知字段忽略以便向后兼容
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    # ------------------------------------------------------------------
    # 必填字段
    # ------------------------------------------------------------------

    task_id: str = Field(
        ...,
        min_length=1,
        description="task_id — 任务唯一 ID，前端与 API 用它定位一条任务",
    )
    name: str = Field(
        ...,
        min_length=1,
        description="name — 任务名称（人类可读），如“负荷预测每日滚动训练”",
    )
    pipeline: str = Field(
        ...,
        min_length=1,
        description="pipeline — 所属管线，如 'load_forecast'、'pv_fault'",
    )
    schedule_type: ScheduleType = Field(
        ...,
        description="schedule_type — 调度策略：rolling_daily | cron | interval",
    )
    created_at: str = Field(
        ...,
        description="created_at — 任务创建时间 ISO 8601",
    )
    updated_at: str = Field(
        ...,
        description="updated_at — 任务最后更新时间 ISO 8601",
    )

    # ------------------------------------------------------------------
    # 可选字段（有默认值）
    # ------------------------------------------------------------------

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
        description=(
            "max_window_days — 滚动训练窗口最大长度（天数）；"
            "超出则从最早端截断；None 表示不限制"
        ),
    )
    slot: str = Field(
        default="default",
        description="slot — 关联的部署槽位（复用已有 slot 分区概念）",
    )
    status: TaskStatus = Field(
        default="stopped",
        description="status — 运行状态 running | stopped | failed",
    )
    last_execution_time: Optional[str] = Field(
        default=None,
        description="last_execution_time — 上次执行完成时间 ISO 8601",
    )
    last_result: Optional[LastResult] = Field(
        default=None,
        description="last_result — 上次执行结果 success | failed | skipped",
    )
    next_scheduled_time: Optional[str] = Field(
        default=None,
        description="next_scheduled_time — 下次预计触发时间 ISO 8601",
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

    # ------------------------------------------------------------------
    # 字段级校验
    # ------------------------------------------------------------------

    @field_validator("trigger_time")
    @classmethod
    def _validate_trigger_time(cls, v: str) -> str:
        """校验 HH:MM 格式并规范化为两位数（如 '9:5' → '09:05'）。"""
        if v is None or v == "":
            return "02:00"
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("trigger_time 必须是 HH:MM 格式")
        try:
            hh = int(parts[0])
            mm = int(parts[1])
        except ValueError as exc:
            raise ValueError("trigger_time 必须是 HH:MM 格式") from exc
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError("trigger_time 的小时应在 0..23、分钟应在 0..59")
        return f"{hh:02d}:{mm:02d}"

    @field_validator("max_window_days")
    @classmethod
    def _validate_max_window_days(cls, v: Optional[int]) -> Optional[int]:
        """max_window_days 允许为 None（不限制）或 >= 1 的整数。"""
        if v is None:
            return None
        if v < 1:
            raise ValueError("max_window_days 必须 >= 1（或为 None 表示不限制）")
        return v
# @AI_GENERATED: end
