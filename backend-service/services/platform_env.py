"""Platform environment helpers for G13.2 production guards."""

from __future__ import annotations

import os


def aip_env() -> str:
    raw = (os.getenv("AIP_ENV") or os.getenv("APP_ENV") or "development").strip().lower()
    if raw in {"prod", "production"}:
        return "production"
    if raw in {"stage", "staging"}:
        return "staging"
    return "development"


def is_production_env() -> bool:
    return aip_env() == "production"


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _falsy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"0", "false", "no", "off"}


def simple_path_switch_allowed() -> bool:
    """Lab/simple cross-path switch — blocked in production unless explicitly overridden."""
    if _truthy("AIP_ALLOW_SIMPLE_PATH_SWITCH"):
        return True
    if _falsy("AIP_ALLOW_SIMPLE_PATH_SWITCH"):
        return False
    return not is_production_env()


def modeling_path_write_auth_required() -> bool:
    """Write APIs for modeling-paths / register-model / switch-fallback."""
    if _falsy("AIP_REQUIRE_MODELING_PATH_AUTH"):
        return False
    if _truthy("AIP_REQUIRE_MODELING_PATH_AUTH"):
        return True
    return is_production_env()


def governance_flags() -> dict[str, bool]:
    return {
        "simple_switch_allowed": simple_path_switch_allowed(),
        "write_auth_required": modeling_path_write_auth_required(),
        "environment": aip_env(),
    }
