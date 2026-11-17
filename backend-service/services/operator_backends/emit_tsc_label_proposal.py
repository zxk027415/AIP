# @AI_GENERATED
"""Emit device-day TSC review proposals with overlapping windows as evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from services.operator_execution.router import OperatorExecutionError
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.label_proposals import (
    allocate_proposal_id,
    save_label_proposal,
)

OPERATOR_ID = "emit_tsc_label_proposal"
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _text(value: Any) -> str:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ""
    return str(value)


def _member_key(site_id: Any, device_id: Any, branch_id: Any, day: Any) -> str:
    return "|".join((_text(site_id), _text(device_id), _text(branch_id), _text(day)))


def _label_name(label: int, params: dict) -> str:
    mapping = params.get("label_names") or {}
    if isinstance(mapping, dict):
        value = mapping.get(str(label), mapping.get(label))
        if value not in (None, ""):
            return str(value)
    return f"label_{label}"


def execute(params: dict, inputs: dict) -> dict:
    data = inputs.get("data")
    predictions = inputs.get("predictions")
    if not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )
    if not isinstance(predictions, list):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'predictions' must be a record list"
        )
    if "time" not in data.columns:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "data is missing time")

    slot = str(
        params.get("slot") or (params.get("_global_config") or {}).get("slot") or "pv_tsc"
    ).strip()
    if slot != "pv_tsc":
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "emit_tsc_label_proposal only supports pv_tsc"
        )

    decisions: dict[str, dict[str, Any]] = {}
    invalid_count = 0
    for prediction in predictions:
        if not isinstance(prediction, dict):
            invalid_count += 1
            continue
        label = prediction.get("predicted_label")
        day_value = prediction.get("target_day") or prediction.get("time_window")
        parsed_day = pd.to_datetime(day_value, errors="coerce")
        if label is None or pd.isna(parsed_day) or prediction.get("error"):
            invalid_count += 1
            continue
        try:
            label_id = int(label)
        except (TypeError, ValueError):
            invalid_count += 1
            continue
        key = _member_key(
            prediction.get("site_id"),
            prediction.get("device_id"),
            prediction.get("branch_id"),
            parsed_day.date().isoformat(),
        )
        candidate = {
            **prediction,
            "predicted_label": label_id,
            "target_day": parsed_day.date().isoformat(),
            "member_key": key,
        }
        previous = decisions.get(key)
        if previous is None or float(candidate.get("confidence") or 0.0) > float(
            previous.get("confidence") or 0.0
        ):
            decisions[key] = candidate

    if not decisions:
        raise OperatorExecutionError(
            OPERATOR_ID, "EmptyProposalError", "no successful device-day decisions to review"
        )

    working = data.copy()
    working["time"] = pd.to_datetime(working["time"], errors="coerce")
    if working["time"].isna().any():
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "data contains invalid time values"
        )
    working["date"] = working["time"].dt.date.astype(str)
    for name in ("site_id", "device_id", "branch_id"):
        if name not in working.columns:
            working[name] = ""
    working["member_key"] = working.apply(
        lambda row: _member_key(
            row.get("site_id"), row.get("device_id"), row.get("branch_id"), row.get("date")
        ),
        axis=1,
    )

    source_keys = set(working["member_key"].astype(str))
    matched_keys = set(decisions) & source_keys
    unmatched_count = len(decisions) - len(matched_keys)
    if not matched_keys:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputMismatchError",
            "predicted device-days do not match any source data rows",
        )
    decisions = {key: value for key, value in decisions.items() if key in matched_keys}
    working = working[working["member_key"].isin(matched_keys)].copy()
    working["cluster_id"] = working["member_key"].map(
        lambda key: int(decisions[str(key)]["predicted_label"])
    )

    clusters: dict[str, Any] = {}
    member_evidence: dict[str, Any] = {}
    for key, decision in decisions.items():
        label_id = int(decision["predicted_label"])
        cluster_key = str(label_id)
        cluster = clusters.setdefault(
            cluster_key,
            {
                "cluster_id": label_id,
                "member_count": 0,
                "member_keys": [],
                "selected_member_keys": [],
                "proposed_label_name": _label_name(label_id, params),
                "representative_member_key": None,
                "representative_stats": {},
                "evidence_by_member": {},
            },
        )
        evidence = {
            "predicted_label": label_id,
            "day_confidence": float(decision.get("confidence") or 0.0),
            "aggregation": decision.get("aggregation"),
            "n_windows": int(decision.get("n_windows") or 0),
            "target_day": decision.get("target_day"),
            "windows": list(decision.get("per_window_details") or []),
            "model_name": decision.get("model_name"),
        }
        cluster["member_keys"].append(key)
        cluster["selected_member_keys"].append(key)
        cluster["evidence_by_member"][key] = evidence
        member_evidence[key] = evidence

    for cluster in clusters.values():
        keys = list(cluster["member_keys"])
        cluster["member_count"] = len(keys)
        representative = max(
            keys,
            key=lambda key: float(member_evidence[key].get("day_confidence") or 0.0),
        )
        cluster["representative_member_key"] = representative
        cluster["representative_stats"] = {
            "mean_confidence": round(
                sum(float(member_evidence[key].get("day_confidence") or 0.0) for key in keys)
                / len(keys),
                6,
            ),
            "evidence_window_count": sum(
                int(member_evidence[key].get("n_windows") or 0) for key in keys
            ),
        }

    proposal_id = allocate_proposal_id(slot)
    proposal_dir = _BACKEND_DIR / "data" / "slot_datasets" / slot / "proposal_rows"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    rows_abs = proposal_dir / f"members-{proposal_id}.csv"
    working.to_csv(rows_abs, index=False, encoding="utf-8")
    rows_ref = rows_abs.relative_to(_BACKEND_DIR).as_posix()
    profile = {
        "granularity": "device_day",
        "evidence_granularity": "overlapping_model_window",
        "member_evidence": member_evidence,
        "member_count": len(decisions),
        "evidence_window_count": sum(
            int(item.get("n_windows") or 0) for item in decisions.values()
        ),
        "skipped_member_count": invalid_count + unmatched_count,
    }
    try:
        record = save_label_proposal(
            slot=slot,
            clusters=clusters,
            source_file_path=params.get("source_file_path") or params.get("file_path"),
            source_workflow_id=params.get("source_workflow_id"),
            source_execution_id=params.get("source_execution_id"),
            member_rows_path=rows_ref,
            cluster_profile=profile,
            proposal_id=proposal_id,
        )
    except SlotDatasetError as exc:
        raise OperatorExecutionError(OPERATOR_ID, exc.code, exc.message) from exc

    artifact_ref = f"data/slot_datasets/{slot}/proposals/{proposal_id}.json"
    artifact_abs = _BACKEND_DIR / artifact_ref
    artifact_abs.parent.mkdir(parents=True, exist_ok=True)
    artifact_abs.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "proposal_id": proposal_id,
        "slot": slot,
        "status": "proposal",
        "artifact_path": artifact_ref,
        "member_count": len(decisions),
        "evidence_window_count": profile["evidence_window_count"],
        "skipped_member_count": profile["skipped_member_count"],
        "cluster_count": len(clusters),
    }
# @AI_GENERATED: end
