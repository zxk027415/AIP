# @AI_GENERATED
"""emit_label_proposal — workflow exit for labeling template A (G11)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError
from services.slot_datasets.label_proposals import save_label_proposal

OPERATOR_ID = "emit_label_proposal"
logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _resolve_slot(params: dict) -> str:
    slot = str(params.get("slot") or params.get("_global_config", {}).get("slot") or "").strip()
    if slot not in ("pv_day", "pv_point"):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            "slot must be pv_day or pv_point (workflow metadata or param)",
        )
    return slot


def _entity_cols(frame: pd.DataFrame) -> list[str]:
    cols = [c for c in ("site_id", "device_id", "branch_id", "date") if c in frame.columns]
    if not cols and "time" in frame.columns:
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["time"], errors="coerce").dt.date.astype(str)
        cols = [c for c in ("site_id", "device_id", "branch_id", "date") if c in frame.columns]
    return cols


def execute(params: dict, inputs: dict) -> dict:
    data = inputs.get("data")
    labels = inputs.get("labels")
    profile_payload = inputs.get("cluster_profile") or {}
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a DataFrame")
    if labels is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'labels' is required")

    slot = _resolve_slot(params)
    label_arr = np.asarray(labels).reshape(-1)
    if len(label_arr) != len(data):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "labels length must match data rows")

    working = data.copy()
    working["cluster_id"] = label_arr.astype(int)
    entity_cols = _entity_cols(working)
    if entity_cols:
        working["member_key"] = working.apply(
            lambda row: "|".join(str(row.get(c, "")) for c in entity_cols),
            axis=1,
        )
    else:
        working["member_key"] = working.index.astype(str)

    profile_clusters = (profile_payload.get("clusters") if isinstance(profile_payload, dict) else {}) or {}
    clusters: dict[str, Any] = {}
    for cid in sorted(working["cluster_id"].unique()):
        cid_str = str(int(cid))
        members = working[working["cluster_id"] == cid]
        prof = profile_clusters.get(cid_str, {})
        default_name = str(params.get("default_label_prefix") or "cluster") + f"_{cid_str}"
        clusters[cid_str] = {
            "cluster_id": int(cid),
            "member_count": int(len(members)),
            "member_keys": members["member_key"].astype(str).tolist(),
            "selected_member_keys": members["member_key"].astype(str).tolist(),
            "proposed_label_name": prof.get("proposed_label_name") or default_name,
            "representative_stats": prof.get("representative_stats") or {},
        }

    proposal_dir = _BACKEND_DIR / "data" / "slot_datasets" / slot / "proposal_rows"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    run_tag = str(params.get("source_execution_id") or params.get("_global_config", {}).get("source_execution_id") or "inline")
    safe_tag = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in run_tag)[:40]
    rows_name = f"members-{safe_tag}.csv"
    rows_abs = proposal_dir / rows_name
    working.to_csv(rows_abs, index=False, encoding="utf-8")
    rel_rows = os.path.relpath(str(rows_abs), start=str(_BACKEND_DIR)).replace("\\", "/")

    record = save_label_proposal(
        slot=slot,
        clusters=clusters,
        source_file_path=params.get("source_file_path") or params.get("file_path"),
        source_workflow_id=params.get("source_workflow_id"),
        source_execution_id=params.get("source_execution_id"),
        member_rows_path=rel_rows,
        cluster_profile=profile_payload if isinstance(profile_payload, dict) else {},
    )

    artifact_rel = f"data/slot_datasets/{slot}/proposals/{record['proposal_id']}.json"
    artifact_abs = _BACKEND_DIR / artifact_rel
    artifact_abs.parent.mkdir(parents=True, exist_ok=True)
    artifact_abs.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("[%s] saved proposal %s for slot=%s", OPERATOR_ID, record["proposal_id"], slot)
    return {
        "proposal_id": record["proposal_id"],
        "slot": slot,
        "status": "proposal",
        "artifact_path": artifact_rel.replace("\\", "/"),
        "cluster_count": len(clusters),
    }
