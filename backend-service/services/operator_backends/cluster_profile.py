# @AI_GENERATED
"""cluster_profile — per-cluster stats and representative members (G11)."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "cluster_profile"

logger = logging.getLogger(__name__)


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
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'data' must be a DataFrame")
    if labels is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Input 'labels' is required")

    label_arr = np.asarray(labels).reshape(-1)
    if len(label_arr) != len(data):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"labels length {len(label_arr)} != data rows {len(data)}",
        )

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

    numeric_cols = working.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols = [c for c in numeric_cols if c not in ("cluster_id",)]

    profiles: dict[str, Any] = {}
    for cid in sorted(working["cluster_id"].unique()):
        members = working[working["cluster_id"] == cid]
        rep_key = str(members.iloc[0]["member_key"])
        stats = {}
        for col in numeric_cols:
            if col in members.columns:
                stats[col] = {
                    "mean": float(members[col].mean()),
                    "std": float(members[col].std(ddof=0) if len(members) > 1 else 0.0),
                    "min": float(members[col].min()),
                    "max": float(members[col].max()),
                }
        profiles[str(int(cid))] = {
            "cluster_id": int(cid),
            "member_count": int(len(members)),
            "member_keys": members["member_key"].astype(str).tolist(),
            "representative_member_key": rep_key,
            "representative_stats": stats,
        }

    logger.info("[%s] built profiles for %d clusters", OPERATOR_ID, len(profiles))
    return {"cluster_profile": {"clusters": profiles}, "profiles": profiles}
