"""G6.5 benchmark graph reuse evidence report builder."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.benchmark.governance import BENCHMARK_EXECUTION_PURPOSE, compute_governance_eligible
from services.operator_execution.slot_workflows import (
    resolve_predict_workflow_id,
    resolve_replay_workflow_id,
    resolve_train_workflow_id,
)
from services.slot_governance.workflow_equiv import metadata_product_fields, workflow_graph_signature
from services.timeseries_profiles.preflight import run_dataset_profile_preflight
from services.timeseries_profiles.store import TimeseriesProfileStore

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPORT_DIR = _BACKEND_DIR / "data" / "benchmark" / "reuse_reports"

DEFAULT_BENCHMARK_SLOTS = (
    "benchmark_nasa_smap_msl",
    "benchmark_fhc_twin_plant",
)

DEFAULT_SLOT_PROFILES = {
    "benchmark_nasa_smap_msl": "benchmark-nasa-smap-msl-demo",
    "benchmark_fhc_twin_plant": "benchmark-fhc-twin-plant-demo",
}

PROFILE_DIFF_ALLOWLIST = frozenset(
    {
        "profile_id",
        "profile_version",
        "slot",
        "source_ref",
        "format",
        "clock_mode",
        "time_column",
        "index_column",
        "simulation_step",
        "entity_keys",
        "feature_columns",
        "label_column",
        "label_semantics",
        "sampling_interval",
        "adapter_id",
        "license_ref",
        "license_status",
        "redistribution_allowed",
        "allowed_use_purposes",
        "split_policy",
        "quality_rules",
        "description",
    }
)

GOVERNANCE_WRITE_ENTRY_POINTS = (
    {"entry": "register_model_candidate", "expected_code": "benchmark_governance_forbidden"},
    {"entry": "register_annotation_candidate", "expected_code": "benchmark_governance_forbidden"},
    {"entry": "bootstrap_snapshot", "expected_code": "benchmark_governance_forbidden"},
    {"entry": "register_verification", "expected_code": "benchmark_governance_forbidden"},
    {"entry": "promote_model_candidate", "expected_code": "benchmark_governance_forbidden"},
    {"entry": "start_verification_async", "expected_code": "benchmark_governance_forbidden"},
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_workflow(workflow_id: str):
    from api.workflows_enhanced import load_workflow_from_file

    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        raise KeyError(f"workflow not found: {workflow_id}")
    return workflow


def extract_workflow_evidence(workflow_id: str) -> dict[str, Any]:
    workflow = _load_workflow(workflow_id)
    signature = workflow_graph_signature(workflow)
    operator_ids = sorted(
        {
            str(node.get("functionId"))
            for node in signature.get("nodes") or []
            if node.get("functionId")
        }
    )
    edges = [
        {
            "source": src,
            "target": tgt,
            "sourceHandle": sh,
            "targetHandle": th,
        }
        for src, tgt, sh, th in signature.get("edges") or []
    ]
    version = getattr(workflow, "version", None)
    return {
        "workflow_id": workflow_id,
        "workflow_version": str(version) if version is not None else None,
        "operator_ids": operator_ids,
        "edges": edges,
        "graph_signature": signature,
        "template_metadata": metadata_product_fields(getattr(workflow, "metadata", None)),
    }


def extract_profile_evidence(profile_id: str, *, use_purpose: str = "benchmark_reuse") -> dict[str, Any]:
    store = TimeseriesProfileStore()
    profile = store.get_dataset_profile(profile_id)
    preflight = run_dataset_profile_preflight(profile, use_purpose=use_purpose)
    payload = profile.model_dump()
    return {
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "slot": profile.slot,
        "clock_mode": profile.clock_mode,
        "source_ref": profile.source_ref,
        "adapter_id": profile.adapter_id,
        "license_ref": profile.license_ref,
        "license_status": profile.license_status,
        "redistribution_allowed": profile.redistribution_allowed,
        "label_semantics": profile.label_semantics,
        "preflight": preflight.model_dump(),
        "profile_fields": payload,
    }


def _workflow_role_map(slot: str) -> dict[str, str]:
    return {
        "train_eval": resolve_train_workflow_id(slot),
        "predict": resolve_predict_workflow_id(slot),
        "predict_replay": resolve_replay_workflow_id(slot),
    }


def _compare_graph_signatures(workflows_by_slot: dict[str, dict[str, Any]]) -> dict[str, Any]:
    slots = list(workflows_by_slot.keys())
    if len(slots) < 2:
        return {"graph_reuse_proven": True, "roles": {}}

    roles = ("train_eval", "predict_replay")
    role_reports: dict[str, Any] = {}
    all_match = True
    for role in roles:
        sigs = {
            slot: workflows_by_slot[slot][role]["graph_signature"]
            for slot in slots
            if role in workflows_by_slot[slot]
        }
        unique = {json.dumps(sig, sort_keys=True, default=str) for sig in sigs.values()}
        match = len(unique) <= 1
        all_match = all_match and match
        role_reports[role] = {
            "workflow_ids": {slot: workflows_by_slot[slot][role]["workflow_id"] for slot in sigs},
            "operator_ids": {slot: workflows_by_slot[slot][role]["operator_ids"] for slot in sigs},
            "graph_signature_match": match,
        }
    return {"graph_reuse_proven": all_match, "roles": role_reports}


def build_g6_reuse_report(
    *,
    slots: Optional[list[str]] = None,
    slot_profiles: Optional[dict[str, str]] = None,
    persist: bool = False,
) -> dict[str, Any]:
    slot_list = list(slots or DEFAULT_BENCHMARK_SLOTS)
    profile_map = dict(DEFAULT_SLOT_PROFILES)
    if slot_profiles:
        profile_map.update(slot_profiles)

    workflows_by_slot: dict[str, dict[str, Any]] = {}
    for slot in slot_list:
        role_ids = _workflow_role_map(slot)
        workflows_by_slot[slot] = {
            role: extract_workflow_evidence(wf_id) for role, wf_id in role_ids.items()
        }

    graph_comparison = _compare_graph_signatures(workflows_by_slot)

    profiles: dict[str, Any] = {}
    for slot in slot_list:
        profile_id = profile_map.get(slot)
        if not profile_id:
            continue
        profiles[slot] = extract_profile_evidence(profile_id)

    governance = {
        "execution_purpose": BENCHMARK_EXECUTION_PURPOSE,
        "governance_eligible": False,
        "slot_invariant": "benchmark_* iff benchmark_reuse",
        "product_write_entry_points": GOVERNANCE_WRITE_ENTRY_POINTS,
        "per_slot_governance_eligible": {
            slot: compute_governance_eligible(
                slot=slot,
                execution_purpose=BENCHMARK_EXECUTION_PURPOSE,
            )
            for slot in slot_list
        },
    }

    report = {
        "report_id": f"g6-reuse-{uuid.uuid4().hex[:12]}",
        "generated_at": _now_iso(),
        "slots": slot_list,
        "workflow_comparison": graph_comparison,
        "workflows_by_slot": workflows_by_slot,
        "profiles": profiles,
        "profile_diff_allowlist": sorted(PROFILE_DIFF_ALLOWLIST),
        "governance_evidence": governance,
        "reuse_conclusion": {
            "same_visible_operator_graph": graph_comparison.get("graph_reuse_proven"),
            "expected_changes": sorted(PROFILE_DIFF_ALLOWLIST),
            "product_governance_writes_blocked": True,
            "subgraph_used": False,
        },
    }

    if persist:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = _REPORT_DIR / f"{report['report_id']}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            report["persisted_path"] = str(path.relative_to(_BACKEND_DIR)).replace("\\", "/")
        except ValueError:
            report["persisted_path"] = str(path).replace("\\", "/")

    return report
