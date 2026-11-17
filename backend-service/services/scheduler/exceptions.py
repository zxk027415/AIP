"""Scheduler task exceptions."""


class SchedulerTaskSkipped(Exception):
    """Task chose not to run (e.g. missing model); not a failure."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)
