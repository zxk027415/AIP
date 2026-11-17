"""Safe relative path resolution for file-backed profiles."""

from __future__ import annotations

import os
from pathlib import Path

ALLOWED_ROOT_ALIASES = {
    "backend_service": Path(__file__).resolve().parents[2],
    "project_root": Path(__file__).resolve().parents[3],
}


class PathGuardError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def resolve_profile_source_path(source_ref: str, path_root_alias: str = "backend_service") -> Path:
    ref = str(source_ref or "").strip()
    if not ref:
        raise PathGuardError("missing_source_ref", "source_ref is required")

    if "://" in ref or ref.startswith("\\\\"):
        raise PathGuardError("unknown_scheme", f"Unsupported source scheme in source_ref: {ref!r}")

    if os.path.isabs(ref):
        raise PathGuardError("absolute_path_forbidden", "Absolute paths are not allowed in profile source_ref")

    normalized = Path(ref.replace("\\", "/"))
    if ".." in normalized.parts:
        raise PathGuardError("path_traversal_forbidden", "source_ref must not contain '..'")

    root = ALLOWED_ROOT_ALIASES.get(path_root_alias)
    if root is None:
        raise PathGuardError("unknown_root_alias", f"Unknown path_root_alias: {path_root_alias!r}")

    candidate = (root / normalized).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise PathGuardError(
            "path_outside_root",
            f"Resolved path escapes allowed root {path_root_alias}: {ref}",
        ) from exc

    if candidate.is_symlink():
        raise PathGuardError("symlink_forbidden", "Symlink source_ref is not allowed")

    return candidate
