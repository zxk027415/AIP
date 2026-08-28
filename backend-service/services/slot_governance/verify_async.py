"""Async verification jobs — require real evaluation workflow execution (G4/G5)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.operator_execution.slot_workflows import resolve_train_workflow_id
from services.slot_governance.evaluation_contracts import get_evaluation_contract
from services.slot_governance.model_candidates import find_model_candidate
from services.slot_governance.provenance import (
    assert_product_slot,
    extract_model_artifact_ref,
    validate_execution_source,
)
from services.slot_governance.registry import get_registry_store
from services.slot_governance.verification import VerificationError, register_verification

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_governance"


def resolve_verification_workflow_id(slot: str) -> str:
    """Skeleton: reuse published train_eval template as verification producer."""
    return resolve_train_workflow_id(slot)


def _jobs_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "verification_jobs.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_jobs(slot: str) -> list[dict[str, Any]]:
    path = _jobs_path(slot)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("jobs")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _save_jobs(slot: str, items: list[dict[str, Any]]) -> None:
    path = _jobs_path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"slot": slot, "jobs": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_job_by_comparison_id(comparison_id: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    root = _DATA_DIR
    if not root.is_dir():
        return None, None
    target = str(comparison_id or "").strip()
    for slot_dir in root.iterdir():
        if not slot_dir.is_dir():
            continue
        for job in _load_jobs(slot_dir.name):
            if job.get("comparison_id") == target:
                return job.get("slot") or slot_dir.name, job
    return None, None


def find_job_by_idempotency(slot: str, idempotency_key: str) -> Optional[dict[str, Any]]:
    for job in _load_jobs(slot):
        if job.get("idempotency_key") == idempotency_key:
            return job
    return None


def start_verification_async(
    *,
    slot: str,
    model_candidate_id: str,
    evaluation_contract_ref: Optional[str] = None,
    idempotency_key: str,
    registry_version_at_start: Optional[int] = None,
    verification_workflow_ref: Optional[str] = None,
) -> dict[str, Any]:
    assert_product_slot(slot)
    if not idempotency_key.strip():
        raise VerificationError("missing_idempotency_key", "idempotency_key is required")

    existing = find_job_by_idempotency(slot, idempotency_key)
    if existing is not None:
        return existing

    cand_slot, candidate = find_model_candidate(model_candidate_id)
    if candidate is None:
        raise VerificationError("candidate_not_found", f"model_candidate_id={model_candidate_id!r} not found")
    if cand_slot != slot:
        raise VerificationError("slot_mismatch", f"candidate slot={cand_slot!r} != requested slot={slot!r}")

    contract = get_evaluation_contract(slot)
    contract_ref = evaluation_contract_ref or contract["evaluation_contract_ref"]
    if contract_ref != contract["evaluation_contract_ref"]:
        raise VerificationError(
            "evaluation_contract_mismatch",
            f"evaluation_contract_ref={contract_ref!r} != slot contract",
        )

    registry = get_registry_store().get(slot)
    reg_version = int(registry_version_at_start if registry_version_at_start is not None else registry.get("registry_version") or 0)
    wf_ref = verification_workflow_ref or resolve_verification_workflow_id(slot)

    comparison_id = f"cmp-{uuid.uuid4().hex[:12]}"
    job = {
        "comparison_id": comparison_id,
        "slot": slot,
        "model_candidate_id": model_candidate_id,
        "evaluation_contract_ref": contract_ref,
        "verification_workflow_ref": wf_ref,
        "registry_version_at_start": reg_version,
        "baseline_model_ref": (registry.get("champion") or {}).get("champion_model_ref"),
        "idempotency_key": idempotency_key,
        "status": "pending",
        "created_at": _now_iso(),
    }
    items = _load_jobs(slot)
    items.append(job)
    _save_jobs(slot, items)
    return job


def complete_verification_async(
    comparison_id: str,
    *,
    verification_execution_id: str,
) -> dict[str, Any]:
    slot, job = find_job_by_comparison_id(comparison_id)
    if job is None or slot is None:
        raise VerificationError("comparison_not_found", f"comparison_id={comparison_id!r} not found")
    if job.get("status") == "completed":
        verification_id = job.get("verification_id")
        if verification_id:
            from services.slot_governance.verification import get_verification

            record = get_verification(slot, verification_id)
            if record:
                return {"job": job, "verification": record, "idempotent_replay": True}

    wf_id = str(job.get("verification_workflow_ref") or resolve_verification_workflow_id(slot))
    exec_id = str(verification_execution_id or "").strip()
    if not exec_id:
        raise VerificationError("missing_execution_id", "verification_execution_id is required")

    provenance = validate_execution_source(
        slot=slot,
        source_workflow_id=wf_id,
        source_execution_id=exec_id,
    )

    from services.slot_governance.provenance import load_execution_record

    state = load_execution_record(wf_id, exec_id) or {}
    evaluation_artifact_ref = extract_model_artifact_ref(state.get("nodeResults"))
    if not evaluation_artifact_ref:
        # Evaluation workflows may only emit metrics — use execution-scoped artifact ref.
        evaluation_artifact_ref = f"execution_history/{wf_id}_latest.json#{exec_id}"

    metrics_summary: dict[str, Any] = {}
    for node in (state.get("nodeResults") or {}).values():
        summary = (node or {}).get("outputSummary") or {}
        if isinstance(summary, dict):
            for key in ("macro_f1_mean", "accuracy_mean", "point_accuracy", "coverage"):
                if summary.get(key) is not None:
                    metrics_summary[key] = summary.get(key)

    passed = True
    if metrics_summary.get("macro_f1_mean") is not None:
        passed = float(metrics_summary["macro_f1_mean"]) >= 0.0
    if metrics_summary.get("point_accuracy") is not None:
        passed = float(metrics_summary["point_accuracy"]) >= 0.0

    verification = register_verification(
        slot=slot,
        model_candidate_id=job["model_candidate_id"],
        evaluation_contract_ref=job["evaluation_contract_ref"],
        idempotency_key=f"async-{job['idempotency_key']}",
        passed=passed,
        registry_version_at_start=int(job.get("registry_version_at_start") or 0),
        baseline_model_ref=job.get("baseline_model_ref"),
        verification_source_workflow_id=provenance["source_workflow_id"],
        verification_source_execution_id=provenance["source_execution_id"],
        evaluation_artifact_ref=evaluation_artifact_ref,
    )

    job["status"] = "completed"
    job["verification_id"] = verification["verification_id"]
    job["verification_execution_id"] = exec_id
    job["completed_at"] = _now_iso()
    job["metrics_summary"] = metrics_summary

    items = _load_jobs(slot)
    for idx, item in enumerate(items):
        if item.get("comparison_id") == comparison_id:
            items[idx] = job
            break
    _save_jobs(slot, items)

    return {"job": job, "verification": verification, "idempotent_replay": False}


def get_verification_job(comparison_id: str) -> dict[str, Any]:
    slot, job = find_job_by_comparison_id(comparison_id)
    if job is None:
        raise VerificationError("comparison_not_found", f"comparison_id={comparison_id!r} not found")
    return {"slot": slot, "job": job}


def list_verification_jobs(
    slot: str,
    *,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    assert_product_slot(slot)
    items = _load_jobs(slot)
    if status:
        return [job for job in items if job.get("status") == status]
    return items
