# @AI_GENERATED: scheduler tasks for all three PV product slots.
"""Scheduler tasks for pv_day, pv_point, and pv_tsc product slots."""
# @AI_GENERATED: end

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from services.operator_execution.slot_workflows import (
    resolve_predict_workflow_id,
    resolve_replay_workflow_id,
)
from services.scheduler.exceptions import SchedulerTaskSkipped
from services.scheduler.slot_product_evidence import persist_replay_tick_evidence
from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model, run_slot_workflow_sync

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_BINDINGS_PATH = _BACKEND_DIR / "data" / "timeseries_point" / "scheduler_bindings.json"
# @AI_GENERATED: pv_tsc 固定运行回执；读写端共用，禁止由 HTTP 参数覆盖路径。
_PV_TSC_STATUS_REL = Path(
    "data/iterative_labeling/pv_scheduler/pv_tsc/prediction_last_run.json"
)
_PV_TSC_STATUS_PATH = _BACKEND_DIR / _PV_TSC_STATUS_REL
DEFAULT_PV_TSC_STALE_AFTER_SECONDS = 36 * 60 * 60
# @AI_GENERATED: end

DEFAULT_PV_POINT_PROFILE_ID = "pv-point-snapshot-684bf7f6"
DEFAULT_CONTEXT_LENGTH = 8
DEFAULT_MAX_POINTS_PER_TICK = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_bindings() -> dict[str, Any]:
    if not _BINDINGS_PATH.is_file():
        return {}
    with _BINDINGS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _save_bindings(payload: dict[str, Any]) -> None:
    _BINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _BINDINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_BINDINGS_PATH)


def _binding_for_slot(slot: str) -> dict[str, Any]:
    all_bindings = _load_bindings()
    entry = all_bindings.get(slot)
    if isinstance(entry, dict):
        return dict(entry)
    if slot == "pv_point":
        return {
            "session_id": "sched-pv_point-default",
            "dataset_profile_id": DEFAULT_PV_POINT_PROFILE_ID,
            "context_length": DEFAULT_CONTEXT_LENGTH,
            "max_points_per_tick": DEFAULT_MAX_POINTS_PER_TICK,
        }
    return {}


def _ensure_replay_session(
    slot: str,
    *,
    model_artifact_ref: Optional[str],
    binding: dict[str, Any],
) -> str:
    from services.timeseries_point.replay_activity import create_session, load_session
    from services.timeseries_profiles.loader import load_dataset_from_profile
    from services.timeseries_profiles.store import TimeseriesProfileStore

    session_id = str(binding.get("session_id") or f"sched-{slot}-default")
    profile_id = str(binding.get("dataset_profile_id") or DEFAULT_PV_POINT_PROFILE_ID)
    store = TimeseriesProfileStore()
    profile_obj = store.get_dataset_profile(profile_id)
    profile = profile_obj.model_dump() if hasattr(profile_obj, "model_dump") else dict(profile_obj)

    try:
        session = load_session(session_id)
        if session.status in {"completed", "failed", "cancelled"}:
            raise FileNotFoundError(f"session rotate ({session.status})")
        if model_artifact_ref and session.model_ref != model_artifact_ref:
            session.model_ref = model_artifact_ref
            from services.timeseries_point import replay_activity as mod

            mod._save_session(session)
        return session_id
    except FileNotFoundError:
        pass

    df = load_dataset_from_profile(profile_obj)
    create_session(
        session_id=session_id,
        profile=profile,
        source_df=df,
        model_ref=model_artifact_ref,
        slot=slot,
        execution_purpose="product_workflow",
        dataset_profile_id=profile_id,
        batch_policy={"max_points_per_step": int(binding.get("max_points_per_tick") or 1)},
    )
    return session_id


