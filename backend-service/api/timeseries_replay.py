"""HTTP API for real-point replay_activity sessions."""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.benchmark.governance import resolve_execution_purpose
from services.timeseries_profiles.loader import load_dataset_from_profile
from services.timeseries_profiles.preflight import run_dataset_profile_preflight
from services.timeseries_profiles.store import TimeseriesProfileStore
from services.timeseries_point.replay_activity import (
    append_pending_feed_points,
    cancel_session,
    create_session,
    load_session,
    pause_session,
    replay_next_point,
    resume_session,
    session_to_dict,
)

router = APIRouter(prefix="/api/timeseries-replay", tags=["timeseries-replay"])
_profile_store = TimeseriesProfileStore()


class CreateReplaySessionRequest(BaseModel):
    session_id: str
    dataset_profile_id: str
    model_ref: Optional[str] = None
    slot: str = "pv_point"
    execution_purpose: Optional[str] = "product_workflow"
    batch_policy: Optional[dict[str, Any]] = None


class ReplayStepRequest(BaseModel):
    idempotency_key: Optional[str] = None
    context_length: int = Field(default=8, ge=2)


class CancelReplayRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/sessions")
def create_replay_session(body: CreateReplaySessionRequest) -> dict[str, Any]:
    try:
        profile_obj = _profile_store.get_dataset_profile(body.dataset_profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    profile = profile_obj.model_dump() if hasattr(profile_obj, "model_dump") else dict(profile_obj)
    if profile.get("slot") != body.slot:
        raise HTTPException(status_code=400, detail="profile slot mismatch")

    try:
        purpose = resolve_execution_purpose(
            slot=body.slot,
            execution_purpose=body.execution_purpose,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    use_purpose: Literal["local_validation", "product_workflow", "benchmark_reuse"] = (
        "benchmark_reuse" if purpose["execution_purpose"] == "benchmark_reuse" else "local_validation"
    )
    preflight = run_dataset_profile_preflight(profile_obj, use_purpose=use_purpose)
    if not preflight.ready:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "dataset profile preflight failed",
                "report": preflight.model_dump(),
            },
        )

    df = load_dataset_from_profile(profile_obj)
    session = create_session(
        session_id=body.session_id,
        profile=profile,
        source_df=df,
        model_ref=body.model_ref,
        slot=body.slot,
        execution_purpose=body.execution_purpose,
        source_digest=preflight.source_digest,
        dataset_profile_id=body.dataset_profile_id,
        batch_policy=body.batch_policy,
    )
    return {
        **session_to_dict(session),
        "total_points": len(session.source_rows),
    }


@router.get("/sessions/{session_id}")
def get_replay_session(
    session_id: str,
    day_from: Optional[str] = Query(default=None),
    day_to: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    try:
        session = load_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session_to_dict(session, day_from=day_from, day_to=day_to)


@router.post("/sessions/{session_id}/pause")
def pause_replay_session(session_id: str) -> dict[str, Any]:
    try:
        session = pause_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_to_dict(session)


@router.post("/sessions/{session_id}/resume")
def resume_replay_session(session_id: str) -> dict[str, Any]:
    try:
        session = resume_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_to_dict(session)


@router.post("/sessions/{session_id}/cancel")
def cancel_replay_session(session_id: str, body: CancelReplayRequest) -> dict[str, Any]:
    try:
        session = cancel_session(session_id, reason=body.reason)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session_to_dict(session)


@router.post("/sessions/{session_id}/next")
def replay_step(session_id: str, body: ReplayStepRequest) -> dict[str, Any]:
    try:
        result = replay_next_point(
            session_id,
            idempotency_key=body.idempotency_key,
            context_length=body.context_length,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        session = None

    point_outcome = dict(result.get("point_outcome") or {})
    alarm_result = None
    if session and point_outcome and session.governance_eligible:
        from services.timeseries_point.point_alarm_store import ingest_point_outcome

        ek = point_outcome.get("entity_key")
        if isinstance(ek, (list, tuple)):
            point_outcome["entity_key"] = "|".join(str(part) for part in ek)
        elif ek is None:
            point_outcome["entity_key"] = "__default__"
        alarm_result = ingest_point_outcome(session.slot, point_outcome)
        result["alarm"] = alarm_result
    return result


class PendingPointRequest(BaseModel):
    entity_key: str = "s1|d1|b1"
    point_time: str
    values: dict[str, Any] = Field(default_factory=dict)


class UpdateAlarmPolicyRequest(BaseModel):
    open_consecutive_points: int = Field(..., ge=1, le=48, description="连续故障点数达到后开告警")
    close_consecutive_points: Optional[int] = Field(None, ge=1, le=48, description="连续正常点数达到后关告警")
    label_switch_consecutive_points: Optional[int] = Field(None, ge=1, le=48)
    cold_start_alarm_enabled: bool = False
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)


@router.get("/slots/{slot}/alarms/summary")
def get_slot_alarm_summary(
    slot: str,
    day_from: Optional[str] = Query(default=None),
    day_to: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    from services.timeseries_point.point_alarm_store import alarm_summary

    return alarm_summary(slot, day_from=day_from, day_to=day_to)


@router.get("/slots/{slot}/alarms/events")
def get_slot_alarm_events(
    slot: str,
    limit: int = 50,
    day_from: Optional[str] = Query(default=None),
    day_to: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    from services.timeseries_point.point_alarm_store import list_events

    return {"slot": slot, "events": list_events(slot, limit=limit, day_from=day_from, day_to=day_to)}


@router.get("/slots/{slot}/alarms/policy")
def get_slot_alarm_policy(slot: str) -> dict[str, Any]:
    from services.timeseries_point.point_alarm_store import alarm_policy_to_dict

    return alarm_policy_to_dict(slot)


@router.put("/slots/{slot}/alarms/policy")
def put_slot_alarm_policy(slot: str, body: UpdateAlarmPolicyRequest) -> dict[str, Any]:
    from services.timeseries_point.point_alarm_store import alarm_policy_to_dict, save_alarm_policy

    payload = body.model_dump()
    if payload.get("close_consecutive_points") is None:
        payload["close_consecutive_points"] = payload["open_consecutive_points"]
    if payload.get("label_switch_consecutive_points") is None:
        payload["label_switch_consecutive_points"] = payload["open_consecutive_points"]
    try:
        policy = save_alarm_policy(slot, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return alarm_policy_to_dict(slot, policy)


@router.get("/slots/{slot}/pending-feed/summary")
def get_pending_feed_summary(slot: str) -> dict[str, Any]:
    from services.timeseries_point.pending_point_feed import pending_summary

    return pending_summary(slot)


@router.post("/slots/{slot}/pending-feed/enqueue")
def enqueue_pending_feed_point(slot: str, body: PendingPointRequest) -> dict[str, Any]:
    from services.timeseries_point.pending_point_feed import enqueue_pending_point

    point = {
        "entity_key": body.entity_key,
        "point_time": body.point_time,
        **body.values,
    }
    entry = enqueue_pending_point(slot, point)
    return {"slot": slot, "point": entry}


@router.post("/slots/{slot}/pending-feed/drain")
def drain_pending_feed_to_session(
    slot: str,
    session_id: str,
    limit: int = 1,
) -> dict[str, Any]:
    try:
        added = append_pending_feed_points(session_id, slot, limit=limit)
        session = load_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "slot": slot,
        "session_id": session_id,
        "points_added": added,
        "cursor": session.cursor,
        "total": len(session.source_rows),
        "status": session.status,
    }
