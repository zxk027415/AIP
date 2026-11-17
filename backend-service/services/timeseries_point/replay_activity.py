"""File-driven real-point replay loop (not a graph operator)."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import pandas as pd

from services.benchmark.governance import resolve_execution_purpose
from services.operator_execution.slot_workflows import resolve_replay_workflow_id
from services.timeseries_point.profile_map import apply_profile_map
from services.timeseries_point.validate_schema import validate_point_schema

_BACKEND = Path(__file__).resolve().parents[2]
_SESSION_ROOT = _BACKEND / "data" / "timeseries_point" / "replay_sessions"
_LOCK = threading.Lock()

ReplayStatus = Literal["pending", "running", "paused", "cancelled", "completed", "failed"]


@dataclass
class ReplaySession:
    session_id: str
    replay_id: str = ""
    slot: str = "pv_point"
    status: ReplayStatus = "pending"
    profile: dict[str, Any] = field(default_factory=dict)
    dataset_profile_id: Optional[str] = None
    source_digest: Optional[str] = None
    clock_mode: str = "event_time"
    execution_purpose: str = "product_workflow"
    governance_eligible: bool = True
    model_ref: Optional[str] = None
    committed_history: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    cursor: int = 0
    entity_cursors: dict[str, int] = field(default_factory=dict)
    source_rows: list[dict[str, Any]] = field(default_factory=list)
    batch_policy: dict[str, Any] = field(default_factory=lambda: {"max_points_per_step": 1})
    range_start: Optional[Any] = None
    range_end: Optional[Any] = None
    candidate_projection_enabled: bool = False
    workflow_id: Optional[str] = None
    use_frozen_graph: bool = True
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    selection_policy: str = "legacy_entity_then_time"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _session_path(session_id: str) -> Path:
    return _SESSION_ROOT / f"{session_id}.json"


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in row.items():
        if isinstance(value, pd.Timestamp):
            safe[key] = value.isoformat()
        else:
            safe[key] = value
    return safe


def _entity_key(row: dict[str, Any], entity_keys: list[str]) -> str:
    if not entity_keys:
        return "__default__"
    return "|".join(str(row.get(key, "")) for key in entity_keys)


def _digest_rows(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sort_source_rows(mapped: pd.DataFrame, contract: dict[str, Any]) -> pd.DataFrame:
    entity_keys = list(contract.get("entity_keys") or [])
    order_column = str(contract.get("time_column") or "")
    clock_mode = str(contract.get("clock_mode") or "event_time")
    if not order_column:
        return mapped.reset_index(drop=True)
    if clock_mode == "index":
        mapped = mapped.copy()
        mapped[order_column] = pd.to_numeric(mapped[order_column], errors="coerce")
        return mapped.sort_values(entity_keys + [order_column]).reset_index(drop=True)
    mapped = mapped.copy()
    mapped[order_column] = pd.to_datetime(mapped[order_column], errors="coerce", utc=True)
    return mapped.sort_values(entity_keys + [order_column]).reset_index(drop=True)


def _init_entity_cursors(rows: list[dict[str, Any]], entity_keys: list[str]) -> dict[str, int]:
    cursors: dict[str, int] = {}
    for row in rows:
        key = _entity_key(row, entity_keys)
        cursors[key] = cursors.get(key, 0)
    return cursors


def _uses_event_time_picker(session: ReplaySession) -> bool:
    return str(session.selection_policy or "") == "earliest_event_time"


def _entity_row_indices(session: ReplaySession) -> dict[str, list[int]]:
    contract = session.profile or {}
    entity_keys = list(contract.get("entity_keys") or [])
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(session.source_rows):
        key = _entity_key(row, entity_keys)
        grouped.setdefault(key, []).append(index)
    return grouped


def _row_event_time(row: dict[str, Any], time_column: str) -> Any:
    value = row.get(time_column)
    try:
        stamp = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(stamp):
            return str(value or "")
        return stamp
    except Exception:
        return str(value or "")


def _pick_next_source_index(session: ReplaySession) -> Optional[int]:
    if not _uses_event_time_picker(session):
        if session.cursor >= len(session.source_rows):
            return None
        return int(session.cursor)
    contract = session.profile or {}
    entity_keys = list(contract.get("entity_keys") or [])
    time_column = str(contract.get("time_column") or "event_time")
    best_index = None
    best_key = None
    best_time = None
    grouped = _entity_row_indices(session)
    for entity, indices in grouped.items():
        consumed = int(session.entity_cursors.get(entity, 0) or 0)
        if consumed >= len(indices):
            continue
        index = indices[consumed]
        row = session.source_rows[index]
        event_time = _row_event_time(row, time_column)
        entity_key = _entity_key(row, entity_keys)
        if best_index is None or (event_time, entity_key) < (best_time, best_key):
            best_index = index
            best_time = event_time
            best_key = entity_key
    return best_index


def _entity_history_rows(session: ReplaySession, entity_key: str, pending_index: int) -> list[dict[str, Any]]:
    contract = session.profile or {}
    entity_keys = list(contract.get("entity_keys") or [])
    history: list[dict[str, Any]] = []
    grouped = _entity_row_indices(session)
    indices = grouped.get(entity_key) or []
    consumed = int(session.entity_cursors.get(entity_key, 0) or 0)
    for index in indices[:consumed]:
        history.append(session.source_rows[index])
    history.append(session.source_rows[pending_index])
    if not history:
        history = [session.source_rows[pending_index]]
    return history


def _reconstruct_committed_history(session: ReplaySession) -> list[dict[str, Any]]:
    """Derive causal history from source rows + cursors (avoid duplicating rows on disk)."""
    if _uses_event_time_picker(session):
        history: list[dict[str, Any]] = []
        grouped = _entity_row_indices(session)
        for entity, indices in grouped.items():
            consumed = int(session.entity_cursors.get(entity, 0) or 0)
            for index in indices[:consumed]:
                history.append(session.source_rows[index])
        return history
    cursor = max(0, min(int(session.cursor or 0), len(session.source_rows)))
    return list(session.source_rows[:cursor])


def _hydrate_source_rows(session: ReplaySession) -> None:
    """Reload source rows from dataset profile when omitted from session snapshot."""
    if session.source_rows:
        return
    profile_id = session.dataset_profile_id
    if not profile_id:
        return
    from services.timeseries_profiles.loader import load_dataset_from_profile
    from services.timeseries_profiles.store import TimeseriesProfileStore

    store = TimeseriesProfileStore()
    profile_obj = store.get_dataset_profile(profile_id)
    profile = (
        session.profile
        if session.profile
        else (profile_obj.model_dump() if hasattr(profile_obj, "model_dump") else dict(profile_obj))
    )
    df = load_dataset_from_profile(profile_obj)
    mapped, contract = apply_profile_map(df, profile)
    report = validate_point_schema(mapped, contract)
    if not report["valid"]:
        raise ValueError(f"replay profile reload invalid: {report['issues']}")
    mapped = _sort_source_rows(mapped, contract)
    session.profile = contract
    session.source_rows = [_json_safe_row(row) for row in mapped.to_dict(orient="records")]


def _save_session(session: ReplaySession) -> None:
    _SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    session.updated_at = _now_iso()
    session.committed_history = _reconstruct_committed_history(session)
    payload = asdict(session)
    payload["committed_history"] = []
    if session.dataset_profile_id:
        payload["source_rows"] = []
    if isinstance(payload.get("outcomes"), list) and len(payload["outcomes"]) > 64:
        payload["outcomes"] = list(payload["outcomes"][-64:])
    tmp = _session_path(session.session_id).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_session_path(session.session_id))


def load_session(session_id: str) -> ReplaySession:
    path = _session_path(session_id)
    if not path.is_file():
        raise FileNotFoundError(f"replay session not found: {session_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("replay_id"):
        payload["replay_id"] = payload.get("session_id", session_id)
    allowed = {item.name for item in ReplaySession.__dataclass_fields__.values()}
    session = ReplaySession(**{key: value for key, value in payload.items() if key in allowed})
    _hydrate_source_rows(session)
    session.committed_history = _reconstruct_committed_history(session)
    return session


def session_entity_overview(session: ReplaySession) -> list[dict[str, Any]]:
    """Aggregate replay source rows and cursors per entity (site/device/branch)."""
    contract = session.profile or {}
    entity_keys = list(contract.get("entity_keys") or [])
    time_column = str(contract.get("time_column") or "time")
    source_counts: dict[str, int] = {}
    last_source_time: dict[str, Any] = {}
    for row in session.source_rows:
        key = _entity_key(row, entity_keys)
        source_counts[key] = int(source_counts.get(key, 0)) + 1
        last_source_time[key] = row.get(time_column)
    last_replay_time: dict[str, Any] = {}
    last_label: dict[str, Any] = {}
    for outcome in session.outcomes:
        key = str(outcome.get("entity_key") or "")
        if not key:
            continue
        last_replay_time[key] = outcome.get("point_time")
        last_label[key] = outcome.get("label")
    rows: list[dict[str, Any]] = []
    for key in sorted(source_counts):
        parts = key.split("|") if key else []
        rows.append(
            {
                "entity_key": key,
                "site_id": parts[0] if len(parts) > 0 else "",
                "device_id": parts[1] if len(parts) > 1 else "",
                "branch_id": parts[2] if len(parts) > 2 else "",
                "source_points": source_counts[key],
                "replayed_points": int(session.entity_cursors.get(key, 0) or 0),
                "last_source_time": last_source_time.get(key),
                "last_replay_time": last_replay_time.get(key),
                "last_label": last_label.get(key),
            }
        )
    return rows


def _stamp_calendar_day(value: Any) -> str:
    raw = str(value or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    parsed = pd.to_datetime(raw, utc=True, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")
    return ""


def _outcome_day(item: dict[str, Any]) -> str:
    return _stamp_calendar_day(item.get("point_time") or item.get("time"))


def outcomes_in_window(
    outcomes: list[dict[str, Any]] | None,
    day_from: str | None = None,
    day_to: str | None = None,
    *,
    limit: int = 400,
) -> list[dict[str, Any]]:
    items = [item for item in (outcomes or []) if isinstance(item, dict)]
    start = str(day_from or "")[:10]
    end = str(day_to or "")[:10]
    if start and end:
        items = [item for item in items if start <= _outcome_day(item) <= end and _outcome_day(item)]
        if len(items) > max(int(limit), 1):
            items = items[-max(int(limit), 1) :]
        return items
    return items[-64:]


def session_to_dict(
    session: ReplaySession,
    *,
    day_from: str | None = None,
    day_to: str | None = None,
) -> dict[str, Any]:
    start = str(day_from or "")[:10] or None
    end = str(day_to or "")[:10] or None
    windowed = outcomes_in_window(session.outcomes, start, end)
    hint_days = sorted(
        {
            day
            for item in (session.outcomes or [])[-64:]
            if isinstance(item, dict)
            for day in [_outcome_day(item)]
            if day
        }
    )
    return {
        "replay_id": session.replay_id or session.session_id,
        "session_id": session.session_id,
        "slot": session.slot,
        "status": session.status,
        "cursor": session.cursor,
        "total": len(session.source_rows),
        "entity_cursors": dict(session.entity_cursors),
        "entity_overview": session_entity_overview(session),
        "clock_mode": session.clock_mode,
        "source_digest": session.source_digest,
        "execution_purpose": session.execution_purpose,
        "governance_eligible": session.governance_eligible,
        "batch_policy": session.batch_policy,
        "range_start": session.range_start,
        "range_end": session.range_end,
        "outcome_count": len(session.outcomes),
        "window_outcome_count": len(windowed),
        "recent_outcomes": windowed,
        "model_ref": session.model_ref,
        "dataset_profile_id": session.dataset_profile_id,
        "workflow_id": session.workflow_id,
        "selection_policy": session.selection_policy,
        "event_clock": _current_event_clock(session),
        "error": session.error,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "window_from": start,
        "window_to": end,
        "latest_outcome_days": hint_days,
    }


def create_session(
    *,
    session_id: str,
    profile: dict[str, Any],
    source_df: pd.DataFrame,
    model_ref: Optional[str] = None,
    slot: str = "pv_point",
    execution_purpose: Optional[str] = None,
    source_digest: Optional[str] = None,
    dataset_profile_id: Optional[str] = None,
    batch_policy: Optional[dict[str, Any]] = None,
) -> ReplaySession:
    purpose_ctx = resolve_execution_purpose(slot=slot, execution_purpose=execution_purpose)
    mapped, contract = apply_profile_map(source_df, profile)
    report = validate_point_schema(mapped, contract)
    if not report["valid"]:
        raise ValueError(f"replay source invalid: {report['issues']}")

    mapped = _sort_source_rows(mapped, contract)
    rows = [_json_safe_row(row) for row in mapped.to_dict(orient="records")]
    entity_keys = list(contract.get("entity_keys") or [])
    order_column = contract.get("time_column")
    range_start = range_end = None
    if order_column and rows:
        if contract.get("clock_mode") == "index":
            values = [row.get(order_column) for row in rows]
            range_start = min(values)
            range_end = max(values)
        else:
            values = pd.to_datetime([row.get(order_column) for row in rows], errors="coerce", utc=True)
            range_start = values.min().isoformat()
            range_end = values.max().isoformat()

    now = _now_iso()
    session = ReplaySession(
        session_id=session_id,
        replay_id=session_id,
        slot=slot,
        status="running",
        profile=contract,
        dataset_profile_id=dataset_profile_id,
        source_digest=source_digest or _digest_rows(rows[: min(len(rows), 32)]),
        clock_mode=str(contract.get("clock_mode") or "event_time"),
        execution_purpose=purpose_ctx["execution_purpose"],
        governance_eligible=purpose_ctx["governance_eligible"],
        model_ref=model_ref,
        source_rows=rows,
        cursor=0,
        entity_cursors=_init_entity_cursors(rows, entity_keys),
        batch_policy=dict(batch_policy or {"max_points_per_step": 1}),
        range_start=range_start,
        range_end=range_end,
        workflow_id=resolve_replay_workflow_id(slot),
        use_frozen_graph=True,
        selection_policy="earliest_event_time",
        created_at=now,
        updated_at=now,
    )
    _save_session(session)
    return session


def pause_session(session_id: str) -> ReplaySession:
    with _LOCK:
        session = load_session(session_id)
        if session.status in {"completed", "cancelled", "failed"}:
            raise ValueError(f"cannot pause replay in status={session.status!r}")
        session.status = "paused"
        _save_session(session)
        return session


def resume_session(session_id: str) -> ReplaySession:
    with _LOCK:
        session = load_session(session_id)
        if session.status != "paused":
            raise ValueError(f"cannot resume replay in status={session.status!r}")
        if session.cursor >= len(session.source_rows):
            session.status = "completed"
        else:
            session.status = "running"
        _save_session(session)
        return session


def cancel_session(session_id: str, *, reason: Optional[str] = None) -> ReplaySession:
    with _LOCK:
        session = load_session(session_id)
        if session.status in {"completed", "cancelled"}:
            return session
        session.status = "cancelled"
        if reason:
            session.error = reason
        _save_session(session)
        return session


def _current_event_clock(session: ReplaySession) -> Any:
    index = _pick_next_source_index(session)
    if index is None:
        return session.range_end
    time_column = str((session.profile or {}).get("time_column") or "event_time")
    return session.source_rows[index].get(time_column)


def _process_one_point(session: ReplaySession, *, idempotency_key: Optional[str], context_length: int) -> dict[str, Any]:
    pending_index = _pick_next_source_index(session)
    if pending_index is None:
        session.status = "completed"
        return {"window_status": "completed", "point_outcome": {}}
    pending_row = session.source_rows[pending_index]
    contract = session.profile
    entity_keys = list(contract.get("entity_keys") or [])
    entity_key = _entity_key(pending_row, entity_keys)
    history_df = pd.DataFrame(_entity_history_rows(session, entity_key, pending_index))
    time_column = str(contract.get("time_column") or "event_time")
    clock_mode = str(contract.get("clock_mode") or "event_time")
    if clock_mode == "index":
        history_df[time_column] = pd.to_numeric(history_df[time_column], errors="coerce")
    else:
        history_df[time_column] = pd.to_datetime(history_df[time_column], errors="coerce", utc=True)

    if session.use_frozen_graph and session.workflow_id:
        from services.timeseries_point.replay_graph_runner import run_frozen_replay_graph

        graph_result = run_frozen_replay_graph(
            session.workflow_id,
            replay_df=history_df,
            pending_row_index=len(history_df) - 1,
            model_ref=session.model_ref,
            profile_contract=contract,
        )
        outcome_dict = dict(graph_result["point_outcome"])
        outcome_dict["idempotency_key"] = idempotency_key
        entity_keys = list(contract.get("entity_keys") or [])
        entity_key = _entity_key(pending_row, entity_keys)
        if not outcome_dict.get("entity_key"):
            outcome_dict["entity_key"] = entity_key
        if not outcome_dict.get("point_time"):
            pt = pending_row.get(time_column)
            outcome_dict["point_time"] = pt.isoformat() if hasattr(pt, "isoformat") else pt
        window_status = "ready" if outcome_dict.get("kind") == "prediction" else "not_ready"
    else:
        from services.timeseries_point.causal_impute import causal_impute_existing_rows
        from services.timeseries_point.causal_window import build_causal_window_for_pending_point
        from services.timeseries_point.predict import predict_point_outcome

        entity_keys = list(contract.get("entity_keys") or [])
        feature_columns = list(contract.get("feature_columns") or [])
        imputed, _ = causal_impute_existing_rows(
            history_df,
            entity_keys=entity_keys,
            time_column=time_column,
            feature_columns=feature_columns,
        )
        window = build_causal_window_for_pending_point(
            imputed,
            entity_keys=entity_keys,
            time_column=time_column,
            feature_columns=feature_columns,
            pending_row_index=len(imputed) - 1,
            context_length=context_length,
        )
        outcome = predict_point_outcome(window, artifact_dir=session.model_ref)
        outcome_dict = {
            "kind": outcome.kind,
            "label": outcome.label,
            "confidence": outcome.confidence,
            "reason": outcome.reason,
            "evidence": outcome.evidence,
            "entity_key": window.entity_key,
            "point_time": window.point_time or pending_row.get(time_column),
            "idempotency_key": idempotency_key,
        }
        window_status = window.status

    entity_keys = list(contract.get("entity_keys") or [])
    entity_key = _entity_key(pending_row, entity_keys)
    session.entity_cursors[entity_key] = int(session.entity_cursors.get(entity_key, 0)) + 1
    session.committed_history.append(_json_safe_row(pending_row))
    session.outcomes.append(outcome_dict)
    session.cursor += 1
    if session.cursor >= len(session.source_rows):
        session.status = "completed"
    return {
        "window_status": window_status,
        "point_outcome": outcome_dict,
    }


def replay_next_point(
    session_id: str,
    *,
    idempotency_key: Optional[str] = None,
    context_length: int = 8,
) -> dict[str, Any]:
    """Process one or a deterministic small batch of pending points."""
    with _LOCK:
        session = load_session(session_id)
        if session.status == "paused":
            return {"status": "paused", "cursor": session.cursor, "total": len(session.source_rows)}
        if session.status == "cancelled":
            return {"status": "cancelled", "cursor": session.cursor, "total": len(session.source_rows)}
        if session.status == "failed":
            return {"status": "failed", "cursor": session.cursor, "total": len(session.source_rows), "error": session.error}
        if session.cursor >= len(session.source_rows):
            session.status = "completed"
            _save_session(session)
            return {"status": "completed", "cursor": session.cursor, "total": len(session.source_rows)}

        if idempotency_key:
            for outcome in session.outcomes:
                if outcome.get("idempotency_key") == idempotency_key:
                    return {
                        "status": "idempotent_replay",
                        "cursor": session.cursor,
                        "point_outcome": outcome,
                    }

        max_points = int((session.batch_policy or {}).get("max_points_per_step") or 1)
        max_points = max(1, min(max_points, 50))
        processed: list[dict[str, Any]] = []
        backup_history = list(session.committed_history)
        backup_outcomes = list(session.outcomes)
        backup_cursor = session.cursor
        backup_entity_cursors = dict(session.entity_cursors)
        backup_status = session.status
        try:
            for step in range(max_points):
                if _pick_next_source_index(session) is None:
                    session.status = "completed"
                    break
                step_key = f"{idempotency_key}:{step}" if idempotency_key and max_points > 1 else idempotency_key
                result = _process_one_point(session, idempotency_key=step_key, context_length=context_length)
                processed.append(result["point_outcome"])
            _save_session(session)
        except Exception as exc:
            session.committed_history = backup_history
            session.outcomes = backup_outcomes
            session.cursor = backup_cursor
            session.entity_cursors = backup_entity_cursors
            session.status = backup_status
            session.status = "failed"
            session.error = str(exc)
            _save_session(session)
            raise

        last = processed[-1] if processed else {}
        return {
            "status": "point_processed" if len(processed) == 1 else "batch_processed",
            "cursor": session.cursor,
            "total": len(session.source_rows),
            "points_processed": len(processed),
            "window_status": processed[-1].get("kind") if processed else None,
            "point_outcome": last,
            "point_outcomes": processed,
            "workflow_id": session.workflow_id,
            "governance_eligible": session.governance_eligible,
        }


def append_pending_feed_points(
    session_id: str,
    slot: str,
    *,
    limit: int = 1,
) -> int:
    """Pull pending real points into session source_rows (G12.2 feed extension)."""
    from services.timeseries_point.pending_point_feed import list_pending_points, mark_processed

    with _LOCK:
        session = load_session(session_id)
        pending = list_pending_points(slot, limit=max(1, min(limit, 32)))
        if not pending:
            return 0

        contract = session.profile
        entity_keys = list(contract.get("entity_keys") or [])
        time_column = str(contract.get("time_column") or "event_time")
        feature_columns = list(contract.get("feature_columns") or [])

        added = 0
        for point in pending:
            row: dict[str, Any] = {}
            entity_key = str(point.get("entity_key") or "")
            parts = entity_key.split("|") if entity_key else []
            for index, key in enumerate(entity_keys):
                row[key] = parts[index] if index < len(parts) else ""
            row[time_column] = point.get("point_time")
            for column in feature_columns:
                if column in point:
                    row[column] = point[column]
            safe_row = _json_safe_row(row)
            insert_at = len(session.source_rows)
            if _uses_event_time_picker(session) and entity_key:
                grouped = _entity_row_indices(session)
                indices = grouped.get(entity_key) or []
                new_time = _row_event_time(safe_row, time_column)
                for index in indices:
                    if _row_event_time(session.source_rows[index], time_column) > new_time:
                        insert_at = index
                        break
                else:
                    insert_at = (indices[-1] + 1) if indices else len(session.source_rows)
            session.source_rows.insert(insert_at, safe_row)
            point_id = str(point.get("point_id") or "")
            if point_id:
                mark_processed(slot, point_id)
            added += 1

        if session.status == "completed" and session.cursor < len(session.source_rows):
            session.status = "running"
        _save_session(session)
        return added