def make_pv_day_predict_task() -> Callable[[], None]:
    """Daily cron: trigger published pv_day.predict workflow with registry model."""

    def _run() -> None:
        slot = "pv_day"
        model_ctx = resolve_slot_scheduler_model(slot)
        artifact = model_ctx.get("model_artifact_ref")
        model_id = model_ctx.get("model_id")
        if not artifact and not model_id:
            raise SchedulerTaskSkipped(
                f"pv_day 无 registry Champion/候选模型，无法触发 {resolve_predict_workflow_id(slot)}"
            )

        from services.slot_datasets.observability_ledger import mark_devices_detected, prepare_day_detect_batch

        batch = prepare_day_detect_batch(slot)
        if not batch.get("input_file_path"):
            raise SchedulerTaskSkipped(
                f"pv_day 水位日 {batch.get('watermark_day')} 无到齐设备（等待 {len(batch.get('waiting_devices') or [])}，跳过 {len(batch.get('skipped_devices') or [])}）"
            )

        workflow_id = resolve_predict_workflow_id(slot)
        result = run_slot_workflow_sync(
            slot=slot,
            workflow_id=workflow_id,
            model_artifact_ref=str(artifact) if artifact else None,
            model_id=str(model_id) if model_id else None,
            extra_global_config={"input_file_path": batch["input_file_path"]},
        )
        mark_devices_detected(
            slot,
            list(batch.get("ready_devices") or []),
            day=str(batch.get("watermark_day")),
            model_id=str(model_id) if model_id else None,
        )
        logger.info(
            "pv_day_predict_task: success execution_id=%s workflow=%s",
            result.get("execution_id"),
            workflow_id,
        )

    return _run


def make_pv_point_replay_tick_task() -> Callable[[], None]:
    """Periodic cron: advance replay_activity one deterministic batch for pv_point."""

    def _run() -> None:
        slot = "pv_point"
        model_ctx = resolve_slot_scheduler_model(slot)
        artifact = model_ctx.get("model_artifact_ref")
        if not artifact:
            raise SchedulerTaskSkipped(
                "pv_point 无 registry 模型 artifact，无法推进 replay_activity"
            )

        workflow_id = resolve_replay_workflow_id(slot)
        binding = _binding_for_slot(slot)
        session_id = _ensure_replay_session(
            slot,
            model_artifact_ref=str(artifact),
            binding=binding,
        )

        if binding.get("pending_feed_enabled"):
            from services.timeseries_point.replay_activity import append_pending_feed_points

            append_pending_feed_points(
                session_id,
                slot,
                limit=int(binding.get("max_points_per_tick") or DEFAULT_MAX_POINTS_PER_TICK),
            )

        from services.timeseries_point.replay_activity import replay_next_point

        tick_key = f"sched-{session_id}-{datetime.now(timezone.utc).replace(microsecond=0).strftime('%Y%m%dT%H%M%SZ')}"
        context_length = int(binding.get("context_length") or DEFAULT_CONTEXT_LENGTH)
        outcome = replay_next_point(
            session_id,
            idempotency_key=tick_key,
            context_length=context_length,
        )

        alarm_result = None
        point_outcome = dict(outcome.get("point_outcome") or {})
        if point_outcome:
            from services.timeseries_point.point_alarm_store import ingest_point_outcome

            ek = point_outcome.get("entity_key")
            if isinstance(ek, (list, tuple)):
                point_outcome["entity_key"] = "|".join(str(part) for part in ek)
            elif ek is None:
                point_outcome["entity_key"] = "__default__"
            alarm_result = ingest_point_outcome(slot, point_outcome)

        exec_id = persist_replay_tick_evidence(
            slot=slot,
            workflow_id=workflow_id,
            session_id=session_id,
            outcome=outcome,
            alarm_result=alarm_result,
        )
        status = outcome.get("status")
        if status == "completed":
            logger.info(
                "pv_point_replay_tick: replay session completed session_id=%s total=%s evidence=%s",
                session_id,
                outcome.get("total"),
                exec_id,
            )
            all_bindings = _load_bindings()
            entry = dict(all_bindings.get(slot) or binding)
            entry["last_completed_at"] = _utc_now_iso()
            stable_session_id = str(binding.get("session_id") or f"sched-{slot}-default")
            entry["session_id"] = stable_session_id
            all_bindings[slot] = entry
            _save_bindings(all_bindings)
            # 立即轮换：下一轮 tick 从 cursor=0 重新开始，避免 session 完成后「触发无响应」
            _ensure_replay_session(
                slot,
                model_artifact_ref=str(artifact),
                binding=entry,
            )
            return

        logger.info(
            "pv_point_replay_tick: session=%s status=%s cursor=%s/%s evidence=%s",
            session_id,
            status,
            outcome.get("cursor"),
            outcome.get("total"),
            exec_id,
        )

    return _run


