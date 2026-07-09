"""
SchedulerEngine — APScheduler-backed cron task scheduler.

Features:
- Per-pipeline independent BackgroundScheduler instances
- Overlap protection: skip new trigger if same task is already running
- Failure retry: retry once after retry_delay seconds; mark failed if retry also fails
- Failure history: keep last 20 FailureRecord per task
- Catch-up: on start, run once if last_execution_time < now - cron_interval
- Independent pipeline start/stop

Pipelines supported: 'load_forecast', 'pv_fault' (and any other string key)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FailureRecord:
    task_id: str
    trigger_time: datetime
    error_message: str
    is_retry: bool


@dataclass
class TaskStatus:
    task_id: str
    last_execution_time: Optional[datetime]
    next_scheduled_time: Optional[datetime]
    last_result: str  # "success" | "failed" | "skipped"
    recent_failures: List[FailureRecord]  # max 20


@dataclass
class SchedulerStatus:
    pipeline: str
    running: bool
    tasks: List[TaskStatus]


# ---------------------------------------------------------------------------
# Internal task metadata
# ---------------------------------------------------------------------------

@dataclass
class _TaskMeta:
    task_id: str
    func: Callable
    cron_expr: str
    pipeline: str
    retry_delay: int  # seconds

    last_execution_time: Optional[datetime] = field(default=None)
    last_result: str = field(default="success")
    recent_failures: deque = field(default_factory=lambda: deque(maxlen=20))


# ---------------------------------------------------------------------------
# SchedulerEngine
# ---------------------------------------------------------------------------

class SchedulerEngine:
    """Manages one BackgroundScheduler per pipeline and dispatches cron tasks."""

    def __init__(self) -> None:
        # pipeline_name -> BackgroundScheduler
        self._schedulers: Dict[str, BackgroundScheduler] = {}
        # pipeline_name -> bool (running state)
        self._pipeline_running: Dict[str, bool] = {}

        # task_id -> _TaskMeta
        self._tasks: Dict[str, _TaskMeta] = {}

        # task_id -> bool (in-flight flag)
        self._task_running: Dict[str, bool] = {}
        self._task_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_task(
        self,
        task_id: str,
        func: Callable,
        cron_expr: str,
        pipeline: str,
        retry_delay: int = 60,
    ) -> None:
        """Register a cron task under the given pipeline.

        The task will not run until start_pipeline(pipeline) is called.
        Minimum granularity is 1 minute (enforced by CronTrigger).
        If the task_id already exists it will be re-registered (replaced).
        """
        meta = _TaskMeta(
            task_id=task_id,
            func=func,
            cron_expr=cron_expr,
            pipeline=pipeline,
            retry_delay=retry_delay,
        )
        self._tasks[task_id] = meta
        with self._task_lock:
            self._task_running[task_id] = False

        # If the pipeline scheduler is already running, add the job live.
        scheduler = self._schedulers.get(pipeline)
        if scheduler is not None and self._pipeline_running.get(pipeline):
            self._add_job_to_scheduler(scheduler, meta)

    def start_pipeline(self, pipeline: str) -> None:
        """Start (or restart) the scheduler for a pipeline.

        Runs catch-up if last_execution_time < now - cron_interval.
        Only affects the named pipeline.
        """
        if self._pipeline_running.get(pipeline):
            logger.debug("Pipeline '%s' is already running.", pipeline)
            return

        scheduler = self._schedulers.get(pipeline)
        if scheduler is None or not scheduler.running:
            scheduler = BackgroundScheduler()
            self._schedulers[pipeline] = scheduler

        # Register all tasks that belong to this pipeline.
        pipeline_tasks = [m for m in self._tasks.values() if m.pipeline == pipeline]
        for meta in pipeline_tasks:
            self._add_job_to_scheduler(scheduler, meta)

        scheduler.start()
        self._pipeline_running[pipeline] = True
        logger.info("Pipeline '%s' started.", pipeline)

        # Catch-up: for tasks with a missed execution, run once immediately.
        for meta in pipeline_tasks:
            self._maybe_catchup(meta)

    def stop_pipeline(self, pipeline: str) -> None:
        """Stop the scheduler for a pipeline. Does NOT affect other pipelines."""
        scheduler = self._schedulers.get(pipeline)
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
            self._schedulers[pipeline] = BackgroundScheduler()  # fresh, not started
        self._pipeline_running[pipeline] = False
        logger.info("Pipeline '%s' stopped.", pipeline)

    def get_status(self, pipeline: str) -> SchedulerStatus:
        """Return the SchedulerStatus for a single pipeline."""
        running = bool(self._pipeline_running.get(pipeline, False))
        pipeline_tasks = [m for m in self._tasks.values() if m.pipeline == pipeline]

        scheduler = self._schedulers.get(pipeline)
        task_statuses = []
        for meta in pipeline_tasks:
            next_time = self._get_next_run_time(scheduler, meta.task_id)
            task_statuses.append(
                TaskStatus(
                    task_id=meta.task_id,
                    last_execution_time=meta.last_execution_time,
                    next_scheduled_time=next_time,
                    last_result=meta.last_result,
                    recent_failures=list(meta.recent_failures),
                )
            )

        return SchedulerStatus(pipeline=pipeline, running=running, tasks=task_statuses)

    def get_all_status(self) -> Dict[str, SchedulerStatus]:
        """Return SchedulerStatus for every known pipeline."""
        pipelines = set(m.pipeline for m in self._tasks.values())
        pipelines.update(self._pipeline_running.keys())
        return {p: self.get_status(p) for p in pipelines}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_job_to_scheduler(
        self, scheduler: BackgroundScheduler, meta: _TaskMeta
    ) -> None:
        """Add (or replace) a job in the given scheduler."""
        job_id = meta.task_id
        # Remove existing job if present to avoid duplicates on re-register.
        try:
            existing = scheduler.get_job(job_id)
            if existing is not None:
                scheduler.remove_job(job_id)
        except Exception:
            pass

        trigger = CronTrigger.from_crontab(meta.cron_expr)
        scheduler.add_job(
            self._make_job_wrapper(meta),
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=None,  # skip misfired triggers; catch-up is manual
        )

    def _make_job_wrapper(self, meta: _TaskMeta) -> Callable:
        """Return a closure that wraps the user function with overlap/retry logic."""

        def _job() -> None:
            self._run_with_protection(meta, is_retry=False)

        return _job

    def _run_with_protection(self, meta: _TaskMeta, is_retry: bool) -> None:
        """Execute meta.func with overlap protection and optional retry."""
        task_id = meta.task_id
        trigger_time = datetime.now()

        # --- Overlap protection ---
        with self._task_lock:
            if self._task_running.get(task_id):
                logger.warning(
                    "Task '%s' is already running; skipping trigger at %s.",
                    task_id,
                    trigger_time,
                )
                meta.last_result = "skipped"
                return
            self._task_running[task_id] = True

        try:
            meta.func()
            meta.last_execution_time = datetime.now()
            meta.last_result = "success"
            logger.debug("Task '%s' completed successfully.", task_id)
        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "Task '%s' failed (is_retry=%s): %s", task_id, is_retry, error_msg
            )
            record = FailureRecord(
                task_id=task_id,
                trigger_time=trigger_time,
                error_message=error_msg,
                is_retry=is_retry,
            )
            meta.recent_failures.append(record)

            if not is_retry:
                # Schedule a single retry after retry_delay seconds.
                meta.last_result = "failed"
                retry_thread = threading.Timer(
                    meta.retry_delay,
                    self._retry_task,
                    args=(meta,),
                )
                retry_thread.daemon = True
                retry_thread.start()
            else:
                # Retry also failed; mark this cycle as definitively failed.
                meta.last_result = "failed"
                logger.error(
                    "Task '%s' retry also failed; cycle marked as failed.", task_id
                )
        finally:
            with self._task_lock:
                self._task_running[task_id] = False

    def _retry_task(self, meta: _TaskMeta) -> None:
        """Called by the retry Timer; runs with overlap protection (is_retry=True)."""
        logger.info("Retrying task '%s'.", meta.task_id)
        self._run_with_protection(meta, is_retry=True)

    def _maybe_catchup(self, meta: _TaskMeta) -> None:
        """Run the task once if the last execution was before the previous cron tick."""
        now = datetime.now()
        if meta.last_execution_time is None:
            # No prior execution recorded; run immediately as catch-up.
            logger.info(
                "Catch-up: task '%s' has no recorded execution; running now.", meta.task_id
            )
            t = threading.Thread(
                target=self._run_with_protection, args=(meta, False), daemon=True
            )
            t.start()
            return

        try:
            interval_seconds = self._cron_interval_seconds(meta.cron_expr)
        except Exception:
            # Cannot determine interval; skip catch-up.
            return

        elapsed = (now - meta.last_execution_time).total_seconds()
        if elapsed > interval_seconds:
            logger.info(
                "Catch-up: task '%s' missed ~%.0f s; running once now.",
                meta.task_id,
                elapsed,
            )
            t = threading.Thread(
                target=self._run_with_protection, args=(meta, False), daemon=True
            )
            t.start()

    @staticmethod
    def _cron_interval_seconds(cron_expr: str) -> float:
        """Estimate the interval in seconds between cron triggers.

        Uses the difference between two consecutive fire times.
        Minimum granularity is 1 minute (60 s).
        """
        trigger = CronTrigger.from_crontab(cron_expr)
        from datetime import timezone

        base = datetime.now(tz=timezone.utc)
        t1 = trigger.get_next_fire_time(None, base)
        if t1 is None:
            return 60.0
        t2 = trigger.get_next_fire_time(t1, t1)
        if t2 is None:
            return 60.0
        interval = (t2 - t1).total_seconds()
        return max(interval, 60.0)

    def _get_next_run_time(
        self, scheduler: Optional[BackgroundScheduler], task_id: str
    ) -> Optional[datetime]:
        """Return next scheduled run time from the APScheduler job, if available."""
        if scheduler is None:
            return None
        try:
            job = scheduler.get_job(task_id)
            if job is not None and job.next_run_time is not None:
                # APScheduler returns timezone-aware datetimes; strip tz for uniformity.
                return job.next_run_time.replace(tzinfo=None)
        except Exception:
            pass
        return None
