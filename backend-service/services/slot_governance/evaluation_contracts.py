"""Per-slot evaluation contract store (immutable refs, G4 skeleton)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.slot_governance.provenance import ProvenanceError, assert_product_slot

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data" / "slot_governance"

_DEFAULT_CONTRACTS: dict[str, dict[str, Any]] = {
    "pv_day": {
        "evaluation_contract_ref": "pv-day-eval-v1",
        "slot": "pv_day",
        "metrics": ["macro_f1_mean", "accuracy_mean"],
        "window_policy": "device_day",
        "aggregate_method": "mean",
        "score_margin": 0.0,
        "min_windows_challenger_better": 1,
        "quality_gates": [],
    },
    "pv_point": {
        "evaluation_contract_ref": "pv-point-eval-v1",
        "slot": "pv_point",
        "metrics": ["point_accuracy", "coverage", "no_decision_rate"],
        "window_policy": "real_point",
        "aggregate_method": "mean",
        "score_margin": 0.0,
        "min_windows_challenger_better": 1,
        "quality_gates": [],
    },
}


def _contract_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _DATA_DIR / safe / "evaluation_contract.json"


def get_evaluation_contract(slot: str) -> dict[str, Any]:
    assert_product_slot(slot)
    path = _contract_path(slot)
    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload.setdefault("slot", slot)
            return payload
    default = _DEFAULT_CONTRACTS.get(slot)
    if default is None:
        raise ProvenanceError("contract_not_found", f"no evaluation contract for slot={slot!r}")
    return dict(default)
