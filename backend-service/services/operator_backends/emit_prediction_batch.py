# @AI_GENERATED
"""emit_prediction_batch — persist workflow predictions for review (G11)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "emit_prediction_batch"
logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_slot(params: dict) -> str:
    slot = str(params.get("slot") or params.get("_global_config", {}).get("slot") or "pv_point").strip()
    if slot not in ("pv_day", "pv_point", "pv_fault"):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"unsupported slot: {slot!r}")
    return slot


def _normalize_predictions(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, pd.DataFrame):
        return data.to_dict(orient="records")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and "predictions" in data:
        inner = data["predictions"]
        if isinstance(inner, list):
            return inner
    raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be DataFrame or prediction list")


def execute(params: dict, inputs: dict) -> dict:
    data = inputs.get("data")
    if data is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' is required")

    slot = _resolve_slot(params)
    granularity = str(params.get("prediction_granularity") or "day").strip().lower()
    if granularity not in ("day", "point"):
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", "prediction_granularity must be day or point")

    rows = _normalize_predictions(data)
    if not rows:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "prediction rows are empty")

    batch_id = str(params.get("batch_id") or f"pb-{uuid.uuid4().hex[:12]}")
    batch_dir = _BACKEND_DIR / "data" / "iterative_labeling" / "prediction_batches" / slot
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_path = batch_dir / f"{batch_id}.json"

    units: list[dict[str, Any]] = []
    annotation_candidate_ids: list[str] = []

    workflow_id = str(params.get("source_workflow_id") or "workflow-inline")
    execution_id = str(params.get("source_execution_id") or params.get("_global_config", {}).get("source_execution_id") or "exec-inline")
    profile_ref = str(params.get("dataset_profile_ref") or params.get("_global_config", {}).get("dataset_profile_ref") or "")

    for row in rows:
        site = row.get("site_id")
        device = row.get("device_id")
        branch = row.get("branch_id")
        tw = row.get("time_window") or row.get("date") or row.get("time")
        pred = row.get("predicted_label", row.get("predictions", row.get("label")))
        unit = {
            "site_id": site,
            "device_id": device,
            "branch_id": branch,
            "time_window": tw,
            "predicted_label": pred,
            "confidence": row.get("confidence", 0.0),
        }
        units.append(unit)

        if granularity == "point" and params.get("project_to_review_queue", True):
            try:
                from services.slot_datasets.annotation_candidates import register_annotation_candidate

                entity_key = "|".join(str(x) for x in (site, device, branch) if x is not None)
                boundary = str(row.get("time") or tw or "")
                candidate = register_annotation_candidate(
                    slot=slot if slot in ("pv_day", "pv_point") else "pv_point",
                    source_workflow_id=workflow_id,
                    source_execution_id=execution_id,
                    dataset_profile_ref=profile_ref or "inline",
                    entity_key=entity_key,
                    boundary_start=boundary,
                    boundary_end=boundary,
                    suggested_label=pred,
                    confidence=float(row.get("confidence") or 0.0),
                    candidate_projection_enabled=True,
                )
                annotation_candidate_ids.append(candidate["annotation_candidate_id"])
            except Exception as exc:
                logger.warning("[%s] annotation candidate skipped: %s", OPERATOR_ID, exc)

    payload = {
        "prediction_batch_id": batch_id,
        "slot": slot,
        "prediction_granularity": granularity,
        "source_workflow_id": workflow_id,
        "source_execution_id": execution_id,
        "created_at": _now_iso(),
        "units": units,
        "annotation_candidate_ids": annotation_candidate_ids,
    }
    batch_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("[%s] wrote batch %s (%d units)", OPERATOR_ID, batch_id, len(units))
    return {
        "prediction_batch_id": batch_id,
        "batch_path": batch_path.relative_to(_BACKEND_DIR).as_posix(),
        "unit_count": len(units),
        "annotation_candidate_ids": annotation_candidate_ids,
        "prediction_granularity": granularity,
    }
