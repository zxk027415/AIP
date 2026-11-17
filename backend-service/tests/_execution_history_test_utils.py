"""Shared helpers for execution_history store tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def patch_execution_history_dirs(monkeypatch, history_dir: Path) -> None:
    by_id = history_dir / "by_id"
    by_id.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("services.execution_history.store._EXEC_DIR", history_dir)
    monkeypatch.setattr("services.execution_history.store._BY_ID_DIR", by_id)


def write_execution_record(payload: dict[str, Any]) -> None:
    from services.execution_history.store import persist_execution_record

    persist_execution_record(payload)
