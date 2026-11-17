"""Slot-level global_config merge, digest, and legacy slot resolution (G0)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

LEGACY_SLOT_ALLOWLIST: dict[tuple[str, str], str] = {}


class SlotConfigError(Exception):
    """Base error for slot configuration resolution."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class SlotConfigTypeConflictError(SlotConfigError):
    """Raised when merge layers disagree on scalar/container types."""

    def __init__(self, path: str, existing_type: str, incoming_type: str):
        self.path = path
        self.existing_type = existing_type
        self.incoming_type = incoming_type
        super().__init__(
            "type_conflict",
            f"Type conflict at {path}: {existing_type} vs {incoming_type}",
        )


def normalize_request_global_config(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SlotConfigError(
            "invalid_global_config",
            "global_config must be an object",
        )
    return dict(value)


def _json_pointer_join(prefix: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    return f"{prefix}/{escaped}" if prefix else f"/{escaped}"


def _assert_mergeable(existing: Any, incoming: Any, path: str) -> None:
    if existing is None or incoming is None:
        return
    if type(existing) is not type(incoming):
        raise SlotConfigTypeConflictError(
            path,
            type(existing).__name__,
            type(incoming).__name__,
        )


def deep_merge_layers(
    platform_default: Mapping[str, Any] | None,
    slot_default: Mapping[str, Any] | None,
    template: Mapping[str, Any] | None,
    request: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge config layers with priority platform < slot_default < template < request."""

    merged: dict[str, Any] = {}
    for layer in (
        platform_default or {},
        slot_default or {},
        template or {},
        request or {},
    ):
        if not isinstance(layer, Mapping):
            raise SlotConfigError("invalid_layer", "Each merge layer must be a mapping")
        _deep_merge_into(merged, layer, "")
    return merged


def _deep_merge_into(target: dict[str, Any], layer: Mapping[str, Any], path: str) -> None:
    for key, value in layer.items():
        child_path = _json_pointer_join(path, str(key))
        if key not in target:
            target[key] = _copy_merge_value(value, child_path)
            continue

        existing = target[key]
        if isinstance(existing, dict) and isinstance(value, Mapping):
            _assert_mergeable(existing, value, child_path)
            _deep_merge_into(existing, value, child_path)
            continue

        _assert_mergeable(existing, value, child_path)
        target[key] = _copy_merge_value(value, child_path)


def _copy_merge_value(value: Any, path: str) -> Any:
    if isinstance(value, Mapping):
        nested: dict[str, Any] = {}
        _deep_merge_into(nested, value, path)
        return nested
    return value


def build_effective_global_config_sources(
    platform_default: Mapping[str, Any] | None,
    slot_default: Mapping[str, Any] | None,
    template: Mapping[str, Any] | None,
    request: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Return leaf JSON Pointer -> winning layer name."""

    layers = (
        ("platform_default", platform_default or {}),
        ("slot_default", slot_default or {}),
        ("template", template or {}),
        ("request", request or {}),
    )
    sources: dict[str, str] = {}
    for layer_name, layer in layers:
        _collect_sources(layer, "", layer_name, sources)
    return sources


def _collect_sources(
    value: Any,
    path: str,
    layer_name: str,
    sources: dict[str, str],
) -> None:
    if isinstance(value, Mapping):
        if not value:
            sources[path or "/"] = layer_name
            return
        for key, child in value.items():
            _collect_sources(child, _json_pointer_join(path, str(key)), layer_name, sources)
        return
    sources[path or "/"] = layer_name


def canonical_digest(obj: Any) -> str:
    encoded = json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_legacy_slot(
    slot: str | None,
    scenario_key: str | None = None,
    workflow_id: str | None = None,
    workflow_version: str | None = None,
) -> dict[str, Any]:
    """
    Resolve the effective slot for an execution request.

    Returns:
        {"ok": True, "slot": str, "legacy_mapped": bool}
    Raises:
        SlotConfigError when resolution fails.
    """

    _ = workflow_version  # reserved for future allowlist entries

    normalized_slot = str(slot or "").strip()
    if not normalized_slot:
        raise SlotConfigError("missing_slot", "slot is required")

    if normalized_slot != "pv_fault":
        if scenario_key not in (None, ""):
            raise SlotConfigError(
                "scenario_key_not_allowed",
                "scenario_key is not allowed when slot is already explicit",
            )
        return {"ok": True, "slot": normalized_slot, "legacy_mapped": False}

    if scenario_key in {"pv_day", "pv_point"}:
        wf_key = str(workflow_id or "").strip()
        mapped = LEGACY_SLOT_ALLOWLIST.get((wf_key, scenario_key))
        if mapped:
            return {"ok": True, "slot": mapped, "legacy_mapped": True}
        raise SlotConfigError(
            "legacy_slot_not_allowed",
            f"legacy mapping for workflow_id={wf_key!r} scenario_key={scenario_key!r} is not allowlisted",
        )

    raise SlotConfigError(
        "invalid_slot",
        "slot 'pv_fault' is legacy-only; use pv_day or pv_point",
    )
