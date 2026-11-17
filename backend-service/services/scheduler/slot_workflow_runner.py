"""Run published slot product workflows from the scheduler (no HTTP layer)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _runtime_artifact_path(model_ref: str) -> str:
    path = str(model_ref or "").replace("\\", "/").strip()
    if path.startswith("backend-service/"):
        path = path[len("backend-service/") :]
    return path


def _artifact_model_id(artifact_ref: Optional[str], candidate_id: Optional[str] = None) -> Optional[str]:
    if artifact_ref:
        name = Path(str(artifact_ref).replace("\\", "/")).name
        if name.endswith(".pkl"):
            return Path(name).stem
        rel = Path(str(artifact_ref).replace("\\", "/"))
        if (rel / "model.pt").is_file() or ((_BACKEND_DIR.parent / artifact_ref / "model.pt").is_file()):
            return None
        return name or (str(candidate_id) if candidate_id else None)
    if candidate_id and not str(candidate_id).startswith("mc-"):
        return str(candidate_id)
    return None


def resolve_slot_scheduler_model(slot: str) -> dict[str, Any]:
    """Resolve detect model: champion → rolling_detect_model → challenger → latest candidate."""
    from services.slot_governance.model_candidates import find_model_candidate, list_model_candidates
    from services.slot_governance.registry import get_registry_store

    registry = get_registry_store().get(slot)
    champion = registry.get("champion") if isinstance(registry.get("champion"), dict) else {}
    challenger = registry.get("challenger") if isinstance(registry.get("challenger"), dict) else {}
    rolling = registry.get("rolling_detect_model") if isinstance(registry.get("rolling_detect_model"), dict) else {}
    source = "registry_fallback"
    candidate: Optional[dict[str, Any]] = None
    candidate_id = None
    artifact_ref = None

    rolling_cid = str(rolling.get("model_candidate_id") or "").strip() or None
    rolling_art = str(rolling.get("model_artifact_ref") or "").strip() or None
    champion_cid = str(
        (champion or {}).get("champion_model_ref")
        or (champion or {}).get("champion_model_candidate_id")
        or ""
    ).strip() or None
    champion_art = str((champion or {}).get("champion_model_artifact_ref") or "").strip() or None

    if champion_cid or champion_art:
        source = "champion"
        candidate_id = champion_cid
        artifact_ref = champion_art
        if champion_cid:
            _, found = find_model_candidate(str(champion_cid))
            candidate = found
            if found:
                artifact_ref = found.get("model_artifact_ref") or artifact_ref
                candidate_id = found.get("model_candidate_id") or candidate_id
    elif rolling_cid or rolling_art:
        source = "rolling_detect_model"
        candidate_id = rolling_cid
        artifact_ref = rolling_art
        if rolling_cid:
            _, found = find_model_candidate(str(rolling_cid))
            candidate = found
            if found:
                artifact_ref = found.get("model_artifact_ref") or artifact_ref
                candidate_id = found.get("model_candidate_id") or candidate_id
    else:
        candidate_id = (
            (challenger or {}).get("challenger_model_candidate_id")
            or (challenger or {}).get("challenger_model_ref")
        )
        artifact_ref = (challenger or {}).get("challenger_model_artifact_ref")
        # @AI_GENERATED: 保留统一 registry 中 Challenger 的真实模型角色，供调度回执与审核证据消费。
        if candidate_id or artifact_ref:
            source = "challenger"
        # @AI_GENERATED: end
        if candidate_id:
            _, found = find_model_candidate(str(candidate_id))
            candidate = found
            if found:
                artifact_ref = found.get("model_artifact_ref") or artifact_ref
                candidate_id = found.get("model_candidate_id") or candidate_id

    if not artifact_ref and not candidate_id:
        registered = list_model_candidates(slot)
        for item in reversed(registered):
            if str(item.get("status") or "") in {"registered", "verified", "passed"}:
                candidate = item
                candidate_id = item.get("model_candidate_id")
                artifact_ref = item.get("model_artifact_ref")
                source = "latest_candidate"
                break

    model_id = _artifact_model_id(str(artifact_ref) if artifact_ref else None, str(candidate_id) if candidate_id else None)

    return {
        "slot": slot,
        "model_candidate_id": candidate_id,
        "model_artifact_ref": artifact_ref,
        "model_id": model_id,
        "registry_version": registry.get("registry_version"),
        "has_champion": bool(champion and champion.get("champion_model_ref")),
        "source": source,
        "candidate": candidate,
    }


def _node_config_mapping(config: Any) -> dict[str, Any]:
    if config is None:
        return {}
    if isinstance(config, dict):
        return dict(config)
    if hasattr(config, "model_dump"):
        return dict(config.model_dump())
    if hasattr(config, "dict"):
        return dict(config.dict())
    return {}


def _write_node_config(data: Any, mapping: dict[str, Any]) -> None:
    config = getattr(data, "config", None)
    if isinstance(config, dict):
        config.update(mapping)
        data.config = config
        return
    if config is None:
        data.config = mapping
        return
    try:
        data.config = type(config)(**mapping)
        return
    except Exception:
        pass
    for key, value in mapping.items():
        try:
            setattr(config, key, value)
        except Exception:
            pass


def _patch_workflow_predict_model(workflow, *, model_id: Optional[str], model_ref: Optional[str]) -> None:
    if not model_id and not model_ref:
        return
    runtime_ref = _runtime_artifact_path(model_ref or "")
    for node in workflow.nodes:
        data = getattr(node, "data", None)
        if data is None:
            continue
        mapping = _node_config_mapping(getattr(data, "config", None))
        function_id = str(mapping.get("functionId") or "")
        if not function_id:
            continue
        changed = False
        if function_id in {"random_forest_classifier", "batch_classifier_predict"} and model_id:
            mapping["model_id"] = model_id
            changed = True
        if function_id == "feature_select" and runtime_ref.endswith(".pkl"):
            mapping["model_path"] = runtime_ref
            changed = True
        if function_id.startswith("ts_point_") and model_ref:
            mapping["model_ref"] = model_ref
            changed = True
        # @AI_GENERATED: inject the governed TSC directory into its prediction node.
        if function_id == "tsc_predict" and model_ref:
            mapping["model_ref"] = runtime_ref or model_ref
            changed = True
        # @AI_GENERATED: end
        if changed:
            _write_node_config(data, mapping)


# @AI_GENERATED: reusable persisted canvas execution for scheduler and cumulative retrain

def _patch_workflow_operator_params(
    workflow: Any,
    overrides: Optional[dict[str, dict[str, Any]]],
) -> None:
    """Apply explicit functionId-scoped overrides to a loaded workflow copy."""
    if not overrides:
        return
    for node in workflow.nodes:
        data = getattr(node, "data", None)
        if data is None:
            continue
        mapping = _node_config_mapping(getattr(data, "config", None))
        function_id = str(mapping.get("functionId") or "").strip()
        node_overrides = overrides.get(function_id)
        if not isinstance(node_overrides, dict):
            continue
        mapping.update(node_overrides)
        _write_node_config(data, mapping)


def run_slot_workflow_sync(
    *,
    slot: str,
    workflow_id: str,
    execution_purpose: str = "product_workflow",
    model_artifact_ref: Optional[str] = None,
    model_id: Optional[str] = None,
    extra_global_config: Optional[dict[str, Any]] = None,
    operator_param_overrides: Optional[dict[str, dict[str, Any]]] = None,
    execution_metadata: Optional[dict[str, Any]] = None,
    require_persisted_execution: bool = False,
    trigger_source: str = "scheduler",
    governance_eligible: Optional[bool] = None,
) -> dict[str, Any]:
    """Execute one frozen workflow synchronously and persist auditable evidence.

    ``operator_param_overrides`` is keyed by ``functionId`` and only patches the
    in-memory workflow copy. ``execution_metadata`` is persisted on the execution
    record but is never forwarded into operators. Callers that gate cursor/model
    governance can set ``require_persisted_execution`` so evidence loss fails
    closed instead of advancing product state. Validation executions default to
    ``governance_eligible=False``; product/training callers may override explicitly.
    """
    from api.workflows_enhanced import (
        _execute_pipeline_sync,
        _graph_digest_for_execution,
        _initial_execution_store_entry,
        _persist_latest_execution,
        load_workflow_from_file,
    )
    from api import workflows_enhanced as wf_mod

    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        raise ValueError(f"workflow not found: {workflow_id}")

    _patch_workflow_predict_model(
        workflow,
        model_id=model_id,
        model_ref=model_artifact_ref,
    )
    _patch_workflow_operator_params(workflow, operator_param_overrides)

    normalized_trigger = str(trigger_source or "scheduler").strip() or "scheduler"
    scheduler_trigger = normalized_trigger == "scheduler"
    effective_governance_eligible = (
        bool(governance_eligible)
        if governance_eligible is not None
        else normalized_trigger != "validation" and execution_purpose != "validation"
    )
    request_gc = {
        "operate_status": "online",
        "run_mode": "online",
        "scheduler_trigger": scheduler_trigger,
        "slot": slot,
    }
    if model_artifact_ref:
        request_gc["model_ref"] = model_artifact_ref
        request_gc["backtest_model_ref"] = model_artifact_ref
    if model_id:
        request_gc["model_id"] = model_id
    if extra_global_config:
        request_gc.update(extra_global_config)

    input_file = (
        str((extra_global_config or {}).get("input_file_path") or "")
        .replace("\\", "/")
        .strip()
    )
    if input_file:
        for node in workflow.nodes:
            data = getattr(node, "data", None)
            if data is None:
                continue
            mapping = _node_config_mapping(getattr(data, "config", None))
            function_id = str(mapping.get("functionId") or "")
            if function_id in {"load_csv", "load_parquet", "load_labeled_dataset"}:
                mapping["file_path"] = input_file
                _write_node_config(data, mapping)

    metadata = dict(workflow.metadata or {})
    template_gc = dict(metadata.get("global_config") or {})
    metadata["global_config"] = {**template_gc, **request_gc}
    metadata["slot"] = slot
    workflow.metadata = metadata

    execution_prefix = {
        "scheduler": "sched",
        "cumulative_retrain": "retrain",
        "validation": "validation",
    }.get(normalized_trigger)
    if execution_prefix is None:
        execution_prefix = "".join(
            char if char.isalnum() else "-" for char in normalized_trigger.lower()
        ).strip("-")[:24] or "external"
    execution_id = f"exec-{execution_prefix}-{uuid.uuid4().hex[:12]}"
    slot_context = {
        "slot": slot,
        "execution_purpose": execution_purpose,
        "governance_eligible": effective_governance_eligible,
        "effective_global_config": metadata["global_config"],
    }
    wf_mod._execution_store[execution_id] = _initial_execution_store_entry(
        execution_id=execution_id,
        workflow_id=workflow_id,
        slot_context=slot_context,
        source_workflow_version=getattr(workflow, "version", None),
        graph_digest=_graph_digest_for_execution(workflow),
    )

    state = wf_mod._execution_store[execution_id]
    state["status"] = "running"
    state["started_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    state["execution_metadata"] = dict(execution_metadata or {})

    execution_data = {
        "slot": slot,
        "execution_purpose": execution_purpose,
        "global_config": request_gc,
        "scheduler_trigger": scheduler_trigger,
    }
    result = _execute_pipeline_sync(workflow, execution_data, execution_id=execution_id)

    state["status"] = "success" if result.get("success") else "failed"
    state["scheduler_trigger"] = scheduler_trigger
    state["trigger_source"] = normalized_trigger
    state["source"] = f"{normalized_trigger}:{workflow_id}"
    state["nodeResults"] = result.get("nodeResults") or {}
    state["logs"] = result.get("logs") or []
    state["executionTime"] = result.get("executionTime")
    state["error"] = result.get("error")
    state["metrics"] = result.get("metrics")
    state["model_id"] = result.get("model_id") or model_id
    state["nodeDurations"] = result.get("nodeDurations")
    state["fault_predictions"] = result.get("fault_predictions")
    state["fault_timeseries"] = result.get("fault_timeseries")
    state["forecast_timestamps"] = result.get("forecast_timestamps")
    state["forecast_values"] = result.get("forecast_values")
    state["y_true"] = result.get("y_true")
    state["y_pred"] = result.get("y_pred")
    state["finished_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    persistence_error: Optional[Exception] = None
    try:
        _persist_latest_execution(workflow_id, state)
    except Exception as exc:  # noqa: BLE001
        persistence_error = exc
        logger.warning("persist latest execution failed wf=%s: %s", workflow_id, exc)
    if persistence_error is not None and require_persisted_execution:
        raise RuntimeError(
            f"workflow execution succeeded but evidence persistence failed: {persistence_error}"
        ) from persistence_error

    if not result.get("success"):
        raise RuntimeError(result.get("error") or f"workflow execution failed: {workflow_id}")

    return {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "source_workflow_version": state.get("source_workflow_version"),
        "slot": slot,
        "success": True,
        "execution_status": state.get("status"),
        "model_id": state.get("model_id"),
        "node_results": state.get("nodeResults") or {},
        "metrics": state.get("metrics"),
        "fault_predictions": state.get("fault_predictions"),
        "execution_time": state.get("executionTime"),
    }
# @AI_GENERATED: end

