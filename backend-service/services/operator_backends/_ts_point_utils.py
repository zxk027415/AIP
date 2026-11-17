"""Shared helpers for ts_point operator backends."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from services.operator_execution.router import OperatorExecutionError


def require_dataframe(inputs: dict, operator_id: str, key: str = "data") -> pd.DataFrame:
    value = inputs.get(key)
    if value is None or not isinstance(value, pd.DataFrame):
        raise OperatorExecutionError(operator_id, "InputError", f"Input '{key}' must be a pandas DataFrame")
    return value


def parse_contract(params: dict) -> dict[str, Any]:
    contract = params.get("contract")
    if isinstance(contract, str):
        contract = json.loads(contract or "{}")
    if not isinstance(contract, dict):
        contract = params
    return contract


def window_result_to_dict(result) -> dict[str, Any]:
    payload = {
        "status": result.status,
        "reason": result.reason,
        "entity_key": result.entity_key,
        "point_time": result.point_time,
        "context_length": result.context_length,
    }
    if result.window_tensor is not None:
        payload["window_tensor"] = result.window_tensor
    return payload


def outcome_to_dict(outcome) -> dict[str, Any]:
    return {
        "kind": outcome.kind,
        "label": outcome.label,
        "confidence": outcome.confidence,
        "reason": outcome.reason,
        "evidence": outcome.evidence,
    }
