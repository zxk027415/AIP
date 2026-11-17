"""G0-S2: slot_config merge and legacy resolution tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.operator_execution.slot_config import (
    LEGACY_SLOT_ALLOWLIST,
    SlotConfigError,
    SlotConfigTypeConflictError,
    build_effective_global_config_sources,
    canonical_digest,
    deep_merge_layers,
    normalize_request_global_config,
    resolve_legacy_slot,
)


def test_deep_merge_recurses_objects():
    merged = deep_merge_layers(
        {"a": {"x": 1}, "b": 1},
        {"a": {"y": 2}},
        {"a": {"z": 3}, "c": "template"},
        {"d": "request"},
    )
    assert merged == {"a": {"x": 1, "y": 2, "z": 3}, "b": 1, "c": "template", "d": "request"}


def test_deep_merge_replaces_arrays():
    merged = deep_merge_layers(
        {"items": [1, 2]},
        None,
        {"items": [9]},
        {"items": [7, 8]},
    )
    assert merged["items"] == [7, 8]


def test_deep_merge_preserves_null():
    merged = deep_merge_layers({"value": 1}, None, None, {"value": None})
    assert merged == {"value": None}


def test_deep_merge_type_conflict_raises():
    with pytest.raises(SlotConfigTypeConflictError):
        deep_merge_layers(None, None, {"threshold": 1}, {"threshold": "1"})


def test_normalize_request_global_config_none_is_empty():
    assert normalize_request_global_config(None) == {}


def test_normalize_request_global_config_rejects_non_object():
    with pytest.raises(SlotConfigError):
        normalize_request_global_config(["bad"])


def test_build_effective_global_config_sources_tracks_layers():
    sources = build_effective_global_config_sources(
        {"base": 1},
        {"slot": True},
        {"template": "t"},
        {"request": "r"},
    )
    assert sources["/base"] == "platform_default"
    assert sources["/slot"] == "slot_default"
    assert sources["/template"] == "template"
    assert sources["/request"] == "request"


def test_canonical_digest_is_stable():
    payload = {"b": 2, "a": {"y": 1, "x": 2}}
    assert canonical_digest(payload) == canonical_digest({"a": {"x": 2, "y": 1}, "b": 2})


def test_resolve_legacy_slot_requires_slot():
    with pytest.raises(SlotConfigError) as exc:
        resolve_legacy_slot(None)
    assert exc.value.code == "missing_slot"


def test_resolve_legacy_slot_explicit_pv_day_ok():
    result = resolve_legacy_slot("pv_day")
    assert result == {"ok": True, "slot": "pv_day", "legacy_mapped": False}


def test_resolve_legacy_slot_empty_allowlist_pv_fault_pv_day_fails():
    assert LEGACY_SLOT_ALLOWLIST == {}
    with pytest.raises(SlotConfigError) as exc:
        resolve_legacy_slot("pv_fault", scenario_key="pv_day", workflow_id="workflow-pv-day")
    assert exc.value.code == "legacy_slot_not_allowed"


def test_resolve_legacy_slot_rejects_scenario_key_with_explicit_slot():
    with pytest.raises(SlotConfigError) as exc:
        resolve_legacy_slot("pv_day", scenario_key="pv_day")
    assert exc.value.code == "scenario_key_not_allowed"
