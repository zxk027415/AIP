"""Persist scheduler / replay evidence for slot product ops UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from services.execution_history.store import persist_execution_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def persist_replay_tick_evidence(
    *,
    slot: str,
    workflow_id: str,
    session_id: str,
    outcome: dict[str, Any],
    alarm_result: Optional[dict[str, Any]] = None,
) -> str:
    """Write replay tick as latest predict_replay execution for accuracy ops."""
    cursor = int(outcome.get("cursor") or 0)
    execution_id = f"exec-replay-{session_id}-c{cursor}"
    point = dict(outcome.get("point_outcome") or {})
    summary = {
        "replay_session_id": session_id,
        "cursor": outcome.get("cursor"),
        "total": outcome.get("total"),
        "points_processed": outcome.get("points_processed", 1),
        "point_outcome_kind": point.get("kind"),
        "point_label": point.get("label"),
        "point_confidence": point.get("confidence"),
        "point_reason": point.get("reason"),
        "replay_status": outcome.get("status"),
        "coverage": (
            float(cursor) / float(outcome["total"])
            if outcome.get("total")
            else None
        ),
    }
    if alarm_result:
        summary["alarm_phase"] = alarm_result.get("phase")
        summary["active_alarm_id"] = alarm_result.get("active_alarm_id")
        summary["alarm_events"] = alarm_result.get("events") or []
    replay_status = str(outcome.get("status") or "")
    ok_status = {
        "point_processed",
        "batch_processed",
        "completed",
        "idempotent_replay",
    }
    state: dict[str, Any] = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "slot": slot,
        "status": "success" if replay_status in ok_status else "failed",
        "scheduler_trigger": True,
        "trigger_source": "replay_activity",
        "source": "scheduler:pv_point_replay_tick",
        "nodeResults": {
            "replay_activity": {
                "status": "success" if replay_status in ok_status else "failed",
                "outputSummary": summary,
            }
        },
        "metrics": summary,
        "finished_at": _now_iso(),
        "started_at": _now_iso(),
    }
    if replay_status not in ok_status:
        state["error"] = f"replay_status={replay_status}"
    persist_execution_record(state)
    return execution_id
