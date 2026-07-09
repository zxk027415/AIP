# @AI_GENERATED
"""
services/deployment/scheduler_engine.py — 部署调度引擎主循环（Rolling Training + T+1 预测编排）

职责（Responsibilities）：
  - 编排每日滚动训练调度：数据拉取 → 滚动窗口选取 → 模型训练 → 预测 T+1 → 精度评估
  - 实现失败重试状态机：记录失败原因，下一周期重试，超过 `max_retries` 后标记 `status="failed"`
  - 新数据到达后无需人工干预 —— 下一次 `trigger_task` 调用会通过 `pipeline.fetch_available_dates`
    读取到最新可用日期，再由 `compute_training_window` 自动纳入训练窗口
  - 通过依赖注入的 `SchedulerPipeline` 协议解耦训练/预测执行，保持引擎纯编排、可单元测试
  - 通过依赖注入的 `now` callable 支持测试冻结时间；不直接调用 `datetime.now()`

不做的事（Non-goals）：
  - 不实际训练 / 预测 / 拉取数据 —— 全部委托给 `SchedulerPipeline` 回调
  - 不落地模型工件 —— 由 `pipeline.train` 自己决定；引擎只透传 artifacts 给 predict
  - 不实现 `cron` / `interval` 调度类型的自动触发 —— 遇到时记录 warning 并跳过，
    但仍允许上层通过 `trigger_task()` 手动执行
  - 不跨进程同步 —— 单进程内使用 `threading.Lock` 保证 `_retry_counts` 一致性

对应需求 / 设计：
  - Requirements 4.1 – 4.6（algorithm-deployment-refactor/requirements.md）
  - design.md 中 SchedulerEngine（调度引擎）组件

关联模块：
  - services/deployment/rolling_window.py — 窗口计算（含 Gap-One-Day 约束）
  - services/deployment/metrics.py         — MAPE / RMSE 精度指标
  - services/deployment/scheduler_models.py — ScheduledTask Pydantic 模型
  - services/deployment/scheduler_store.py  — 任务持久化（JSON）

重试状态机（Retry state machine，对应 requirement 4.6）：
  以 `max_retries=3` 为例：
    Before attempt 1: retry_count=0
    Attempt 1 fails → 0 < 3 → retry_count := 1，status 仍为 'running'
    Attempt 2 fails → 1 < 3 → retry_count := 2，status 仍为 'running'
    Attempt 3 fails → 2 < 3 → retry_count := 3，status 仍为 'running'
    Attempt 4 fails → 3 < 3 为 False → status := 'failed'，retry_count 清零
  成功执行时 retry_count 立即清零（不论此前是否失败）。
  `retry_on_failure=False` 时首次失败即直接 status='failed'（不进入计数）。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

from services.deployment.metrics import compute_mape, compute_rmse
from services.deployment.rolling_window import compute_training_window
from services.deployment.scheduler_models import ScheduledTask
from services.deployment.scheduler_store import SchedulerStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 依赖注入协议 —— 训练 / 预测 / 数据读写的抽象接口
# ---------------------------------------------------------------------------

@runtime_checkable
class SchedulerPipeline(Protocol):
    """SchedulerPipeline — 调度引擎依赖的 pipeline-agnostic 回调协议

    调度引擎自己不知道模型如何训练、数据从哪来。具体行为由实现方注入，
    例如 load_forecast、pv_fault 各自实现一个 pipeline adapter。

    所有方法都接受 `pipeline`（管线名，例如 "load_forecast"）和 `slot`（槽位，
    例如 "default"）作为路由参数，实现方可据此选择数据源、模型家族等。
    """

    def fetch_available_dates(self, pipeline: str, slot: str) -> Sequence[date]:
        """返回当前可用于训练的历史数据日期集合（允许无序、重复；内部会去重）。"""
        ...

    def train(
        self,
        pipeline: str,
        slot: str,
        training_dates: Sequence[date],
    ) -> Dict[str, Any]:
        """在给定日期集合上训练模型，返回工件（如 {"model_ref": "..."}）。

        实现层若训练失败，应抛异常 —— 引擎会捕获并走重试逻辑。
        """
        ...

    def predict(
        self,
        pipeline: str,
        slot: str,
        model_artifacts: Dict[str, Any],
        predict_date: date,
    ) -> float:
        """对 `predict_date` 做预测，返回预测值。失败抛异常。"""
        ...

    def fetch_actual(
        self,
        pipeline: str,
        slot: str,
        predict_date: date,
    ) -> Optional[Sequence[float]]:
        """返回 `predict_date` 的实际值序列；`None` 表示数据未到达（跳过精度评估）。"""
        ...

    def get_prediction_series(
        self,
        pipeline: str,
        slot: str,
        predict_date: date,
    ) -> Optional[Sequence[float]]:
        """返回与 `fetch_actual` 对应的历史预测值序列；`None` 表示未录入历史预测（跳过精度）。

        通常来说，`predict_date` 会等于本次触发日期 T：
        今天要评估的是 “昨天预测的今天” 的精度 —— 昨天在 T-1 触发时预测了 (T-1)+1 = T。
        """
        ...


# ---------------------------------------------------------------------------
# 结果类型
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TriggerResult:
    """TriggerResult — 单次触发的运行结果（编排层视角，不可变）

    字段说明（Fields）：
      task_id       — 调度任务 ID
      trigger_date  — 本次触发的日期 T（`date`，不含时分秒）
      result        — 结果分类：'success' | 'failed' | 'skipped'
      reason        — 补充说明（失败原因或跳过原因）；success 时为 None
      window_days   — 本次实际使用的滚动训练窗口天数；跳过 / 早期失败时为 0
      mape          — 精度评估 MAPE；None 表示本次未做精度评估
      rmse          — 精度评估 RMSE；None 表示本次未做精度评估
    """

    task_id: str
    trigger_date: date
    result: str
    reason: Optional[str] = None
    window_days: int = 0
    mape: Optional[float] = None
    rmse: Optional[float] = None


# ---------------------------------------------------------------------------
# 调度引擎
# ---------------------------------------------------------------------------

class SchedulerEngine:
    """SchedulerEngine — 单进程内的定时调度编排器

    使用方式（Usage）：

        store = SchedulerStore()
        engine = SchedulerEngine(store=store, pipeline=my_pipeline_adapter)

        # 1) 手动触发一次（测试或运维手动补跑）
        result = engine.trigger_task("sched-001", trigger_date=date(2026, 6, 8))

        # 2) 由外部定时器周期性调用（如 APScheduler、简单 while+sleep）
        results = engine.run_due_tasks()

    并发说明（Concurrency）：
      - 引擎内部使用 `threading.Lock` 保护重试计数字典的一致性
      - `SchedulerStore` 自身也是线程安全的（内部原子写）
      - 不推荐跨进程共享同一份 tasks.json（会有 last-write-wins 语义）

    时间注入（Time injection）：
      - `now` callable 默认为 `datetime.now`；测试时可注入固定时间
      - `trigger_task` 的 `trigger_date` 参数用于测试；不传时使用 `now().date()`
    """

    # 目前只有 rolling_daily 支持自动触发；其他类型允许手动 trigger_task 但不参与 run_due_tasks
    _SUPPORTED_AUTO_SCHEDULE_TYPE = "rolling_daily"

    # 默认触发时间（trigger_time 无法解析时兜底）
    _DEFAULT_TRIGGER_HOUR = 2
    _DEFAULT_TRIGGER_MINUTE = 0

    def __init__(
        self,
        store: SchedulerStore,
        pipeline: SchedulerPipeline,
        *,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.store = store
        self.pipeline = pipeline
        # 显式收敛所有时间读取到这里；测试可注入固定时间。
        self._now: Callable[[], datetime] = now or datetime.now
        # 每个 task_id 累积的重试次数；成功后清零，永久失败后清零并停留在 status=failed。
        # 仅内存，进程重启后归零 —— 与 requirement 4.6 描述的“下一周期重试”语义一致。
        self._retry_counts: Dict[str, int] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 对外接口 1：手动 / 单次触发
    # ------------------------------------------------------------------

    def trigger_task(
        self,
        task_id: str,
        trigger_date: Optional[date] = None,
    ) -> TriggerResult:
        """对指定任务执行一次触发（数据 → 训练 → 预测 → 精度评估）

        参数：
          task_id      — 目标任务 ID（对应 ScheduledTask.task_id）
          trigger_date — 触发日期 T；不传则使用 `self._now().date()`

        返回：
          TriggerResult — 结构化结果

        流程（对应 requirements 4.1 – 4.5）：
          1. 从 store 加载任务；不存在返回 failed；status='stopped' 返回 skipped
          2. `pipeline.fetch_available_dates(...)` 数据拉取
          3. `compute_training_window(...)` 计算窗口
             （enforces Gap-One-Day + max_window_days 截断；无数据 → skipped）
          4. `pipeline.train(...)` 训练模型；异常走重试逻辑（req 4.6）
          5. `pipeline.predict(...)` 预测 T+1；异常走重试逻辑
          6. `pipeline.fetch_actual` / `get_prediction_series` 精度评估
             （actual 未到达或无历史预测则跳过精度，但整体仍算 success）
          7. 更新任务 status / last_execution_time / last_result / next_scheduled_time
        """
        current_dt = self._now()
        trigger_d = trigger_date if trigger_date is not None else current_dt.date()

        task = self.store.get_task(task_id)

        # -------- 步骤 0：任务存在性 & 状态检查 --------
        if task is None:
            logger.warning("SchedulerEngine.trigger_task: task_id=%s not found", task_id)
            return TriggerResult(
                task_id=task_id,
                trigger_date=trigger_d,
                result="failed",
                reason="task_not_found",
            )

        if task.status == "stopped":
            # 已停止的任务不参与触发（无论自动还是手动）
            return TriggerResult(
                task_id=task.task_id,
                trigger_date=trigger_d,
                result="skipped",
                reason="task_stopped",
            )

        # -------- 步骤 1：数据拉取（req 4.1） --------
        try:
            available = self.pipeline.fetch_available_dates(task.pipeline, task.slot)
        except Exception as exc:
            logger.exception(
                "fetch_available_dates 失败 task_id=%s pipeline=%s",
                task.task_id, task.pipeline,
            )
            return self._record_failure(
                task, trigger_d, current_dt,
                reason=f"fetch_available_dates_error: {exc}",
                window_days=0,
            )

        # -------- 步骤 2：滚动窗口计算（req 4.2 / 4.3 / 4.7） --------
        window = compute_training_window(trigger_d, task.max_window_days, available)
        if window.training_end is None:
            # 无可用训练数据不算失败，属于 skipped —— 等新数据入库后下一周期自动进入窗口（req 4.3）
            return self._record_skip(
                task, trigger_d, current_dt,
                reason="no_training_data",
                window_days=0,
            )

        # -------- 步骤 3：模型训练（req 4.2） --------
        try:
            artifacts = self.pipeline.train(
                task.pipeline, task.slot, window.included_dates,
            )
        except Exception as exc:
            logger.exception("pipeline.train 失败 task_id=%s", task.task_id)
            return self._record_failure(
                task, trigger_d, current_dt,
                reason=f"train_error: {exc}",
                window_days=window.window_days,
            )

        # -------- 步骤 4：预测 T+1（req 4.4） --------
        try:
            _prediction = self.pipeline.predict(
                task.pipeline, task.slot, artifacts, window.predict_target,
            )
        except Exception as exc:
            logger.exception("pipeline.predict 失败 task_id=%s", task.task_id)
            return self._record_failure(
                task, trigger_d, current_dt,
                reason=f"predict_error: {exc}",
                window_days=window.window_days,
            )

        # -------- 步骤 5：精度评估（req 4.5，针对 trigger_d：昨天预测的今天）--------
        # 语义：昨天在 T-1 触发时预测了 (T-1)+1 = T；今天 T 触发时评估该预测。
        # 遵循 design.md 错误处理表：actual 未到达 / 无历史预测 → last_result='skipped'
        # （状态显示“已跳过（数据未到达）”）；训练 + 预测本身已完成，不算失败。
        accuracy_eval_date = trigger_d
        try:
            actual_series = self.pipeline.fetch_actual(
                task.pipeline, task.slot, accuracy_eval_date,
            )
            predicted_series = self.pipeline.get_prediction_series(
                task.pipeline, task.slot, accuracy_eval_date,
            )
        except Exception as exc:
            # 精度评估异常按“未取到数据”处理 —— 记 warning 后走 skipped，
            # 不算失败（训练与 T+1 预测已经成功产出）
            logger.warning(
                "精度评估异常 task_id=%s date=%s: %s",
                task.task_id, accuracy_eval_date, exc,
            )
            return self._record_skip(
                task, trigger_d, current_dt,
                reason=f"accuracy_eval_error: {exc}",
                window_days=window.window_days,
            )

        if actual_series is None or predicted_series is None:
            return self._record_skip(
                task, trigger_d, current_dt,
                reason="actual_not_arrived" if actual_series is None else "no_prior_prediction",
                window_days=window.window_days,
            )

        if len(actual_series) == 0 or len(actual_series) != len(predicted_series):
            return self._record_skip(
                task, trigger_d, current_dt,
                reason="accuracy_series_shape_mismatch",
                window_days=window.window_days,
            )

        # 数据齐全 —— 计算 MAPE / RMSE。actual 含 0 时 MAPE 未定义但 RMSE 仍可算，
        # 两者分别 try/except，能算多少算多少。
        mape_val: Optional[float] = None
        rmse_val: Optional[float] = None
        try:
            mape_val = compute_mape(actual_series, predicted_series)
        except ValueError as metric_exc:
            logger.warning(
                "compute_mape 跳过 (task_id=%s, date=%s): %s",
                task.task_id, accuracy_eval_date, metric_exc,
            )
        try:
            rmse_val = compute_rmse(actual_series, predicted_series)
        except ValueError as metric_exc:
            logger.warning(
                "compute_rmse 跳过 (task_id=%s, date=%s): %s",
                task.task_id, accuracy_eval_date, metric_exc,
            )

        # -------- 步骤 6：成功落账 --------
        return self._record_success(
            task, trigger_d, current_dt,
            window_days=window.window_days,
            mape=mape_val,
            rmse=rmse_val,
        )

    # ------------------------------------------------------------------
    # 对外接口 2：批量扫描 due tasks
    # ------------------------------------------------------------------

    def run_due_tasks(
        self,
        current_time: Optional[datetime] = None,
    ) -> List[TriggerResult]:
        """扫描所有 running 状态的任务，触发到期任务（next_scheduled_time ≤ current_time）

        仅处理 `schedule_type='rolling_daily'` 的任务；`cron` / `interval` 任务不参与
        自动触发（会记录 warning），但仍可通过 `trigger_task` 手动执行。

        参数：
          current_time — 当前时间；不传则使用 `self._now()`

        返回：
          List[TriggerResult] — 本轮所有触发结果（顺序与 store.list_tasks 顺序一致）
        """
        now_dt = current_time if current_time is not None else self._now()
        results: List[TriggerResult] = []

        for task in self.store.list_tasks():
            if task.status != "running":
                continue

            if task.schedule_type != self._SUPPORTED_AUTO_SCHEDULE_TYPE:
                logger.warning(
                    "run_due_tasks: task_id=%s schedule_type=%s 尚未支持自动触发，"
                    "请通过 trigger_task 手动执行",
                    task.task_id, task.schedule_type,
                )
                continue

            # next_scheduled_time 未设置（新任务或格式非法）视为立即到期，让首轮触发能启动
            next_time = self._parse_next_time(task, fallback=now_dt)
            if next_time > now_dt:
                continue

            result = self.trigger_task(task.task_id, trigger_date=now_dt.date())
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # 内部：结果落账 + 重试状态机
    # ------------------------------------------------------------------

    def _record_success(
        self,
        task: ScheduledTask,
        trigger_d: date,
        exec_dt: datetime,
        window_days: int,
        mape: Optional[float],
        rmse: Optional[float],
    ) -> TriggerResult:
        """成功落账：清零重试计数，更新任务字段与下次调度时间。"""
        with self._lock:
            self._retry_counts[task.task_id] = 0
        updated = task.model_copy(update={
            "status": "running",  # 成功后总是保持 / 回到 running
            "last_execution_time": exec_dt.isoformat(),
            "last_result": "success",
            "next_scheduled_time": self._compute_next_scheduled_time(task, trigger_d),
            "updated_at": exec_dt.isoformat(),
        })
        self.store.upsert_task(updated)
        return TriggerResult(
            task_id=task.task_id,
            trigger_date=trigger_d,
            result="success",
            window_days=window_days,
            mape=mape,
            rmse=rmse,
        )

    def _record_skip(
        self,
        task: ScheduledTask,
        trigger_d: date,
        exec_dt: datetime,
        reason: str,
        window_days: int,
    ) -> TriggerResult:
        """跳过落账：不影响重试计数（既非失败也非成功），仅更新执行时间与下次调度时间。"""
        updated = task.model_copy(update={
            "last_execution_time": exec_dt.isoformat(),
            "last_result": "skipped",
            "next_scheduled_time": self._compute_next_scheduled_time(task, trigger_d),
            "updated_at": exec_dt.isoformat(),
        })
        self.store.upsert_task(updated)
        return TriggerResult(
            task_id=task.task_id,
            trigger_date=trigger_d,
            result="skipped",
            reason=reason,
            window_days=window_days,
        )

    def _record_failure(
        self,
        task: ScheduledTask,
        trigger_d: date,
        exec_dt: datetime,
        reason: str,
        window_days: int,
    ) -> TriggerResult:
        """失败落账：按 retry_on_failure / max_retries 决定 status 是保持 running 还是标记 failed。

        参见模块 docstring 的“重试状态机”部分。
        """
        with self._lock:
            current_retries = self._retry_counts.get(task.task_id, 0)
            if not task.retry_on_failure:
                # 显式禁用重试 → 首次失败即 failed
                new_status = "failed"
                self._retry_counts[task.task_id] = 0
            elif current_retries < task.max_retries:
                # 还有重试额度 → 保持 running，下一周期继续
                new_status = "running"
                self._retry_counts[task.task_id] = current_retries + 1
            else:
                # 重试耗尽 → 标记 failed 并清零计数（下次人工恢复后从头计）
                new_status = "failed"
                self._retry_counts[task.task_id] = 0

        updated = task.model_copy(update={
            "status": new_status,
            "last_execution_time": exec_dt.isoformat(),
            "last_result": "failed",
            "next_scheduled_time": self._compute_next_scheduled_time(task, trigger_d),
            "updated_at": exec_dt.isoformat(),
        })
        self.store.upsert_task(updated)

        logger.warning(
            "SchedulerEngine failure task_id=%s reason=%s retries=%d/%d status→%s",
            task.task_id, reason, self._retry_counts.get(task.task_id, 0),
            task.max_retries, new_status,
        )

        return TriggerResult(
            task_id=task.task_id,
            trigger_date=trigger_d,
            result="failed",
            reason=reason,
            window_days=window_days,
        )

    # ------------------------------------------------------------------
    # 内部：下次调度时间 / next_scheduled_time 计算
    # ------------------------------------------------------------------

    def _compute_next_scheduled_time(
        self,
        task: ScheduledTask,
        trigger_d: date,
    ) -> Optional[str]:
        """rolling_daily：下一日的 trigger_time；其他类型返回 None（不参与自动调度）。"""
        if task.schedule_type != self._SUPPORTED_AUTO_SCHEDULE_TYPE:
            return None
        trigger_time_obj = self._parse_trigger_time(task.trigger_time)
        next_dt = datetime.combine(trigger_d + timedelta(days=1), trigger_time_obj)
        return next_dt.isoformat()

    def _parse_trigger_time(self, trigger_time: str) -> time:
        """解析 HH:MM，异常时兜底为默认 02:00（`ScheduledTask` 模型已校验，这里再做一层防守）。"""
        try:
            hh_str, mm_str = trigger_time.split(":")
            return time(int(hh_str), int(mm_str))
        except (ValueError, AttributeError):
            logger.warning(
                "无法解析 trigger_time=%r，使用默认 %02d:%02d",
                trigger_time, self._DEFAULT_TRIGGER_HOUR, self._DEFAULT_TRIGGER_MINUTE,
            )
            return time(self._DEFAULT_TRIGGER_HOUR, self._DEFAULT_TRIGGER_MINUTE)

    def _parse_next_time(self, task: ScheduledTask, fallback: datetime) -> datetime:
        """把 `task.next_scheduled_time` 解析为 datetime；缺失 / 非法 → 返回 fallback（视为立即到期）。"""
        raw = task.next_scheduled_time
        if not raw:
            return fallback
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            logger.warning(
                "task_id=%s next_scheduled_time 格式非法 (%r)，视为立即到期",
                task.task_id, raw,
            )
            return fallback


__all__ = [
    "SchedulerPipeline",
    "TriggerResult",
    "SchedulerEngine",
]
# @AI_GENERATED: end
