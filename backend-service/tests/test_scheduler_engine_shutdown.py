# -*- coding: utf-8 -*-
"""SchedulerEngine 退出时必须先停 APScheduler，避免向已关闭线程池投任务。"""

from services.scheduler.engine import SchedulerEngine


def test_shutdown_all_stops_running_scheduler() -> None:
    engine = SchedulerEngine()
    engine.register_task(
        "noop_tick",
        lambda: None,
        "* * * * *",
        "pv_fault",
    )
    engine.start_pipeline("pv_fault", catchup=False)
    assert engine._pipeline_running["pv_fault"] is True
    assert engine._schedulers["pv_fault"].running is True

    engine.shutdown_all(wait=False)

    assert engine._pipeline_running.get("pv_fault") is False
    assert engine._schedulers == {}
    engine.shutdown_all(wait=False)