# @AI_GENERATED
def _parse_status_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pv_tsc_stale_after_seconds(cron_expr: Optional[str]) -> int:
    if cron_expr:
        try:
            from services.scheduler.engine import SchedulerEngine

            cadence = SchedulerEngine._cron_interval_seconds(cron_expr)
            return int(max(3600, cadence * 1.5))
        except Exception:
            logger.warning("pv_tsc run-status: invalid cron_expr=%r", cron_expr)
    return DEFAULT_PV_TSC_STALE_AFTER_SECONDS


def _safe_status_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def get_pv_tsc_predict_run_status(
    *,
    cron_expr: Optional[str] = None,
    scheduler_last_execution_time: Optional[str] = None,
    scheduler_last_result: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Read the fixed pv_tsc receipt and classify its operational freshness.

    HTTP callers cannot supply a file path. The four-state contract is
    no_run_yet/model_pending/success/stale; business-level skipped outcomes remain
    visible under ``last_run`` instead of being misreported as transport failures.
    """
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    else:
        checked_at = checked_at.astimezone(timezone.utc)
    stale_after = _pv_tsc_stale_after_seconds(cron_expr)
    scheduler_time = _parse_status_datetime(scheduler_last_execution_time)
    base: dict[str, Any] = {
        "task_id": "pv_tsc_predict",
        "pipeline": "pv_tsc",
        "slot": "pv_tsc",
        "state": "stale",
        "reason": "unclassified",
        "checked_at": checked_at.replace(microsecond=0).isoformat(),
        "status_file": _PV_TSC_STATUS_REL.as_posix(),
        "cron_expr": cron_expr,
        "stale_after_seconds": stale_after,
        "model": {
            "artifact_registered": False,
            "source": None,
            "model_candidate_id": None,
            "registry_version": None,
        },
        "scheduler_task": {
            "last_execution_time": scheduler_last_execution_time,
            "last_result": scheduler_last_result,
        },
        "freshness": {
            "updated_at": None,
            "age_seconds": None,
            "is_stale": True,
            "model_matches_current": None,
        },
        "last_run": None,
    }

    try:
        model_ctx = resolve_slot_scheduler_model("pv_tsc")
    except Exception:
        base["reason"] = "model_resolution_failed"
        return base

    artifact_registered = bool(str(model_ctx.get("model_artifact_ref") or "").strip())
    current_candidate = str(model_ctx.get("model_candidate_id") or "").strip() or None
    current_version = model_ctx.get("registry_version")
    base["model"] = {
        "artifact_registered": artifact_registered,
        "source": model_ctx.get("source"),
        "model_candidate_id": current_candidate,
        "registry_version": current_version,
    }
    if not artifact_registered:
        base["state"] = "model_pending"
        base["reason"] = "no_registered_model_artifact"
        base["freshness"]["is_stale"] = False
        return base

    if not _PV_TSC_STATUS_PATH.is_file():
        if scheduler_last_result == "failed" and scheduler_time is not None:
            base["state"] = "stale"
            base["reason"] = "scheduler_failed_without_receipt"
        else:
            base["state"] = "no_run_yet"
            base["reason"] = "status_receipt_not_created"
            base["freshness"]["is_stale"] = False
        return base

    try:
        payload = json.loads(_PV_TSC_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        base["reason"] = "invalid_status_payload"
        return base
    if not isinstance(payload, dict):
        base["reason"] = "invalid_status_payload"
        return base

    updated_at = _parse_status_datetime(payload.get("updated_at"))
    receipt_candidate = str(payload.get("model_candidate_id") or "").strip() or None
    receipt_version = payload.get("registry_version")
    if current_candidate:
        model_matches = receipt_candidate == current_candidate
    elif current_version is not None and receipt_version is not None:
        model_matches = receipt_version == current_version
    else:
        model_matches = True

    batch_ids = payload.get("batch_ids")
    review_ids = payload.get("review_ids")
    last_run = {
        "outcome": payload.get("status"),
        "reason": payload.get("reason"),
        "modeling_path": payload.get("modeling_path"),
        "strategy_name": payload.get("strategy_name"),
        "window_start": payload.get("window_start"),
        "window_end": payload.get("window_end"),
        "points_detected": _safe_status_int(payload.get("points_detected")),
        "points_deferred": _safe_status_int(payload.get("points_deferred")),
        "devices_processed": _safe_status_int(payload.get("devices_processed")),
        "batch_ids": list(batch_ids) if isinstance(batch_ids, list) else [],
        "review_ids": list(review_ids) if isinstance(review_ids, list) else [],
        "started_at": payload.get("started_at"),
        "updated_at": payload.get("updated_at"),
        "model_source": payload.get("model_source"),
        "model_candidate_id": receipt_candidate,
        "registry_version": receipt_version,
    }
    base["last_run"] = last_run
    base["freshness"]["updated_at"] = payload.get("updated_at")
    base["freshness"]["model_matches_current"] = model_matches

    if updated_at is None:
        base["reason"] = "missing_or_invalid_updated_at"
        return base
    age_seconds = (checked_at - updated_at).total_seconds()
    base["freshness"]["age_seconds"] = round(max(age_seconds, 0.0), 3)
    if age_seconds < -300:
        base["reason"] = "status_clock_skew"
        return base
    if scheduler_last_result == "failed" and scheduler_time and scheduler_time > updated_at:
        base["reason"] = "scheduler_failed_after_last_receipt"
        return base
    if not model_matches:
        base["reason"] = "model_changed_since_last_receipt"
        return base
    if age_seconds > stale_after:
        base["reason"] = "status_receipt_expired"
        return base
    if str(payload.get("reason") or "") in {
        "model_pending",
        "missing_champion_model_ref",
    }:
        base["state"] = "model_pending"
        base["reason"] = "last_run_model_pending"
        base["freshness"]["is_stale"] = False
        return base

    base["state"] = "success"
    base["reason"] = "fresh_run_receipt"
    base["freshness"]["is_stale"] = False
    return base


def make_pv_tsc_predict_task(pv_repo: Any) -> Callable[[], None]:
    """Periodic cron: run the pv_tsc MultiRocket Challenger in an isolated slot.

    模型来自统一 slot-governance registry，解析顺序与部署页一致：Champion →
    rolling_detect_model → Challenger → latest candidate。首次上线可仅登记 Challenger，
    不要求提前 Promote；仓储由应用启动层注入，任务不再创建第二套 DB 生命周期。
    """

    def _run() -> None:
        slot = "pv_tsc"
        model_ctx = resolve_slot_scheduler_model(slot)
        artifact = str(model_ctx.get("model_artifact_ref") or "").strip()
        if not artifact:
            raise SchedulerTaskSkipped(
                "pv_tsc 无可用 Champion/rolling/Challenger 模型工件，跳过本轮检测"
            )

        from services.scheduler.pv_dual_path.scheduler import DualPathScheduler
        from services.scheduler.pv_dual_path.tsc_strategy import TscDailyStrategy
        from services.scheduler.tasks.pv_fault_tasks import _atomic_write_json
        from services.slot_governance.registry import get_registry_store

        def _read_tsc_paths(requested_slot: str) -> dict[str, Any]:
            if requested_slot != slot:
                raise ValueError(f"pv_tsc task received unexpected slot={requested_slot!r}")
            registry = get_registry_store().get(slot)
            activation_epoch_id = str(
                registry.get("active_activation_epoch_id") or "lab-unbounded"
            ).strip()
            return {
                "production_path": "tsc",
                "fallback_path": "tsc",
                "active_activation_epoch_id": activation_epoch_id,
                "path_models": {
                    "tsc": {
                        "model_ref": artifact,
                        "model_candidate_id": model_ctx.get("model_candidate_id"),
                        "source": model_ctx.get("source"),
                    }
                },
                "production_model_ref": artifact,
                "registry_source": "slot_governance",
            }

        def _write_tsc_status(payload: dict[str, Any]) -> None:
            enriched = {
                **payload,
                "task_id": "pv_tsc_predict",
                "pipeline": "pv_tsc",
                "slot": slot,
                "model_source": model_ctx.get("source"),
                "model_candidate_id": model_ctx.get("model_candidate_id"),
                "registry_version": model_ctx.get("registry_version"),
            }
            _atomic_write_json(_PV_TSC_STATUS_PATH, enriched)

        scheduler = DualPathScheduler(
            strategies={"tsc": TscDailyStrategy(pv_repo)},
            read_modeling_paths=_read_tsc_paths,
            status_writer=_write_tsc_status,
        )
        result = scheduler.dispatch(slot=slot)
        logger.info(
            "pv_tsc_predict_task: status=%s source=%s predictions=%d devices=%d",
            result.status,
            model_ctx.get("source"),
            result.points_detected,
            result.devices_processed,
        )

    return _run
# @AI_GENERATED: end
