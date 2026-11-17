"""Persisted workflow execution records (latest + per execution_id index)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_EXEC_DIR = _BACKEND_DIR / "data" / "execution_history"
_BY_ID_DIR = _EXEC_DIR / "by_id"


def execution_history_dir() -> Path:
    return _EXEC_DIR


def _safe(obj: Any, depth: int = 0) -> Any:
    if depth > 6:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe(i, depth + 1) for i in obj]
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return f"ndarray{list(obj.shape)}"
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
    except ImportError:
        pass
    try:
        import pandas as pd

        if isinstance(obj, pd.DataFrame):
            return f"DataFrame{list(obj.shape)}"
    except ImportError:
        pass
    return str(obj)


def persist_execution_record(state: dict[str, Any]) -> None:
    """Write latest file and immutable index entry keyed by execution_id."""
    workflow_id = str(state.get("workflow_id") or state.get("source_workflow_id") or "").strip()
    execution_id = str(state.get("execution_id") or "").strip()
    if not workflow_id:
        return

    _EXEC_DIR.mkdir(parents=True, exist_ok=True)
    payload = _safe(state)

    latest_path = _EXEC_DIR / f"{workflow_id}_latest.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if execution_id:
        _BY_ID_DIR.mkdir(parents=True, exist_ok=True)
        index_path = _BY_ID_DIR / f"{execution_id}.json"
        index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_latest_execution(workflow_id: str) -> Optional[dict[str, Any]]:
    path = _EXEC_DIR / f"{workflow_id}_latest.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def load_execution_by_id(execution_id: str) -> Optional[dict[str, Any]]:
    exec_id = str(execution_id or "").strip()
    if not exec_id:
        return None
    path = _BY_ID_DIR / f"{exec_id}.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def load_execution_record(
    workflow_id: str,
    execution_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Prefer indexed record by execution_id; fallback to workflow latest."""
    if execution_id:
        indexed = load_execution_by_id(execution_id)
        if indexed is not None:
            indexed_wf = str(indexed.get("workflow_id") or indexed.get("source_workflow_id") or "")
            if not workflow_id or indexed_wf == workflow_id:
                return indexed
    return load_latest_execution(workflow_id)
