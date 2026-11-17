"""Validate workflow execution provenance for slot governance."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from services.operator_execution.slot_workflows import resolve_train_workflow_id
from services.execution_history.store import load_execution_record

_SUCCESS_STATUSES = frozenset({"success", "succeeded"})


class ProvenanceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_benchmark_slot(slot: str) -> bool:
    return str(slot or "").strip().startswith("benchmark_")


def assert_product_slot(slot: str) -> None:
    key = str(slot or "").strip()
    if not key:
        raise ProvenanceError("missing_slot", "slot is required")
    if is_benchmark_slot(key):
        raise ProvenanceError(
            "benchmark_governance_forbidden",
            f"benchmark slot {key!r} cannot write product governance records",
        )


def load_persisted_execution(workflow_id: str, execution_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    return load_execution_record(workflow_id, execution_id)


# @AI_GENERATED: TSC directory artifacts expose several compatible summary aliases.
def extract_model_artifact_ref(node_results: Any) -> Optional[str]:
    if not isinstance(node_results, dict):
        return None
    aliases = ("model_artifact_ref", "model_path", "model_ref", "model_dir")
    for node in node_results.values():
        if not isinstance(node, dict):
            continue
        summary = node.get("outputSummary")
        if not isinstance(summary, dict):
            continue
        for key in aliases:
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None
# @AI_GENERATED: end


def validate_execution_provenance(
    *,
    slot: str,
    source_workflow_id: str,
    source_execution_id: str,
    model_artifact_ref: Optional[str] = None,
    expected_status: str = "success",
) -> dict[str, Any]:
    """
    Ensure a succeeded execution exists and matches slot/workflow/execution_id.

    Returns normalized provenance dict for persistence.
    """
    assert_product_slot(slot)

    wf_id = str(source_workflow_id or "").strip()
    exec_id = str(source_execution_id or "").strip()
    if not wf_id or not exec_id:
        raise ProvenanceError("missing_provenance", "source_workflow_id and source_execution_id are required")

    state = load_execution_record(wf_id, exec_id)
    if state is None:
        raise ProvenanceError(
            "execution_not_found",
            f"no persisted execution for workflow_id={wf_id!r} execution_id={exec_id!r}",
        )

    persisted_exec_id = str(state.get("execution_id") or "").strip()
    if persisted_exec_id != exec_id:
        raise ProvenanceError(
            "execution_id_mismatch",
            f"expected execution_id={exec_id!r}, persisted={persisted_exec_id!r}",
        )

    status = str(state.get("status") or "").strip().lower()
    allowed = _SUCCESS_STATUSES if expected_status in _SUCCESS_STATUSES else {expected_status}
    if status not in allowed:
        raise ProvenanceError(
            "execution_not_succeeded",
            f"execution status={status!r} is not allowed (need {sorted(allowed)!r})",
        )

    exec_slot = str(state.get("slot") or "").strip()
    if exec_slot and exec_slot != slot:
        raise ProvenanceError(
            "slot_mismatch",
            f"execution slot={exec_slot!r} != requested slot={slot!r}",
        )

    if state.get("governance_eligible") is False:
        raise ProvenanceError(
            "governance_not_eligible",
            f"execution {exec_id!r} is not eligible for product governance writes",
        )

    # When execution has no slot field (legacy runs), infer from train workflow mapping.
    if not exec_slot:
        inferred = resolve_train_workflow_id(slot)
        if wf_id != inferred and wf_id != resolve_train_workflow_id(None):
            raise ProvenanceError(
                "slot_inference_failed",
                f"execution missing slot and workflow_id={wf_id!r} does not match slot={slot!r}",
            )

    artifact = (model_artifact_ref or "").strip() or extract_model_artifact_ref(state.get("nodeResults"))
    if not artifact:
        raise ProvenanceError(
            "missing_model_artifact",
            "model_artifact_ref is required and could not be inferred from execution nodeResults",
        )

    return {
        "slot": slot,
        "source_workflow_id": wf_id,
        "source_workflow_version": state.get("source_workflow_version"),
        "source_execution_id": exec_id,
        "model_artifact_ref": artifact,
        "execution_status": status,
    }


def validate_execution_source(
    *,
    slot: str,
    source_workflow_id: str,
    source_execution_id: str,
    expected_status: str = "success",
) -> dict[str, Any]:
    """Light provenance check for annotation / evaluation producers (no artifact required)."""
    assert_product_slot(slot)

    wf_id = str(source_workflow_id or "").strip()
    exec_id = str(source_execution_id or "").strip()
    if not wf_id or not exec_id:
        raise ProvenanceError("missing_provenance", "source_workflow_id and source_execution_id are required")

    state = load_execution_record(wf_id, exec_id)
    if state is None:
        raise ProvenanceError(
            "execution_not_found",
            f"no persisted execution for workflow_id={wf_id!r} execution_id={exec_id!r}",
        )

    persisted_exec_id = str(state.get("execution_id") or "").strip()
    if persisted_exec_id != exec_id:
        raise ProvenanceError(
            "execution_id_mismatch",
            f"expected execution_id={exec_id!r}, persisted={persisted_exec_id!r}",
        )

    status = str(state.get("status") or "").strip().lower()
    allowed = _SUCCESS_STATUSES if expected_status in _SUCCESS_STATUSES else {expected_status}
    if status not in allowed:
        raise ProvenanceError(
            "execution_not_succeeded",
            f"execution status={status!r} is not allowed (need {sorted(allowed)!r})",
        )

    exec_slot = str(state.get("slot") or "").strip()
    if exec_slot and exec_slot != slot:
        raise ProvenanceError(
            "slot_mismatch",
            f"execution slot={exec_slot!r} != requested slot={slot!r}",
        )

    if state.get("governance_eligible") is False:
        raise ProvenanceError(
            "governance_not_eligible",
            f"execution {exec_id!r} is not eligible for product governance writes",
        )

    return {
        "slot": slot,
        "source_workflow_id": wf_id,
        "source_workflow_version": state.get("source_workflow_version"),
        "source_execution_id": exec_id,
        "execution_status": status,
    }
